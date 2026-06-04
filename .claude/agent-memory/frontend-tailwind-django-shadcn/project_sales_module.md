---
name: project-sales-module
description: Templates, padrões visuais e convenções do módulo de vendas (sale_list, sale_form, sale_return_form)
metadata:
  type: project
---

## Módulo de Vendas — Estrutura de Templates

### Arquivos principais
- `templates/services/sale_list.html` — lista paginada com KPIs, filtros e tabela
- `templates/services/sale_form.html` — formulário com 4 abas (Itens / Financeiro / Fiscal / Devoluções)
- `templates/services/sale_return_form.html` — formulário de devolução

### Convenções visuais estabelecidas

**Cabeçalho de página** — faixa `bg-slate-900 text-white` com título, subtitle e botões de ação (Exportar CSV + Nova Venda).

**KPI Cards** — grid 2/4 colunas, `bg-white rounded-xl border border-slate-200 shadow-sm p-5`, ícone em box colorida 44x44, valor em `text-xl font-black text-slate-900`.

**Badges de status** (Sale.Status):
- FINALIZADA → `bg-green-100 text-green-800`
- CANCELADO → `bg-red-100 text-red-800`
- RASCUNHO → `bg-amber-100 text-amber-800`
- EM_ANDAMENTO → `bg-blue-100 text-blue-800`
- ATENDIDO → `bg-teal-100 text-teal-800`
- PRONTO → `bg-indigo-100 text-indigo-800`
- RECEBIDO → `bg-emerald-100 text-emerald-800`
- VENDA_AGENCIADA → `bg-violet-100 text-violet-800`

**Tabela** — `thead` com `bg-slate-50`, th em `text-[10px] font-black text-slate-500 uppercase tracking-widest`, `tfoot` em `bg-slate-900 text-white` para totais.

**Paginação** — query params preservados manualmente (sem `{% querystring %}`). Links `?page=N&q=...&status=...&date_from=...&date_to=...&seller=...`.

### sale_form.html — estrutura de abas

Painel fixo `fixed inset-0 top-16 bg-white flex flex-col overflow-hidden`. Tabs via JS `switchTab(tabName)`:
- `tab-items` — aba Itens (grid cliente 12 colunas: 5 cliente + 3 status + 2 PO + 2 prazo)
- `tab-payment` — aba Financeiro (parcelas + desconto global com toggle R$/%))
- `tab-fiscal` — aba Fiscal (fiscal + observações + comissão + endereço entrega colapsível)
- `tab-returns` — aba Devoluções (apenas `{% if is_detail %}`)

### Funcionalidades JS do sale_form

- `discountMode` — toggle R$/% para desconto por linha (botão `#discount-mode-btn`)
- `globalDiscountMode` — toggle R$/% para desconto global (botão `#global-discount-mode-btn`)
- `updateCommission()` — calcula comissão com base no total e `id_commission_rate`
- `toggleDelivery()` — seção colapsível do endereço de entrega, auto-abre se campos tiverem valor
- `switchTab(tab)` — agora inclui `#tab-returns` no querySelectorAll
- `updateTotals()` — calcula subtotal, margem por linha (verde/âmbar/vermelho), total líquido; chama `updateCommission()` no final
- `addToCart()` — propaga `data-cost` do produto para o `data-cost` da linha

### Colunas da tabela de carrinho

`# | Produto | Qtd | Unitário | Desc.[toggle] | Custo | Margem | Subtotal | Ações`

Margem colorida: >= 30% → `text-green-600`, >= 15% → `text-amber-600`, < 15% → `text-red-500`.

### Contexto de view esperado (sale_form)

`sale`, `form` (SaleForm), `formset` (SaleItemFormSet), `can_edit`, `is_detail`, `title`, `products`, `clients`, `payment_methods`, `initial_installments`, `returns` (SaleReturn queryset — apenas em detail).

### Contexto de view esperado (sale_list)

`sales` (paginated), `total_vendido`, `count_vendas`, `ticket_medio`, `count_rascunhos`, `sellers`, `all_statuses`, `q`, `status_filter`, `date_from`, `date_to`, `seller_id`.

**Why:** Módulo implementado com design Bling-ERP-inspired, precisão em IHC e acessibilidade.
**How to apply:** Qualquer nova feature do módulo de vendas deve seguir esses padrões visuais e de nomenclatura.
