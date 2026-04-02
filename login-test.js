const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  
  try {
    console.log('Acessando página de login...');
    await page.goto('http://localhost:8000/accounts/login');
    
    console.log('Preenchendo credenciais...');
    await page.fill('#id_username', 'admin');
    await page.fill('#id_password', 'admin');
    
    console.log('Realizando login...');
    await page.click('button[type="submit"]');
    
    await page.waitForLoadState('networkidle');
    
    console.log('Login realizado com sucesso!');
    console.log('URL atual:', page.url());
    
    // Aguardar 3 segundos para visualizar o resultado
    await page.waitForTimeout(3000);
    
  } catch (error) {
    console.error('Erro durante o login:', error);
  } finally {
    await browser.close();
  }
})();
