# 🧪 Guia de Testes - Gestão de Serviços

## 📋 Estratégia de Testes

### 1️⃣ **Estrutura Recomendada**

```
tests/
├── e2e/                    # Testes end-to-end (Playwright)
│   ├── auth.spec.js        # Testes de autenticação
│   ├── colaborador.spec.js # Fluxos de colaborador
│   ├── admin.spec.js       # Fluxos de administrador
│   ├── orders.spec.js      # CRUD de Ordens de Serviço
│   └── clients.spec.js     # CRUD de Clientes
│
├── integration/            # Testes de integração (Django)
│   ├── test_views.py
│   ├── test_models.py
│   └── test_forms.py
│
├── unit/                   # Testes unitários
│   ├── test_utils.py
│   └── test_validators.py
│
├── fixtures/               # Dados de teste
│   └── test_data.json
│
├── screenshots/            # Screenshots de falhas
│
└── playwright.config.js    # Configuração central
```

---

## 🎯 **Tipos de Teste por Situação**

### **Testes E2E (End-to-End) - Playwright**
✅ **Quando usar:**
- Fluxos críticos do usuário
- Integrações entre múltiplas páginas
- Validar permissões e acesso
- Testar funcionalidades PWA

❌ **Quando NÃO usar:**
- Validações simples de formulário
- Lógica de negócio isolada
- Performance (são mais lentos)

### **Testes de Integração - Django**
✅ **Quando usar:**
- Testar views + models + forms juntos
- Validar requisições HTTP
- Testar autenticação/autorização
- Integração com banco de dados

### **Testes Unitários - Django**
✅ **Quando usar:**
- Funções utilitárias (`utils.py`)
- Métodos de models
- Validadores customizados
- Lógica de negócio isolada

---

## 🚀 **Abordagens de Execução**

### **Opção 1: Testes Isolados (Seu Método Atual)**
```bash
# Executar um teste específico
node tests/e2e/colaborador.spec.js

# Executar todos manualmente
node tests/e2e/auth.spec.js
node tests/e2e/orders.spec.js
```

**Prós:** Simples, rápido para testar uma funcionalidade
**Contras:** Trabalhoso, sem relatórios consolidados

---

### **Opção 2: Test Runner Automático (RECOMENDADO)**

#### **Playwright Test Runner** ⭐
```bash
# Executar todos os testes E2E
npx playwright test

# Executar em modo watch (re-executa ao salvar)
npx playwright test --watch

# Executar só os testes que falharam
npx playwright test --last-failed

# Gerar relatório HTML
npx playwright test --reporter=html
```

#### **Django Test Runner**
```bash
# Todos os testes Django
python manage.py test

# Testes específicos
python manage.py test services.tests.test_views

# Com coverage
coverage run --source='.' manage.py test
coverage report
```

---

### **Opção 3: CI/CD Automático (IDEAL para produção)**
- Roda todos os testes automaticamente no push/PR
- GitHub Actions, GitLab CI, etc.
- Impede merge se houver falhas

---

## 📝 **Estrutura de Teste Recomendada (Playwright)**

```javascript
// tests/e2e/colaborador.spec.js
const { test, expect } = require('@playwright/test');

// Configuração antes de cada teste
test.beforeEach(async ({ page }) => {
  await page.goto('http://localhost:8000/accounts/login');
  await page.fill('#id_username', 'colaborador');
  await page.fill('#id_password', 'colaborador123');
  await page.click('button[type="submit"]');
  await page.waitForURL('http://localhost:8000/');
});

test.describe('Fluxo do Colaborador', () => {
  test('deve acessar dashboard após login', async ({ page }) => {
    await expect(page).toHaveTitle(/Dashboard/);
  });

  test('deve visualizar lista de ordens', async ({ page }) => {
    await page.click('a[href*="orders"]');
    await expect(page.locator('h1')).toContainText('Ordens');
  });

  test('não deve acessar área administrativa', async ({ page }) => {
    await page.goto('http://localhost:8000/admin/');
    await expect(page).toHaveURL(/login/);
  });
});
```

---

## ⚙️ **Configuração Playwright (playwright.config.js)**

```javascript
module.exports = {
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 2, // Retry em caso de falha
  use: {
    baseURL: 'http://localhost:8000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chrome',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    command: 'python manage.py runserver',
    port: 8000,
    timeout: 120000,
    reuseExistingServer: true,
  },
};
```

---

## 🎬 **Workflow Recomendado**

### **Durante Desenvolvimento:**
1. Escreve código
2. Roda teste específico: `npx playwright test colaborador.spec.js`
3. Se passar, commita

### **Antes de Push:**
1. Roda todos os testes: `npx playwright test`
2. Verifica se todos passam
3. Faz push

### **CI/CD (Automático):**
1. GitHub Action roda todos os testes
2. Se falhar, impede merge
3. Se passar, pode fazer deploy

---

## 📊 **Quando Criar Novos Testes?**

### **Sempre que:**
✅ Adicionar nova funcionalidade crítica
✅ Corrigir um bug (teste de regressão)
✅ Criar nova permissão/role
✅ Modificar fluxo de autenticação

### **Não precisa testar:**
❌ Código third-party (Django, Tailwind)
❌ Getters/setters simples
❌ Templates estáticos

---

## 🛠️ **Ferramentas Complementares**

### **Page Object Model (POM)** - Reutilização
```javascript
// tests/pages/LoginPage.js
class LoginPage {
  constructor(page) {
    this.page = page;
  }

  async login(username, password) {
    await this.page.fill('#id_username', username);
    await this.page.fill('#id_password', password);
    await this.page.click('button[type="submit"]');
  }
}

// Uso em qualquer teste
const loginPage = new LoginPage(page);
await loginPage.login('colaborador', 'colaborador123');
```

### **Fixtures/Factories** - Dados de Teste
```python
# tests/factories.py
from services.models import User

class UserFactory:
    @staticmethod
    def create_colaborador():
        return User.objects.create_user(
            username='test_colab',
            password='test123',
            role='COLLABORATOR'
        )
```

---

## 🎯 **Recomendação Final**

### Para este projeto (Gestão de Serviços):

1. **Imediato (Básico):**
   - 5-6 testes E2E críticos (login, CRUD de OS, permissões)
   - Executar manualmente antes de cada release

2. **Curto Prazo (Intermediário):**
   - Configurar Playwright Test Runner
   - Adicionar testes de integração Django
   - Rodar `npx playwright test` antes de push

3. **Longo Prazo (Avançado):**
   - CI/CD com GitHub Actions
   - Testes automáticos em cada PR
   - Coverage mínimo de 70%

---

## 📚 **Recursos**

- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Django Testing](https://docs.djangoproject.com/en/5.2/topics/testing/)
- [Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)

---

**TL;DR:** Use Playwright Test Runner (`npx playwright test`) para rodar todos os testes de uma vez. Crie um arquivo por funcionalidade (não por fluxo completo), organize em pastas, e rode antes de cada push. 🚀
