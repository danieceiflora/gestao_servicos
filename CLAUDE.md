# CLAUDE.md — Instruções do Projeto

## Autonomia de Execução

Quando uma implementação for planejada e acordada com o usuário (via conversa), prossiga com todas as fases **sem pedir confirmação a cada etapa**. Execute o plano completo e informe o progresso ao longo do caminho. Só interrompa para confirmar se encontrar uma decisão genuinamente ambígua ou destrutiva (ex: apagar dados, force-push em branch protegida).

---

## Stack do Projeto

- **Backend:** Django (Python)
- **Frontend:** Django Template Language (DTL) + Tailwind CSS + shadcn/ui patterns + HTMX
- **Banco:** SQLite (desenvolvimento) / PostgreSQL (produção)
- **App do técnico:** SPA offline-first com IndexedDB (Dexie.js) + Service Worker
- **Tarefas assíncronas:** management commands rodados por um scheduler dedicado (`integracoes/management/commands/run_scheduler.py`, via APScheduler + `django-apscheduler`, jobstore no Postgres). Roda em container próprio (`scheduler` no `docker-compose.yml`, mesmo padrão do `media_worker`). Histórico de execuções visível em `/admin/django_apscheduler/`.

---

## Comandos Úteis

```bash
python manage.py runserver          # sobe o servidor de desenvolvimento
python manage.py makemigrations     # gera migrações
python manage.py migrate            # aplica migrações
python manage.py check              # verifica erros de configuração (rodar sempre após mudanças em models)
python manage.py shell_plus         # shell interativo (se django-extensions instalado)
```

---

## Estrutura de Apps e Convenções de Arquivos

```
services/
  models.py              # todos os modelos do projeto
  urls.py                # registro de URLs
  views.py               # views gerais de OS
  views_finance.py       # views financeiras (billing, installments, pagamentos)
  views_offline.py       # API do app do técnico (bootstrap, sync push/pull, upload mídia)
  views_equipe.py        # gestão da equipe
  views_stock.py         # controle de estoque
  views_bi.py            # dashboard / Business Intelligence
  views_maintenance.py   # contratos e visitas de manutenção
  workflow.py            # disparos automáticos (Chatwoot, WhatsApp — ver nota abaixo)
  utils_media.py         # processamento de imagem/vídeo (PIL + ffmpeg)
  utils/finance.py       # create_billing_for_os() e helpers financeiros

templates/services/
  finance/               # templates financeiros
  equipe/
    offline_app.html     # app shell do técnico (SPA)
    components/          # partials do app do técnico (modais, etc.)
  partials/              # partials HTMX gerais

static/js/
  offline-app.js         # lógica da UI do app do técnico (OfflineApp)
  offline-db.js          # IndexedDB / fila de sincronização (OfflineDB)
  push-notifications.js  # gerenciamento de notificações push

integracoes/
  models.py              # SystemConfig (singleton: pix_key, pix_bank, company_name, etc.)
```

---

## Modelo de OS por Etapas — Conceito Central

Esta é a mudança mais significativa do sistema. Uma Ordem de Serviço (`ServiceOrder`) agora possui múltiplas **etapas** (`ServiceOrderTask`), cada uma representando uma fase do trabalho.

### Tipos de Etapa (`ServiceOrderTask.TaskType`)

| Tipo | Descrição | Comportamento |
|------|-----------|---------------|
| `ORCAMENTO` | Vistoria / Levantamento de orçamento | Itens são referência histórica — **nunca cobrados diretamente** quando EXECUCAO/GARANTIA existem |
| `EXECUCAO` | Execução / Instalação | Itens desta etapa são a base do faturamento e da baixa de estoque |
| `GARANTIA` | Atendimento de garantia | Prioridade máxima na lógica de status |

### Status de Etapa (`ServiceOrderTask.TaskStatus`)
`AGENDADO` → `EM_ANDAMENTO` → `CONCLUIDO` / `CANCELADO` / `NAO_EXECUTADO`

### Fluxo Típico de uma OS

