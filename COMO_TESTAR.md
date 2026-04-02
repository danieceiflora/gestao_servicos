# 🧪 Como Executar os Testes

## 📦 Instalação (já feita)
```bash
npm install -D @playwright/test
npx playwright install chromium
```

## 🚀 Comandos Principais

### **Executar TODOS os testes**
```bash
npm test
# ou
npm run test
```

### **Ver testes rodando (com browser visível)**
```bash
npm run test:headed
```

### **Modo UI Interativo (RECOMENDADO para desenvolvimento)**
```bash
npm run test:ui
```
Abre uma interface gráfica onde você pode:
- Ver todos os testes
- Rodar individualmente
- Ver passo a passo
- Inspecionar elementos

### **Debug de um teste específico**
```bash
npm run test:debug
```

### **Executar apenas testes de autenticação**
```bash
npm run test:auth
```

### **Executar apenas testes de colaborador**
```bash
npm run test:colaborador
```

### **Ver relatório HTML do último teste**
```bash
npm run test:report
```

---

## 📂 Arquivos Criados

```
gestao_servicos/
├── tests/
│   ├── e2e/
│   │   ├── auth.spec.js          ✅ Testes de login/logout
│   │   └── colaborador.spec.js   ✅ Testes de fluxo do colaborador
│   ├── pages/
│   │   └── LoginPage.js          ✅ Page Object para reutilizar código
│   ├── fixtures/                 📁 Para dados de teste
│   └── screenshots/              📁 Screenshots de falhas
├── playwright.config.js          ⚙️ Configuração central
└── TESTING_GUIDE.md              📚 Guia completo
```

---

## ⚡ Fluxo de Trabalho Recomendado

### **Durante desenvolvimento:**
```bash
# 1. Abre a UI para ver os testes em tempo real
npm run test:ui

# 2. Desenvolve a funcionalidade

# 3. Cria/atualiza o teste correspondente

# 4. Roda o teste específico na UI
```

### **Antes de fazer commit:**
```bash
# Roda todos os testes para garantir que nada quebrou
npm test
```

### **Se um teste falhar:**
```bash
# 1. Veja o relatório HTML
npm run test:report

# 2. Debug o teste específico
npm run test:debug

# 3. Veja screenshots em tests/screenshots/
```

---

## 📝 Como Criar um Novo Teste

### **1. Crie o arquivo em `tests/e2e/`**
```javascript
// tests/e2e/meu-novo-teste.spec.js
const { test, expect } = require('@playwright/test');

test.describe('Minha Funcionalidade', () => {
  test('deve fazer algo', async ({ page }) => {
    await page.goto('/');
    // seus testes aqui
  });
});
```

### **2. Execute o novo teste**
```bash
npx playwright test tests/e2e/meu-novo-teste.spec.js
```

---

## 🎯 Exemplos Práticos

### **Testar criação de Ordem de Serviço**
```javascript
test('deve criar nova ordem de serviço', async ({ page }) => {
  // Login
  await page.goto('/accounts/login');
  await page.fill('#id_username', 'admin');
  await page.fill('#id_password', 'admin');
  await page.click('button[type="submit"]');
  
  // Criar OS
  await page.click('a[href*="order/new"]');
  await page.fill('#id_title', 'Manutenção de Calhas');
  await page.selectOption('#id_status', 'OPEN');
  await page.click('button[type="submit"]');
  
  // Verificar sucesso
  await expect(page.locator('.alert-success')).toBeVisible();
});
```

### **Testar permissões**
```javascript
test('colaborador não deve editar outras OS', async ({ page }) => {
  // Login como colaborador
  await page.goto('/accounts/login');
  await page.fill('#id_username', 'colaborador');
  await page.fill('#id_password', 'colaborador123');
  await page.click('button[type="submit"]');
  
  // Tentar acessar edição de OS de outro usuário
  await page.goto('/orders/123/edit');
  
  // Deve ser bloqueado
  await expect(page.locator('.alert-danger')).toContainText(/permissão/);
});
```

---

## 🔧 Dicas

### **Esperar elementos carregarem**
```javascript
await page.waitForSelector('.my-element');
await page.waitForLoadState('networkidle');
```

### **Fechar modais/banners que atrapalham**
```javascript
const banner = await page.$('#banner-notification');
if (banner) await banner.click();
```

### **Tirar screenshots para debug**
```javascript
await page.screenshot({ path: 'debug.png', fullPage: true });
```

### **Verificar textos**
```javascript
await expect(page.locator('h1')).toContainText('Dashboard');
```

---

## 🎬 Resultado Final

✅ **Testes organizados e reutilizáveis**
✅ **Relatórios automáticos com screenshots**
✅ **Execução fácil com `npm test`**
✅ **UI interativa para desenvolvimento**

---

**Próximos Passos:**
1. Execute: `npm run test:ui`
2. Veja os testes rodando
3. Crie novos testes conforme adiciona funcionalidades
4. Rode `npm test` antes de cada commit

🎉 **Sistema de testes profissional configurado!**
