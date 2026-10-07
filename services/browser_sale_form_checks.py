"""Run explicitly: manage.py test services.browser_sale_form_checks."""
from decimal import Decimal
import re

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright, expect

from services.models import Product, Sale, User


class SaleFormBrowserChecks(StaticLiveServerTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sale-form-manager', role=User.Roles.MANAGER, phone='')
        self.client.force_login(self.user)
        Product.objects.create(name='Produto A', code='SALE-FORM-A', default_unit_price=Decimal('10'), current_stock=10)
        self.product_b = Product.objects.create(
            name='Produto B', code='SALE-FORM-B', default_unit_price=Decimal('20'), current_stock=10,
        )

    def test_remove_then_add_and_save(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context()
                context.add_cookies([{
                    'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                    'url': self.live_server_url,
                }])
                context.route('https://**', lambda route: route.fulfill(
                    content_type='application/javascript',
                    body='window.lucide={createIcons(){}};' if 'lucide' in route.request.url else '',
                ))
                page = context.new_page()
                page.goto(self.live_server_url + reverse('sale_create'))

                page.locator('#product-search').fill('Produto A')
                page.locator('.product-item[data-name="Produto A"]').click()
                page.locator('#formset-container .item-row').first.get_by_role('button').click()
                expect(page.locator('#formset-container .item-row').first).to_be_hidden()
                expect(page.locator('input[name="items-0-DELETE"]')).to_be_checked()

                page.locator('#product-search').fill('Produto B')
                page.locator('.product-item[data-name="Produto B"]').click()
                expect(page.locator('#formset-container .item-row:visible')).to_have_count(1)
                page.locator('#submit-btn').click()
                page.wait_for_url(re.compile(r'/vendas/\d+/$'))

            finally:
                browser.close()

        sale = Sale.objects.get()
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.items.get().product_id, self.product_b.pk)
