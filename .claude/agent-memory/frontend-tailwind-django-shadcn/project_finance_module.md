---
name: project-finance-module
description: Estrutura de templates e convenções do módulo de Contas a Pagar (finance)
metadata:
  type: project
---

Módulo de Contas a Pagar localizado em `templates/services/finance/` e `templates/services/partials/`.

**Arquivos de template:**
- `expense_list.html` — lista principal com tabs (Parcelas, Recorrências, Previsão de Vencimentos), filtros, tabela desktop e lista mobile
- `cashflow.html` — fluxo de caixa com saldo de contas bancárias e projeção mensal
- `bank_accounts.html` — grid de contas bancárias com saldo inicial/atual
- `bank_account_form.html` — formulário genérico para criar/editar conta bancária
- `partials/installment_payment_modal.html` — modal HTMX de baixa de pagamento com: lista de baixas registradas, formulário de nova baixa (com Nº Doc e upload de comprovante), seção de desconto/isenção via `<details>`

**Padrões estabelecidos:**
- Modal carregado via HTMX em `<dialog id="payment-dialog">`, target `#payment-modal-body`
- Formulário de baixa usa `enctype="multipart/form-data"` para suportar upload de comprovante
- Comprovantes exibidos como links `bg-blue-50` com ícone `paperclip` na lista de baixas
- Nº Documento exibido no cabeçalho da parcela como badge `bg-slate-100`
- Tabela de parcelas tem 8 colunas: Vencimento, Fornecedor, Descrição, Parcela, Nº Doc., Valor, Status, Ações
- Banner de alerta vermelho `overdue_count`/`overdue_total` aparece acima do header quando há atrasos
- Filtros expandidos: q, status (hidden), date_from, date_to, category

**Why:** Módulo ERP com visual inspirado no Bling.

**How to apply:** Ao adicionar novas features no módulo financeiro, respeitar as convenções de nomenclatura de contexto da view (current_q, current_status, current_date_from, current_date_to, current_category, overdue_count, overdue_total) e os nomes de URL estabelecidos.
