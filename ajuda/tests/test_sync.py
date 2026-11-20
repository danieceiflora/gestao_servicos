"""Contratos da importação conservadora e do catálogo oficial versionado."""
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import URLResolver, get_resolver

from ajuda.initial_content import ARTICLES, CATEGORIES
from ajuda.management.commands import sync_help_content as sync
from ajuda.models import Article, ArticleStep, Category, ContextLink


def run_sync(*args):
    output = StringIO()
    call_command('sync_help_content', *args, stdout=output)
    return output.getvalue()


class HelpCatalogTests(TestCase):
    def test_read_only_modes_do_not_create_missing_content(self):
        run_sync('--dry-run')
        self.assertEqual(Category.objects.count(), 0)
        self.assertEqual(Article.objects.count(), 0)
        with self.assertRaises(CommandError):
            run_sync('--check')
        self.assertEqual(Category.objects.count(), 0)

    def test_initial_catalog_is_valid_and_context_screens_exist(self):
        run_sync()
        for category in Category.objects.all():
            category.full_clean()
        for article in Article.objects.all():
            article.full_clean()
            for step in article.steps.all():
                step.full_clean()
        names = set()
        def collect(patterns, namespace=''):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    child_namespace = namespace + pattern.namespace + ':' if pattern.namespace else namespace
                    collect(pattern.url_patterns, child_namespace)
                elif pattern.name:
                    names.add(namespace + pattern.name)
        collect(get_resolver().url_patterns)
        self.assertFalse(set(ContextLink.objects.values_list('view_name', flat=True)) - names)
        self.assertEqual(Article.objects.count(), len(ARTICLES))
        self.assertEqual(Category.objects.count(), len(CATEGORIES))

    def test_existing_category_with_wrong_access_module_is_not_silently_adopted(self):
        source_category = next(category for category in CATEGORIES if category['module'] == 'financeiro')
        category = Category.objects.create(name='Local', slug=source_category['slug'], module='geral')
        output = run_sync()
        self.assertIn('CONFLITO', output)
        self.assertFalse(Article.objects.filter(category=category).exists())
        category.refresh_from_db()
        self.assertEqual(category.module, 'geral')
        with self.assertRaises(CommandError):
            run_sync('--check')


class HelpSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        run_sync()

    def first_article(self):
        return Article.objects.get(slug=ARTICLES[0]['slug'])

    def changed_sources(self):
        sources = deepcopy(ARTICLES)
        sources[0]['title'] = 'Título da próxima versão'
        sources[0]['steps'][0]['content'] += ' Instrução revisada.'
        return sources

    def test_repeat_is_idempotent_and_check_passes(self):
        before = [sync.article_snapshot(article) for article in Article.objects.select_related('category').all()]
        pks = list(ArticleStep.objects.values_list('pk', flat=True))
        run_sync()
        run_sync('--check')
        self.assertEqual(pks, list(ArticleStep.objects.values_list('pk', flat=True)))
        self.assertEqual(before, [sync.article_snapshot(article) for article in Article.objects.select_related('category').all()])

    def test_unmodified_official_article_receives_versioned_update(self):
        with patch.object(sync, 'ARTICLES', self.changed_sources()):
            run_sync()
            article = self.first_article()
            self.assertEqual(article.title, 'Título da próxima versão')
            self.assertEqual(article.source_hash, sync.article_hash(article))
            run_sync('--check')

    def test_check_and_dry_run_never_apply_updates(self):
        before = self.first_article().title
        with patch.object(sync, 'ARTICLES', self.changed_sources()):
            run_sync('--dry-run')
            with self.assertRaises(CommandError):
                run_sync('--check')
        self.assertEqual(self.first_article().title, before)

    def test_manual_content_and_custom_article_are_preserved(self):
        article = self.first_article()
        article.content = 'Texto escrito pelo administrador'
        article.save()
        local = Article.objects.create(category=article.category, title='Guia local', slug='guia-local')
        with patch.object(sync, 'ARTICLES', self.changed_sources()):
            self.assertIn('CONFLITO', run_sync())
        article.refresh_from_db()
        self.assertEqual(article.content, 'Texto escrito pelo administrador')
        self.assertTrue(Article.objects.filter(pk=local.pk).exists())
        with self.assertRaises(CommandError):
            run_sync('--check')

    def test_manual_video_image_status_and_step_changes_are_preserved(self):
        cases = ('video', 'image', 'status', 'step', 'screen')
        for index, case in enumerate(cases):
            article = Article.objects.get(slug=ARTICLES[index]['slug'])
            if case == 'video':
                article.video_url = 'https://youtu.be/Abc_12-xyZ0'
            elif case == 'status':
                article.status = 'ARCHIVED'
            elif case == 'image':
                step = article.steps.first()
                step.image = 'ajuda/local.png'
                step.image_alt = 'Imagem local'
                step.save()
            elif case == 'step':
                step = article.steps.first()
                step.content = 'Passo local'
                step.save()
            else:
                ContextLink.objects.create(article=article, view_name='client_list')
            article.save()
        snapshots = {article.pk: sync.article_snapshot(article) for article in Article.objects.all()}
        run_sync()
        for article in Article.objects.all():
            self.assertEqual(sync.article_snapshot(article), snapshots[article.pk])

    def test_renamed_official_slug_does_not_create_duplicate(self):
        article = self.first_article()
        article.slug = 'slug-renomeado'
        article.save()
        run_sync()
        self.assertEqual(Article.objects.count(), len(ARTICLES))
        self.assertFalse(Article.objects.filter(slug=ARTICLES[0]['slug']).exists())

    def test_existing_local_slug_is_not_adopted_as_official(self):
        article = self.first_article()
        article.source_key = ''
        article.source_hash = ''
        article.save()
        run_sync()
        article.refresh_from_db()
        self.assertEqual(article.source_hash, '')

    def test_failure_rolls_back_all_writes_for_the_article(self):
        article = self.first_article()
        before = sync.article_snapshot(article)
        with patch.object(sync, 'ARTICLES', self.changed_sources()), patch.object(ContextLink.objects, 'create', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                run_sync()
        article.refresh_from_db()
        self.assertEqual(sync.article_snapshot(article), before)
