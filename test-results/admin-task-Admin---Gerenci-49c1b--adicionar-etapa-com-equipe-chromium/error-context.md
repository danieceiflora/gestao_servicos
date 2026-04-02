# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: admin-task.spec.js >> Admin - Gerenciamento de Etapas >> Admin deve conseguir adicionar etapa com equipe
- Location: tests\e2e\admin-task.spec.js:15:5

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first()

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - banner [ref=e2]:
    - generic [ref=e3]:
      - generic [ref=e4]:
        - img [ref=e6]
        - generic [ref=e9]: Gestão de Serviços
      - navigation [ref=e10]:
        - link "Dashboard" [ref=e11] [cursor=pointer]:
          - /url: /
        - link "Clientes" [ref=e12] [cursor=pointer]:
          - /url: /clients/
        - link "Equipe" [ref=e13] [cursor=pointer]:
          - /url: /professionals/
        - link "Agenda" [ref=e14] [cursor=pointer]:
          - /url: /orders/calendar/
        - link "Ordens" [ref=e15] [cursor=pointer]:
          - /url: /orders/
        - generic [ref=e16]:
          - generic [ref=e17]:
            - paragraph [ref=e18]: admin
            - paragraph [ref=e19]: Colaborador
          - button "Sair" [ref=e21]:
            - img [ref=e22]
  - main [ref=e25]:
    - generic [ref=e26]:
      - generic [ref=e27]:
        - generic [ref=e28]:
          - heading "Ordens de Serviço" [level=2] [ref=e29]
          - paragraph [ref=e30]: Acompanhe o ciclo de vida dos serviços.
        - generic [ref=e31]:
          - generic [ref=e32]:
            - img [ref=e33]
            - textbox "Buscar OS, cliente, endereço..." [ref=e36]
          - link "Novo Agendamento" [ref=e37] [cursor=pointer]:
            - /url: /orders/new/
            - img [ref=e38]
            - text: Novo Agendamento
      - table [ref=e42]:
        - rowgroup [ref=e43]:
          - row "OS ID Cliente / Imóvel Status Ações" [ref=e44]:
            - columnheader "OS ID" [ref=e45]
            - columnheader "Cliente / Imóvel" [ref=e46]
            - columnheader "Status" [ref=e47]
            - columnheader "Ações" [ref=e48]
        - rowgroup [ref=e49]:
          - row "#93dc7d69 daniel de sousa Rua T 49, 499 Aguardando Pagamento" [ref=e50]:
            - cell "#93dc7d69" [ref=e51]
            - cell "daniel de sousa Rua T 49, 499" [ref=e52]:
              - generic [ref=e53]:
                - generic [ref=e54]:
                  - generic [ref=e55]: daniel de sousa
                  - generic [ref=e56]: Rua T 49, 499
                - button "Abrir no GPS" [ref=e57] [cursor=pointer]:
                  - img [ref=e58]
            - cell "Aguardando Pagamento" [ref=e60]:
              - generic [ref=e61]: Aguardando Pagamento
            - cell [ref=e62]:
              - generic [ref=e63]:
                - link [ref=e64] [cursor=pointer]:
                  - /url: /orders/93dc7d69-1e47-4763-8e8c-30aaf9f87b7e/
                  - img [ref=e65]
                - link "Editar OS" [ref=e68] [cursor=pointer]:
                  - /url: /orders/93dc7d69-1e47-4763-8e8c-30aaf9f87b7e/edit/
                  - img [ref=e69]
          - row "#bf28cc6a cei curso especial de ingles Rua T 49, 499 Aguardando Pagamento" [ref=e72]:
            - cell "#bf28cc6a" [ref=e73]
            - cell "cei curso especial de ingles Rua T 49, 499" [ref=e74]:
              - generic [ref=e75]:
                - generic [ref=e76]:
                  - generic [ref=e77]: cei curso especial de ingles
                  - generic [ref=e78]: Rua T 49, 499
                - button "Abrir no GPS" [ref=e79] [cursor=pointer]:
                  - img [ref=e80]
            - cell "Aguardando Pagamento" [ref=e82]:
              - generic [ref=e83]: Aguardando Pagamento
            - cell [ref=e84]:
              - generic [ref=e85]:
                - link [ref=e86] [cursor=pointer]:
                  - /url: /orders/bf28cc6a-d611-4c5b-bb09-eee060963dbc/
                  - img [ref=e87]
                - link "Editar OS" [ref=e90] [cursor=pointer]:
                  - /url: /orders/bf28cc6a-d611-4c5b-bb09-eee060963dbc/edit/
                  - img [ref=e91]
          - row "#809a0183 cei curso especial de ingles Rua T 49, 499 Orçamento Realizado - Aguardando Aprovação" [ref=e94]:
            - cell "#809a0183" [ref=e95]
            - cell "cei curso especial de ingles Rua T 49, 499" [ref=e96]:
              - generic [ref=e97]:
                - generic [ref=e98]:
                  - generic [ref=e99]: cei curso especial de ingles
                  - generic [ref=e100]: Rua T 49, 499
                - button "Abrir no GPS" [ref=e101] [cursor=pointer]:
                  - img [ref=e102]
            - cell "Orçamento Realizado - Aguardando Aprovação" [ref=e104]:
              - generic [ref=e105]: Orçamento Realizado - Aguardando Aprovação
            - cell [ref=e106]:
              - generic [ref=e107]:
                - link [ref=e108] [cursor=pointer]:
                  - /url: /orders/809a0183-d91f-471d-b0ce-f46d1e45aaf5/
                  - img [ref=e109]
                - link "Editar OS" [ref=e112] [cursor=pointer]:
                  - /url: /orders/809a0183-d91f-471d-b0ce-f46d1e45aaf5/edit/
                  - img [ref=e113]
          - row "#bd7e8db6 daniel de sousa Rua T 49, 499 Finalizado" [ref=e116]:
            - cell "#bd7e8db6" [ref=e117]
            - cell "daniel de sousa Rua T 49, 499" [ref=e118]:
              - generic [ref=e119]:
                - generic [ref=e120]:
                  - generic [ref=e121]: daniel de sousa
                  - generic [ref=e122]: Rua T 49, 499
                - button "Abrir no GPS" [ref=e123] [cursor=pointer]:
                  - img [ref=e124]
            - cell "Finalizado" [ref=e126]:
              - generic [ref=e127]: Finalizado
            - cell [ref=e128]:
              - link [ref=e130] [cursor=pointer]:
                - /url: /orders/bd7e8db6-bdad-414f-86dc-802a37beffa8/
                - img [ref=e131]
