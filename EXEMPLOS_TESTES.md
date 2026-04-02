# 📝 Exemplos de Solicitações com Testes

## Exemplo 1: Mudança Simples (Campo de Formulário)

### **Sua solicitação:**
```
"Muda o label do campo de senha de 'Senha' para 'Password'"
```

### **O que o agente fará:**

#### 1️⃣ Modificar o Template
```diff
# templates/registration/login.html
- <label for="id_password">Senha</label>
+ <label for="id_password">Password</label>
```

#### 2️⃣ Atualizar Teste (se necessário)
```javascript
// tests/e2e/auth.spec.js
// Neste caso, não precisa atualizar pois testamos o ID, não o label
// Mas se tivéssemos teste checando texto:
- await expect(page.locator('label[for="id_password"]')).toHaveText('Senha');
+ await expect(page.locator('label[for="id_password"]')).toHaveText('Password');
```

#### 3️⃣ Executar Testes
```bash
npm test
```

#### 4️⃣ Reportar
```
✅ Alterações feitas:
   - templates/registration/login.html
   
✅ Testes executados:
   - 10/10 testes passaram ✅
   
🎉 Pronto para commit!
```

---

## Exemplo 2: Nova Funcionalidade (Deletar OS)

### **Sua solicitação:**
```
"Adiciona botão de deletar ordem de serviço. 
Só usuários ADMIN podem deletar. 
Deve pedir confirmação antes de deletar."
```

### **O que o agente fará:**

#### 1️⃣ Criar View
```python
# services/views.py
@login_required
@require_role(['ADMIN'])
def delete_order(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    if request.method == 'POST':
        order.delete()
        messages.success(request, 'Ordem de serviço deletada com sucesso!')
        return redirect('order_list')
    return render(request, 'orders/confirm_delete.html', {'order': order})
```

#### 2️⃣ Adicionar URL
```python
# services/urls.py
path('orders/<int:order_id>/delete/', views.delete_order, name='order_delete'),
```

#### 3️⃣ Criar Template
```html
<!-- templates/orders/confirm_delete.html -->
<h1>Confirmar exclusão</h1>
<form method="post">
  {% csrf_token %}
  <p>Tem certeza que deseja deletar a OS #{{ order.id }}?</p>
  <button type="submit" class="btn-danger">Sim, deletar</button>
  <a href="{% url 'order_detail' order.id %}">Cancelar</a>
</form>
```

#### 4️⃣ Adicionar Botão no Template
```html
<!-- templates/orders/detail.html -->
{% if user.role == 'ADMIN' %}
  <a href="{% url 'order_delete' order.id %}" class="btn-danger">Deletar OS</a>
{% endif %}
```

#### 5️⃣ **CRIAR TESTES** ⭐
```javascript
// tests/e2e/orders.spec.js (NOVO ARQUIVO)
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('../pages/LoginPage');

test.describe('Gerenciamento de Ordens', () => {
  
  test('admin deve ver botão de deletar', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsAdmin();
    
    await page.goto('/orders/1');
    
    const deleteButton = page.locator('a:has-text("Deletar OS")');
    await expect(deleteButton).toBeVisible();
  });
  
  test('colaborador NÃO deve ver botão de deletar', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsColaborador();
    
    await page.goto('/orders/1');
    
    const deleteButton = page.locator('a:has-text("Deletar OS")');
    await expect(deleteButton).not.toBeVisible();
  });
  
  test('admin deve confirmar antes de deletar', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsAdmin();
    
    await page.goto('/orders/1');
    await page.click('a:has-text("Deletar OS")');
    
    // Deve mostrar página de confirmação
    await expect(page.locator('h1')).toContainText('Confirmar exclusão');
    await expect(page.locator('button[type="submit"]')).toContainText('Sim, deletar');
  });
  
  test('admin deve deletar ordem com sucesso', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsAdmin();
    
    await page.goto('/orders/1');
    await page.click('a:has-text("Deletar OS")');
    await page.click('button:has-text("Sim, deletar")');
    
    // Deve redirecionar para lista
    await expect(page).toHaveURL(/orders/);
    await expect(page.locator('.alert-success')).toContainText('deletada com sucesso');
  });
  
  test('colaborador não deve acessar URL de deletar diretamente', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAsColaborador();
    
    // Tentar acessar URL diretamente
    await page.goto('/orders/1/delete/');
    
    // Deve ser bloqueado
    await expect(page.locator('.alert-danger')).toBeVisible();
  });
});
```

#### 6️⃣ Executar Testes
```bash
npm test
```

#### 7️⃣ Reportar
```
✅ Código criado:
   - services/views.py (função delete_order)
   - services/urls.py (nova rota)
   - templates/orders/confirm_delete.html
   - templates/orders/detail.html (botão deletar)
   
✅ Testes criados:
   - tests/e2e/orders.spec.js (5 novos testes)
   
✅ Resultado dos testes:
   - 15/15 testes passaram ✅
   
🎉 Funcionalidade completa com cobertura de testes!
```

