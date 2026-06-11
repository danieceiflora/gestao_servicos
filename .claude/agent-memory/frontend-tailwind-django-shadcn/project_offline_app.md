---
name: project-offline-app
description: App offline-first do técnico: arquitetura de abas, estado, SignaturePad, sync e padrões de componentes JS
metadata:
  type: project
---

O app do técnico é uma SPA offline-first baseada em IndexedDB (Dexie.js, variável `db`) com dois arquivos principais:

- Template: `templates/services/equipe/offline_app.html`
- JS: `static/js/offline-app.js`
- Modais: `templates/services/equipe/components/offline_modals.html`

## Arquitetura de abas (redesign 2026-06)

A tela de detalhe usa um template único `tpl-task-detail` com 7 abas fixas no rodapé:
`info | itens | checklist | anexos | ocorrencias | assinatura | historico`

O state do OfflineApp agora inclui:
- `detailRoot: null` — referência ao nó raiz do detalhe atual (necessário para `_refreshOccurrencesTab`)
- `activeTab: 'info'`

Métodos privados do detalhe:
- `_fillDetailHeader(root, task, client, prop)` — preenche cabeçalho sticky
- `_setupTabs(root, taskId, isMaintenance)` — esconde abas Itens/Checklist para manutenção
- `_switchTab(root, tabName)` — troca painel ativo + ativa lazy-init do SignaturePad
- `_initInfoTab`, `_initItemsTab`, `_initChecklistTab`, `_initMediaTab`, `_initOccurrencesTab`, `_initSignatureTab`, `_initHistoryTab`
- `_refreshOccurrencesTab(taskId)` — atualiza lista de ocorrências, badge vermelho e banner blocking na aba Assinatura; chamado após `confirmOccurrence`
- `_initSignaturePad(root)` — lazy-init do SignaturePad no canvas `#sig-canvas`; `_sigPadInited` controla inicialização única
- `_initPaymentGrid(methodsGrid, detailsEl)` — injeta botões de métodos de pagamento
- `_confirmFinish(taskId, panel)` — finaliza tarefa sem modal; assina inline
- `_confirmIncomplete(taskId, panel)` — registra incompleto com enqueue `TASK_INCOMPLETE`

## Fluxo manutenção

`renderMaintenanceTaskDetail` agora é apenas um stub que delega para `renderTaskDetail(container, task.id)`.
`openMaintenanceFinishModal` e `confirmMaintenanceFinish` foram removidos — manutenção usa a aba Assinatura igualmente.
O modal `modal-finish-maintenance` ainda existe no HTML de modais (para compatibilidade/legado).

## Modal removido

`modal-finish` foi removido de `offline_modals.html`. A finalização é 100% inline na aba Assinatura.

## Padrão de botão GPS no novo template

O botão Navegar usa `id="info-btn-gps"` com atributos `data-gps-lat`, `data-gps-lng`, `data-gps-address`, `data-gps-trigger="true"` (mesmo padrão do GPS modal global).

**Why:** Redesign inspirado no Opergo/Auvo para reduzir scroll e melhorar UX em campo.
**How to apply:** Ao criar novas seções no detalhe, adicionar novo painel `tab-panel-X` e botão `tab-btn` no rodapé.