```

# Test source

```ts
  1   | const { test, expect } = require('@playwright/test');
  2   | const { LoginPage } = require('../pages/LoginPage');
  3   | 
  4   | test.describe('Admin - Gerenciamento de Etapas', () => {
  5   |     test.beforeEach(async ({ page }) => {
  6   |         // Login como admin
  7   |         const loginPage = new LoginPage(page);
  8   |         await loginPage.goto();
  9   |         await loginPage.loginAsAdmin();
  10  |         
  11  |         // Aguardar redirecionamento após login
  12  |         await page.waitForLoadState('networkidle');
  13  |     });
  14  | 
  15  |     test('Admin deve conseguir adicionar etapa com equipe', async ({ page }) => {
  16  |         // Navegar para lista de ordens de serviço
  17  |         await page.goto('/orders/');
  18  |         await page.waitForLoadState('networkidle');
  19  |         
  20  |         // Verificar se há ordens na tabela (desktop view)
  21  |         const tableRows = page.locator('tbody tr');
  22  |         const rowCount = await tableRows.count();
  23  |         
  24  |         if (rowCount === 0) {
  25  |             console.log('⚠️  Nenhuma OS encontrada para teste.');
  26  |             test.skip();
  27  |             return;
  28  |         }
  29  |         
  30  |         // Clicar no link "Ver Detalhes" da primeira OS
  31  |         const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
> 32  |         await firstViewLink.click();
      |                             ^ Error: locator.click: Test timeout of 30000ms exceeded.
  33  |         await page.waitForLoadState('networkidle');
  34  |         
  35  |         // Obter ID da OS atual da URL
  36  |         const currentUrl = page.url();
  37  |         const orderId = currentUrl.match(/orders\/([a-f0-9-]+)/)?.[1];
  38  |         
  39  |         expect(orderId).toBeTruthy();
  40  |         
  41  |         // Navegar para adicionar nova etapa
  42  |         await page.goto(`/orders/${orderId}/tasks/add/`);
  43  |         await page.waitForLoadState('networkidle');
  44  |         
  45  |         // Verificar se está na página correta
  46  |         await expect(page.locator('h2')).toContainText('Adicionar Nova Etapa');
  47  |         
  48  |         // Preencher tipo de etapa
  49  |         await page.selectOption('select[name="task_type"]', 'EXECUTION');
  50  |         
  51  |         // Preencher data e hora (futuro)
  52  |         const futureDate = new Date();
  53  |         futureDate.setDate(futureDate.getDate() + 2);
  54  |         const dateStr = futureDate.toISOString().slice(0, 16);
  55  |         await page.fill('input[name="scheduled_at"]', dateStr);
  56  |         
  57  |         // Verificar se o campo de equipe está visível (Admin deve ver)
  58  |         const teamSection = page.locator('h3:has-text("Equipe Alocada")');
  59  |         await expect(teamSection).toBeVisible();
  60  |         
  61  |         // Tentar selecionar profissional (se existir algum)
  62  |         const professionalSelect = page.locator('select[name="team_members-0-professional"]');
  63  |         await expect(professionalSelect).toBeVisible();
  64  |         
  65  |         const options = await professionalSelect.locator('option').count();
  66  |         if (options > 1) {
  67  |             await professionalSelect.selectOption({ index: 1 });
  68  |             
  69  |             // Selecionar função
  70  |             const roleSelect = page.locator('select[name="team_members-0-role"]');
  71  |             const roleOptions = await roleSelect.locator('option').count();
  72  |             if (roleOptions > 1) {
  73  |                 await roleSelect.selectOption({ index: 1 });
  74  |             }
  75  |         }
  76  |         
  77  |         // Preencher observações
  78  |         await page.fill('textarea[name="notes"]', 'Etapa de teste criada pelo admin');
  79  |         
  80  |         // Submeter formulário
  81  |         await page.click('button[type="submit"]');
  82  |         
  83  |         // Verificar se voltou para detalhes da OS
  84  |         await page.waitForURL(`**/orders/${orderId}/`, { timeout: 10000 });
  85  |         
  86  |         // Verificar mensagem de sucesso
  87  |         await expect(page.locator('text=/sucesso/i')).toBeVisible({ timeout: 5000 });
  88  |     });
  89  | 
  90  |     test('Admin deve conseguir editar equipe de uma etapa existente', async ({ page }) => {
  91  |         // Navegar para lista de ordens de serviço
  92  |         await page.goto('/orders/');
  93  |         await page.waitForLoadState('networkidle');
  94  |         
  95  |         // Clicar no link "Ver Detalhes" da primeira OS
  96  |         const firstViewLink = page.locator('a[href*="/orders/"]:has-text("Ver Detalhes")').first();
  97  |         
  98  |         if (await firstViewLink.count() === 0) {
  99  |             console.log('⚠️  Nenhuma OS encontrada.');
  100 |             test.skip();
  101 |             return;
  102 |         }
  103 |         
  104 |         await firstViewLink.click();
  105 |         await page.waitForLoadState('networkidle');
  106 |         
  107 |         // Verificar se há tarefas/etapas
  108 |         const editButtons = page.locator('a[href*="/tasks/"][href*="/edit/"]');
  109 |         const editButtonCount = await editButtons.count();
  110 |         
  111 |         if (editButtonCount === 0) {
  112 |             console.log('⚠️  Nenhuma etapa encontrada para editar. Pulando teste.');
  113 |             test.skip();
  114 |             return;
  115 |         }
  116 |         
  117 |         // Clicar no botão de editar da primeira task
  118 |         await editButtons.first().click();
  119 |         await page.waitForLoadState('networkidle');
  120 |         
  121 |         // Verificar se está na página de edição
  122 |         await expect(page.locator('h2')).toContainText('Editar Etapa');
  123 |         
  124 |         // Verificar se campos de equipe estão visíveis e editáveis para Admin
  125 |         const professionalSelect = page.locator('select[name="team_members-0-professional"]');
  126 |         await expect(professionalSelect).toBeVisible();
  127 |         await expect(professionalSelect).toBeEnabled();
  128 |         
  129 |         // Tentar adicionar um novo membro
  130 |         const addMemberButton = page.locator('button:has-text("Adicionar Membro")');
  131 |         if (await addMemberButton.count() > 0) {
  132 |             await addMemberButton.click();
```