# Plano de Ação: Refatoração da Lógica de Tasks (Etapas)

Este documento detalha as mudanças necessárias em `services/views.py` e templates relacionados para consolidar a arquitetura de **Tasks** em Ordens de Serviço.

## 1. Refatoração da Execução de Tarefas
Atualmente, a execução é baseada no ID da Ordem de Serviço, o que limita o fluxo quando há múltiplas etapas (Vistoria, Orçamento, Execução, Garantia).

- [ ] **Alterar `service_order_execution`**: Mudar a assinatura para `task_execution(request, task_id)`.
- [ ] **Isolamento de Mídias**: Garantir que fotos/vídeos enviados durante a execução sejam vinculados à `Task` específica, não apenas à `ServiceOrder`.
- [ ] **Controle de Status**: Atualizar o status da `Task` (IN_PROGRESS, COMPLETED) e disparar a atualização automática da `ServiceOrder` apenas quando a última task for concluída.

## 2. Agendamento de Novas Etapas (Tasks)
Implementar a capacidade de adicionar novas etapas a uma OS existente (ex: Agendar Execução após aprovação do Orçamento).

- [ ] **Nova View `task_add(request, order_id)`**: Interface para escolher o tipo de tarefa, data e equipe para uma OS já aberta.
- [ ] **Formulário de Reuso**: Adaptar `ServiceOrderSchedulingForm` para funcionar de forma independente da criação da OS.

## 3. Edição e Cancelamento de Tasks
Permitir ajustes finos em agendamentos individuais sem afetar o histórico da OS.

- [ ] **Nova View `task_edit(request, task_id)`**: Para alterar data, hora ou equipe de uma etapa específica.
- [ ] **Nova View `task_cancel(request, task_id)`**: Para cancelar uma etapa, com opção de registrar o motivo.

## 4. Validação Robusta de Disponibilidade
Garantir integridade dos dados no backend.

- [ ] **Validação no `form_valid`**: No momento do salvamento de qualquer Task, validar novamente a disponibilidade de cada membro da equipe usando `check_professional_availability`.
- [ ] **Feedback de Conflito**: Retornar mensagens de erro claras caso ocorra um conflito de agenda no servidor.

## 5. Atualização da Interface de Detalhes (Detail View)
- [ ] **Timeline por Etapas**: O template `order_detail.html` deve exibir uma timeline clara mostrando:
    - Quem executou cada etapa.
    - Mídias vinculadas a cada etapa específica.
    - Notas e horários de início/fim por etapa.

---
**Nota:** A conclusão deste plano permitirá que a OS suporte fluxos complexos, como múltiplas visitas técnicas ou retrabalhos, mantendo o histórico organizado por etapas.