```
1. OS criada → etapa ORCAMENTO agendada
2. Técnico realiza o orçamento → etapa ORCAMENTO concluída
3. Orçamento enviado ao cliente para aprovação (is_approved=False)
4. Cliente aprova → etapa EXECUCAO criada (com itens CLONADOS do ORCAMENTO)
5. Técnico executa → etapa EXECUCAO concluída
6. OS status = CONCLUIDA, estoque baixado, workflow de recibo disparado
```

### Regra Anti-Soma-Dupla (CRÍTICA)

Quando uma etapa de ORCAMENTO avança para EXECUCAO, os itens do orçamento são **clonados** para a etapa de execução. Para evitar contagem dupla:

- `ServiceOrder.total_value` **exclui itens de ORCAMENTO** quando existem etapas de EXECUCAO ou GARANTIA.
- A baixa de estoque em `update_status()` usa o **mesmo filtro** — apenas itens de EXECUCAO/GARANTIA.
- O flag `ServiceOrder.stock_lowered` evita baixas duplicadas.

```python
# Lógica em ServiceOrder.total_value e update_status():
exec_garantia_types = [ServiceOrderTask.TaskType.EXECUCAO, ServiceOrderTask.TaskType.GARANTIA]
has_exec_or_garantia = self.tasks.filter(task_type__in=exec_garantia_types).exists()
if has_exec_or_garantia:
    billable = self.items.filter(task__task_type__in=exec_garantia_types)
else:
    billable = self.items.all()  # fase de orçamento puro, usa tudo
```

### Valor de Faturamento por Etapa

`ServiceOrderTask.billing_value` → usa `task.value` se definido explicitamente; caso contrário, soma os itens da etapa (`task.items.all()`).

### Status da OS (`ServiceOrder.Status`) — derivado automaticamente via `update_status()`

| Status | Condição |
|--------|----------|
| `ORCAMENTO_AGENDADO` | Etapa ORCAMENTO com status AGENDADO |
| `ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO` | Etapa ORCAMENTO concluída, sem EXECUCAO |
| `APROVADO_AGUARDANDO_AGENDAMENTO` | Etapa EXECUCAO criada e aprovada (`is_approved=True`), não agendada |
| `AGUARDANDO_EXECUCAO` | Etapa EXECUCAO agendada ou em andamento |
| `CONCLUIDA` | Todas as etapas EXECUCAO concluídas (ou GARANTIA concluída) |
| `GARANTIA` | Etapa GARANTIA existente e não concluída |
| `CANCELADO` | OS cancelada — estoque estornado automaticamente |

`update_status()` é chamado automaticamente no `save()` de `ServiceOrderTask` e deve ser chamado manualmente após mudanças de status via API/sync.

---

## App do Técnico (Offline-First)

### Arquitetura

- **SPA** carregada em `templates/services/equipe/offline_app.html`
- **OfflineApp** (`static/js/offline-app.js`): lógica de UI, navegação por hash, tabs, assinatura, ocorrências, mídias
- **OfflineDB** (`static/js/offline-db.js`): IndexedDB via Dexie.js, fila de sincronização, bootstrap

### Fluxo de Dados

```
Bootstrap (GET /api/tecnico/bootstrap/)
  → tasks, orders, clients, properties, checklists, ocorrências, métodos de pagamento, visitas de manutenção
  → salvo no IndexedDB (Dexie)

Ação offline
  → salva no IndexedDB
  → enfileira em sync_queue ({ type, payload, status: 'pending' })

Sincronização (POST /api/tecnico/sincronizar/push/)
  → envia lote de textChanges (exceto MEDIA_UPLOAD e PROPERTY_GPS_UPDATE)
  → envia mídias uma a uma via POST /api/tecnico/etapa/{id}/upload-midia/
```

### Tipos de Sync (`sync_queue.type`)