---

## Exemplo 3: Refatoração (Mudança de Nome)

### **Sua solicitação:**
```
"Renomeia o campo 'phone' do User para 'whatsapp'"
```

### **O que o agente fará:**

#### 1️⃣ Modificar Model
```python
# services/models.py
class User(AbstractUser):
-   phone = models.CharField(max_length=20, verbose_name="Telefone/WhatsApp")
+   whatsapp = models.CharField(max_length=20, verbose_name="WhatsApp")
```

#### 2️⃣ Criar Migração
```bash
python manage.py makemigrations
python manage.py migrate
```

#### 3️⃣ Atualizar Templates
```html
<!-- templates/users/profile.html -->
- <p>Telefone: {{ user.phone }}</p>
+ <p>WhatsApp: {{ user.whatsapp }}</p>
```

#### 4️⃣ Atualizar Forms
```python
# services/forms.py
class UserForm(forms.ModelForm):
    class Meta:
        model = User
-       fields = ['username', 'email', 'phone']
+       fields = ['username', 'email', 'whatsapp']
```

#### 5️⃣ **ATUALIZAR TESTES** ⭐
```javascript
// tests/e2e/users.spec.js
test('deve cadastrar usuário com whatsapp', async ({ page }) => {
  await page.goto('/users/new');
  await page.fill('#id_username', 'novouser');
  await page.fill('#id_email', 'user@example.com');
- await page.fill('#id_phone', '67999999999');
+ await page.fill('#id_whatsapp', '67999999999');
  await page.click('button[type="submit"]');
  
  await expect(page.locator('.alert-success')).toBeVisible();
});
```

#### 6️⃣ Buscar Todas as Referências
```bash
# Buscar no código
grep -r "phone" services/ templates/

# Buscar nos testes
grep -r "phone" tests/
```

#### 7️⃣ Executar Testes
```bash
npm test
```

#### 8️⃣ Reportar
```
✅ Refatoração completa:
   - services/models.py (campo renomeado)
   - services/forms.py (field atualizado)
   - templates/users/profile.html (exibição)
   - Migração criada e aplicada
   
✅ Testes atualizados:
   - tests/e2e/users.spec.js (seletores atualizados)
   
✅ Resultado dos testes:
   - 12/12 testes passaram ✅
   
⚠️ Verificar manualmente:
   - Verificar se há referências em JavaScript
   - Checar integração com WhatsApp API
```

---

## Exemplo 4: Correção de Bug

### **Sua solicitação:**
```
"Corrige o bug: logout não está redirecionando para login"
```

### **O que o agente fará:**

#### 1️⃣ Identificar o Problema
```python
# core/urls.py
path('accounts/logout/', LogoutView.as_view(), name='logout'),
# Problema: não tem next_page definido
```

#### 2️⃣ Corrigir
```python
# core/urls.py
path('accounts/logout/', LogoutView.as_view(next_page='login'), name='logout'),
```

#### 3️⃣ **VERIFICAR SE TESTES JÁ DETECTAM O BUG** ⭐
```bash
npm test
```

Resultado:
```
❌ 2 testes falhando:
   - auth.spec.js: "deve fazer logout corretamente"
   - colaborador.spec.js: "deve poder fazer logout"
```

✅ **Bom! Os testes já pegaram o bug!**

#### 4️⃣ Executar Testes Novamente
```bash
npm test
```

#### 5️⃣ Reportar
```
✅ Bug corrigido:
   - core/urls.py (adicionado next_page='login')
   
✅ Testes agora passam:
   - 10/10 testes passaram ✅
   
🎉 Bug resolvido! Os testes confirmam que funciona.
```

---

## 📋 Checklist para o Agente

### **Toda vez que modificar código:**

- [ ] 1. Fazer as modificações solicitadas
- [ ] 2. Identificar testes relacionados em `tests/e2e/`
- [ ] 3. Atualizar/criar testes correspondentes
- [ ] 4. Executar `npm test`
- [ ] 5. Reportar:
  - Arquivos modificados
  - Testes atualizados/criados
  - Resultado dos testes
  - Status: ✅ Pronto | ⚠️ Precisa ajuste

---

## 🎯 Benefício Final

Com esse workflow, **VOCÊ** nunca mais precisa se preocupar em:
- ❌ "Será que isso quebrou alguma coisa?"
- ❌ "Esqueci de testar um caso de uso"
- ❌ "Vou testar manualmente depois"

Porque o agente já:
- ✅ Atualiza os testes automaticamente
- ✅ Roda e verifica
- ✅ Reporta se algo quebrou

**Resultado:** Código sempre testado e funcionando! 🚀
