import json
from decimal import Decimal
from datetime import date
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.gateways.base import ChargeData
from pagamentos.models import GatewayConfig
from integracoes.models import PlatformInvoice, PlatformSubscription, PlatformSubscriptionEvent
from services.models import User


class AsaasGatewayFeeTests(TestCase):
    def _charge_payload(self, method, amount):
        gateway = AsaasGateway()
        data = ChargeData(
            customer_name='Cliente', customer_document='12345678901', customer_email='',
            description='Teste', amount=Decimal(amount), due_date=date.today(),
            method=method, external_reference='test',
        )
        with patch.object(gateway, '_get_or_create_customer', return_value='cus_1'), \
             patch.object(gateway, '_get', return_value={}), \
             patch.object(gateway, '_post', return_value={
                 'id': 'pay_1', 'status': 'PENDING', 'value': float(data.amount),
             }) as mocked_post:
            gateway.create_charge(data, wallet_id='wallet_client')
        return mocked_post.call_args.args[1]

    def test_pix_fee_respects_minimum(self):
        payload = self._charge_payload('PIX', '100.00')
        self.assertEqual(payload['split'][0]['fixedValue'], 97.50)

    def test_pix_fee_uses_percentage_inside_range(self):
        payload = self._charge_payload('PIX', '1000.00')
        self.assertEqual(payload['split'][0]['fixedValue'], 992.00)

    def test_pix_fee_respects_maximum(self):
        payload = self._charge_payload('PIX', '2000.00')
        self.assertEqual(payload['split'][0]['fixedValue'], 1990.00)

    def test_boleto_uses_fixed_fee(self):
        payload = self._charge_payload('BOLETO', '100.00')
        self.assertEqual(payload['split'][0]['fixedValue'], 97.50)


class GatewayFeeAcceptanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin-fees', password='secret', phone='62999999999',
        )
        self.client.force_login(self.user)
        self.config = GatewayConfig.load()
        self.url = reverse('pagamentos:gateway_config')

    def test_enabled_method_requires_acceptance(self):
        self.config.status = GatewayConfig.Status.APPROVED
        self.config.save(update_fields=['status'])
        response = self.client.post(self.url, {'action': 'save', 'pix_enabled': 'on'}, follow=True)
        self.config.refresh_from_db()

        self.assertFalse(self.config.has_current_fee_acceptance)
        self.assertFalse(self.config.can_generate_charges)
        self.assertContains(response, 'marque a declaração de ciência')

    @patch('pagamentos.views._handle_create_subaccount')
    def test_subaccount_creation_requires_acceptance(self, mocked_create):
        response = self.client.post(self.url, {'action': 'create_subaccount'}, follow=True)

        mocked_create.assert_not_called()
        self.assertContains(response, 'marque a declaração de ciência')

    def test_acceptance_records_user_and_current_values(self):
        self.client.post(self.url, {
            'action': 'save', 'pix_enabled': 'on', 'fee_terms_accepted': 'on',
        })
        self.config.refresh_from_db()

        self.assertTrue(self.config.has_current_fee_acceptance)
        self.assertEqual(self.config.fee_terms_accepted_by, self.user)
        self.assertIsNotNone(self.config.fee_terms_accepted_at)
        self.assertEqual(self.config.fee_terms_snapshot, self.config.current_fee_terms())

    @override_settings(ASAAS_PIX_COMMODITY_PERCENT=Decimal('1.00'))
    def test_changed_fee_invalidates_previous_acceptance(self):
        old_terms = dict(self.config.current_fee_terms())
        old_terms['pix_percent'] = '0.80'
        self.config.fee_terms_snapshot = old_terms
        self.config.fee_terms_accepted_at = timezone.now()
        self.config.save()

        self.assertFalse(self.config.has_current_fee_acceptance)


class AsaasGatewaySubscriptionTests(TestCase):
    def setUp(self):
        self.gw = AsaasGateway()

    @patch.object(AsaasGateway, '_get')
    @patch.object(AsaasGateway, '_post')
    @patch.object(AsaasGateway, '_get_or_create_customer')
    def test_create_subscription_returns_subscription_and_qr_code(self, mock_customer, mock_post, mock_get):
        mock_customer.return_value = 'cus_123'
        mock_post.return_value = {'id': 'sub_abc', 'status': 'ACTIVE'}

        def fake_get(path, params=None, api_key=None):
            if path == 'subscriptions/sub_abc/payments':
                return {'data': [{'id': 'pay_1', 'dueDate': '2026-08-08'}]}
            if path == 'payments/pay_1/pixQrCode':
                return {'payload': 'copia-e-cola-xyz', 'encodedImage': 'base64img=='}
            raise AssertionError(f'unexpected path {path}')

        mock_get.side_effect = fake_get

        result = self.gw.create_subscription(
            customer_name='Empresa Teste',
            customer_document='12345678000199',
            value=Decimal('99.00'),
            cycle='MONTHLY',
            description='Assinatura da Plataforma',
        )

        self.assertEqual(result['subscription_id'], 'sub_abc')
        self.assertEqual(result['first_charge_id'], 'pay_1')
        self.assertEqual(result['qr_code'], 'copia-e-cola-xyz')
        self.assertEqual(result['qr_code_base64'], 'base64img==')
        self.assertEqual(result['next_due_date'], '2026-08-08')

        mock_post.assert_called_once()
        posted_payload = mock_post.call_args[0][1]
        self.assertEqual(posted_payload['billingType'], 'PIX')
        self.assertEqual(posted_payload['value'], 99.0)
        self.assertEqual(posted_payload['cycle'], 'MONTHLY')

    @patch.object(AsaasGateway, '_get')
    @patch.object(AsaasGateway, '_post')
    @patch.object(AsaasGateway, '_get_or_create_customer')
    def test_create_subscription_tolerates_missing_first_payment(self, mock_customer, mock_post, mock_get):
        mock_customer.return_value = 'cus_123'
        mock_post.return_value = {'id': 'sub_abc', 'status': 'ACTIVE'}
        mock_get.return_value = {'data': []}

        result = self.gw.create_subscription(
            customer_name='Empresa Teste',
            customer_document='12345678000199',
            value=Decimal('99.00'),
            cycle='MONTHLY',
            description='Assinatura da Plataforma',
        )

        self.assertEqual(result['subscription_id'], 'sub_abc')
        self.assertEqual(result['first_charge_id'], '')
        self.assertEqual(result['qr_code'], '')

    def test_parse_webhook_extracts_subscription_id(self):
        payload = {
            'event': 'PAYMENT_RECEIVED',
            'payment': {'id': 'pay_1', 'value': 99.0, 'subscription': 'sub_abc'},
        }
        normalized = self.gw.parse_webhook(payload)
        self.assertEqual(normalized['status'], 'RECEIVED')
        self.assertEqual(normalized['subscription_id'], 'sub_abc')

    def test_parse_webhook_extracts_due_date(self):
        payload = {
            'event': 'PAYMENT_OVERDUE',
            'payment': {'id': 'pay_2', 'subscription': 'sub_abc', 'dueDate': '2026-09-08'},
        }
        normalized = self.gw.parse_webhook(payload)
        self.assertEqual(normalized['due_date'], '2026-09-08')


