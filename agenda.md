# Regras de Negócio: Gestão de Agenda e Calendário

Este documento define as diretrizes para o funcionamento do sistema de agendamento de Orçamentos e Execuções de Serviço.

---

## 1. Tipos de Eventos na Agenda

A agenda deve exibir e gerenciar dois tipos principais de eventos:

1.  **Visita Técnica (Orçamento):**
    *   **Gatilho:** Quando a OS está no status `WAITING_BUDGET` e uma data/equipe é definida.
    *   **Duração Estimada Padrão:** 1 hora (configurável).
    *   **Identificação Visual:** Cor Azul (ou ícone específico).
2.  **Execução de Serviço:**
    *   **Gatilho:** Quando a OS está no status `APPROVED_WAITING_SCHEDULE` e uma data/equipe de execução é definida.
    *   **Duração Estimada Padrão:** 4 horas (configurável).
    *   **Identificação Visual:** Cor Verde (ou ícone específico).

---

## 2. Regras de Disponibilidade do Profissional

Antes de confirmar qualquer agendamento, o sistema deve validar os seguintes critérios:

### 2.1 Grade de Horário Base
*   O agendamento deve obrigatoriamente cair dentro da janela de disponibilidade cadastrada no perfil do profissional (`ProfessionalAvailability`).

### 2.2 Regra de Intervalo Mínimo (Janela de Segurança)
*   **Buffer de 1:30h:** Para garantir tempo de deslocamento e execução, o sistema **não permite** que um profissional tenha dois agendamentos com intervalo inferior a **1 hora e 30 minutos** entre seus horários de início.
*   **Exemplo:** Se um orçamento está agendado para as 09:00, o próximo agendamento para este mesmo profissional só poderá ocorrer a partir das 10:30 (ou antes das 07:30).

### 2.3 Exclusões e Bloqueios
*   Bloqueios de Agenda (Férias, Folgas, etc) impedem qualquer agendamento no período.

---

## 3. Fluxo de Agendamento no Sistema

1.  **Seleção de Data e Hora:** O Administrador escolhe o momento do serviço.
2.  **Seleção de Equipe:** Ao selecionar um ou mais colaboradores:
    *   O sistema realiza uma checagem em tempo real (via AJAX/API) da disponibilidade de cada membro.
    *   **Alerta Visual:** Se um colaborador estiver ocupado, o sistema deve exibir um aviso: *"Técnico João já possui um Orçamento agendado para este horário"*.
3.  **Confirmação:** O agendamento só é salvo se todos os membros da equipe passarem na validação.

---

## 4. Visualização (Interface)

*   **Visão Geral (Dashboard):** Calendário mensal/semanal com todos os serviços da empresa.
*   **Visão por Profissional:** Filtro para visualizar a agenda individual de um colaborador específico.
*   **Ações Rápidas:**
    *   Clique no evento: Abre detalhes da OS.
    *   Arrastar (Drag & Drop): Altera a data/hora do serviço (dispara nova validação de conflitos).

---

## 5. Pendências Técnicas

*   [ ] Definir se haverá "tempo de deslocamento" entre um serviço e outro (Ex: intervalo obrigatório de 30 min).
*   [ ] Implementar lógica de "Duração Estimada" por tipo de serviço ou campo manual na OS.
