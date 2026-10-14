const { test, expect } = require('@playwright/test');
const path = require('path');

test('campo único permite expandir, buscar e selecionar uma subcategoria', async ({ page }) => {
  await page.setContent(`
    <label for="category">Categoria</label>
    <select id="category" name="category" data-category-picker data-category-placeholder="Sem categoria">
      <option value="">Sem categoria</option>
      <option value="1" data-category-name="Operacional" data-parent-id="">Operacional</option>
      <option value="2" data-category-name="Transporte" data-parent-id="1">Operacional / Transporte</option>
      <option value="3" data-category-name="Material" data-parent-id="1">Operacional / Material</option>
      <option value="4" data-category-name="Administrativo" data-parent-id="">Administrativo</option>
    </select>
    <label for="filter-category">Filtro</label>
    <select id="filter-category" name="category" data-category-picker data-category-placeholder="Todas categorias">
      <option value="">Todas categorias</option>
      <option value="1" data-category-name="Operacional" data-parent-id="">Operacional</option>
      <option value="2" data-category-name="Transporte" data-parent-id="1">Operacional / Transporte</option>
    </select>
  `);
  await page.addStyleTag({ path: path.resolve(__dirname, '../../static/css/financial-category-picker.css') });
  await page.addScriptTag({ path: path.resolve(__dirname, '../../static/js/financial-category-picker.js') });

  const trigger = page.locator('#category-picker');
  await trigger.click();
  await page.getByRole('button', { name: 'Expandir Operacional' }).click();
  await page.getByRole('button', { name: 'Transporte' }).click();
  await expect(page.locator('#category')).toHaveValue('2');
  await expect(trigger).toContainText('Operacional / Transporte');

  await trigger.click();
  await page.getByRole('searchbox', { name: 'Buscar categoria' }).fill('mater');
  await expect(page.getByRole('button', { name: 'Material' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Transporte' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Material' }).click();
  await expect(page.locator('#category')).toHaveValue('3');

  await trigger.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('searchbox', { name: 'Buscar categoria' })).toBeFocused();
  await page.keyboard.type('admin');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('#category')).toHaveValue('4');

  const filterTrigger = page.locator('#filter-category-picker');
  await filterTrigger.click();
  await page.getByRole('button', { name: 'Operacional', exact: true }).click();
  await expect(page.locator('#filter-category')).toHaveValue('1');
  await filterTrigger.click();
  await page.getByRole('button', { name: 'Todas categorias' }).click();
  await expect(page.locator('#filter-category')).toHaveValue('');
});