class AsaasWebhookPlatformInvoiceRoutingTests(TestCase):
    """
    O webhook do Asaas é o mesmo já configurado no painel para cobranças de
    clientes (GatewayCharge) — faturas da própria plataforma (PlatformInvoice)
    são roteadas pela mesma rota em vez de precisar de uma nova configuração.
    """

    def setUp(self):
        import datetime as dt
        self.invoice = PlatformInvoice.objects.create(
            due_date=dt.date(2026, 8, 10), value_cents=9900, asaas_charge_id='pay_plat_1',
        )

    def _post_webhook(self, event, payment_extra=None):
        payload = {'event': event, 'payment': {'id': 'pay_plat_1', **(payment_extra or {})}}
        return self.client.post(
            reverse('pagamentos:asaas_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_payment_received_marks_invoice_paga(self):
        response = self._post_webhook('PAYMENT_RECEIVED')
        self.assertEqual(response.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PlatformInvoice.Status.PAGA)
        self.assertIsNotNone(self.invoice.paid_at)

    def test_payment_overdue_marks_invoice_atrasada(self):
        response = self._post_webhook('PAYMENT_OVERDUE')
        self.assertEqual(response.status_code, 200)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, PlatformInvoice.Status.ATRASADA)

    def test_unknown_charge_id_does_not_error(self):
        response = self.client.post(
            reverse('pagamentos:asaas_webhook'),
            data=json.dumps({'event': 'PAYMENT_RECEIVED', 'payment': {'id': 'pay_does_not_exist'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)


class AsaasWebhookPlatformSubscriptionRoutingTests(TestCase):
    """
    A assinatura recorrente (Pix Automático) não tem webhook próprio — os
    charge ids dos ciclos futuros não são conhecidos com antecedência, então
    o roteamento é feito por subscription_id, pela mesma pagamentos:asaas_webhook.
    """

    def setUp(self):
        self.subscription = PlatformSubscription.load()
        self.subscription.subscription_id = 'sub_abc'
        self.subscription.status = PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO
        self.subscription.save()

    def _post_webhook(self, event, charge_id='pay_cycle_1', extra=None):
        payload = {
            'event': event,
            'payment': {'id': charge_id, 'subscription': 'sub_abc', **(extra or {})},
        }
        return self.client.post(
            reverse('pagamentos:asaas_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_payment_received_activates_subscription(self):
        response = self._post_webhook('PAYMENT_RECEIVED')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.ATIVA)

        event = PlatformSubscriptionEvent.objects.get()
        self.assertEqual(event.mapped_status, PlatformSubscription.Status.ATIVA)
        self.assertEqual(event.charge_id, 'pay_cycle_1')

    def test_payment_overdue_marks_subscription_atrasada(self):
        response = self._post_webhook('PAYMENT_OVERDUE')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.ATRASADA)

    def test_updates_next_due_date_from_payload(self):
        self._post_webhook('PAYMENT_RECEIVED', extra={'dueDate': '2026-09-10'})

        self.subscription.refresh_from_db()
        import datetime as dt
        self.assertEqual(self.subscription.next_due_date, dt.date(2026, 9, 10))

    def test_unrecognized_event_persists_history_without_changing_status(self):
        response = self._post_webhook('PAYMENT_SOMETHING_NEW')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO)

        event = PlatformSubscriptionEvent.objects.get()
        self.assertEqual(event.mapped_status, '')
        self.assertIn('não reconhecido', event.notes)

    def test_unknown_subscription_id_falls_through_without_error(self):
        response = self.client.post(
            reverse('pagamentos:asaas_webhook'),
            data=json.dumps({'event': 'PAYMENT_RECEIVED', 'payment': {'id': 'pay_x', 'subscription': 'sub_does_not_exist'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PlatformSubscriptionEvent.objects.count(), 0)
