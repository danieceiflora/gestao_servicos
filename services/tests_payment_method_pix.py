from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from pagamentos.models import BillingChargeConfig, GatewayConfig
from services.forms import PaymentMethodForm
from services.models import Billing, Client, Installment, PaymentMethod, Sale, User
from services.utils.finance import create_billing_for_sale


class PaymentMethodPixFormTests(TestCase):
    def base_data(self, **overrides):
        data = {
            'descricao': 'PIX de teste',
            'tipo_provedor': 'PIX',
            'tarifa_porcentagem': '0',
            'tarifa_minima': '0',
            'tarifa_fixa': '0',
            'prazo_recebimento': '0',
            'codigo_sefaz': '17',
            'ativo': 'on',
            'integra_gateway': 'on',
            'pix_type': PaymentMethod.PixType.STATIC,
            'pix_key': ' financeiro@example.com ',
        }
        data.update(overrides)
        return data

    def test_static_pix_requires_key_and_disables_gateway(self):
        invalid_form = PaymentMethodForm(data=self.base_data(pix_key=''))
        self.assertFalse(invalid_form.is_valid())
        self.assertIn('pix_key', invalid_form.errors)

        form = PaymentMethodForm(data=self.base_data())
        self.assertTrue(form.is_valid(), form.errors)
        method = form.save()
        self.assertEqual(method.pix_key, 'financeiro@example.com')
        self.assertFalse(method.integra_gateway)

    def test_dynamic_pix_enables_gateway_and_clears_key(self):
        form = PaymentMethodForm(data=self.base_data(
            pix_type=PaymentMethod.PixType.DYNAMIC,
            pix_key='chave-nao-utilizada',
            integra_gateway='',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        method = form.save()
        self.assertTrue(method.integra_gateway)
        self.assertEqual(method.pix_key, '')

    def test_non_pix_clears_pix_fields(self):
        form = PaymentMethodForm(data=self.base_data(
            tipo_provedor='DINHEIRO',
            codigo_sefaz='01',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        method = form.save()
        self.assertEqual(method.pix_type, '')
        self.assertEqual(method.pix_key, '')


@override_settings(PAYMENT_PROCESSOR_NAME='GynBots')
class PublicBillingStaticPixTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(name='Cliente PIX')
        self.method = PaymentMethod.objects.create(
            descricao='PIX estático',
            tipo_provedor='PIX',
            codigo_sefaz='17',
            integra_gateway=False,
            pix_type=PaymentMethod.PixType.STATIC,
            pix_key='financeiro@example.com',
        )
        self.billing = Billing.objects.create(
            client=self.client_record,
            total_amount=Decimal('125.50'),
        )
        self.installment = Installment.objects.create(
            billing=self.billing,
            installment_number=1,
            due_date=date.today(),
            amount=Decimal('125.50'),
            payment_method=self.method,
        )
        self.gateway = GatewayConfig.load()
        self.url = reverse('public_billing_page', args=[self.billing.public_token])

    def test_shows_static_key_without_processor_when_all_methods_disabled(self):
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = False
        self.gateway.save(update_fields=['pix_enabled', 'boleto_enabled'])

        response = self.client.get(self.url)

        self.assertContains(response, 'financeiro@example.com')
        self.assertContains(response, 'Copiar chave PIX')
        self.assertNotContains(response, 'Pagamento processado com segurança por')
        self.assertNotContains(response, 'será processado por')

    def test_does_not_show_static_key_when_a_gateway_method_is_enabled(self):
        self.gateway.status = GatewayConfig.Status.APPROVED
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = True
        self.gateway.save(update_fields=['status', 'pix_enabled', 'boleto_enabled'])

        response = self.client.get(self.url)

        self.assertNotContains(response, 'financeiro@example.com')
        self.assertContains(response, 'Boleto Bancário')
        self.assertContains(response, 'Pagamento processado com segurança por')

    def test_missing_static_key_falls_back_to_contact_message(self):
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = False
        self.gateway.save(update_fields=['pix_enabled', 'boleto_enabled'])
        self.method.pix_key = ''
        self.method.save(update_fields=['pix_key'])

        response = self.client.get(self.url)

        self.assertContains(response, 'Entre em contato para combinar a forma de pagamento.')

    def test_installment_without_method_uses_unique_active_static_pix(self):
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = False
        self.gateway.save(update_fields=['pix_enabled', 'boleto_enabled'])
        self.installment.payment_method = None
        self.installment.save(update_fields=['payment_method'])

        response = self.client.get(self.url)

        self.assertContains(response, 'financeiro@example.com')
        self.assertNotContains(response, 'Entre em contato para combinar a forma de pagamento.')

    def test_installment_without_method_does_not_choose_between_multiple_static_pix(self):
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = False
        self.gateway.save(update_fields=['pix_enabled', 'boleto_enabled'])
        self.installment.payment_method = None
        self.installment.save(update_fields=['payment_method'])
        PaymentMethod.objects.create(
            descricao='Outro PIX estático',
            tipo_provedor='PIX',
            codigo_sefaz='17',
            ativo=True,
            integra_gateway=False,
            pix_type=PaymentMethod.PixType.STATIC,
            pix_key='outra-chave',
        )

        response = self.client.get(self.url)

        self.assertNotContains(response, 'financeiro@example.com')
        self.assertNotContains(response, 'outra-chave')
        self.assertContains(response, 'Entre em contato para combinar a forma de pagamento.')

    def test_explicit_non_pix_method_is_not_replaced_by_static_fallback(self):
        self.gateway.pix_enabled = False
        self.gateway.boleto_enabled = False
        self.gateway.save(update_fields=['pix_enabled', 'boleto_enabled'])
        cash = PaymentMethod.objects.create(
            descricao='Dinheiro',
            tipo_provedor='DINHEIRO',
            codigo_sefaz='01',
            ativo=True,
        )
        self.installment.payment_method = cash
        self.installment.save(update_fields=['payment_method'])

        response = self.client.get(self.url)

        self.assertNotContains(response, 'financeiro@example.com')
        self.assertContains(response, 'Entre em contato para combinar a forma de pagamento.')


class BillingCreationPaymentMethodTests(TestCase):
    def test_charge_config_supplies_method_when_installment_has_none(self):
        user = User.objects.create_user(username='billing-test', password='test')
        client = Client.objects.create(name='Cliente da venda')
        method = PaymentMethod.objects.create(
            descricao='PIX estático da regra',
            tipo_provedor='PIX',
            codigo_sefaz='17',
            ativo=True,
            integra_gateway=False,
            pix_type=PaymentMethod.PixType.STATIC,
            pix_key='regra@example.com',
        )
        charge_config = BillingChargeConfig.objects.create(
            name='Regra PIX estático',
            default_payment_method=method,
        )
        sale = Sale.objects.create(
            user=user,
            client=client,
            total_amount=Decimal('50.00'),
        )

        billing = create_billing_for_sale(sale, charge_config=charge_config)

        self.assertEqual(billing.installments.get().payment_method, method)
