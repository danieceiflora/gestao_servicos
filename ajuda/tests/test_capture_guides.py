"""Opt-in real browser guide captures; never uses the customer database.

HELP_CAPTURE_GUIDES=1 DEBUG=True PYTHONUTF8=1 <python> manage.py test \
    ajuda.tests.test_capture_guides --settings=core.test_settings --noinput

Node Playwright/Chromium and Pillow are prerequisites. CDN bytes are downloaded
unchanged to the Hermes scratch cache; no application/API responses are mocked.
Only the final WebP images and public, credential-free manifest enter the repo.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client as BrowserClient, override_settings
from django.urls import reverse
from django.utils import timezone

from services.models import (
    Client, ClientPhone, PaymentMethod, Professional, ProfessionalRole, Property,
    Service, ServiceChecklistItem, ServiceItem, ServiceOrder, ServiceOrderTask,
    ServiceOrderTeam, ServicePayment, TaskChecklistResponse, User, WorkSchedule, WorkScheduleDay,
)
from integracoes.models import SystemConfig


ASSETS = {
    'https://unpkg.com/lucide@latest': ('lucide.js', 'https://cdn.jsdelivr.net/npm/lucide@0.468.0/dist/umd/lucide.min.js'),
    'https://unpkg.com/htmx.org@1.9.12': ('htmx.js', 'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/dist/htmx.min.js'),
    'https://unpkg.com/dexie@latest/dist/dexie.js': ('dexie.js', 'https://cdn.jsdelivr.net/npm/dexie@4.0.11/dist/dexie.js'),
    'https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js': ('signature.js', None),
    'https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/js/tom-select.complete.min.js': ('tom-select.js', None),
    'https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/css/tom-select.css': ('tom-select.css', None),
}


def download_assets(scratch):
    cache = scratch / 'help-capture-assets'
    cache.mkdir(parents=True, exist_ok=True)
    assets = {}
    for url, (name, fallback) in ASSETS.items():
        target = cache / name
        if not target.exists():
            failures = []
            for source in dict.fromkeys([url, fallback or url]):
                try:
                    with urlopen(Request(source, headers={'User-Agent': 'HelpGuideCapture/1.0'}), timeout=45) as response:
                        body = response.read()
                    if len(body) < 500 or body.lstrip().startswith(b'<'):
                        raise ValueError('CDN did not return a real script/stylesheet')
                    target.write_bytes(body)
                    break
                except Exception as exc:
                    failures.append(f'{source}: {exc}')
            else:
                raise RuntimeError('; '.join(failures))
        assets[url] = str(target)
    return assets


@skipUnless(os.environ.get('HELP_CAPTURE_GUIDES') == '1', 'Set HELP_CAPTURE_GUIDES=1 to create real guide images')
@override_settings(
    VAPID_PUBLIC_KEY='', VAPID_PRIVATE_KEY='', ASAAS_API_KEY='',
    ASAAS_CLIENT_API_KEY='', BASEERP_API_KEY='', WEBHOOK_SHARED_SECRET='',
    SITE_URL='http://example.invalid',
)
class HelpCaptureGuidesTests(StaticLiveServerTestCase):
    databases = {'default'} if os.environ.get('HELP_CAPTURE_GUIDES') == '1' else set()

    def test_capture_real_guides(self):
        self.assertEqual(settings.DATABASES['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertIn('memory', str(settings.DATABASES['default']['NAME']))
        self.assertEqual(settings.STORAGES['default']['BACKEND'], 'django.core.files.storage.InMemoryStorage')
        # Native Windows Python may rewrite TMPDIR to the system Temp directory.
        # Use the explicit Hermes workspace scratch root instead.
        scratch = Path.home() / 'AppData/Local/hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        assets = download_assets(scratch)
        manager = User.objects.create_superuser(username='guide-manager', password=None, role=User.Roles.MANAGER, first_name='Gestor Demonstração')
        worker = User.objects.create_user(username='guide-worker', role=User.Roles.COLLABORATOR, first_name='Técnico Exemplo')
        role = ProfessionalRole.objects.create(name='Técnico')
        schedule = WorkSchedule.objects.create(name='Escala demonstrativa')
        for weekday in range(7):
            WorkScheduleDay.objects.create(schedule=schedule, day_of_week=weekday, start_time='00:00', end_time='23:59')
        professional = Professional.objects.create(user=worker, name='Técnico Exemplo', phone='00000000000', work_schedule=schedule)
        professional.roles.add(role)
        client = Client.objects.create(name='Cliente Demonstração', client_type='PF')
        ClientPhone.objects.create(client=client, phone='00000000000', is_primary=True)
        prop = Property.objects.create(client=client, address='Rua de Demonstração', number='100', complement='Local fictício', neighborhood='Bairro Exemplo', city='Cidade Exemplo', state='MS')
        config = SystemConfig.load()
        config.company_name = 'Empresa Demonstração'
        config.technician_can_view_order_values = True
        config.save()
        PaymentMethod.objects.create(descricao='Dinheiro', tipo_provedor='MANUAL', codigo_sefaz='01', integra_gateway=False)
        order = ServiceOrder.objects.create(client_property=prop, description='Atendimento de demonstração para treinamento. Conferir instalação e testar funcionamento.', technical_notes='Dados fictícios; não realizar contato ou cobrança.', service_type='INSTALACAO')
        scheduled = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
        task = ServiceOrderTask.objects.create(service_order=order, task_type='EXECUCAO', scheduled_at=scheduled, scheduled_end_at=scheduled + timedelta(hours=2), is_approved=True, skip_auto_billing=True, notes='Demonstração: conferir instalação e segurança antes dos testes.')
        ServiceOrderTeam.objects.create(task=task, professional=professional, role=role)
        service = Service.objects.create(name='Inspeção demonstrativa', base_price='150.00')
        ServiceChecklistItem.objects.create(service=service, name='Conferir instalação e segurança', description='Confirme a inspeção antes de concluir o atendimento.', evidence_type='TEXTO', is_required=True)
        ServiceChecklistItem.objects.create(service=service, name='Testar funcionamento', description='Registre OK somente depois do teste.', evidence_type='FOTO', is_required=False, order=10)
        ServiceItem.objects.create(service_order=order, task=task, service=service, description='Inspeção demonstrativa', quantity=1, unit_price='150.00')
        sessions = {}
        for profile, user in [('manager', manager), ('worker', worker)]:
            browser = BrowserClient()
            browser.force_login(user)
            sessions[profile] = browser.cookies[settings.SESSION_COOKIE_NAME].value
        with tempfile.TemporaryDirectory(prefix='help-guide-captures-', dir=scratch) as temporary:
            payload = {
                'baseURL': self.live_server_url, 'sessions': sessions,
                'cookieName': settings.SESSION_COOKIE_NAME, 'assets': assets,
                'output': temporary, 'taskId': str(task.pk),
                'clientId': str(client.pk), 'propertyId': str(prop.pk),
                'professionalId': str(professional.pk), 'roleId': str(role.pk),
                'schedule': scheduled.strftime('%Y-%m-%dT%H:%M'),
                'endSchedule': (scheduled + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'availableSchedule': (scheduled + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
                'availableEnd': (scheduled + timedelta(days=1, hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'orderRoute': reverse('service_order_detail', args=[order.pk]),
            }
            # A hard safety belt: Django cannot send requests to any integration.
            with patch('requests.sessions.Session.request', side_effect=RuntimeError('External integrations disabled during guide capture')) as external_requests:
                result = subprocess.run(['node', str(Path(settings.BASE_DIR) / 'tests/help_capture.cjs')], input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, cwd=settings.BASE_DIR, timeout=300)
            self.assertEqual(external_requests.call_count, 0, 'No integration should even be attempted')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((Path(temporary) / 'manifest.json').read_text(encoding='utf-8'))
            from ajuda.initial_content import ARTICLES
            slugs = {'cadastrar-cliente-e-imovel', 'agendar-os-com-etapas', 'preparar-app-tecnico-offline', 'iniciar-tarefa-checklist-e-anexos', 'finalizar-tarefa-e-sincronizar'}
            expected = {(a['slug'], s['sort_order']) for a in ARTICLES if a['slug'] in slugs for s in a['steps']}
            self.assertEqual({(m['article_slug'], m['step_order']) for m in manifest}, expected)
            self.assertEqual(len(manifest), len(expected))
            from PIL import Image
            output = Path(settings.BASE_DIR) / 'static/help/screenshots'
            output.mkdir(parents=True, exist_ok=True)
            for entry in manifest:
                self.assertRegex(entry['filename'], r'^[a-z0-9_-]+\.webp$')
                png = Path(temporary) / entry['filename'].replace('.webp', '.png')
                with Image.open(png) as image:
                    image.save(output / entry['filename'], format='WEBP', quality=88, method=6)
                with Image.open(output / entry['filename']) as image:
                    self.assertEqual(image.format, 'WEBP')
                    self.assertGreater(image.width, 300)
            (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            self.assertEqual(ServicePayment.objects.count(), 0, 'Capturing must not register payments')
            task.refresh_from_db()
            self.assertEqual(task.status, 'EM_ANDAMENTO')
            print(result.stdout.strip())
            responses = TaskChecklistResponse.objects.filter(task=task)
            print(f'Checklist diagnostic: {responses.count()} real server responses; {responses.filter(completed=True).count()} marked completed after UI OK + sync. Screens reflect the unmodified application, not a claim of checklist persistence.')
            print(f'Verified {len(manifest)} WebP guide images; zero receipts; zero external requests; database isolated.')
