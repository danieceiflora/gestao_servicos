import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from pagamentos.models import GatewayCharge, GatewayConfig
from pagamentos.settlement import apply_charge_status
from services.forms import PaymentMethodForm
from services.models import Billing, Client, Installment, PaymentMethod, SalePayment, User
from services.payment_fees import calculate_fee, terms_for_method


class FeeRuleTests(TestCase):
    def test_method_form_shows_catalog(self):
        user = User.objects.create_user(username='fee-form-manager', role=User.Roles.MANAGER, phone='')
        self.client.force_login(user)
        response = self.client.get(reverse('payment_method_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ASAAS_PIX')
        self.assertContains(response, 'Tarifa Máxima')

    def test_minimum_maximum_and_fixed(self):
        terms = {'percent': '2', 'minimum': '2.50', 'maximum': '10', 'fixed': '1'}
        self.assertEqual(calculate_fee('100', terms), Decimal('3.50'))
        self.assertEqual(calculate_fee('300', terms), Decimal('7.00'))
        self.assertEqual(calculate_fee('1000', terms), Decimal('11.00'))

    def test_integrated_form_rejects_tampered_fee(self):
        form = PaymentMethodForm(data={
            'descricao': 'Pix Asaas', 'tipo_provedor': 'PIX', 'pix_type': 'DYNAMIC',
            'integra_gateway': 'on', 'integrated_product': 'ASAAS_PIX',
            'tarifa_porcentagem': '0', 'tarifa_minima': '2.50',
            'tarifa_maxima': '10', 'tarifa_fixa': '0',
            'prazo_recebimento': '0', 'codigo_sefaz': '17', 'pos_behavior': 'WAIT_GATEWAY',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('tarifa_porcentagem', form.errors)

    def test_boleto_form_rejects_legacy_fixed_fee(self):
        form = PaymentMethodForm(data={
            'descricao': 'Boleto híbrido', 'tipo_provedor': 'BOLETO',
            'integra_gateway': 'on', 'integrated_product': 'ASAAS_BOLETO',
            'tarifa_porcentagem': '0.80', 'tarifa_minima': '2.50',
            'tarifa_maxima': '10.00', 'tarifa_fixa': '2.50',
            'prazo_recebimento': '0', 'codigo_sefaz': '15', 'pos_behavior': 'RECEIVED_NOW',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('tarifa_fixa', form.errors)


class RecordedFeeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='fees-manager', role=User.Roles.MANAGER, phone='')
        self.client.force_login(self.user)
        self.customer = Client.objects.create(name='Cliente tarifas', cpf='52998224725')
        self.method = PaymentMethod.objects.create(
            descricao='Cartão', tipo_provedor='CARTAO_CREDITO', codigo_sefaz='03',
            tarifa_porcentagem=Decimal('2'), tarifa_minima=Decimal('2.50'),
            tarifa_maxima=Decimal('10'), tarifa_fixa=Decimal('1'),
        )

    def test_receivable_manual_payment_uses_rule_snapshot(self):
        billing = Billing.objects.create(client=self.customer, total_amount=100)
        inst = Installment.objects.create(billing=billing, amount=100, installment_number=1, due_date=date.today())
        response = self.client.post(reverse('installment_pay', args=[inst.pk]), {
            'payment_method[]': [str(self.method.pk)], 'payment_amount[]': ['100'],
            'payment_date[]': ['2026-09-29'],
        })
        self.assertEqual(response.status_code, 302)
        payment = SalePayment.objects.get(installment=inst)
        self.assertEqual(payment.valor_tarifa, Decimal('3.50'))
        self.assertEqual(payment.valor_liquido, Decimal('96.50'))
        self.method.refresh_from_db()
        self.assertEqual(payment.fee_terms, terms_for_method(self.method))
        self.assertEqual(payment.fee_status, 'CONFIRMED')

    def test_gateway_stays_estimated_until_split_done_and_is_idempotent(self):
        method = PaymentMethod.objects.create(
            descricao='Pix Asaas', tipo_provedor='PIX', codigo_sefaz='17',
            integra_gateway=True, integrated_product='ASAAS_PIX', pix_type='DYNAMIC',
        )
        billing = Billing.objects.create(client=self.customer, total_amount=100)
        inst = Installment.objects.create(billing=billing, amount=100, installment_number=1, due_date=date.today())
        config = GatewayConfig.load()
        config.wallet_id = 'company-wallet'
        config.save(update_fields=['wallet_id'])
        charge = GatewayCharge.objects.create(
            installment=inst, payment_method=method, config=config,
            external_id='pay_fee_test', method='PIX', amount=100, due_date=date.today(),
        )
        apply_charge_status(charge.pk, 'RECEIVED', '97.50')
        payment = SalePayment.objects.get(gateway_charge=charge)
        self.assertEqual(payment.fee_status, 'ESTIMATED')
        self.assertEqual(payment.valor_tarifa, Decimal('2.50'))
        self.assertEqual(payment.fee_terms['product'], 'ASAAS_PIX')
        payload = {'event': 'PAYMENT_SPLIT_DONE', 'payment': {'id': charge.external_id},
                   'additionalInfo': {'splitId': 'split-1'}}
        split = {'id': 'split-1', 'status': 'DONE', 'payment': {'id': charge.external_id},
                 'walletId': 'company-wallet', 'totalValue': 94.75}
        with patch('pagamentos.views.AsaasGateway.get_paid_split', return_value={**split, 'walletId': 'other-wallet'}):
            response = self.client.post(reverse('pagamentos:asaas_webhook'),
                                        json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 422)
        payment.refresh_from_db()
        self.assertEqual(payment.fee_status, 'ESTIMATED')
        with patch('pagamentos.views.AsaasGateway.get_paid_split', return_value=split):
            for _ in range(2):
                response = self.client.post(reverse('pagamentos:asaas_webhook'),
                                            json.dumps(payload), content_type='application/json')
                self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.valor_liquido, Decimal('94.75'))
        self.assertEqual(payment.valor_tarifa, Decimal('5.25'))
        self.assertEqual(payment.fee_status, 'CONFIRMED')
        self.assertEqual(SalePayment.objects.filter(gateway_charge=charge).count(), 1)
        apply_charge_status(charge.pk, 'RECEIVED', '99.00')
        payment.refresh_from_db()
        self.assertEqual(payment.valor_liquido, Decimal('94.75'))


class ManualReceiptGatewayCancellationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='receipt-manager', role=User.Roles.MANAGER, phone='')
        self.client.force_login(user)
        client = Client.objects.create(name='Cliente baixa', cpf='52998224725')
        self.method = PaymentMethod.objects.create(
            descricao='Dinheiro', tipo_provedor='DINHEIRO', codigo_sefaz='01',
        )
        self.billing = Billing.objects.create(client=client, total_amount=100)
        self.installment = Installment.objects.create(
            billing=self.billing, amount=100, installment_number=1, due_date=date.today(),
        )

    def charge(self, external_id, status):
        return GatewayCharge.objects.create(
            installment=self.installment, config=GatewayConfig.load(),
            external_id=external_id, method='PIX', status=status,
            amount=100, due_date=date.today(),
        )

    def pay(self, amount):
        return self.client.post(reverse('installment_pay', args=[self.installment.pk]), {
            'payment_method[]': [str(self.method.pk)],
            'payment_amount[]': [str(amount)],
            'payment_date[]': ['2026-09-29'],
        })

    @patch('pagamentos.gateways.asaas.AsaasGateway')
    def test_partial_receipt_cancels_pending_and_overdue_charges(self, gateway_class):
        pending = self.charge('pay_pending', GatewayCharge.Status.PENDING)
        overdue = self.charge('pay_overdue', GatewayCharge.Status.OVERDUE)
        received = self.charge('pay_received', GatewayCharge.Status.RECEIVED)
        gateway_class.return_value.cancel_charge.return_value = True

        response = self.pay(40)

        self.assertEqual(response.status_code, 302)
        self.installment.refresh_from_db()
        self.assertEqual(self.installment.status, Installment.Status.PARCIAL)
        self.assertEqual(SalePayment.objects.get(installment=self.installment).valor_bruto, 40)
        pending.refresh_from_db()
        overdue.refresh_from_db()
        received.refresh_from_db()
        self.assertEqual(pending.status, GatewayCharge.Status.CANCELLED)
        self.assertEqual(overdue.status, GatewayCharge.Status.CANCELLED)
        self.assertEqual(received.status, GatewayCharge.Status.RECEIVED)
        self.assertCountEqual(
            [call.args[0] for call in gateway_class.return_value.cancel_charge.call_args_list],
            ['pay_pending', 'pay_overdue'],
        )

    @patch('pagamentos.gateways.asaas.AsaasGateway')
    def test_full_receipt_cancels_overdue_charge(self, gateway_class):
        charge = self.charge('pay_full', GatewayCharge.Status.OVERDUE)
        gateway_class.return_value.cancel_charge.return_value = True

        self.pay(100)

        self.installment.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(self.installment.status, Installment.Status.PAGO)
        self.assertEqual(charge.status, GatewayCharge.Status.CANCELLED)
        gateway_class.return_value.cancel_charge.assert_called_once_with('pay_full')

    @patch('pagamentos.gateways.asaas.AsaasGateway')
    def test_failed_cancellation_keeps_receipt_and_warns(self, gateway_class):
        unconfirmed = self.charge('pay_unconfirmed', GatewayCharge.Status.PENDING)
        errored = self.charge('pay_errored', GatewayCharge.Status.OVERDUE)
        gateway_class.return_value.cancel_charge.side_effect = [False, TimeoutError('timeout')]

        response = self.pay(40)

        self.assertEqual(SalePayment.objects.get(installment=self.installment).valor_bruto, 40)
        unconfirmed.refresh_from_db()
        errored.refresh_from_db()
        self.assertEqual(unconfirmed.status, GatewayCharge.Status.PENDING)
        self.assertEqual(errored.status, GatewayCharge.Status.OVERDUE)
        notices = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Pagamento de' in str(notice) for notice in notices))
        self.assertTrue(any(
            'pay_unconfirmed' in str(notice) and 'pay_errored' in str(notice) and notice.level_tag == 'warning'
            for notice in notices
        ))

    @patch('pagamentos.gateways.asaas.AsaasGateway')
    def test_receipt_without_active_charge_skips_gateway(self, gateway_class):
        self.charge('pay_cancelled', GatewayCharge.Status.CANCELLED)

        self.pay(100)

        gateway_class.assert_not_called()
