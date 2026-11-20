"""Protege a ajuda de cache compartilhado entre sessões do app offline."""
from pathlib import Path
import json
import shutil
import subprocess
from unittest import skipUnless
from django.conf import settings
from django.test import SimpleTestCase


class HelpOfflineBoundaryTests(SimpleTestCase):
    @skipUnless(shutil.which('node'), 'Node necessário para exercitar o service worker')
    def test_cache_policy_rejects_help_redirects_and_no_store(self):
        script = """
            const fs = require('node:fs'), vm = require('node:vm');
            const context = {self: {addEventListener() {}}, URL};
            vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
            const response = (url, redirected = false, control = '') => ({
                ok: true, url, redirected, headers: {get: () => control}
            });
            console.log(JSON.stringify([
                context.mayCacheResponse(response('https://example.test/app/')),
                context.mayCacheResponse(response('https://example.test/ajuda/', true)),
                context.mayCacheResponse(response('https://example.test/ajuda/')),
                context.mayCacheResponse(response('https://example.test/ajuda')),
                context.mayCacheResponse(response('https://example.test/app/', false, 'private, no-store')),
                context.mayCacheResponse({ok: false, type: 'opaque'}),
                context.mayCacheResponse({ok: false, type: 'basic'}),
            ]));
        """
        result = subprocess.run(['node', '-e', script, str(Path(settings.BASE_DIR) / 'static/js/serviceworker.js')], check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(result.stdout), [True, False, False, False, False, True, False])

    @skipUnless(shutil.which('node'), 'Node necessário para exercitar o service worker')
    def test_activation_removes_old_shells_without_touching_indexeddb(self):
        script = """
            const fs = require('node:fs'), vm = require('node:vm');
            const callbacks = {}, deleted = [], waits = [];
            const context = {
                self: {addEventListener: (name, callback) => callbacks[name] = callback, clients: {claim: async () => {}}},
                caches: {keys: async () => ['gestao-servicos-v8', 'gestao-servicos-v9'], delete: async name => deleted.push(name)},
                indexedDB: {deleteDatabase: () => {throw new Error('Fila offline não pode ser apagada');}}, console: {log() {}}
            };
            vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
            callbacks.activate({waitUntil: promise => waits.push(promise)});
            Promise.all(waits).then(() => console.log(JSON.stringify(deleted)));
        """
        result = subprocess.run(['node', '-e', script, str(Path(settings.BASE_DIR) / 'static/js/serviceworker.js')], check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(result.stdout), ['gestao-servicos-v8'])

    @skipUnless(shutil.which('node'), 'Node necessário para exercitar o service worker')
    def test_fetch_handler_does_not_intercept_help_or_authentication(self):
        script = """
            const fs = require('node:fs'), vm = require('node:vm');
            const callbacks = {};
            vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
                self: { addEventListener: (event, callback) => callbacks[event] = callback },
                URL, console, fetch: async () => ({ok: false})
            });
            const result = {};
            for (const path of ['/ajuda', '/ajuda/', '/ajuda/artigo/teste/', '/ajuda/contexto/', '/accounts/login/', '/admin/', '/app/']) {
                let intercepted = false;
                callbacks.fetch({request: {method: 'GET', url: 'https://example.test' + path},
                    respondWith: () => intercepted = true});
                result[path] = intercepted;
            }
            console.log(JSON.stringify(result));
        """
        result = subprocess.run(
            ['node', '-e', script, str(Path(settings.BASE_DIR) / 'static/js/serviceworker.js')],
            check=True, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(json.loads(result.stdout), {
            '/ajuda': False, '/ajuda/': False, '/ajuda/artigo/teste/': False, '/ajuda/contexto/': False,
            '/accounts/login/': False, '/admin/': False, '/app/': True,
        })

    @skipUnless(shutil.which('node'), 'Node necessário para exercitar o service worker')
    def test_actual_fetch_handler_never_saves_or_replays_redirected_help(self):
        script = """
            const fs = require('node:fs'), vm = require('node:vm');
            const callbacks = {}, storage = new Map();
            let offline = false;
            const key = request => typeof request === 'string' ? new URL(request, 'https://example.test').href : request.url;
            const context = {
                URL, Response, console,
                self: {addEventListener: (event, callback) => callbacks[event] = callback},
                fetch: async request => {
                    if (offline) throw new Error('offline');
                    const alias = request.url.endsWith('/help-alias');
                    return {ok: true, type: 'basic', redirected: alias,
                        url: alias ? 'https://example.test/ajuda/' : request.url,
                        headers: {get: () => alias ? 'private, no-store' : ''},
                        text: async () => alias ? 'restricted guide' : 'generic operational shell',
                        clone() {return this;}};
                },
                caches: {
                    open: async () => ({put: async (request, response) => storage.set(key(request), response)}),
                    match: async request => storage.get(key(request)),
                }
            };
            vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
            async function request(path) {
                let response; const waits = [];
                callbacks.fetch({request: {method: 'GET', url: 'https://example.test' + path, mode: 'navigate'},
                    respondWith: promise => response = promise, waitUntil: promise => waits.push(promise)});
                const result = await response;
                await Promise.all(waits);
                return result;
            }
            (async () => {
                await request('/help-alias');
                const savedAlias = storage.has('https://example.test/help-alias');
                offline = true;
                const blocked = await request('/help-alias');
                offline = false;
                await request('/app/');
                offline = true;
                const shell = await request('/app/');
                console.log(JSON.stringify({savedAlias, offlineStatus: blocked.status,
                    offlineHelp: await blocked.text(), cachedShell: await shell.text()}));
            })().catch(error => {console.error(error); process.exitCode = 1;});
        """
        result = subprocess.run(['node', '-e', script, str(Path(settings.BASE_DIR) / 'static/js/serviceworker.js')], check=True, capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(result.stdout), {
            'savedAlias': False, 'offlineStatus': 503, 'offlineHelp': 'Offline',
            'cachedShell': 'generic operational shell',
        })
