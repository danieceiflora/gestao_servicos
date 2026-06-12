---
name: project-order-detail-ui
description: Padrões visuais e de layout da tela de detalhe de OS (order_detail.html) após redesign completo
metadata:
  type: project
---

Template: `templates/services/orders/order_detail.html`

**Decisões de layout consolidadas:**

- Header: `bg-white -mx-4 px-4 pt-4 pb-4 border-b border-slate-200 mb-0` — ancora o topo visualmente antes da tab bar.
- Tab bar: ícone inline ao lado do texto (`inline-flex items-center gap-2`), sem empilhamento. Borda ativa `border-slate-900`.
- Tab Resumo: layout `flex flex-col lg:flex-row gap-5` com coluna principal (flex-1) + sidebar fixa `lg:w-72 xl:w-80`. Cards condicionais (assinatura, origem/garantia) ficam na coluna principal — nunca criam buracos no grid.
- Sidebar do Resumo: fundo `bg-slate-50` para diferenciar de cards principais `bg-white`.
- Descrição do problema: borda lateral colorida `border-l-4 border-amber-400` em vez de fundo total — mais editorial, menos peso.
- Tab Financeiro: layout de duas colunas `flex flex-col lg:flex-row gap-5` — resumo de valores à esquerda, status/ações à direita. Removido `max-w-lg` centralizado.
- Checklist: card de resposta com borda `border-emerald-200 bg-emerald-50/40` quando `response.completed`, neutro quando não.
- Ocorrências: layout de `divide-y divide-slate-100` dentro do card, sem cards aninhados por ocorrência — mais leve.
- Tabelas de itens: `px-5 py-3.5` (reduzido de px-6 py-4) e `tabular-nums` em valores monetários.
- Botões de ação de item na tabela: `p-1.5` com hover colorido por contexto (`hover:bg-blue-50` para editar, `hover:bg-red-50` para deletar).

**Why:** Usuário reportou cards com espaços em branco, layout sem coesão, aba Financeiro esquecida com max-w-lg.

**How to apply:** Ao criar novas abas ou seções nesta tela, seguir o padrão de coluna principal + sidebar para conteúdo misto. Evitar `grid grid-cols-2` puro com cards condicionais.
