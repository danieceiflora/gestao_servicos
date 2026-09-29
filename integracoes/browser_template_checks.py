"""Explicit browser checks, with rendered templates and no requests to Meta.

Run: python manage.py test integracoes.browser_template_checks
"""
import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from playwright.sync_api import sync_playwright

from .template_editor import TemplateEditForm, initial_state
from .tests_template_editor import sample_template


class TemplateEditorBrowserChecks(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1280, 'height': 900})
        self.addCleanup(self.page.close)
        self.page.route('**/*', lambda route: route.abort())
        template = sample_template()
        form = TemplateEditForm(template=template)
        html = render_to_string('integracoes/whatsapp_template_edit.html', {
            'template': template, 'editor_state': initial_state(template), 'form': form,
            'category_locked': True, 'retry': False,
        })
        # Keep the real rendered markup and JSON; load only the editor's script.
        html = re.sub(r'<script\b(?![^>]*type="application/json")[^>]*>.*?</script>', '', html, flags=re.S)
        self.page.set_content(html)
        self.page.add_style_tag(path=str(Path(settings.BASE_DIR) / 'static/dist/output.css'))
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.add_script_tag(path=str(Path(settings.BASE_DIR) / 'static/js/whatsapp-template-edit.js'))

    def test_example_change_enables_submit_and_blocks_duplicates(self):
        page = self.page
        self.assertTrue(page.locator('#submit-btn').is_disabled())
        page.get_by_label('Exemplo para {{1}}', exact=True).fill('99')
        self.assertTrue(page.locator('#submit-btn').is_enabled())
        self.assertEqual(page.locator('#preview-body').inner_text(), 'Pedido 99 e 99')
        page.evaluate("""() => {
            window.submissions = [];
            document.getElementById('template-edit-form').addEventListener('submit', event => {
                if (!event.defaultPrevented) window.submissions.push(Object.fromEntries(new FormData(event.target)));
                event.preventDefault();
            });
        }""")
        page.locator('#submit-btn').click()
        self.assertEqual(page.locator('#submit-btn').inner_text(), 'Aguarde…')
        self.assertTrue(page.locator('#submit-btn').is_disabled())
        page.evaluate("document.getElementById('template-edit-form').dispatchEvent(new Event('submit', {cancelable: true}))")
        self.assertEqual(page.evaluate('window.submissions.length'), 1)
        self.assertEqual(page.evaluate('window.submissions[0].body_examples'), '["99"]')
        self.assertEqual(self.errors, [])

    def test_header_preview_media_and_safe_variable_insertion(self):
        page = self.page
        page.locator('#header_text').fill('Olá {{1}}!')
        page.locator('#header_example').fill('<Ana>')
        self.assertEqual(page.locator('#preview-header').inner_text(), 'Olá <Ana>!')
        page.locator('#header_type').select_option('IMAGE')
        self.assertTrue(page.locator('#header_file').is_visible())
        self.assertTrue(page.locator('#header_file').evaluate('(input) => input.required'))
        page.locator('#header_file').set_input_files({'name': 'example.png', 'mimeType': 'image/png', 'buffer': b'image'})
        self.assertEqual(page.locator('#preview-header-media').inner_text(), 'example.png')
        page.locator('#header_type').select_option('NONE')
        self.assertFalse(page.locator('#header_file').is_visible())
        page.locator('#body_text').fill('Olá ')
        page.locator('[data-insert-variable="1"]').click()
        self.assertEqual(page.locator('#body_text').input_value(), 'Olá {{1}}')
        self.assertEqual(page.locator('#examples-list input').count(), 1)
        page.locator('#examples-list input').fill('"><img src=x onerror=alert(1)>')
        self.assertEqual(page.locator('#examples-list img').count(), 0)
        self.assertEqual(self.errors, [])

    def test_add_reorder_remove_buttons_and_mobile_layout(self):
        page = self.page
        page.locator('#add-button').click()
        rows = page.locator('#button-editor > div')
        rows.nth(1).locator('select').select_option('QUICK_REPLY')
        rows.nth(1).get_by_label('Texto do botão', exact=True).fill('Confirmar')
        rows.nth(1).get_by_role('button', name='Subir', exact=True).click()
        self.assertEqual(page.locator('#preview-buttons > div').first.inner_text(), 'Confirmar')
        rows.nth(1).get_by_role('button', name='Remover', exact=True).click()
        self.assertEqual(rows.count(), 1)
        self.assertEqual(page.locator('#buttons-json').input_value(), '[{"type":"QUICK_REPLY","text":"Confirmar"}]')
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.locator('#add-button').is_visible())
        self.assertLessEqual(page.locator('#template-edit-form').bounding_box()['width'], 390)
        self.assertEqual(self.errors, [])
