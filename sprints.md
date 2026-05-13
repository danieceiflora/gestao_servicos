# Sprints de Desenvolvimento - Gestão de Serviços PWA

Acompanhamento detalhado das tarefas para execução do projeto.

---

## ✅ Sprint 1: Estrutura Base e Ambiente (CONCLUÍDA)
- [x] **1.1 Configuração Django:**
  - [x] Setup inicial do projeto e `venv`.
  - [x] Configuração de `settings.py` (Static, Media, Templates).
- [x] **1.2 Identidade Visual (Tailwind CSS):**
  - [x] Integração via `node_modules`.
  - [x] Configuração de `input.css` e `output.css`.
- [x] **1.3 PWA Basics:**
  - [x] Configuração `django-pwa`.
  - [x] Manifesto e Service Worker básico.

---

## ✅ Sprint 2: Gestão de Clientes e Imóveis (CONCLUÍDA)
- [x] **2.1 CRUD de Clientes:**
  - [x] Modelo `Client` com múltiplos telefones e e-mails.
  - [x] Listagem e Busca de Clientes.
- [x] **2.2 Gestão de Imóveis:**
  - [x] Modelo `Property` vinculado ao cliente.
  - [x] Integração com Geolocation API para capturar latitude/longitude.
  - [x] Interface de cadastro de imóveis com mapa.

---

## ✅ Sprint 3: Fluxo de Vistoria e Orçamento (CONCLUÍDA)
*Foco: O início do ciclo de serviço operacional.*

- [x] **3.1 Modelo de Ordem de Serviço:**
  - [x] Criar `ServiceOrder` (UUID, Status, Cliente, Imóvel).
  - [x] Criar `ServiceMedia` (FK para `ServiceOrder`, suporte a Imagem e Vídeo).
  - [x] Criar `ServiceItem` para composição de orçamento.
- [x] **3.2 Fluxo de Vistoria (Colaborador):**
  - [x] Interface para criar nova OS a partir de um Imóvel.
  - [x] Implementar upload múltiplo de fotos e vídeos como evidências.
- [x] **3.3 Orçamento e Precificação:**
  - [x] Campos para detalhamento técnico e valores.
  - [x] Cálculo automático de total do orçamento (JS).
  - [x] View de detalhamento da Ordem de Serviço.
- [x] **3.4 Designação de Equipe (Administrador):**
  - [x] Vincular múltiplos colaboradores a uma Ordem de Serviço.
  - [x] Definir a função específica (Técnico, Ajudante, etc) para cada colaborador na execução daquela OS.

---

## 🚀 Sprint 3.5: Gestão de Agenda Central (EM ANDAMENTO)
*Foco: O motor de horários e a visualização mestre.*

- [x] **3.5.1 Regras de Negócio:** Documentação das regras de 1:30h e conflitos (`agenda.md`).
- [x] **3.5.2 Estrutura de Dados:** Campos de agendamento em `ServiceOrder` e modelo `ProfessionalScheduleBlock`.
- [x] **3.5.3 Motor de Validação:** API de checagem de disponibilidade com regra de buffer (`utils.py`).
- [x] **3.5.4 Dashboard de Calendário:** 
    - [x] Implementar FullCalendar.js para visualização de Orçamentos e Execuções.
    - [x] Filtro por Profissional no calendário.
- [x] **3.5.5 Interface de Bloqueios:** Tela para cadastrar folgas/férias de colaboradores.

---

## ✅ Sprint 4: Gestão de Equipes e Disponibilidade (CONCLUÍDA)
*Foco: Integração do agendamento com a alocação de pessoas.*

- [x] **4.1 Cadastro de Profissionais:** CRUD de Instaladores e suas funções.
- [x] **4.2 Disponibilidade Base:** Configuração de horários de trabalho semanais.
- [x] **4.3 Designação Inteligente:** 
    - [x] Integrar avisos de conflito em tempo real na tela de designar equipe.
    - [x] Impedir salvamento de equipes em horários de conflito (Validação no Servidor).
- [x] **4.4 Agendamento Visual:** Interface visual para agendar orçamentos e execuções para colaboradores. 

---

## 🚀 Sprint 5: Execução e Finalização (EM ANDAMENTO)
*Foco: Trabalho de campo e encerramento.*

- [x] **5.1 Visão de Campo:** Interface operacional para colaboradores (sem exibição de valores).
- [x] **5.2 Evidências Finais:** Upload de mídias pós-serviço (antes/depois) e mudança de status.
- [x] **5.3 Assinatura Digital:** Captura de assinatura do cliente no encerramento.
- [ ] **5.4 Check-list Inteligente:** Itens dinâmicos por tipo de serviço (CONCLUÍDO).
- [ ] **5.5 Relatório de Performance:** Tempo de execução e deslocamento.

---

## 📅 Sprint 6: Garantia e Polimento
- [ ] **6.1 Fluxo de Garantia:** Acompanhamento de serviços finalizados.
- [ ] **6.2 Dashboard Administrativo:** Gráficos de produtividade e faturamento.
- [ ] **6.3 Refatoração UI/UX:** Ajustes finais de navegação PWA.

---

## ✅ Sprint 8: Consolidação da Arquitetura de Tasks (CONCLUÍDA)
*Foco: Transição definitiva da gestão baseada em OS para gestão baseada em Etapas (Tasks).*

- [x] **8.1 Refatoração de Views Core:**
  - [x] Migrar execução de OS (`order_id`) para execução por Etapa (`task_id`).
  - [x] Implementar `task_add` para agendar novas fases em OS existentes.
  - [x] Criar views de edição (`task_edit`) e cancelamento (`task_cancel`) de etapas.
- [x] **8.2 Integridade e Validação:**
  - [x] Adicionar validação de disponibilidade (server-side) no salvamento de cada etapa.
  - [x] Garantir que mídias e notas sejam estritamente vinculadas à `Task` correta.
- [x] **8.3 Evolução UI/UX (Timeline):**
  - [x] Reformular `order_detail.html` para exibir o histórico cronológico de todas as etapas.
  - [x] Melhorar a visualização de equipes e fotos por etapa concluída.