| Tipo | Payload |
|------|---------|
| `TASK_START` | `{ task_id, started_at }` |
| `TASK_FINISH` | `{ task_id, finished_at, data: { customer_name, customer_signature, notes, payment } }` |
| `TASK_INCOMPLETE` | `{ task_id, data: { notes } }` |
| `CHECKLIST_UPDATE` | `{ task_id, data: { response_id, CONCLUIDO, text_response } }` |
| `OCCURRENCE_CREATE` | `{ task_id, data: { category, occurrence_type, description, local_occurrence_id } }` |
| `MAINTENANCE_VISIT_START` | `{ visit_id, started_at }` |
| `MAINTENANCE_VISIT_FINISH` | `{ visit_id, finished_at, notes }` |
| `MEDIA_UPLOAD` | `{ task_id, media_id, response_id, occurrence_id }` — processado separadamente |
| `PROPERTY_GPS_UPDATE` | `{ property_id, latitude, longitude }` — processado separadamente |

### Tabs da UI do Técnico

O detalhe de uma tarefa é organizado em 7 tabs (barra sticky no topo com scroll horizontal):
`Info | Itens | Checklist | Anexos | Ocorrências | Assinatura | Histórico`

- Tabs de Manutenção escondem Itens, Checklist e Histórico.
- Assinatura do cliente é **opcional** (não bloqueia finalização).
- Ocorrência com categoria `IMPEDITIVA` exibe banner vermelho em Ocorrências e Assinatura.
- O toggle Concluído/Incompleto fica na tab Assinatura.

### Tarefas de Manutenção vs OS

Visitas de manutenção são convertidas no bootstrap para tasks com `source: 'MAINTENANCE'` e `task_id: 'maint_{visit_id}'`. O JS detecta isso e enfileira `MAINTENANCE_VISIT_FINISH` em vez de `TASK_FINISH`.

---

## Modelos Financeiros

Localização: `services/models.py` (seção `# --- CONTAS A PAGAR ---`)

- `Billing` — cobrança centralizada por OS
- `Installment` — parcelas de uma cobrança
- `ServicePayment` — pagamentos legados (mantido para compatibilidade)
- `PaymentMethod` — métodos de pagamento ativos
- `create_billing_for_os()` — garante/retorna a cobrança centralizada da OS (em `utils/finance.py`)

---

## Ocorrências (`Occurrence`)

- `OccurrenceCategory`: `IMPEDITIVA`, `SOLICITACAO_MATERIAL`, `GERAL`
- `OccurrenceType`: `ATRASO`, `FALTA_MATERIAL`, `CLIENTE_AUSENTE`, `IMPEDIMENTO_LOCAL`, `ACIONAMENTO_GARANTIA`, `OUTRO`
- `OccurrenceStatus`: `REGISTRADA`, `RESOLVIDA`

Categoria `IMPEDITIVA` bloqueia o fluxo normal de conclusão no app do técnico.

---

## Manutenção Preventiva

- `MaintenanceContract` — contratos com frequência (SEMANAL, QUINZENAL, MENSAL, etc.)
- `MaintenanceVisit` — visitas geradas automaticamente no bootstrap
- Auto-geração de visitas do mês corrente ocorre em `api_tecnico_bootstrap()` para contratos ativos

---

## Módulo de Expedição / Produção (app `producao`)

Fila de trabalho físico. Uma **Ordem de Produção (OP)** nasce quando uma venda
ou uma **etapa de OS** atinge um status configurável em `/producao/configuracoes/`.

```
producao/
  models.py       # ProductionSettings (singleton), ProductionOrder, ProductionItem, ProductionEvent
  services.py     # TODO o domínio: sync_from_sale/sync_from_task, update_status, ações do operador
  signals.py      # entrada automática na fila (debounce + on_commit)
  permissions.py  # can_view / can_operate / can_manage
  views.py        # board, board_partial (polling), order_detail, settings_view
services/utils/bom.py   # explode_bom() / find_composition_cycle() — travessia da ficha técnica
templates/producao/
static/js/producao-board.js
```

### Premissa central: a OP NÃO movimenta estoque

A baixa já acontece nos caminhos de venda (`views_finance`, `views_pos`,
`pos_payments`) e de OS (`ServiceOrder.update_status`), e `Product.reduce_stock`
já consome os componentes de produtos compostos. **Produção é um painel de
trabalho, não documento de estoque.** `producao/tests_sync.py` trava isso:
nenhuma ação de produção cria `StockMovement`.

