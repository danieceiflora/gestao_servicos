from copy import deepcopy
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import TestCase

from ajuda.initial_content import ARTICLES
from ajuda.management.commands import sync_help_content as sync
from ajuda.models import Article, Category
from ajuda.tests.test_sync import run_sync


class HelpScreenshotSyncTests(TestCase):
    def test_source_snapshots_track_official_screenshots(self):
        source = deepcopy(ARTICLES[0])
        source['steps'][0]['screenshot'] = 'help/screenshots/primeiro.webp'
        self.assertEqual(sync.source_snapshot(source)['steps'][0]['screenshot'], 'help/screenshots/primeiro.webp')

    def test_missing_screenshot_fails_before_writing_any_content(self):
        sources = deepcopy(ARTICLES)
        sources[0]['steps'][0]['screenshot'] = 'help/screenshots/arquivo-inexistente.webp'
        sources[0]['steps'][0]['image_alt'] = 'Print inexistente'
        with patch.object(sync, 'ARTICLES', sources):
            with self.assertRaises(CommandError):
                run_sync()
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)

    def test_legacy_hash_is_upgraded_for_untouched_content(self):
        run_sync()
        article = Article.objects.get(slug=ARTICLES[0]['slug'])
        snapshot = sync.article_snapshot(article)
        for step in snapshot['steps']:
            step.pop('screenshot', None)
        legacy_hash = sync.content_hash(snapshot)
        article.source_hash = legacy_hash
        article.save(update_fields=['source_hash'])
        run_sync()
        article.refresh_from_db()
        self.assertNotEqual(article.source_hash, legacy_hash)
        self.assertEqual(article.source_hash, sync.article_hash(article))
        run_sync('--check')

    def test_legacy_upgrade_preserves_manual_edits(self):
        run_sync()
        article = Article.objects.get(slug=ARTICLES[0]['slug'])
        snapshot = sync.article_snapshot(article)
        for step in snapshot['steps']:
            step.pop('screenshot', None)
        article.source_hash = sync.content_hash(snapshot)
        article.title = 'Título escrito pelo cliente'
        article.save()
        self.assertIn('CONFLITO', run_sync())
        article.refresh_from_db()
        self.assertEqual(article.title, 'Título escrito pelo cliente')
