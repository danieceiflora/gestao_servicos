# 🔄 Workflow: Código + Testes Sincronizados

## ✅ **SIM! Sempre atualize os testes junto com o código**

---

## 🎯 **Regra de Ouro**

> **"Toda mudança de código = mudança no teste correspondente"**

### **Por quê?**
- ✅ Garante que os testes continuam válidos
- ✅ Detecta bugs imediatamente
- ✅ Serve como documentação do que mudou
- ✅ Evita "testes quebrados" acumulando

---

## 📋 **Checklist: O que atualizar**

### **Quando você modificar o CÓDIGO, atualize:**

#### **1. Mudança em Template/HTML**
```html
<!-- ANTES: -->
<input name="cliente" id="id_cliente">

<!-- DEPOIS: -->
<input name="customer" id="id_customer">
```

**⚠️ Atualizar no teste:**
```javascript
// ANTES:
await page.fill('#id_cliente', 'João');

// DEPOIS:
await page.fill('#id_customer', 'João');
```

---

#### **2. Mudança em URL/Rota**
```python
# ANTES:
path('orders/', views.order_list, name='order_list')

# DEPOIS:
path('servicos/', views.order_list, name='order_list')
```

**⚠️ Atualizar no teste:**
```javascript
// ANTES:
await page.goto('/orders/');

// DEPOIS:
await page.goto('/servicos/');
```

---

#### **3. Mudança em Lógica de Negócio**
```python
# ANTES: Qualquer usuário pode criar OS
def create_order(request):
    # ...

# DEPOIS: Só ADMIN e MANAGER podem criar OS
@require_role(['ADMIN', 'MANAGER'])
def create_order(request):
    # ...
```

**⚠️ Atualizar/Adicionar teste:**
```javascript
// ADICIONAR NOVO TESTE:
test('colaborador não deve criar ordem de serviço', async ({ page }) => {
  // Login como colaborador
  await loginPage.loginAsColaborador();
  
  // Tentar criar OS
  await page.goto('/orders/new');
  
  // Deve ser bloqueado
  await expect(page.locator('.alert-danger')).toBeVisible();
});
```

---

#### **4. Mudança em Mensagens/Textos**
```python
# ANTES:
messages.success(request, 'Ordem criada com sucesso!')

# DEPOIS:
messages.success(request, 'OS criada! 🎉')
```

**⚠️ Atualizar no teste:**
```javascript
// ANTES:
await expect(page.locator('.alert-success')).toContainText('Ordem criada com sucesso!');

// DEPOIS:
await expect(page.locator('.alert-success')).toContainText('OS criada!');
```

---

#### **5. Nova Funcionalidade**
```python
# NOVO:
def approve_order(request, order_id):
    order = get_object_or_404(ServiceOrder, id=order_id)
    order.status = 'APPROVED'
    order.save()
    return redirect('order_detail', order_id=order.id)
```

**⚠️ Criar NOVO teste:**
```javascript
// tests/e2e/orders.spec.js - ADICIONAR:
test('deve aprovar ordem de serviço', async ({ page }) => {
  await loginPage.loginAsAdmin();
  
  await page.goto('/orders/1');
  await page.click('button:has-text("Aprovar")');
  
  await expect(page.locator('.badge')).toContainText('Aprovado');
});
```

---

## 🤖 **Como o Agente (Gemini CLI) deve agir**

### **Quando você pedir:**

#### **Exemplo 1: Mudança Simples**
```
Você: "Muda o ID do campo de senha para 'password_field'"
```

**Agente deve:**
1. ✅ Modificar o template HTML
2. ✅ Atualizar `tests/e2e/auth.spec.js`:
   ```javascript
   // ANTES: passwordInput = '#id_password'
   // DEPOIS: passwordInput = '#password_field'
   ```
3. ✅ Rodar `npm test` para verificar

---

#### **Exemplo 2: Nova Funcionalidade**
```
Você: "Adiciona botão de deletar OS, só para ADMIN"
```

