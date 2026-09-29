from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from services.forms_pos import PosSettingsForm
from services.models import Client, SaleSettings, User
from services.pos_payments import start_checkout
from services.tests_pos_payments import PaymentFixtures
from services.views_pos import _save_cart


class PosDefaultConsumerTests(PaymentFixtures, TestCase):
    def configure(self, client=None):
        config = SaleSettings.get()
        config.pos_default_client = client or self.customer
        config.save()

    def draft(self, **changes):
        with transaction.atomic():
            return _save_cart(self.payload(client_id='', **changes), self.session, self.user, False)

    def test_anonymous_sale_uses_default_for_pix_and_keeps_split_wallet(self):
        self.configure()
        self.config.wallet_id = 'wallet_test'
        self.config.save()
        sale = self.start(self.payload(client_id=''))
        self.assertEqual(sale.client, self.customer)
        self.assertTrue(sale.uses_default_pos_client)
        self.assertEqual(sale.billing.client, self.customer)
        data = self.gateway.create_charge.call_args.args[0]
        self.assertEqual(data.customer_document, self.customer.document)
        self.assertEqual(self.gateway.create_charge.call_args.kwargs['wallet_id'], 'wallet_test')

    def test_explicit_customer_has_priority(self):
        self.configure(Client.objects.create(name='Padrão', cpf='12345678909'))
        sale = self.start()
        self.assertEqual(sale.client, self.customer)
        self.assertFalse(sale.uses_default_pos_client)

    def test_invalid_explicit_customer_never_falls_back(self):
        self.configure()
        for client_id in ['invalid', '00000000-0000-0000-0000-000000000001']:
            with self.assertRaisesMessage(ValueError, 'Cliente selecionado não encontrado'):
                start_checkout(self.payload(client_id=client_id), self.user)

    def test_unidentified_sale_without_config_can_receive_cash(self):
        sale = self.start(self.payload(client_id='', payments=[{'method_id': self.cash.pk, 'amount': '150'}]))
        self.assertIsNone(sale.client)
        self.assertEqual(sale.status, 'FINALIZADA')

    def test_unidentified_pix_without_config_has_actionable_error(self):
        with self.assertRaisesMessage(ValueError, 'Configurações do PDV'):
            start_checkout(self.payload(client_id=''), self.user)

    def test_explicit_customer_without_document_is_not_replaced(self):
        self.configure()
        other = Client.objects.create(name='Sem documento')
        with self.assertRaisesMessage(ValueError, 'Atualize o cadastro'):
            start_checkout(self.payload(client_id=str(other.pk)), self.user)

    def test_draft_keeps_original_default_after_settings_change(self):
        self.configure()
        sale = self.draft()
        other = Client.objects.create(name='Novo padrão', cpf='12345678909')
        self.configure(other)
        reopened = self.draft(sale_id=sale.pk)
        self.assertEqual(reopened.client, self.customer)
        self.assertTrue(reopened.uses_default_pos_client)
        self.assertEqual(self.draft().client, other)
        response = self.client.get(reverse('pos_home'))
        payload = next(d for d in response.context['draft_payloads'] if d['id'] == sale.pk)
        self.assertTrue(payload['uses_default_pos_client'])

    def test_existing_anonymous_draft_does_not_change(self):
        sale = self.draft()
        self.configure()
        self.assertIsNone(self.draft(sale_id=sale.pk).client)

    def test_removing_explicit_client_uses_current_default(self):
        self.configure()
        other = Client.objects.create(name='Identificado')
        with transaction.atomic():
            sale = _save_cart(self.payload(client_id=str(other.pk)), self.session, self.user, False)
        sale = self.draft(sale_id=sale.pk)
        self.assertEqual(sale.client, self.customer)
        self.assertTrue(sale.uses_default_pos_client)

    def test_settings_validation_save_clear_and_delete_protection(self):
        other = Client.objects.create(name='Sem documento')
        form = PosSettingsForm({'pos_default_client': str(other.pk)}, instance=SaleSettings.get())
        self.assertFalse(form.is_valid())
        response = self.client.post(reverse('pos_settings'), {'pos_default_client': str(self.customer.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SaleSettings.get().pos_default_client, self.customer)
        with self.assertRaises(ProtectedError):
            self.customer.delete()
        self.client.post(reverse('pos_settings'), {'pos_default_client': ''})
        self.assertIsNone(SaleSettings.get().pos_default_client)

    def test_settings_access_restricted(self):
        user = User.objects.create_user(username='no-settings', phone='')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('pos_settings')).status_code, 403)
        self.assertEqual(self.client.post(reverse('pos_settings'), {'pos_default_client': str(self.customer.pk)}).status_code, 403)
