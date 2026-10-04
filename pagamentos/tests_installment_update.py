from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.tz_utils import local_today
from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.gateways.base import ChargeData, ChargeResult
from pagamentos.gateways.base import ChargeRejected
from pagamentos.models import GatewayCharge, GatewayConfig
from services.models import Billing, Client, Installment, User


class InstallmentUpdateTests(TestCase):
    def setUp(self):
        user = User.objects.create_superuser(username='installment-editor', password='secret')
        self.client.force_login(user)
        customer = Client.objects.create(name='Cliente Edição')
        billing = Billing.objects.create(client=customer, total_amount=Decimal('100.00'))
        self.billing = billing
        self.due_date = local_today() + timedelta(days=10)
        self.installment = Installment.objects.create(
            billing=billing, installment_number=1, due_date=self.due_date,
            amount=Decimal('100.00'),
            discount_type=Installment.DiscountType.FIXED,
            discount_value=Decimal('10.00'), discount_due_days=2,
            discount_deadline=self.due_date - timedelta(days=2),
        )
        self.url = reverse('pagamentos:installment_update', args=[self.installment.pk])

    def post_data(self, **changes):
        data = {
            'due_date': self.due_date.isoformat(), 'amount': '100.00',
            'discount_type': 'FIXED', 'discount_value': '10.00',
            'discount_deadline': (self.due_date - timedelta(days=2)).isoformat(),
            'interest_monthly': '1.00', 'fine_type': 'PERCENTAGE', 'fine_value': '2.00',
        }
        data.update(changes)
        return data

    def add_charge(self, method='BOLETO', status=GatewayCharge.Status.PENDING):
        config = GatewayConfig.load()
        config.wallet_id = 'wallet_client'
        config.save(update_fields=['wallet_id'])
        return GatewayCharge.objects.create(
            installment=self.installment, config=config, external_id='pay_test',
            method=method, status=status,
            amount=Decimal('100.00'), due_date=self.due_date,
            discount_type='FIXED', discount_value=Decimal('10.00'), discount_due_days=2,
        )

    def test_calendar_deadline_stays_fixed_when_due_date_changes(self):
        new_due = self.due_date + timedelta(days=3)
        response = self.client.post(self.url, self.post_data(due_date=new_due.isoformat()))
        self.assertEqual(response.status_code, 302)
        self.installment.refresh_from_db()
        self.assertEqual(self.installment.discount_deadline, self.due_date - timedelta(days=2))
        self.assertEqual(self.installment.discount_due_days, 5)

    def test_edit_modal_shows_calendar_deadline_and_named_terms(self):
        response = self.client.get(reverse('billing_detail', args=[self.billing.pk]))
        self.assertContains(response, 'id="edit-discount-deadline"')
        self.assertContains(response, 'Data limite do desconto')
        self.assertContains(response, 'Valor do desconto')
        self.assertContains(response, 'Juros (% ao mês)')
        self.assertContains(response, 'Valor da multa')
        self.assertContains(response, f'data-discount-deadline="{(self.due_date - timedelta(days=2)).isoformat()}"')

    def test_gateway_receives_new_terms_and_refreshes_artifacts(self):
        charge = self.add_charge()
        deadline = self.due_date - timedelta(days=4)
        result = ChargeResult(
            external_id='pay_test', status='PENDING', method='BOLETO',
            amount=Decimal('120.00'), due_date=self.due_date,
            boleto_barcode='nova-linha', pix_copy_paste='novo-pix',
        )
        with patch('pagamentos.views._get_gateway') as gateway_factory:
            gateway_factory.return_value.update_charge.return_value = result
            self.client.post(self.url, self.post_data(
                amount='120.00', discount_value='12.00',
                discount_deadline=deadline.isoformat(),
            ))
            args, kwargs = gateway_factory.return_value.update_charge.call_args
        self.assertEqual(args[0], 'pay_test')
        self.assertEqual(args[1].discount_due_days, 4)
        self.assertEqual(kwargs['wallet_id'], 'wallet_client')
        self.installment.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(self.installment.amount, Decimal('120.00'))
        self.assertEqual(charge.boleto_barcode, 'nova-linha')
        self.assertEqual(charge.pix_copy_paste, 'novo-pix')

    def test_gateway_error_keeps_original_installment(self):
        charge = self.add_charge()
        with patch('pagamentos.views._get_gateway') as gateway_factory, \
             patch('pagamentos.views.logger.exception'):
            gateway_factory.return_value.update_charge.side_effect = ValueError('Asaas recusou')
            self.client.post(self.url, self.post_data(amount='120.00'))
        self.installment.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(self.installment.amount, Decimal('100.00'))
        self.assertEqual(charge.amount, Decimal('100.00'))

    def test_removing_terms_clears_installment_and_gateway_snapshot(self):
        charge = self.add_charge(method='PIX')
        result = ChargeResult(
            external_id='pay_test', status='PENDING', method='PIX',
            amount=Decimal('100.00'), due_date=self.due_date,
            pix_copy_paste='pix-atualizado',
        )
        with patch('pagamentos.views._get_gateway') as gateway_factory:
            gateway_factory.return_value.update_charge.return_value = result
            self.client.post(self.url, self.post_data(
                discount_type='NONE', discount_value='0', discount_deadline='',
                interest_monthly='0', fine_type='NONE', fine_value='0',
            ))
            data = gateway_factory.return_value.update_charge.call_args.args[1]
        self.installment.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(data.discount_type, '')
        self.assertEqual(data.discount_value, Decimal('0'))
        self.assertIsNone(self.installment.discount_deadline)
        self.assertEqual(self.installment.interest_monthly, Decimal('0'))
        self.assertEqual(charge.discount_value, Decimal('0'))
        self.assertEqual(charge.pix_copy_paste, 'pix-atualizado')

    def test_overdue_charge_is_updated(self):
        self.add_charge(status=GatewayCharge.Status.OVERDUE)
        result = ChargeResult(
            external_id='pay_test', status='OVERDUE', method='BOLETO',
            amount=Decimal('100.00'), due_date=self.due_date,
        )
        with patch('pagamentos.views._get_gateway') as gateway_factory:
            gateway_factory.return_value.update_charge.return_value = result
            self.client.post(self.url, self.post_data())
            gateway_factory.return_value.update_charge.assert_called_once()

    def test_invalid_discount_deadline_does_not_call_gateway(self):
        self.add_charge()
        with patch('pagamentos.views._get_gateway') as gateway_factory:
            self.client.post(self.url, self.post_data(
                discount_deadline=(self.due_date + timedelta(days=1)).isoformat(),
            ))
        gateway_factory.assert_not_called()