Por isso "aguardando material" é um **flag manual** do operador — o módulo não
detecta falta de saldo sozinho.

### Granularidade: uma OP por etapa de OS

Os itens da OP de OS são `task.items.filter(product__isnull=False)`. Isso
**dispensa** replicar a heurística anti-soma-dupla dos itens clonados do
orçamento, e nenhum cálculo financeiro foi tocado. Consequência: `ServiceItem`
com `task=None` (orçamento geral) nunca entra na fila.

### Status

`AGUARDANDO` → `EM_SEPARACAO` / `EM_PRODUCAO` → `PRONTO` → `ENTREGUE`.
`AGUARDANDO_MATERIAL` tem prioridade sobre todos; `ENTREGUE` e `CANCELADO` são
terminais e `update_status()` não os sobrescreve. Derivado dos itens em
`producao.services.derive_status`.

`delivery_mode`: `RETIRADA` | `TECNICO` | `ENVIO` (vendas com endereço de
entrega preenchido nascem como `ENVIO`).

### Regras invioláveis

1. **`ProductionItem.save()` NÃO recalcula o status da OP.** Toda mutação passa
   por `producao/services.py`. O anti-padrão a evitar é `ServiceItem.save()`,
   que chama `update_status()` da OS e faz 20 saves num formset de 20 itens.
2. `update_status()` nunca chama a sincronização; a sincronização chama
   `update_status()` uma vez, no final.
3. **`source_key` (`"sale_item:<pk>"`) é a chave de matching da sincronização,
   nunca a FK.** As FKs de origem são `SET_NULL` porque `views_pos._save_cart`
   apaga e recria todos os `SaleItem`, e o formset de `sale_detail` deleta de
   verdade. `UniqueConstraint(production_order, source_key)` garante
   idempotência.
4. **A sincronização manda em** `quantity`, `description`, `product`,
   `variant`. **Nunca toca** `quantity_done`, `status`, datas, `notes`.
   Reduzir a quantidade abaixo do já produzido marca `needs_review`, nunca
   trunca. Item removido da origem depois de iniciado vira `CANCELADO`, nunca
   é apagado.
5. **`RASCUNHO` não pode ser status de gatilho** — o form não o oferece.
6. Permissões dedicadas `operate_production` / `manage_production`: o público
   do painel é `COLABORADOR`, para quem `user.is_manager` é False.

### Notificações — reuso de `NotificationConfig`

`ProductionOrder` está registrado no motor existente, então as mensagens são
configuradas em Notificações Automáticas escolhendo o modelo "Ordem de Produção".
**Sem regra cadastrada, nada é enviado** — a opcionalidade é nativa.

Registrar um model novo lá exige **seis** pontos, todos hardcoded:
`MODEL_CHOICES` (`integracoes/models.py`), `CURATED_FIELDS` e o ramo de
`get_mappable_fields(only_phones=True)` (`integracoes/utils.py`),
`ajax_get_status_choices` e `status_labels` (`integracoes/views.py`), e o
disparo. O mais fácil de esquecer é `ajax_get_status_choices` — sem ele os
dropdowns de status ficam vazios e a regra é inutilizável.

**`ProductionOrder` NÃO está em `DYNAMIC_NOTIFICATION_MODELS`** e não deve ser
adicionado: o receiver genérico despacha dentro da transação (HTTP ao
Chatwoot + PDF antes do commit). O disparo é explícito em
`producao/services._dispatch_status_notification`, dentro de
`transaction.on_commit`, com **uma notificação por transição commitada** —
concluir 5 itens passa por dois status mas manda uma mensagem só.

### Tempo real: polling HTMX, sem SSE/WebSocket

`board_partial` responde **HTTP 204** quando a versão recebida bate com
`services.board_version()`. O HTMX trata 204 como "não trocar nada", então
scroll, foco e ícones ficam intactos de graça.

