# 📑 Plano de Implementação: Financeiro Centralizado e Contas a Receber

Este documento detalha a estratégia para desacoplar o financeiro das operações (OS e Vendas), centralizando os recebimentos em uma nova estrutura de **Cobranças** e **Parcelas**.

---

## 1. Mudanças no Modelo de Dados (Backend)

### 1.1. Configurações Globais (`integracoes/models.py`)
- **Model `SystemConfig`**:
    - Adicionar `billing_default_due_days` (IntegerField, default=1): Define o prazo padrão para vencimento após a conclusão do serviço ou venda.

### 1.2. Módulo de Vendas (`services/models.py`)
- **Model `Sale`**:
    - Adicionar campo `number` (PositiveIntegerField, único, sequencial).
    - Implementar lógica no `save()` para auto-incremento (iniciando em 1000).
    - Adicionar campo `status` (DRAFT, COMPLETED, CANCELLED).

### 1.3. Novos Modelos Financeiros (`services/models.py`)
- **Model `Billing` (Cobrança)**:
    - `id`: UUID (Primary Key).
    - `number`: PositiveIntegerField (Sequencial).
    - `client`: ForeignKey para `Client`.
    - `sale`: OneToOneField para `Sale` (opcional).
    - `service_order`: OneToOneField para `ServiceOrder` (opcional).
    - `total_amount`: DecimalField (Valor bruto).
    - `discount`: DecimalField (Desconto global da cobrança).
    - `status`: CharChoices (PENDING, PARTIAL, PAID, CANCELLED).
    - `created_at`, `updated_at`.

- **Model `Installment` (Parcela)**:
    - `billing`: ForeignKey para `Billing`.
    - `installment_number`: PositiveIntegerField (1, 2, 3...).
    - `due_date`: DateField.
    - `amount`: DecimalField.
    - `payment_method`: ForeignKey para `PaymentMethod` (opcional no rascunho, obrigatório na baixa).
    - `status`: CharChoices (PENDING, PAID, OVERDUE).
    - `paid_at`: DateTimeField (Data da baixa).
    - `notes`: TextField.

---

## 2. Fluxo de Negócio & Lógica

### 2.1. Ordem de Serviço (OS)
- Ao atingir o status `FINISHED`, o sistema gera automaticamente um registro em `Billing` vinculado àquela OS.
- A data de vencimento da primeira (ou única) parcela será `hoje + SystemConfig.billing_default_due_days`.

### 2.2. Pedido de Venda
- A tela `sale_form.html` será reformulada.
- O usuário poderá definir a "Condição de Pagamento" (ex: 1x, 3x).
- Ao salvar a venda, o sistema gera a `Billing` e as `Installment` correspondentes.

---

## 3. Experiência do Usuário (Frontend Web)

### 3.1. Formulário de Venda (`sale_form.html`)
- **Interface em Abas**:
    - **Aba 1: Itens/Carrinho**: Foco na seleção de produtos e quantidades (já existente, mas agora isolada).
    - **Aba 2: Pagamento/Financeiro**: Onde ficarão as configurações de cobrança.
- **Campos da Aba Pagamento**:
    - Condição de Pagamento (Dropdown: À vista, 1x, 2x, 3x...).
    - Dias para Vencimento (Input numérico, inicia com o valor global).
    - **Botão "Gerar Cobrança"**: Ao clicar, o sistema calcula e projeta as parcelas em uma tabela editável.
- **Tabela de Parcelas (Resultante)**:
    - Colunas: Parcela, Vencimento, Valor, Forma de Pagto, Observação.
    - O usuário pode alterar manualmente o valor de uma parcela ou sua data antes de finalizar.
- **Ação Final**: O botão "Finalizar Venda" agora valida se a cobrança foi gerada e se os valores batem.

### 3.2. Painel Financeiro (Novo)
- Criar listagem de "Contas a Receber" filtrável por Status, Cliente e Data.
- Opção de dar "Baixa" manual em parcelas.

---

## 4. Estratégia Offline (Técnico)

### 4.1. IndexedDB (`offline-app.js`)
- Adicionar stores: `billings` e `installments`.
- Ao finalizar uma OS, o JS gera um registro em `billings` e abre a interface de "Registrar Recebimento".

### 4.2. Interface do Técnico (`offline_app.html`)
- Na aba de **"Concluídas"**, cada OS terá um botão "Financeiro / Receber".
- Permitir adicionar múltiplos recebimentos (que criarão registros de `Installment` com status `PAID` localmente).

### 4.3. Sincronização
- Ao sincronizar, o sistema prioriza subir a OS e, em seguida, as Cobranças e Parcelas vinculadas.

---

## 5. Plano de Migração

1.  **Fase 1**: Criar os novos modelos e aplicar migrações.
2.  **Fase 2**: Atualizar o `Sale` para suportar `number` e `status`.
3.  **Fase 3**: Implementar a lógica de geração de cobranças no Backend (Signals/Views).
4.  **Fase 4**: Refatorar o `sale_form.html` para o novo fluxo de parcelamento.
5.  **Fase 5**: Atualizar o App Offline do Técnico para suportar o novo fluxo de recebimento pós-finalização.
6.  **Fase 6**: (Futuro) Migrar dados legados e remover colunas antigas (se necessário).

---

**Aprovação:**
- [ ] Usuário revisou e aprovou a estratégia de numeração de vendas.
- [ ] Usuário revisou e aprovou a separação em Cobranças/Parcelas.
