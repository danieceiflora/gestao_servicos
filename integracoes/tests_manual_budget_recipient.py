from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from integracoes.models import ManualMessageConfig
from services.models import Client, ClientPhone, Property, ServiceOrder, User


@override_settings(DEBUG=True)
class BudgetRecipientTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='budget-recipient-admin', password='test', phone='67999999999'
        )
        self.client.force_login(self.user)
        self.customer = Client.objects.create(name='Cliente Teste')
        property_obj = Property.objects.create(
            client=self.customer, address='Rua Teste', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        self.order = ServiceOrder.objects.create(client_property=property_obj)
        self.config = ManualMessageConfig.objects.create(
            trigger='ENVIO_ORCAMENTO', template_name='orcamento',
        )
        self.send_url = reverse('service_order_send_budget', args=[self.order.pk])
        self.config_url = reverse('integracoes:manual_message_config_edit', args=['ENVIO_ORCAMENTO'])

    @patch('integracoes.views.MetaCloudAPI')
    def test_config_saves_fixed_phone_and_rejects_invalid_phone(self, meta_api):
        meta_api.return_value.get_templates.return_value = {'data': []}
        response = self.client.post(self.config_url, {
            'template_name': 'orcamento', 'recipient_type': 'FIXED',
            'fixed_phone': '(67) 99999-9999', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.fixed_phone, '+5567999999999')
        self.assertEqual(self.config.recipient_type, 'FIXED')

        response = self.client.post(self.config_url, {
            'template_name': 'orcamento', 'recipient_type': 'FIXED',
            'fixed_phone': '123', 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.config.refresh_from_db()
        self.assertEqual(self.config.fixed_phone, '+5567999999999')

    @patch('services.views.BudgetPDFGenerator')
    @patch('integracoes.utils.dispatch_manual_message')
    def test_fixed_phone_sends_without_customer_phone(self, dispatch, pdf_generator):
        self.config.recipient_type = 'FIXED'
        self.config.fixed_phone = '+5567999999999'
        self.config.save()
        pdf_generator.return_value.generate.return_value = b'%PDF-test'
        dispatch.return_value = True

        response = self.client.get(self.send_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(dispatch.call_args.kwargs['phone'], '+5567999999999')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.AGUARDANDO_APROVACAO)

    @patch('services.views.BudgetPDFGenerator')
    @patch('integracoes.utils.dispatch_manual_message')
    def test_customer_phone_remains_default(self, dispatch, pdf_generator):
        ClientPhone.objects.create(client=self.customer, phone='67999999999')
        pdf_generator.return_value.generate.return_value = b'%PDF-test'
        dispatch.return_value = True

        self.client.get(self.send_url)

        self.assertEqual(dispatch.call_args.kwargs['phone'], '+5567999999999')

    @patch('services.views.BudgetPDFGenerator')
    @patch('integracoes.utils.dispatch_manual_message')
    def test_inactive_config_without_customer_phone_does_not_send(self, dispatch, pdf_generator):
        self.config.recipient_type = 'FIXED'
        self.config.fixed_phone = '+5567999999999'
        self.config.is_active = False
        self.config.save()

        response = self.client.get(self.send_url)

        self.assertEqual(response.status_code, 302)
        dispatch.assert_not_called()
        pdf_generator.assert_not_called()

    @patch('services.views.ChatwootClient')
    @patch('services.views.BudgetPDFGenerator')
    @patch('integracoes.utils.dispatch_manual_message')
    def test_legacy_fallback_uses_fixed_phone(self, dispatch, pdf_generator, chatwoot_cls):
        self.config.recipient_type = 'FIXED'
        self.config.fixed_phone = '+5567999999999'
        self.config.save()
        pdf_generator.return_value.generate.return_value = b'%PDF-test'
        dispatch.return_value = False
        chatwoot = chatwoot_cls.return_value
        chatwoot.search_contact.return_value = None
        chatwoot.create_contact.return_value = {'id': 1}
        chatwoot.get_or_create_conversation.return_value = {'id': 2}
        chatwoot.config.chatwoot_budget_template = ''
        chatwoot.send_message.return_value = {'id': 3}
        chatwoot.extract_message_tracking.return_value = ('3', '2')
        chatwoot.get_label_by_title.return_value = {'title': 'Orçamento-Enviado'}

        self.client.get(self.send_url)

        self.assertEqual(chatwoot.create_contact.call_args.args[1], '+5567999999999')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, ServiceOrder.Status.AGUARDANDO_APROVACAO)

    @patch('services.views.ChatwootClient')
    @patch('services.views.BudgetPDFGenerator')
    @patch('integracoes.utils.dispatch_manual_message')
    def test_failed_fallback_does_not_advance_order(self, dispatch, pdf_generator, chatwoot_cls):
        self.config.recipient_type = 'FIXED'
        self.config.fixed_phone = '+5567999999999'
        self.config.save()
        pdf_generator.return_value.generate.return_value = b'%PDF-test'
        dispatch.return_value = False
        chatwoot = chatwoot_cls.return_value
        chatwoot.search_contact.return_value = {'id': 1}
        chatwoot.get_or_create_conversation.return_value = {'id': 2}
        chatwoot.config.chatwoot_budget_template = ''
        chatwoot.send_message.return_value = None
        initial_status = self.order.status

        self.client.get(self.send_url)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, initial_status)
