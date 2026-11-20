"""Verifica capturas reais versionadas, associação editorial e leitura visual."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from io import StringIO
from PIL import Image

from ajuda.initial_content import ARTICLES
from services.models import User


class GuideCaptureManifestTests(SimpleTestCase):
    def test_every_capture_is_linked_to_the_exact_editorial_step(self):
        folder = Path(settings.BASE_DIR) / 'static/help/screenshots'
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        articles = {article['slug']: article for article in ARTICLES}
        keys = [(entry['article_slug'], entry['step_order']) for entry in manifest]
        self.assertEqual(len(keys), len(set(keys)))
        for entry in manifest:
            source = articles[entry['article_slug']]
            step = next(step for step in source['steps'] if step['sort_order'] == entry['step_order'])
            self.assertEqual(step.get('screenshot'), 'help/screenshots/' + entry['filename'])
            self.assertEqual(step['image_alt'], entry['alt'])
            self.assertTrue(source['featured'])

    def test_bundled_screenshots_are_real_valid_webp_files_with_full_guide_coverage(self):
        folder = Path(settings.BASE_DIR) / 'static/help/screenshots'
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(manifest), 18)
        filenames = [entry['filename'] for entry in manifest]
        self.assertEqual(len(filenames), len(set(filenames)))
        self.assertLess(sum((folder / filename).stat().st_size for filename in filenames), 5 * 1024 * 1024)
        for entry in manifest:
            self.assertRegex(entry['filename'], r'^[a-z0-9_-]+\.webp$')
            self.assertTrue(entry['alt'])
            with Image.open(folder / entry['filename']) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertGreaterEqual(image.width, 400)
                image.verify()
        for slug in {entry['article_slug'] for entry in manifest}:
            article = next(article for article in ARTICLES if article['slug'] == slug)
            self.assertEqual({entry['step_order'] for entry in manifest if entry['article_slug'] == slug}, {step['sort_order'] for step in article['steps']})


class VisualGuideRenderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('sync_help_content', stdout=StringIO())
        cls.user = User.objects.create_user(username='visual-guide-manager', role=User.Roles.MANAGER)

    def test_real_prints_and_accessible_enlargement_are_available(self):
        self.client.force_login(self.user)
        response = self.client.get('/ajuda/artigo/agendar-os-com-etapas/')
        self.assertContains(response, 'src="/static/help/screenshots/os-cliente-imovel.webp"')
        self.assertContains(response, 'aria-label="Ampliar print do passo 1"')
        self.assertContains(response, 'id="help-print-dialog"')
        self.assertContains(response, 'dados de demonstração')
        self.assertContains(response, 'href="#passo-4"')

    def test_screenshot_filter_and_thumbnail_use_existing_assets(self):
        self.client.force_login(self.user)
        response = self.client.get('/ajuda/', {'illustrated': '1'})
        self.assertEqual(len(response.context['articles']), 5)
        self.assertContains(response, 'Com prints')
        self.assertContains(response, '/static/help/screenshots/cliente-buscar.webp')