class AsaasInstallmentUpdatePayloadTests(TestCase):
    def charge_data(self, **changes):
        params = {
            'customer_name': 'Cliente', 'customer_document': '12345678901',
            'customer_email': '', 'description': 'Parcela',
            'amount': Decimal('100.00'), 'due_date': local_today() + timedelta(days=10),
            'method': 'BOLETO', 'external_reference': '1',
            'discount_type': 'FIXED', 'discount_value': Decimal('10.00'),
            'discount_due_days': 3,
        }
        params.update(changes)
        return ChargeData(**params)

    def payload(self, data):
        gateway = AsaasGateway()
        with patch.object(gateway, '_put', return_value={'status': 'PENDING', 'value': float(data.amount)}) as put, \
             patch.object(gateway, '_get', return_value={}):
            gateway.update_charge('pay_test', data, wallet_id='wallet_client')
        return put.call_args.args[1]

    def test_split_tracks_amount_and_discount(self):
        for method in ('PIX', 'BOLETO'):
            with self.subTest(method=method):
                payload = self.payload(self.charge_data(
                    method=method, amount=Decimal('1000.00'), discount_value=Decimal('100.00'),
                ))
                self.assertEqual(payload['discount']['dueDateLimitDays'], 3)
                self.assertEqual(payload['split'][0]['fixedValue'], 892.80)

    def test_removing_terms_sends_explicit_zeroes(self):
        payload = self.payload(self.charge_data(
            discount_type='NONE', discount_value=Decimal('0'),
            interest_monthly=Decimal('0'), fine_type='NONE', fine_value=Decimal('0'),
        ))
        self.assertEqual(payload['discount']['value'], 0)
        self.assertEqual(payload['interest']['value'], 0)
        self.assertEqual(payload['fine']['value'], 0)
        self.assertEqual(payload['split'][0]['fixedValue'], 97.50)

    def test_unconfirmed_discount_is_rejected(self):
        gateway = AsaasGateway()
        data = self.charge_data(discount_type='NONE', discount_value=Decimal('0'))
        with patch.object(gateway, '_put', return_value={
            'status': 'PENDING', 'value': 100.0, 'discount': {'value': 10.0},
        }), self.assertRaises(ChargeRejected):
            gateway.update_charge('pay_test', data)
