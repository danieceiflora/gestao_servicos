const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

const smokeRoutes = [
  '/',
  '/ordens/',
  '/clientes/',
  '/profissionais/',
  '/produtos/',
  '/vendas/',
  '/estoque/notas-entrada/',
  '/financeiro/',
  '/financeiro/contas-a-receber/',
  '/financeiro/contas-a-pagar/',
  '/financeiro/metodos-pagamento/',
  '/ocorrencias/',
  '/manutencao/contratos/',
  '/manutencao/equipamentos/',
  '/manutencao/fechamentos/',
  '/relatorios/operacional/',
  '/integracoes/fiscal/config/',
  '/integracoes/pagamentos/gateway/',
  '/integracoes/pagamentos/regras/',
];

test.describe('Layout responsivo gerencial', () => {
  test.beforeEach(async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.loginAsAdmin();
  });

  test('drawer abre, prende o foco e fecha por Escape', async ({ page }) => {
    test.skip((page.viewportSize()?.width || 0) >= 1280, 'Comportamento exclusivo do layout compacto');
    const button = page.locator('#mobile-menu-button');
    const root = page.locator('#mobile-menu');
    const drawer = page.locator('#mobile-menu-drawer');

    await expect(button).toBeVisible();
    await button.click();
    await expect(root).toHaveAttribute('aria-hidden', 'false');
    await expect(button).toHaveAttribute('aria-expanded', 'true');
    await expect(drawer).toBeVisible();
    await expect(page.locator('body')).toHaveCSS('overflow', 'hidden');

    await page.keyboard.press('Escape');
    await expect(root).toHaveAttribute('aria-hidden', 'true');
    await expect(button).toHaveAttribute('aria-expanded', 'false');
    await expect(button).toBeFocused();
  });

  test('todas as rotas principais permanecem dentro da viewport', async ({ page }) => {
    for (const route of smokeRoutes) {
      const response = await page.goto(route);
      expect(response?.status(), `status HTTP inesperado em ${route}`).toBeLessThan(400);
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#main-content')).toBeVisible();
      const layout = await page.evaluate(() => {
        const width = document.documentElement.clientWidth;
        const offenders = [...document.querySelectorAll('body *')]
          .filter(el => {
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.position === 'fixed') return false;
            const rect = el.getBoundingClientRect();
            return rect.right > width + 1 || rect.left < -1;
          })
          .slice(0, 8)
          .map(el => ({ tag: el.tagName, id: el.id, className: String(el.className).slice(0, 100), rect: el.getBoundingClientRect().toJSON() }));
        return { overflow: document.documentElement.scrollWidth - width, offenders };
      });
      expect(layout.overflow, `overflow horizontal em ${route}: ${JSON.stringify(layout.offenders)}`).toBeLessThanOrEqual(1);
    }
  });

  test('troca hamburger por navegação desktop no breakpoint de 1280px', async ({ page }) => {
    await page.setViewportSize({ width: 1279, height: 800 });
    await expect(page.locator('#mobile-header')).toBeVisible();
    await expect(page.locator('#desktop-header')).toBeHidden();

    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(page.locator('#mobile-header')).toBeHidden();
    await expect(page.locator('#desktop-header')).toBeVisible();
  });
});
