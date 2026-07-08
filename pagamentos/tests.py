from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase

from pagamentos.gateways.asaas import AsaasGateway


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
                return {'data': [{'id': 'pay_1'}]}
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
