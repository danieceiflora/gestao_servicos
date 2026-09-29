"""Explicit browser check with a simulated gateway; no real charge is cancelled."""
from datetime import date
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright, expect

from pagamentos.models import GatewayCharge
from services.models import Sale, Billing, Installment
from services.tests_pos_payments import PaymentFixtures


class SaleCancellationBrowserChecks(PaymentFixtures, StaticLiveServerTestCase):
    def test_confirmation_busy_state_and_success(self):
        sale = Sale.objects.create(user=self.user, client=self.customer, status='RASCUNHO', total_amount=150)
        billing = Billing.objects.create(sale=sale, client=self.customer, total_amount=150)
        inst = Installment.objects.create(billing=billing, amount=150, installment_number=1, due_date=date.today(), payment_method=self.pix)
        GatewayCharge.objects.create(installment=inst, config=self.config, payment_method=self.pix,
                                    external_id='pay_browser_cancel', method='PIX', amount=150, due_date=date.today())
        cancel_url = reverse('sale_cancel', kwargs={'number': sale.number})
        detail_url = reverse('sale_detail', kwargs={'number': sale.number})
        with patch('services.sale_cancellation.AsaasGateway') as gateway_cls, sync_playwright() as playwright:
            gateway = gateway_cls.return_value
            gateway.get_charge.return_value = self.result(amount=150)
            gateway.cancel_charge.return_value = True
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value, 'url': self.live_server_url}])
                page = context.new_page()
                page.route('https://**', lambda route: route.fulfill(content_type='application/javascript', body='window.lucide={createIcons(){}};' if 'lucide' in route.request.url else ''))
                confirmations = []
                page.on('dialog', lambda dialog: (confirmations.append(dialog.message), dialog.accept()))
                page.goto(self.live_server_url + detail_url)
                form = page.locator(f'form[action="{cancel_url}"]')
                form.evaluate("form => form.addEventListener('submit', () => sessionStorage.setItem('cancel-state', form.querySelector('button').textContent + ':' + form.querySelector('button').disabled))")
                form.get_by_role('button').click()
                expect(page.get_by_text('Venda, conta a receber e cobranças canceladas.', exact=False)).to_be_visible()
                self.assertEqual(page.evaluate("sessionStorage.getItem('cancel-state')"), 'Cancelando…:true')
                self.assertIn('cobranças abertas no gateway', confirmations[0])
                gateway.cancel_charge.assert_called_once_with('pay_browser_cancel')
                expect(page.locator(f'form[action="{cancel_url}"]')).to_have_count(0)
            finally:
                browser.close()
