from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from ajuda.models import Article, ArticleStep, Category


class VideoTests(SimpleTestCase):
    def test_youtube_watch_and_short_links_produce_trusted_embed(self):
        from ajuda.video import video_embed_url
        for url in ('https://www.youtube.com/watch?v=Abc_12-xyZ0&t=30', 'https://youtu.be/Abc_12-xyZ0', 'https://www.youtube.com/shorts/Abc_12-xyZ0'):
            with self.subTest(url=url):
                self.assertEqual(video_embed_url(url), 'https://www.youtube-nocookie.com/embed/Abc_12-xyZ0')

    def test_vimeo_links_produce_trusted_embed(self):
        from ajuda.video import video_embed_url
        self.assertEqual(video_embed_url('https://vimeo.com/123456789'), 'https://player.vimeo.com/video/123456789')
        self.assertEqual(video_embed_url('https://vimeo.com/123456789/abcdef1234'), 'https://player.vimeo.com/video/123456789?h=abcdef1234')

    def test_unsafe_links_never_become_iframe_sources(self):
        from ajuda.video import video_embed_url, validate_video_url
        for url in ('javascript:alert(1)', 'http://youtube.com/watch?v=Abc_12-xyZ0', 'https://youtube.com.evil.test/watch?v=Abc_12-xyZ0', 'https://youtube.com@evil.test/watch?v=Abc_12-xyZ0', 'https://evil@youtube.com/watch?v=Abc_12-xyZ0', 'https://youtube.com:999/watch?v=Abc_12-xyZ0', 'https://youtu.be/invalid', 'https://www.youtube.com/embed/Abc_12-xyZ0/other', '<iframe src=x>', 'https://vimeo.com/123456789/invalid%22hash', 'https://player.vimeo.com/video/123?h=%22onload=1'):
            with self.subTest(url=url):
                self.assertEqual(video_embed_url(url), '')
                with self.assertRaises(ValidationError):
                    validate_video_url(url)

    def test_blank_video_is_optional(self):
        from ajuda.video import video_embed_url, validate_video_url
        self.assertEqual(video_embed_url(''), '')
        validate_video_url('')


class ArticleValidationTests(TestCase):
    def test_admin_model_validation_rejects_arbitrary_video_provider(self):
        category = Category.objects.create(name='Geral', slug='geral')
        article = Article(category=category, title='Teste', slug='teste', video_url='https://evil.test/video')
        with self.assertRaises(ValidationError) as error:
            article.full_clean()
        self.assertIn('video_url', error.exception.message_dict)

    def test_step_image_requires_accessible_description(self):
        category = Category.objects.create(name='Geral', slug='geral')
        article = Article.objects.create(category=category, title='Teste', slug='teste')
        step = ArticleStep(article=article, title='Imagem', image='ajuda/teste.png')
        with self.assertRaises(ValidationError) as error:
            step.full_clean()
        self.assertIn('image_alt', error.exception.message_dict)
