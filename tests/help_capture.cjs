// Real Django screens only. Run through the isolated Python opt-in test.
// Session cookies travel over stdin, never into images, logs or the manifest.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
    const manifest = [];
    const routes = new Set();
    const errors = [];
    const browser = await chromium.launch({ headless: true });
    let activePage;
    async function context(profile, viewport) {
        const ctx = await browser.newContext({ baseURL: fixture.baseURL, viewport, serviceWorkers: 'block', locale: 'pt-BR', timezoneId: 'America/Sao_Paulo', deviceScaleFactor: 1 });
        await ctx.addCookies([{ name: fixture.cookieName, value: fixture.sessions[profile], url: fixture.baseURL }]);
        // Preserve the exact bytes of real libraries. Never stub icons or API data.
        await ctx.route('**/*', async route => {
            const url = route.request().url();
            if (new URL(url).origin === fixture.baseURL) return route.continue();
            const asset = fixture.assets[url];
            if (asset) return route.fulfill({ body: fs.readFileSync(asset), contentType: asset.endsWith('.css') ? 'text/css' : 'application/javascript' });
            return route.abort();
        });
        await ctx.addInitScript(() => { delete Navigator.prototype.serviceWorker; });
        const page = await ctx.newPage();
        page.setDefaultTimeout(15000);
        page.on('pageerror', e => errors.push(e.message));
        page.on('dialog', dialog => dialog.accept());
        return { ctx, page };
    }
    async function go(page, url) {
        activePage = page;
        const response = await page.goto(url, { waitUntil: 'networkidle' });
        assert.equal(response.status(), 200, url);
        routes.add(new URL(page.url()).pathname);
        assert(await page.locator('svg.lucide').count() > 0, `Real Lucide icons missing: ${url}`);
    }
    async function capture(page, slug, order, name, selectors, caption, focus = selectors[0]) {
        activePage = page;
        const heights = {
            'cliente-buscar': 700, 'cliente-identificacao': 1200, 'cliente-imovel': 1000,
            'os-cliente-imovel': 850, 'os-etapas-equipe': 1350,
            'os-conflito-agenda': 850, 'os-conferir-resultado': 800,
        };
        await page.setViewportSize({ width: page.viewportSize().width, height: heights[name] || (name.startsWith('tecnico-encerramento') || name.startsWith('tecnico-sem-') || name.startsWith('tecnico-confirmar-') ? 1100 : 950) });
        await page.locator(focus).first().evaluate(el => el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }));
        await page.waitForTimeout(180);
        const boxes = [];
        for (const selector of selectors) {
            const el = page.locator(selector).first();
            assert(await el.isVisible(), `Highlight not visible: ${selector}`);
            const box = await el.boundingBox();
            assert(box && box.width > 0 && box.height > 0, selector);
            boxes.push(box);
        }
        const viewport = page.viewportSize();
        assert(boxes.some(b => b.y >= 0 && b.y < viewport.height - 70), 'Target outside capture');
        await page.evaluate(({ boxes, caption, step }) => {
            const layer = document.createElement('div');
            layer.id = 'help-capture-annotations';
            layer.setAttribute('aria-label', 'Anotações temporárias do tutorial');
            layer.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;font-family:Arial,sans-serif';
            for (const b of boxes) {
                const halo = document.createElement('div');
                halo.style.cssText = `position:absolute;left:${Math.max(3, b.x-3)}px;top:${Math.max(3,b.y-3)}px;width:${Math.min(b.width+6,innerWidth-6)}px;height:${b.height+6}px;border:3px solid #e05212;border-radius:10px;box-shadow:0 0 0 3px #fff9;box-sizing:border-box`;
                const badge = document.createElement('span');
                badge.textContent = String(step);
                badge.style.cssText = 'position:absolute;left:-8px;top:-13px;background:#ba3907;color:white;border:2px solid white;border-radius:50%;width:25px;height:25px;text-align:center;line-height:22px;font-size:14px;font-weight:bold';
                halo.appendChild(badge);
                layer.appendChild(halo);
            }
            const note = document.createElement('div');
            note.textContent = `ANOTAÇÃO ${step} • ${caption}`;
            note.style.cssText = 'position:absolute;bottom:0;left:0;right:0;padding:13px 16px;background:#132238;color:white;border-top:4px solid #e05212;font-size:14px;line-height:1.4;font-weight:600;box-shadow:0 -2px 8px #0002';
            layer.appendChild(note);
            document.body.appendChild(layer);
        }, { boxes, caption, step: order / 10 });
        const filename = `${name}.webp`;
        try {
            await page.screenshot({ path: path.join(fixture.output, `${name}.png`), animations: 'disabled' });
        } finally {
            await page.locator('#help-capture-annotations').evaluate(node => node.remove());
        }
        const url = new URL(page.url());
        routes.add(url.pathname + url.hash);
        manifest.push({ article_slug: slug, step_order: order, filename, alt: caption + ' — tela real com dados fictícios e destaque numerado.', route: url.pathname + url.hash, highlight: selectors.join(', '), viewport });
        console.log(`Captured ${slug}:${order} ${filename}`);
    }
    async function next(page) {
        await page.locator('#wizard-btn-next').click();
        await page.waitForTimeout(280);
    }
    async function tab(page, name) {
        await page.locator(`.tab-btn[data-tab="${name}"]`).click();
        await page.locator(`#tab-panel-${name}`).waitFor({ state: 'visible' });
    }
    try {
        const manager = await context('manager', { width: 1280, height: 1050 });
        const page = manager.page;
        const clients = 'cadastrar-cliente-e-imovel';
        await go(page, '/clientes/?search=Demonstra%C3%A7%C3%A3o');
        await capture(page, clients, 10, 'cliente-buscar', ['input[name="search"]', 'tbody tr'], 'Procure o cliente e confira os imóveis antes de duplicar o cadastro.');
        await go(page, '/clientes/novo/');
        await page.locator('#id_name').fill('Cliente Demonstração — novo cadastro');
        await page.locator('#id_phones-0-phone').fill('00000000000');
        await page.locator('#id_emails-0-email').fill('demonstracao@example.invalid');
        await capture(page, clients, 20, 'cliente-identificacao', ['#unified-form > section:first-of-type', '#phones-formset-container'], 'Escolha PF ou PJ, informe o nome e revise os contatos.', '#id_name');
        for (const [field, value] of Object.entries({ address: 'Rua de Demonstração', number: '200', complement: 'Local fictício', neighborhood: 'Bairro Exemplo', city: 'Cidade Exemplo', state: 'MS' })) {
            await page.locator(`#id_properties-0-${field}`).fill(value);
        }
        await capture(page, clients, 30, 'cliente-imovel', ['#properties-formset-container', '#unified-form button[type="submit"]'], 'Confira endereço, número e complemento do imóvel e finalize o cadastro.');
        await page.locator('#unified-form button[type="submit"]').click();
        await page.waitForLoadState('networkidle');
        assert.equal(new URL(page.url()).pathname, '/clientes/');
        const savedClient = page.locator('tbody tr').filter({ hasText: 'Cliente Demonstração — novo cadastro' });
        assert((await savedClient.innerText()).includes('Rua de Demonstração, 200'), 'New client and property must really be saved');
        const os = 'agendar-os-com-etapas';
        await go(page, '/ordens/nova/');
        await page.locator('.ts-control').click();
        await page.locator('.ts-control input').fill('Cliente Demonstração');
        await page.locator('.ts-dropdown .option').filter({ hasText: 'Cliente Demonstração (Sem documento)' }).first().click();
        await page.locator(`#id_client_property option[value="${fixture.propertyId}"]`).waitFor({ state: 'attached' });
        await page.locator('#id_client_property').selectOption(fixture.propertyId);
        await capture(page, os, 10, 'os-cliente-imovel', ['#os-section-client', '#wizard-progress'], 'No novo agendamento, selecione cliente e imóvel e avance para os detalhes.', '#os-section-client');
        await next(page);
        await page.locator('#id_description').fill('Atendimento demonstrativo: vistoria e planejamento da instalação.');
        await page.locator('#id_service_type').selectOption('INSTALACAO');
        await next(page);
        await page.locator('[name="task_0_type"]').selectOption('ORCAMENTO');
        await page.locator('#id_scheduled_at').fill(fixture.schedule);
        await page.locator('#id_scheduled_end_at').fill(fixture.endSchedule);
        await page.locator('[name="task_0_professional[]"]').selectOption(fixture.professionalId);
        await page.locator('[name="task_0_role[]"]').selectOption(fixture.roleId);
        await capture(page, os, 20, 'os-etapas-equipe', ['#tasks-container'], 'Defina tipo, início, fim e equipe de cada etapa.', '[name="task_0_type"]');
        await next(page);
        await page.locator('#wizard-btn-submit').click();
        await page.waitForLoadState('networkidle');
        const conflict = page.getByRole('alert').filter({ hasText: 'Conflito de agenda' });
        await conflict.waitFor();
        assert((await conflict.textContent()).includes('Técnico Exemplo'));
        await capture(page, os, 30, 'os-conflito-agenda', ['#toast-container [role="alert"]'], 'Leia o conflito real de agenda. Altere o horário ou a equipe antes de tentar salvar.');
        // Server returned the bound form, preserving submitted data; use its real wizard.
        await next(page);
        await next(page);
        await page.locator('#id_scheduled_at').fill(fixture.availableSchedule);
        await page.locator('#id_scheduled_end_at').fill(fixture.availableEnd);
        await next(page);
        await page.locator('#wizard-btn-submit').click();
        await page.waitForLoadState('networkidle');
        assert(/\/ordens\/[0-9a-f-]+\/$/.test(new URL(page.url()).pathname), `Order not saved: ${page.url()}`);
        await page.locator('[data-tab="etapas"]').click();
        await capture(page, os, 40, 'os-conferir-resultado', ['#tab-etapas'], 'Confira a OS salva, o imóvel, o horário e a equipe da etapa.', '#tab-etapas');
        await manager.ctx.close();

        const worker = await context('worker', { width: 430, height: 1100 });
        const mobile = worker.page;
        activePage = mobile;
        const prepare = 'preparar-app-tecnico-offline';
        await go(mobile, '/app/');
        await mobile.locator('.task-card').first().waitFor();
        await mobile.waitForFunction(() => !OfflineDB._syncInProgress);
        await capture(mobile, prepare, 10, 'tecnico-agenda', ['#section-scheduled .task-list'], 'Carregue Minha Agenda com internet e confira o atendimento esperado.');
        await mobile.locator('#btn-sync-now').click();
        await mobile.waitForFunction(() => !OfflineDB._syncInProgress);
        await capture(mobile, prepare, 20, 'tecnico-sincronizar-filtros', ['#btn-sync-now', '#filter-status', '#filter-hide-completed'], 'Sincronize e confira conexão, última sincronização e filtros.', '#filter-status');
        // Open the actual task by its real hash link through the application's router.
        await mobile.locator('.task-card').filter({ hasText: 'EXECUCAO' }).first().click();
        await mobile.locator('#tab-panel-info').waitFor({ state: 'visible' });
        assert(new URL(mobile.url()).hash === `#task/${fixture.taskId}`);
        await tab(mobile, 'itens');
        assert((await mobile.locator('#tab-panel-itens').innerText()).includes('Inspeção demonstrativa'));
        await tab(mobile, 'checklist');
        await tab(mobile, 'info');
        await capture(mobile, prepare, 30, 'tecnico-info-atendimento', ['#tab-panel-info'], 'Em Info, confira cliente, endereço e instruções antes de ficar sem conexão.');
        const start = 'iniciar-tarefa-checklist-e-anexos';
        await capture(mobile, start, 10, 'tecnico-iniciar-servico', ['#info-btn-start'], 'Comece o trabalho usando INICIAR SERVIÇO AGORA.', '#info-btn-start');
        await mobile.locator('#info-btn-start').click();
        await mobile.getByText('Serviço em andamento', { exact: true }).waitFor();
        await tab(mobile, 'checklist');
        await mobile.locator('.btn-check-ok').first().click();
        await mobile.locator('.btn-check-ok').nth(1).click();
        await capture(mobile, start, 20, 'tecnico-checklist', ['#tab-panel-checklist'], 'Revise cada item do checklist e registre o resultado real da verificação.');
        await tab(mobile, 'anexos');
        await capture(mobile, start, 30, 'tecnico-anexos', ['#tab-btn-add-media', '#tab-btn-add-video'], 'Adicione evidências no contexto certo; aqui estão os controles reais de Anexos.');
        await mobile.locator('#btn-sync-now').click();
        await mobile.waitForFunction(() => !OfflineDB._syncInProgress);
        await capture(mobile, start, 40, 'tecnico-conferir-envios', ['#btn-sync-now', '#last-sync-time', '#online-status-indicator'], 'Ao recuperar internet, sincronize e confira o indicador e as pendências.', '#btn-sync-now');
        const finish = 'finalizar-tarefa-e-sincronizar';
        await tab(mobile, 'checklist');
        await capture(mobile, finish, 10, 'tecnico-revisar-checklist', ['#tab-panel-checklist'], 'Antes de finalizar, revise checklist, anexos e ocorrências.');
        await tab(mobile, 'ocorrencias');
        await tab(mobile, 'assinatura');
        await mobile.locator('#sig-customer-name').fill('Cliente Demonstração');
        await mobile.locator('#sig-notes').fill('Demonstração: inspeção realizada e funcionamento conferido. Nenhum pagamento recebido.');
        await capture(mobile, finish, 20, 'tecnico-encerramento', ['#sig-toggle-complete', '#sig-customer-name', '#sig-notes'], 'Na aba Concluir, informe quem recebeu e o relatório; assinatura é opcional.', '#sig-customer-name');
        assert.equal(await mobile.evaluate(() => OfflineApp.state.payment.method), null);
        await capture(mobile, finish, 30, 'tecnico-sem-recebimento', ['#sig-payment-section'], 'Sem pagamento, mantenha o método desmarcado. Não registre promessa de pagamento.');
        await capture(mobile, finish, 40, 'tecnico-confirmar-finalizacao', ['#sig-btn-confirm'], 'Revise antes de CONFIRMAR E FINALIZAR; depois sincronize. Captura antes da confirmação.');
        // Deliberately do NOT confirm finalization or any receipt. All earlier text
        // syncs went to the real isolated Django API, not fabricated responses.
        assert.equal(await mobile.evaluate(() => OfflineApp.state.payment.method), null);
        await worker.ctx.close();
        assert.deepEqual(errors, [], 'Unexpected app JavaScript errors');
        fs.writeFileSync(path.join(fixture.output, 'manifest.json'), JSON.stringify(manifest, null, 2));
        console.log(JSON.stringify({ captures: manifest.length, routes: [...routes], payments: 'not recorded', finalization: 'pre-confirmation only', javascriptErrors: errors }));
    } catch (error) {
        if (activePage && !activePage.isClosed()) console.error('Visible screen:', (await activePage.locator('body').innerText()).slice(0, 6500));
        console.error('Page errors:', errors);
        throw error;
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
