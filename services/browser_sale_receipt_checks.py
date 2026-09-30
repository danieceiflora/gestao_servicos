"""Run explicitly: manage.py test services.browser_sale_receipt_checks."""
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright, expect

from services.models import Sale
from services.tests_pos_payments import PaymentFixtures


class SaleReceiptBrowserChecks(PaymentFixtures, StaticLiveServerTestCase):
    def test_list_action_on_desktop_and_mobile_and_print(self):
        sale = Sale.objects.create(user=self.user, client=self.customer, status='RASCUNHO', total_amount=150)
        Sale.objects.filter(pk=sale.pk).update(status='FINALIZADA')
        receipt_url = reverse('sale_receipt', args=[sale.number])
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value, 'url': self.live_server_url}])
                context.route('https://**', lambda route: route.fulfill(content_type='application/javascript', body='window.lucide={createIcons(){}};' if 'lucide' in route.request.url else ''))
                page = context.new_page()
                for width in [1280, 390]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.goto(self.live_server_url + reverse('sale_list'))
                    page.locator('.sale-actions:visible').first.locator('summary').click()
                    with page.expect_popup() as popup:
                        page.locator(f'a[href="{receipt_url}"]:visible').click()
                    receipt = popup.value
                    expect(receipt.locator('#receipt-customer')).to_contain_text(self.customer.name)
                    expect(receipt.locator('#receipt-customer')).to_contain_text(self.customer.cpf)
                    expect(receipt.get_by_role('button', name='Imprimir', exact=True)).to_be_visible()
                    receipt.emulate_media(media='print')
                    expect(receipt.get_by_role('button', name='Imprimir', exact=True)).to_be_hidden()
                    expect(receipt.get_by_role('link', name='Voltar', exact=True)).to_be_hidden()
                    expect(receipt.locator('#receipt-customer')).to_be_visible()
                    receipt.close()
            finally:
                browser.close()
