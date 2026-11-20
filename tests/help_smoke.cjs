// Smoke real: Django fornece sessões/servidor de teste via stdin; sem senhas reais.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
    const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
    const browser = await chromium.launch({ headless: true });
    const results = [];
    let visualChecks = 0;
    try {
        for (const profile of ['manager', 'worker']) {
            const context = await browser.newContext({ baseURL: fixture.baseURL, serviceWorkers: 'block' });
            await context.addCookies([{ name: fixture.cookieName, value: fixture.sessions[profile], url: fixture.baseURL }]);
            // Isola serviços externos: testamos páginas reais, não a disponibilidade dos CDNs.
            await context.route('**/*', route => {
                const url = route.request().url();
                if (new URL(url).origin === fixture.baseURL) return route.continue();
                if (fixture.lucideAsset && url === 'https://unpkg.com/lucide@latest') return route.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(fixture.lucideAsset) });
                return route.abort();
            });
            await context.addInitScript(hasRealLucide => {
                if (!hasRealLucide) window.lucide = { createIcons() {} };
                // Representa navegador sem SW; o bloqueio do Playwright resolve
                // register() sem registro e o django-pwa tenta acessar .scope.
                delete Navigator.prototype.serviceWorker;
            }, Boolean(fixture.lucideAsset));
            const page = await context.newPage();
            page.setDefaultTimeout(10000);
            const errors = [];
            page.on('pageerror', error => errors.push(error.message));
            const paths = profile === 'manager'
                ? ['/ajuda/', '/ajuda/categoria/ordens-de-servico/', '/ajuda/artigo/agendar-os-com-etapas/']
                : ['/ajuda/', '/ajuda/categoria/app-tecnico/', '/ajuda/artigo/finalizar-tarefa-e-sincronizar/'];
            for (const width of [320, 390, 1440]) {
                await page.setViewportSize({ width, height: 900 });
                for (const path of paths) {
                    const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
                    assert.equal(response.status(), 200, `${profile} ${path}`);
                    assert(await page.locator('h1').isVisible());
                    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false, `overflow ${profile} ${path} @${width}`);
                    if (path.startsWith('/ajuda/artigo/')) {
                        assert.equal(await page.locator('.help-step-image').count(), 4);
                        const firstPrint = page.locator('.help-step-image').first();
                        await firstPrint.scrollIntoViewIfNeeded();
                        await page.waitForFunction(() => {
                            const image = document.querySelector('.help-step-image');
                            return image.complete && image.naturalWidth >= 400;
                        });
                        const enlarge = page.getByRole('button', { name: 'Ampliar print do passo 1', exact: true });
                        await enlarge.click();
                        assert(await page.locator('#help-print-dialog').evaluate(dialog => dialog.open));
                        await page.waitForFunction(() => document.querySelector('[data-help-dialog-image]').naturalWidth >= 400);
                        await page.keyboard.press('Escape');
                        assert.equal(await page.locator('#help-print-dialog').evaluate(dialog => dialog.open), false);
                        assert(await enlarge.evaluate(button => document.activeElement === button));
                        visualChecks += 1;
                    }
                    results.push(`${profile} ${path} @${width}`);
                }
            }
            if (process.env.HELP_SCREENSHOT_DIR) {
                fs.mkdirSync(process.env.HELP_SCREENSHOT_DIR, { recursive: true });
                await page.setViewportSize({ width: 390, height: 900 });
                await page.screenshot({ path: path.join(process.env.HELP_SCREENSHOT_DIR, `help-${profile}-mobile.png`) });
                await page.setViewportSize({ width: 1440, height: 900 });
                await page.goto('/ajuda/');
                await page.waitForFunction(() => [...document.querySelectorAll('.help-card-cover img')].filter(image => {
                    const box = image.getBoundingClientRect();
                    return box.bottom > 0 && box.top < window.innerHeight;
                }).every(image => image.complete && image.naturalWidth > 0));
                await page.screenshot({ path: path.join(process.env.HELP_SCREENSHOT_DIR, `help-${profile}-desktop.png`) });
            }
            await page.goto('/ajuda/');
            await page.getByLabel('Buscar tutoriais', { exact: true }).fill('sincronizacao');
            await Promise.all([page.waitForURL('**/ajuda/?**'), page.getByRole('button', { name: 'Buscar', exact: true }).click()]);
            assert.equal(await page.getByLabel('Buscar tutoriais', { exact: true }).inputValue(), 'sincronizacao');
            assert(await page.getByRole('link', { name: 'Limpar filtros', exact: true }).isVisible());
            await page.getByRole('link', { name: 'Limpar filtros', exact: true }).click();
            await page.getByLabel('Somente com prints', { exact: true }).check();
            await page.getByRole('button', { name: 'Buscar', exact: true }).click();
            await page.waitForURL('**/ajuda/?**illustrated=1**');
            assert.equal(await page.locator('.help-article-card').count(), profile === 'manager' ? 5 : 3);
            assert(await page.locator('.help-card-cover img').first().isVisible());
            await page.getByRole('link', { name: 'Limpar filtros', exact: true }).click();
            await page.getByLabel('Somente com vídeo', { exact: true }).check();
            await page.getByRole('button', { name: 'Buscar', exact: true }).click();
            await page.getByRole('heading', { name: 'Nenhum tutorial encontrado', exact: true }).waitFor();
            if (profile === 'worker') {
                assert.equal((await page.goto('/ajuda/categoria/financeiro/')).status(), 404);
                assert.equal((await page.goto('/ajuda/artigo/conferir-cobrancas-e-baixar-recebimentos/')).status(), 404);
                await page.goto('/app/', { waitUntil: 'domcontentloaded' });
                const summary = page.locator('summary').filter({ hasText: 'Como usar esta tela?' });
                await summary.focus();
                await page.keyboard.press('Enter');
                const guide = page.getByRole('link', { name: /Prepare a agenda do técnico antes de ficar offline/ });
                await guide.waitFor({ state: 'visible' });
                assert(await guide.isVisible());
                assert.equal(await guide.getAttribute('target'), '_blank');
                assert.equal(await guide.getAttribute('rel'), 'noopener');
                // O app operacional carrega dados próprios; não faz parte do smoke da ajuda.
            } else {
                await page.goto('/ajuda/');
                await page.getByRole('link', { name: 'Próxima', exact: true }).click();
                assert(new URL(page.url()).searchParams.get('page') === '2');
                const shell = await page.goto('/app/', { waitUntil: 'domcontentloaded' });
                assert(!(await shell.text()).includes('Guia reservado de gestores'), 'shell cacheável não pode conter título restrito');
                const summary = page.locator('summary').filter({ hasText: 'Como usar esta tela?' });
                await summary.click();
                const reserved = page.getByRole('link', { name: /Guia reservado de gestores/ });
                await reserved.waitFor({ state: 'visible' });
                // Troca a sessão no MESMO shell, sem recarregar: a consulta deve
                // usar as permissões atuais e não manter o resultado do gestor.
                await summary.click();
                await context.addCookies([{ name: fixture.cookieName, value: fixture.sessions.worker, url: fixture.baseURL }]);
                await summary.click();
                await page.getByRole('link', { name: /Prepare a agenda do técnico antes de ficar offline/ }).waitFor({ state: 'visible' });
                assert.equal(await reserved.count(), 0, 'título do gestor não pode persistir para o colaborador');
                await context.setOffline(true);
                await page.waitForFunction(() => document.querySelector('[data-help-context-panel]').textContent.includes('Conecte-se à internet'));
                assert.equal(await reserved.count(), 0);
                await context.setOffline(false);
            }
            // O app offline sem profissional é deliberadamente excluído desse gate.
            const helpErrors = errors.filter(message => !/OfflineDB|Dexie|OfflineApp/.test(message));
            assert.deepEqual(helpErrors, [], `JavaScript ${profile}: ${helpErrors}`);
            await context.close();
        }
        const anonymous = await browser.newContext({ baseURL: fixture.baseURL, serviceWorkers: 'block' });
        const response = await anonymous.request.get('/ajuda/', { maxRedirects: 0 });
        assert.equal(response.status(), 302);
        assert(response.headers().location.startsWith('/accounts/login/'));
        await anonymous.close();
        const noScript = await browser.newContext({ baseURL: fixture.baseURL, javaScriptEnabled: false, serviceWorkers: 'block' });
        await noScript.route('**/*', route => new URL(route.request().url()).origin === fixture.baseURL ? route.continue() : route.abort());
        await noScript.addCookies([{ name: fixture.cookieName, value: fixture.sessions.manager, url: fixture.baseURL }]);
        const fallback = await noScript.newPage();
        await fallback.goto('/ajuda/artigo/agendar-os-com-etapas/');
        await Promise.all([
            fallback.waitForURL('**/static/help/screenshots/os-cliente-imovel.webp'),
            fallback.getByRole('link', { name: 'Ampliar print do passo 1', exact: true }).click(),
        ]);
        assert(new URL(fallback.url()).pathname.endsWith('/static/help/screenshots/os-cliente-imovel.webp'));
        await noScript.close();
        console.log(JSON.stringify({ responsivePages: results.length, visualDialogs: visualChecks, noScriptImageLink: 'passed', screenshotFilter: 'passed', profiles: 2, search: 'passed', videoEmptyState: 'passed', pagination: 'passed', directAccess: 'blocked', contextualKeyboard: 'passed', sessionSwitch: 'passed', offlineContext: 'cleared', anonymous: 'redirected', externalMedia: 'not exercised' }));
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
