from django.apps import apps
from django.test import TestCase


class HelpModelTests(TestCase):
    def test_new_article_starts_as_draft_with_stable_public_url(self):
        self.assertTrue(apps.is_installed('ajuda'), 'Central de ajuda deve estar instalada')
        Category = apps.get_model('ajuda', 'Category')
        Article = apps.get_model('ajuda', 'Article')
        category = Category.objects.create(name='Primeiros passos', slug='primeiros-passos')
        article = Article.objects.create(category=category, title='Começar', slug='comecar')
        self.assertEqual(article.status, 'DRAFT')
        self.assertEqual(article.get_absolute_url(), '/ajuda/artigo/comecar/')
        self.assertEqual(category.get_absolute_url(), '/ajuda/categoria/primeiros-passos/')
