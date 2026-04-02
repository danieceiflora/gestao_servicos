const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

test.describe('Admin - Gerenciamento de Etapas', () => {
    test.beforeEach(async ({ page }) => {
        // Login como admin
        const loginPage = new LoginPage(page);
        await loginPage.goto();
        await loginPage.loginAsAdmin();
        
        // Aguardar redirecionamento após login
        await page.waitForLoadState('networkidle');
    });

    test('Admin deve conseguir adicionar etapa com equipe', async ({ page }) => {
        // Navegar para lista de ordens de serviço
        await page.goto('/orders/');
        await page.waitForLoadState('networkidle');
        
        // Verificar se há ordens na tabela (desktop view)
        const tableRows = page.locator('tbody tr');
        const rowCount = await tableRows.count();
        
        if (rowCount === 0) {
            console.log('⚠️  Nenhuma OS encontrada para teste.');
            test.skip();
            return;
        }
        
        // Clicar no link "Ver Detalhes" da primeira OS
        const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
        await firstViewLink.click();
        await page.waitForLoadState('networkidle');
        
        // Obter ID da OS atual da URL
        const currentUrl = page.url();
        const orderId = currentUrl.match(/orders\/([a-f0-9-]+)/)?.[1];
        
        expect(orderId).toBeTruthy();
        
        // Navegar para adicionar nova etapa
        await page.goto(`/orders/${orderId}/tasks/add/`);
        await page.waitForLoadState('networkidle');
        
        // Verificar se está na página correta
        await expect(page.locator('h2')).toContainText('Adicionar Nova Etapa');
        
        // Preencher tipo de etapa
        await page.selectOption('select[name="task_type"]', 'EXECUTION');
        
        // Preencher data e hora (futuro)
        const futureDate = new Date();
        futureDate.setDate(futureDate.getDate() + 2);
        const dateStr = futureDate.toISOString().slice(0, 16);
        await page.fill('input[name="scheduled_at"]', dateStr);
        
        // Verificar se o campo de equipe está visível (Admin deve ver)
        const teamSection = page.locator('h3:has-text("Equipe Alocada")');
        await expect(teamSection).toBeVisible();
        
        // Tentar selecionar profissional (se existir algum)
        const professionalSelect = page.locator('select[name="team_members-0-professional"]');
        await expect(professionalSelect).toBeVisible();
        
        const options = await professionalSelect.locator('option').count();
        if (options > 1) {
            await professionalSelect.selectOption({ index: 1 });
            
            // Selecionar função
            const roleSelect = page.locator('select[name="team_members-0-role"]');
            const roleOptions = await roleSelect.locator('option').count();
            if (roleOptions > 1) {
                await roleSelect.selectOption({ index: 1 });
            }
        }
        
        // Preencher observações
        await page.fill('textarea[name="notes"]', 'Etapa de teste criada pelo admin');
        
        // Submeter formulário
        await page.click('button[type="submit"]');
        
        // Verificar se voltou para detalhes da OS
        await page.waitForURL(`**/orders/${orderId}/`, { timeout: 10000 });
        
        // Verificar mensagem de sucesso
        await expect(page.locator('text=/sucesso/i')).toBeVisible({ timeout: 5000 });
    });

    test('Admin deve conseguir editar equipe de uma etapa existente', async ({ page }) => {
        // Navegar para lista de ordens de serviço
        await page.goto('/orders/');
        await page.waitForLoadState('networkidle');
        
        // Clicar no link "Ver Detalhes" da primeira OS
        const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
        
        if (await firstViewLink.count() === 0) {
            console.log('⚠️  Nenhuma OS encontrada.');
            test.skip();
            return;
        }
        
        await firstViewLink.click();
        await page.waitForLoadState('networkidle');
        
        // Verificar se há tarefas/etapas
        const editButtons = page.locator('a[href*="/tasks/"][href*="/edit/"]');
        const editButtonCount = await editButtons.count();
        
        if (editButtonCount === 0) {
            console.log('⚠️  Nenhuma etapa encontrada para editar. Pulando teste.');
            test.skip();
            return;
        }
        
        // Clicar no botão de editar da primeira task
        await editButtons.first().click();
        await page.waitForLoadState('networkidle');
        
        // Verificar se está na página de edição
        await expect(page.locator('h2')).toContainText('Editar Etapa');
        
        // Verificar se campos de equipe estão visíveis e editáveis para Admin
        const professionalSelect = page.locator('select[name="team_members-0-professional"]');
        await expect(professionalSelect).toBeVisible();
        await expect(professionalSelect).toBeEnabled();
        
        // Tentar adicionar um novo membro
        const addMemberButton = page.locator('button:has-text("Adicionar Membro")');
        if (await addMemberButton.count() > 0) {
            await addMemberButton.click();
            
            // Verificar se novo campo foi adicionado
            const newProfessionalSelect = page.locator('select[name="team_members-1-professional"]');
            await expect(newProfessionalSelect).toBeVisible({ timeout: 2000 });
        }
        
        // Modificar observações
        await page.fill('textarea[name="notes"]', `Etapa editada pelo admin em ${new Date().toLocaleString('pt-BR')}`);
        
        // Salvar
        await page.click('button[type="submit"]');
        
        // Verificar redirecionamento
        await page.waitForURL('**/orders/**/');
        
        // Verificar mensagem de sucesso
        await expect(page.locator('text=/atualizada com sucesso|sucesso/i')).toBeVisible({ timeout: 5000 });
    });

    test('Admin deve ver todos os campos de gerenciamento', async ({ page }) => {
        // Navegar para lista de ordens
        await page.goto('/orders/');
        await page.waitForLoadState('networkidle');
        
        const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
        
        if (await firstViewLink.count() === 0) {
            console.log('⚠️  Nenhuma OS encontrada.');
            test.skip();
            return;
        }
        
        await firstViewLink.click();
        await page.waitForLoadState('networkidle');
        
        // Obter ID da URL
        const currentUrl = page.url();
        const orderId = currentUrl.match(/orders\/([a-f0-9-]+)/)?.[1];
        
        // Ir para adicionar etapa
        await page.goto(`/orders/${orderId}/tasks/add/`);
        await page.waitForLoadState('networkidle');
        
        // Aguardar um pouco para garantir que tudo foi renderizado
        await page.waitForTimeout(1000);
        
        // Verificar campos visíveis apenas para Admin
        await expect(page.locator('select[name="status"]')).toBeVisible();
        await expect(page.locator('input[name="is_approved"]')).toBeVisible();
        await expect(page.locator('select[name="payment_method"]')).toBeVisible();
        await expect(page.locator('input[name="value"]')).toBeVisible();
        
        // Verificar campos de equipe
        await expect(page.locator('select[name="team_members-0-professional"]')).toBeVisible();
        await expect(page.locator('select[name="team_members-0-role"]')).toBeVisible();
        
        // Verificar botão de adicionar membro
        await expect(page.locator('button:has-text("Adicionar Membro")')).toBeVisible();
        
        console.log('✅ Todos os campos de gerenciamento estão visíveis para Admin');
    });
});
