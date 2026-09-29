"""Run explicitly: manage.py test services.browser_payment_checks (Playwright Chromium)."""
from datetime import date
from decimal import Decimal

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright, expect

from pagamentos.models import GatewayCharge
from services.models import Billing, Installment
from services.tests_pos_payments import PaymentFixtures


class PaymentBrowserChecks(PaymentFixtures, StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self.billing = Billing.objects.create(client=self.customer, total_amount=150)
        self.installment = Installment.objects.create(billing=self.billing, amount=150, installment_number=1, due_date=date.today())
        self.public_url = reverse('public_billing_page', args=[self.billing.public_token])
        self.legacy_billing = Billing.objects.create(client=self.customer, total_amount=150)
        legacy_inst = Installment.objects.create(billing=self.legacy_billing, amount=150, installment_number=1, due_date=date.today())
        GatewayCharge.objects.create(installment=legacy_inst, config=self.config, method='PIX', amount=150,
                                     external_id='legacy_pix', due_date=date.today(), pix_copy_paste='legacy-visible-code')
        self.legacy_url = reverse('public_billing_page', args=[self.legacy_billing.public_token])
        cookie = self.client.cookies['sessionid'].value
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.context = self.browser.new_context(viewport={'width': 1280, 'height': 900})
        self.context.add_cookies([{'name': 'sessionid', 'value': cookie, 'url': self.live_server_url}])
        self.page = self.context.new_page()
        # No external services are needed for checkout; icons are decorative.
        self.page.route('https://**', lambda route: route.fulfill(
            content_type='application/javascript', body='window.lucide={createIcons(){}};' if 'lucide' in route.request.url else '',
        ))
        self.page_errors = []
        self.page.on('pageerror', lambda error: self.page_errors.append(str(error)))
        self.alerts = []
        self.page.on('dialog', lambda dialog: (self.alerts.append(dialog.message), dialog.dismiss()))

    def tearDown(self):
        if hasattr(self, 'browser'):
            self.browser.close()
            self.playwright.stop()
        super().tearDown()

    def prepare_cart(self):
        self.page.goto(self.live_server_url + reverse('pos_home'))
        self.page.locator('#product-search').fill('Produto')
        self.page.locator('#product-results button').first.click()
        self.page.locator('#client-search').fill('Cliente PIX')
        self.page.locator('#client-results button').filter(has_text='Cliente PIX').click()
        self.page.get_by_role('button', name='Receber F9').click()

    def set_row(self, number, method, amount):
        row = self.page.locator('.payment-row').nth(number)
        row.locator('select').select_option(str(method.pk))
        row.locator('.amount').fill(amount)
        row.locator('.tendered').fill(amount)

    def begin_mixed(self):
        self.prepare_cart()
        self.set_row(0, self.cash, '50')
        self.page.get_by_role('button', name='Adicionar forma', exact=True).click()
        self.set_row(1, self.pix, '100')
        self.page.get_by_role('button', name='Finalizar venda', exact=True).click()
        self.page.wait_for_timeout(500)
        self.assertEqual(self.page_errors, [])
        self.assertEqual(self.alerts, [])
        expect(self.page.get_by_label('PIX copia e cola')).to_have_value('pix-test-code')

    def test_mixed_checkout_recovers_after_reload_and_confirms(self):
        self.begin_mixed()
        self.page.reload()
        expect(self.page.get_by_label('PIX copia e cola')).to_have_value('pix-test-code')
        data = self.gateway.create_charge.call_args.args[0]
        response = self.page.request.post(self.live_server_url + reverse('pagamentos:asaas_webhook'), data={
            'event': 'PAYMENT_RECEIVED', 'payment': {
                'id': f'pay_{data.external_reference}', 'value': 100, 'netValue': 97.5,
            },
        })
        self.assertTrue(response.ok)
        expect(self.page.get_by_role('link', name='Abrir comprovante')).to_be_visible(timeout=10000)
        self.assertEqual(self.gateway.create_charge.call_count, 1)
        self.assertEqual(self.page_errors, [])

    def test_replace_only_unpaid_part(self):
        self.begin_mixed()
        self.gateway.get_charge.return_value = self.result()
        self.gateway.cancel_charge.return_value = True
        self.page.get_by_role('button', name='Trocar forma deste saldo').click()
        self.page.get_by_label('Nova forma de pagamento').select_option(str(self.cash.pk))
        self.page.get_by_role('button', name='Confirmar troca e recebimentos').click()
        expect(self.page.get_by_role('link', name='Abrir comprovante')).to_be_visible()
        self.gateway.cancel_charge.assert_called_once()
        self.assertEqual(self.page_errors, [])

    def test_multiple_pix_parts_confirm_separately(self):
        self.prepare_cart()
        self.set_row(0, self.pix, '50')
        self.page.get_by_role('button', name='Adicionar forma', exact=True).click()
        self.set_row(1, self.pix, '100')
        self.page.get_by_role('button', name='Finalizar venda', exact=True).click()
        expect(self.page.get_by_label('PIX copia e cola')).to_have_count(2)
        calls = list(self.gateway.create_charge.call_args_list)
        for index, call in enumerate(calls):
            data = call.args[0]
            self.page.request.post(self.live_server_url + reverse('pagamentos:asaas_webhook'), data={
                'event': 'PAYMENT_RECEIVED', 'payment': {'id': f'pay_{data.external_reference}', 'value': float(data.amount)},
            })
            if index == 0:
                expect(self.page.get_by_label('PIX copia e cola')).to_have_count(1, timeout=10000)
                expect(self.page.get_by_role('link', name='Abrir comprovante')).to_have_count(0)
        expect(self.page.get_by_role('link', name='Abrir comprovante')).to_be_visible(timeout=10000)

    def test_public_only_offers_boleto_and_keeps_existing_pix(self):
        self.page.goto(self.live_server_url + self.public_url)
        self.page.get_by_role('button', name='Entendi, prosseguir com o pagamento').click()
        expect(self.page.get_by_role('button', name='Boleto híbrido', exact=True)).to_be_visible()
        expect(self.page.get_by_role('button', name='PIX no caixa', exact=True)).to_have_count(0)
        self.page.get_by_role('button', name='Boleto híbrido', exact=True).click()
        expect(self.page.get_by_role('button', name='Gerar boleto', exact=True)).to_be_visible()
        self.page.goto(self.live_server_url + self.legacy_url)
        expect(self.page.get_by_text('legacy-visible-code', exact=True)).to_be_visible()
