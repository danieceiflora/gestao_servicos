"""Smoke Chromium opcional, com servidor/banco isolados e sem login real.

HELP_BROWSER_TESTS=1 DEBUG=True python manage.py test ajuda.tests.test_browser --settings=core.test_settings
Requer npm install e npx playwright install chromium.
"""
import json
from io import StringIO
import os
from pathlib import Path
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import Client, override_settings

from ajuda.models import Article, Category, ContextLink
from services.models import User


@skipUnless(os.environ.get('HELP_BROWSER_TESTS') == '1', 'Habilite HELP_BROWSER_TESTS=1 para o smoke Chromium')
@override_settings(VAPID_PUBLIC_KEY='')
class HelpBrowserTests(StaticLiveServerTestCase):
    def test_real_help_navigation_desktop_and_mobile(self):
        call_command('sync_help_content', verbosity=0, stdout=StringIO())
        restricted = Article.objects.create(
            category=Category.objects.get(slug='financeiro'), title='Guia reservado de gestores',
            slug='guia-reservado-gestores', status='PUBLISHED', audience='MANAGERS',
        )
        ContextLink.objects.create(article=restricted, view_name='equipe_offline_app')
        profiles = {}
        for name, role in [('manager', User.Roles.MANAGER), ('worker', User.Roles.COLLABORATOR)]:
            user = User.objects.create_user(username=f'browser-{name}', role=role)
            client = Client()
            client.force_login(user)
            profiles[name] = client.cookies[settings.SESSION_COOKIE_NAME].value
        payload = {'baseURL': self.live_server_url, 'sessions': profiles, 'cookieName': settings.SESSION_COOKIE_NAME}
        lucide = Path.home() / 'AppData/Local/hermes/cache/scratch/help-capture-assets/lucide.js'
        if lucide.is_file():
            payload['lucideAsset'] = str(lucide)
        result = subprocess.run(
            ['node', str(Path(settings.BASE_DIR) / 'tests' / 'help_smoke.cjs')],
            input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True,
            cwd=settings.BASE_DIR, timeout=150,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())
