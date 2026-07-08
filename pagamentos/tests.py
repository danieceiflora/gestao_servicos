import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse

from pagamentos.gateways.asaas import AsaasGateway
from integracoes.models import PlatformInvoice, PlatformSubscription, PlatformSubscriptionEvent


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