**Agente deve:**
1. ✅ Criar view `delete_order`
2. ✅ Adicionar URL
3. ✅ Adicionar botão no template
4. ✅ **Criar novo teste** em `tests/e2e/orders.spec.js`:
   ```javascript
   test('admin deve deletar OS', async ({ page }) => { ... });
   test('colaborador não deve ver botão de deletar', async ({ page }) => { ... });
   ```
5. ✅ Rodar `npm test`

---

#### **Exemplo 3: Refatoração**
```
Você: "Renomeia 'ServiceOrder' para 'WorkOrder'"
```

**Agente deve:**
1. ✅ Renomear model, views, templates
2. ✅ Atualizar TODOS os testes que mencionam "ServiceOrder"
3. ✅ Atualizar URLs nos testes
4. ✅ Rodar `npm test` para garantir que nada quebrou

---

## 🎯 **Fluxo Ideal de Trabalho**

### **Para VOCÊ (desenvolvedor):**

```bash
# 1. Solicita mudança
"Adiciona validação de CPF no cadastro de cliente"

# 2. Agente faz mudanças no código + testes

# 3. Você verifica e roda
npm test

# 4. Se passar, comita tudo junto
git add .
git commit -m "feat: validação de CPF com testes"
```

---

### **Para o AGENTE (Gemini CLI):**

#### **Sempre que modificar código:**

```
✅ 1. Identificar arquivos de teste relacionados
✅ 2. Atualizar/criar testes correspondentes
✅ 3. Rodar `npm test` para validar
✅ 4. Reportar resultado dos testes
```

#### **Exemplo de resposta do agente:**

```
✅ Código modificado:
   - services/views.py (adicionado delete_order)
   - templates/orders/detail.html (botão deletar)
   
✅ Testes atualizados:
   - tests/e2e/orders.spec.js (2 novos testes)
   
✅ Resultado dos testes:
   - 12 testes passaram ✅
   - 0 testes falharam
   
🎉 Pronto para commit!
```

---

## ⚠️ **Exceções: Quando NÃO precisa atualizar testes**

### **❌ NÃO precisa atualizar se:**

1. **Mudança puramente estética (CSS)**
   ```css
   /* Mudar cor de botão: #000 -> #333 */
   ```
   → Não afeta funcionalidade

2. **Comentários/docstrings**
   ```python
   # Atualizar comentário explicativo
   ```
   → Não muda comportamento

3. **Logs internos**
   ```python
   logger.debug("Processing order...")  # Mudou texto do log
   ```
   → Não visível para usuário

4. **Performance/otimização (sem mudança de comportamento)**
   ```python
   # ANTES: for loop
   # DEPOIS: list comprehension (mesmo resultado)
   ```
   → Testes existentes já cobrem

---

## 📚 **Resumo Final**

### **Regra Simples:**

| **Mudança no Código** | **Ação nos Testes** |
|---|---|
| Template (IDs, classes) | ✅ Atualizar seletores |
| URLs/rotas | ✅ Atualizar navegação |
| Lógica/permissões | ✅ Adicionar novos testes |
| Mensagens | ✅ Atualizar expectations |
| Nova funcionalidade | ✅ Criar novos testes |
| Refatoração | ✅ Atualizar todos relacionados |
| CSS/estilo | ❌ Não precisa |
| Comentários | ❌ Não precisa |

---

## 🎬 **Comando Mágico**

**Depois de qualquer mudança:**

```bash
npm test
```

Se todos passarem → **✅ Pronto para commit!**  
Se algum falhar → **⚠️ Código ou teste precisa de ajuste**

---

## 💡 **Benefício Final**

> **Com testes sincronizados, você:**
> - ✅ Detecta bugs imediatamente
> - ✅ Refatora com confiança
> - ✅ Documenta mudanças automaticamente
> - ✅ Nunca quebra funcionalidades antigas

---

**TL;DR:** SIM! Sempre atualize os testes junto com o código. O agente deve fazer isso automaticamente. Execute `npm test` após cada mudança. 🚀
