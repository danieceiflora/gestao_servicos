const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

test.describe('Autenticação', () => {
  let loginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    await loginPage.goto();
  });

  test('deve fazer login com credenciais válidas (admin)', async ({ page }) => {
    await loginPage.loginAsAdmin();
    
    // Verificar redirecionamento para dashboard
    await expect(page).toHaveURL('/');
    await expect(page).toHaveTitle(/Dashboard/);
  });

  test('deve fazer login com credenciais válidas (colaborador)', async ({ page }) => {
    await loginPage.loginAsColaborador();
    
    await expect(page).toHaveURL('/');
    await expect(page).toHaveTitle(/Dashboard/);
  });

  test('deve mostrar erro com credenciais inválidas', async ({ page }) => {
    await loginPage.login('usuario_invalido', 'senha_errada');
    
    // Deve permanecer na página de login
    await expect(page).toHaveURL(/login/);
    
    // Verificar mensagem de erro
    const errorMessage = page.locator('.bg-red-50');
    await expect(errorMessage).toBeVisible();
    await expect(errorMessage).toContainText(/incorretos/i);
  });

  test('deve mostrar erro com campos vazios', async ({ page }) => {
    await page.click(loginPage.submitButton);
    
    // HTML5 validation impede submit
    const usernameInput = page.locator(loginPage.usernameInput);
    await expect(usernameInput).toBeFocused();
  });

  test('deve fazer logout corretamente', async ({ page }) => {
    await loginPage.loginAsAdmin();
    
    // Navegar para logout
    await page.goto('/accounts/logout');
    
    // Deve retornar para login
    await expect(page).toHaveURL(/login/);
  });
});