- `hx-trigger="every 20s[shouldPollBoard()]"` — pausa com aba oculta, modal
  aberto ou foco num campo (`static/js/producao-board.js`).
- Filtros vivem **fora** da região trocada e viajam por `hx-include`.
- **`lucide.createIcons()` depois de cada swap é obrigatório** —
  `base_root.html` só inicializa os ícones no load.
- Mutações alvejam a mesma região do polling, então não há corrida clique ×
  atualização. Botões, não drag-and-drop.
- Classes de cor de coluna vêm inteiras do Python: o Tailwind varre nomes
  literais e `bg-{{ tone }}-100` nunca seria gerado.

### Fora de escopo (decisão explícita)

App offline do técnico não recebe dados de produção; entrada de produto
acabado em estoque; regras de push configuráveis; roteiro de produção com
etapas sequenciais por produto.

---

## Integrações e Workflows

- **Chatwoot**: disparo automático de mensagens em eventos de OS (recibo de pagamento, etc.)
- **WhatsApp automático**: **DEFERIDO** — não implementar disparo automático até que o usuário configure nas regras de notificação
- `trigger_payment_receipt_workflow(service_order)` — dispara em thread separada ao concluir uma OS

### Formato de Botão CTA (URL dinâmica) no Chatwoot — CRÍTICO

O Chatwoot usa seu **próprio formato** para parâmetros de botão, diferente da Meta API nativa. Nunca usar a estrutura da Meta (`index`, `sub_type`, `parameters[]`).

**Formato correto** em `processed_params.buttons`:
```json
[
  { "type": "url", "parameter": "sufixo-dinamico-aqui" }
]
```

**Formato ERRADO** (Meta API nativa — não funciona no Chatwoot):
```json
[
  { "index": 0, "sub_type": "url", "type": "button", "parameters": [{ "type": "text", "text": "sufixo" }] }
]
```

O `parameter` deve conter **apenas o sufixo dinâmico** (ex: UUID), nunca a URL completa. O template WhatsApp já contém o prefixo estático; o Chatwoot/Meta concatena os dois. Implementação em `integracoes/chatwoot_client.py` → método `send_template`, bloco `url_suffix`.

---

## Processamento de Mídia

- Upload via `POST /api/tecnico/etapa/{id}/upload-midia/`
- Arquivo salvo em `MEDIA_PROCESSING_ROOT` como `raw_*.{ext}`
- `MediaProcessingJob` criado com `status=PENDENTE` para processamento assíncrono
- `utils_media.py` usa PIL (imagens) e ffmpeg (vídeos)
- Sempre passar filename com extensão no FormData: `formData.append('file', blob, 'upload.jpg')`

---

## Pitfalls Conhecidos

1. **Nunca usar `Occurrence.OccurrenceCategory.GENERAL`** — o atributo correto é `GERAL`. Idem `OccurrenceType.OTHER` → `OUTRO`.
2. **`task.save(update_fields=[...])` em `ServiceOrderTask`** dispara `update_status()` via `save()` do modelo — não chamar `update_status()` manualmente depois.
3. **Itens sem task associada** adicionados via `order_item_add` quando já existe etapa EXECUCAO ficam invisíveis no `total_value` — ainda sem warning implementado.
4. **`stock_lowered`** deve ser verificado antes de qualquer lógica de estoque manual para evitar duplicação.
5. **`Http404` dentro de `try/except Exception`** é capturado como 400 — preferir `.filter().first()` com checagem explícita quando dentro de blocos genéricos.
6. **`increase_stock(explode_composition=...)`** — `reduce_stock` consome os componentes de um produto `COM_COMPOSICAO`; `increase_stock` só devolve o pai, a menos que receba `explode_composition=True`. Passe True em **estorno** (reedição/cancelamento de venda, devolução com restock, cancelamento de OS) e mantenha False em **entrada** de verdade (nota de compra, ajuste manual).
7. **Composição circular** não é impedida pelo banco (`unique_together` permite `parent == component`). Toda travessia da ficha técnica usa a guarda de `services/utils/bom.py`; `ProductComposition.clean()` rejeita a aresta antes de gravar.
