const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ 
    headless: false,
    slowMo: 500 // Slow down para visualizar melhor
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    console.log('=== TESTE DE FLUXO: USUÁRIO COLABORADOR ===\n');
    
    // 1. LOGIN
    console.log('📋 Passo 1: Acessando página de login...');
    await page.goto('http://localhost:8000/accounts/login');
    await page.waitForLoadState('networkidle');
    
    console.log('📋 Passo 2: Fazendo login como colaborador...');
    await page.fill('#id_username', 'colaborador');
    await page.fill('#id_password', 'colaborador123');
    await page.click('button[type="submit"]');
    await page.waitForLoadState('networkidle');
    
    console.log('✅ Login realizado! URL:', page.url());
    
    // 2. NAVEGAÇÃO NO DASHBOARD
    console.log('\n📋 Passo 3: Verificando dashboard...');
    await page.waitForTimeout(1000);
    
    // Fechar banner de notificação se existir
    const closeBanner = await page.$('#push-permission-banner button, [id*="banner"] button[aria-label*="fechar"], [id*="banner"] button:has-text("Não")');
    if (closeBanner) {
      await closeBanner.click();
      console.log('✅ Banner de notificação fechado');
      await page.waitForTimeout(500);
    }
    
    // Verificar título da página
    const title = await page.title();
    console.log('📄 Título da página:', title);
    
    // Capturar screenshot do dashboard
    await page.screenshot({ path: 'test-screenshots/01-dashboard.png', fullPage: true });
    console.log('📸 Screenshot salvo: 01-dashboard.png');
    
    // 3. TENTAR ACESSAR ORDENS DE SERVIÇO
    console.log('\n📋 Passo 4: Tentando acessar Ordens de Serviço...');
    
    // Procurar por links/botões relacionados a OS
    const osLinks = await page.$$('a[href*="order"], a[href*="servic"]');
    console.log(`🔍 Encontrados ${osLinks.length} links relacionados a OS`);
    
    if (osLinks.length > 0) {
      await osLinks[0].click();
      await page.waitForLoadState('networkidle');
      console.log('✅ Navegou para:', page.url());
      await page.screenshot({ path: 'test-screenshots/02-ordens-servico.png', fullPage: true });
      console.log('📸 Screenshot salvo: 02-ordens-servico.png');
    }
    
    // 4. VERIFICAR MENU/NAVEGAÇÃO DISPONÍVEL
    console.log('\n📋 Passo 5: Verificando menu de navegação disponível...');
    const menuItems = await page.$$('nav a, aside a, [role="navigation"] a');
    console.log(`🔍 Encontrados ${menuItems.length} itens de menu`);
    
    for (let i = 0; i < Math.min(menuItems.length, 5); i++) {
      const text = await menuItems[i].textContent();
      const href = await menuItems[i].getAttribute('href');
      console.log(`   - ${text.trim()}: ${href}`);
    }
    
    // 5. TESTAR BUSCA (se existir)
    console.log('\n📋 Passo 6: Testando funcionalidade de busca...');
    const searchInput = await page.$('input[type="search"], input[placeholder*="busca"], input[placeholder*="pesquisa"]');
    
    if (searchInput) {
      await searchInput.fill('teste');
      console.log('✅ Campo de busca encontrado e preenchido');
      await page.screenshot({ path: 'test-screenshots/03-busca.png', fullPage: true });
    } else {
      console.log('⚠️  Campo de busca não encontrado');
    }
    
    // 6. VERIFICAR PERFIL DO USUÁRIO
    console.log('\n📋 Passo 7: Acessando perfil do usuário...');
    const profileLinks = await page.$$('a[href*="profile"], a[href*="perfil"], button:has-text("perfil")');
    
    if (profileLinks.length > 0) {
      await profileLinks[0].click();
      await page.waitForLoadState('networkidle');
      console.log('✅ Perfil acessado:', page.url());
      await page.screenshot({ path: 'test-screenshots/04-perfil.png', fullPage: true });
    } else {
      console.log('⚠️  Link de perfil não encontrado');
    }
    
    // 7. TESTAR RESTRIÇÕES DE ACESSO (tentar acessar área administrativa)
    console.log('\n📋 Passo 8: Testando restrições de acesso (admin)...');
    await page.goto('http://localhost:8000/admin/');
    await page.waitForLoadState('networkidle');
    
    const currentUrl = page.url();
    if (currentUrl.includes('login')) {
      console.log('✅ Acesso ao admin bloqueado corretamente (redirecionado para login)');
    } else if (currentUrl.includes('admin')) {
      console.log('⚠️  Usuário colaborador tem acesso ao admin!');
    }
    await page.screenshot({ path: 'test-screenshots/05-admin-test.png', fullPage: true });
    
    // 8. LOGOUT
    console.log('\n📋 Passo 9: Fazendo logout...');
    await page.goto('http://localhost:8000/accounts/logout');
    await page.waitForLoadState('networkidle');
    console.log('✅ Logout realizado! URL:', page.url());
    await page.screenshot({ path: 'test-screenshots/06-logout.png', fullPage: true });
    
    console.log('\n=== TESTE CONCLUÍDO COM SUCESSO ===');
    console.log('📁 Screenshots salvos em: test-screenshots/');
    
    // Aguardar 3 segundos antes de fechar
    await page.waitForTimeout(3000);
    
  } catch (error) {
    console.error('\n❌ ERRO durante o teste:', error.message);
    await page.screenshot({ path: 'test-screenshots/error.png', fullPage: true });
    console.log('📸 Screenshot do erro salvo: error.png');
  } finally {
    await browser.close();
  }
})();
