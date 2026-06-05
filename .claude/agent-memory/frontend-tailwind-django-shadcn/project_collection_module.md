---
name: project-collection-module
description: Templates, modelos e URLs do módulo de Régua de Cobrança reestruturado (Sequências + Etapas)
metadata:
  type: project
---

O módulo de Régua de Cobrança foi reestruturado em 2025-06 para usar Sequências com Etapas indexadas por `occurrence`.

**Modelos principais:**
- `CollectionSequence`: régua global com `min_interval_days`, `max_occurrences`, `start_after_days_overdue`, `stop_after_days_overdue`, `is_active`
- `CollectionStep`: etapa de uma sequência com `occurrence` (int), `label`, `template_name`, `wait_days_before_next`, `effective_interval` (property = max(min_interval_days, wait_days_before_next))
- `CollectionLog`: histórico de envios por parcela (campos: `step`, `installment`, `status` SENT/FAILED, `sent_at`, `notes`)
- `CollectionInstallmentState`: rastreador por parcela (`current_occurrence`, `next_eligible_date`, `is_paused`)

**URLs:**
- `integracoes:collection_sequence_list`
- `integracoes:collection_sequence_create`
- `integracoes:collection_sequence_edit` pk=seq.pk
- `integracoes:collection_sequence_delete` pk=seq.pk
- `integracoes:collection_step_create` seq_pk=sequence.pk
- `integracoes:collection_step_edit` pk=step.pk
- `integracoes:collection_step_delete` pk=step.pk

**Templates criados:**
- `templates/integracoes/collection/sequence_list.html` — context: `sequences` (prefetch steps+logs), `recent_logs` (últimos 50)
- `templates/integracoes/collection/sequence_form.html` — context CREATE: `{}` / EDIT: `sequence`, `steps`
- `templates/integracoes/collection/step_form.html` — context: `sequence`, `templates`, `next_occurrence`, `step` (edit)

**Padrões visuais adotados:**
- Pipeline horizontal de etapas no sequence_list: bolinhas numeradas bg-slate-900, conectores linha+chevron
- Intervalo efetivo em âmbar quando `effective_interval > wait_days_before_next`
- Metadados da sequência como pills com ícones Lucide
- JS no step_form: `Math.max(min_interval_days, waitVal)` com toggle visual âmbar no `#effective_interval_display`

**HTMX endpoint de template details:**
- `integracoes:ajax_get_template_details` com params `model_name=Installment`, `step_id=<id>` (era `rule_id` no modelo antigo)

**Why:** Reestruturação do módulo de cobrança — o modelo antigo (CollectionRule) usava tipo de gatilho (BEFORE_DUE/ON_DUE/AFTER_DUE), o novo usa sequências com etapas numeradas por ocorrência para maior flexibilidade.

**How to apply:** Ao criar novas views/templates neste módulo, usar `step.occurrence` e `sequence.min_interval_days`. O campo `step_id` (não `rule_id`) é o param HTMX para templates.
