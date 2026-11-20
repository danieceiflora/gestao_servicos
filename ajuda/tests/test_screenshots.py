from django.core.exceptions import ValidationError
import mimetypes
from django.test import TestCase, override_settings
from django.urls import reverse

from ajuda.models import Article, ArticleStep, Category
from services.models import User


@override_settings(MEDIA_URL='/media/')
class HelpScreenshotModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Geral', slug='geral')
        self.article = Article.objects.create(category=self.category, title='Guia visual', slug='guia-visual', status='PUBLISHED')

    def test_bundled_screenshot_has_static_url_without_upload(self):
        self.assertIn('screenshot', {field.name for field in ArticleStep._meta.fields})
        step = ArticleStep(article=self.article, title='Abra a tela', screenshot='help/screenshots/cliente-lista.webp', image_alt='Novo cliente destacado')
        self.assertEqual(step.illustration_url, '/static/help/screenshots/cliente-lista.webp')
        self.assertFalse(step.image)

    def test_webp_is_served_as_image_instead_of_download_on_windows(self):
        self.assertEqual(mimetypes.guess_type('help/screenshots/cliente-buscar.webp')[0], 'image/webp')

    def test_uploaded_image_takes_precedence_over_official_screenshot(self):
        step = ArticleStep(article=self.article, title='Abra a tela', screenshot='help/screenshots/cliente-lista.webp', image='ajuda/local.png', image_alt='Imagem própria')
        self.assertEqual(step.illustration_url, '/media/ajuda/local.png')

    def test_arbitrary_urls_and_path_traversal_are_rejected(self):
        for path in ('https://evil.test/image.webp', '../secrets.webp', 'help/screenshots/../image.webp', 'help/screenshots/image.svg', '/help/screenshots/image.webp'):
            with self.subTest(path=path):
                step = ArticleStep(article=self.article, title='Print', screenshot=path, image_alt='Descrição')
                with self.assertRaises(ValidationError):
                    step.full_clean()
                self.assertEqual(step.illustration_url, '')

    def test_screenshot_requires_accessible_description(self):
        step = ArticleStep(article=self.article, title='Print', screenshot='help/screenshots/cliente-lista.webp')
        with self.assertRaises(ValidationError) as error:
            step.full_clean()
        self.assertIn('image_alt', error.exception.message_dict)

    def test_cover_and_illustration_count_follow_ordered_steps(self):
        ArticleStep.objects.create(article=self.article, title='Sem imagem', sort_order=10)
        ArticleStep.objects.create(article=self.article, title='Primeiro print', sort_order=20, screenshot='help/screenshots/primeiro.webp', image_alt='Primeiro')
        ArticleStep.objects.create(article=self.article, title='Outro print', sort_order=30, screenshot='help/screenshots/outro.webp', image_alt='Outro')
        self.assertEqual(self.article.cover_url, '/static/help/screenshots/primeiro.webp')
        self.assertEqual(self.article.illustrated_step_count, 2)

    def test_text_only_guide_does_not_pretend_to_have_screenshots(self):
        self.assertEqual(self.article.cover_url, '')
        self.assertEqual(self.article.illustrated_step_count, 0)


class HelpScreenshotFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='visual-worker')
        self.client.force_login(self.user)
        self.general = Category.objects.create(name='Geral', slug='geral')
        self.visual = Article.objects.create(category=self.general, title='Visual', slug='visual', status='PUBLISHED')
        self.text = Article.objects.create(category=self.general, title='Texto', slug='texto', status='PUBLISHED')
        ArticleStep.objects.create(article=self.visual, title='Print', screenshot='help/screenshots/primeiro.webp', image_alt='Primeiro')
        ArticleStep.objects.create(article=self.visual, title='Print 2', screenshot='help/screenshots/outro.webp', image_alt='Outro')
        finance = Category.objects.create(name='Financeiro', slug='financeiro', module='financeiro')
        self.secret = Article.objects.create(category=finance, title='Restrito', slug='restrito', status='PUBLISHED')
        ArticleStep.objects.create(article=self.secret, title='Restrito', screenshot='help/screenshots/restrito.webp', image_alt='Restrito')

    def test_illustrated_filter_deduplicates_and_respects_module_access(self):
        for url in (reverse('ajuda:index'), self.general.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url, {'illustrated': '1'})
                self.assertEqual(list(response.context['articles']), [self.visual])
                self.assertTrue(response.context['illustrated_only'])

    def test_unfiltered_list_includes_text_guides(self):
        response = self.client.get(reverse('ajuda:index'))
        self.assertEqual(set(response.context['articles']), {self.visual, self.text})
