import uuid

from django.test import TestCase
from django.urls import reverse

from services.models import Client, Sale, User
from services.tests_pos_payments import PaymentFixtures


class SaleReceiptTests(PaymentFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.sale = Sale.objects.create(user=self.user, client=self.customer, status='RASCUNHO', total_amount=150)
        self.url = reverse('sale_receipt', args=[self.sale.number])

    def status(self, status, **fields):
        Sale.objects.filter(pk=self.sale.pk).update(status=status, **fields)

    def test_concluded_statuses_and_customer(self):
        for status in ['FINALIZADA', 'ATENDIDO', 'RECEBIDO']:
            self.status(status)
            response = self.client.get(self.url)
            self.assertContains(response, self.customer.name)
            self.assertContains(response, self.customer.cpf)
            self.assertContains(response, reverse('sale_list'))
            self.assertContains(response, 'COMPROVANTE NÃO FISCAL')

    def test_invalid_statuses_and_pending_integrated_checkout(self):
        for status in ['RASCUNHO', 'EM_ANDAMENTO', 'PRONTO', 'VENDA_AGENCIADA', 'CANCELADO', 'AGUARDANDO_PAGAMENTO']:
            self.status(status)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.status('ATENDIDO', pos_checkout_key=uuid.uuid4())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_default_customer_is_anonymous_on_receipt(self):
        self.status('FINALIZADA', uses_default_pos_client=True)
        response = self.client.get(self.url)
        self.assertContains(response, 'Consumidor final')
        self.assertNotContains(response, self.customer.cpf)
        self.assertNotContains(response, self.customer.name)
        self.status('FINALIZADA', client=None, uses_default_pos_client=False)
        self.assertContains(self.client.get(self.url), 'Consumidor final')

    def test_company_and_missing_document(self):
        company = Client.objects.create(name='Empresa Exemplo LTDA', trade_name='Empresa Exemplo', client_type='PJ', cnpj='11222333000181')
        self.status('FINALIZADA', client=company)
        response = self.client.get(self.url)
        self.assertContains(response, company.display_name)
        self.assertContains(response, company.cnpj)
        self.assertContains(response, 'CNPJ:')
        Client.objects.filter(pk=company.pk).update(cnpj=None)
        self.assertNotContains(self.client.get(self.url), 'CNPJ:')

    def test_permissions(self):
        self.status('FINALIZADA')
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        operator = User.objects.create_user(username='receipt-operator', phone='')
        self.client.force_login(operator)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_pos_route_keeps_permissions_and_back_destination(self):
        self.status('FINALIZADA', origin='POS')
        response = self.client.get(reverse('pos_receipt', args=[self.sale.number]))
        self.assertContains(response, self.customer.name)
        self.assertContains(response, reverse('pos_home'))
        other = User.objects.create_user(username='other-receipt-operator', phone='')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('pos_receipt', args=[self.sale.number])).status_code, 403)

    def test_list_links_for_desktop_and_mobile(self):
        self.status('FINALIZADA')
        self.assertContains(self.client.get(reverse('sale_list')), f'href="{self.url}"', count=2)
        self.status('CANCELADO')
        self.assertNotContains(self.client.get(reverse('sale_list')), f'href="{self.url}"')
