const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

test.describe('Debug - Visualizar Formset de Equipe', () => {
    test('Capturar screenshot da página de adicionar etapa', async ({ page }) => {
        // Login como admin
        const loginPage = new LoginPage(page);
        await loginPage.goto();
        await loginPage.loginAsAdmin();
        await page.waitForLoadState('networkidle');
        
        // Navegar para ordens
        await page.goto('/orders/');
        await page.waitForLoadState('networkidle');
        
        // Clicar na primeira OS
        const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
        if (await firstViewLink.count() > 0) {
            await firstViewLink.click();
            await page.waitForLoadState('networkidle');
            
            // Obter ID
            const currentUrl = page.url();
            const orderId = currentUrl.match(/orders\/([a-f0-9-]+)/)?.[1];
            
            if (orderId) {
                // Navegar para adicionar etapa
                await page.goto(`/orders/${orderId}/tasks/add/`);
                await page.waitForLoadState('networkidle');
                
                // Capturar screenshot
                await page.screenshot({ path: 'test-screenshots/task-add-page.png', fullPage: true });
                
                // Verificar se o formset está no DOM
                const formset = page.locator('#team-formset');
                await expect(formset).toBeVisible();
                
                // Contar quantos team-form-item existem
                const teamForms = page.locator('.team-form-item');
                const count = await teamForms.count();
                console.log(`✅ Encontrado ${count} formulário(s) de equipe no DOM`);
                
                if (count > 0) {
                    // Verificar o primeiro formulário
                    const firstForm = teamForms.first();
                    await expect(firstForm).toBeVisible();
                    
                    // Verificar select de professional
                    const professionalSelect = firstForm.locator('select[name*="professional"]');
                    const professionalVisible = await professionalSelect.isVisible();
                    console.log(`Professional select visível: ${professionalVisible}`);
                    
                    if (professionalVisible) {
                        const options = await professionalSelect.locator('option').count();
                        console.log(`Opções no select de professional: ${options}`);
                        
                        // Listar as opções
                        const optionsText = await professionalSelect.locator('option').allTextContents();
                        console.log('Opções:', optionsText);
                    }
                    
                    // Verificar select de role
                    const roleSelect = firstForm.locator('select[name*="role"]');
                    const roleVisible = await roleSelect.isVisible();
                    console.log(`Role select visível: ${roleVisible}`);
                    
                    if (roleVisible) {
                        const optionsRole = await roleSelect.locator('option').count();
                        console.log(`Opções no select de role: ${optionsRole}`);
                        
                        const optionsRoleText = await roleSelect.locator('option').allTextContents();
                        console.log('Opções de função:', optionsRoleText);
                    }
                }
            }
        }
    });
});
