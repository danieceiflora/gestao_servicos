const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

test.describe('Fluxo do Colaborador', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsColaborador();
    
    // Fechar banner de notificação se existir
    const closeBanner = await page.$('#push-permission-banner button');
    if (closeBanner) {
      await closeBanner.click();
    }
  });

  test('deve acessar dashboard após login', async ({ page }) => {
    await expect(page).toHaveTitle(/Dashboard/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('deve visualizar menu de navegação', async ({ page }) => {
    // Verificar existência de menu
    const menuItems = page.locator('nav a, aside a');
    const count = await menuItems.count();
    
    expect(count).toBeGreaterThan(0);
  });

  test('não deve acessar área administrativa', async ({ page }) => {
    await page.goto('/admin/');
    
    // Deve ser bloqueado e redirecionado para login do admin
    await expect(page).toHaveURL(/admin\/login/);
  });

  test('deve acessar lista de ordens de serviço', async ({ page }) => {
    // Procurar link para ordens
    const orderLink = page.locator('a[href*="order"]').first();
    
    if (await orderLink.isVisible()) {
      await orderLink.click();
      await page.waitForLoadState('networkidle');
      
      // Verificar que navegou para página de ordens
      await expect(page.url()).toContain('order');
    }
  });

  test('deve poder fazer logout', async ({ page }) => {
    await page.goto('/accounts/logout');
    
    // Deve retornar para login
    await expect(page).toHaveURL(/login/);
  });
});
