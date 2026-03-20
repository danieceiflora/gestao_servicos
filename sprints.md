# Sprints de Desenvolvimento - Gestão de Serviços PWA

Acompanhamento detalhado das tarefas para execução do projeto.

---

## ✅ Sprint 1: Estrutura Base e Ambiente (CONCLUÍDA)
...
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

---

## ⏳ Sprint 4: Integração WhatsApp & Aprovação (POSTERGADA)
*Foco: Comunicação oficial via API.*

- [ ] **4.1 Configuração Meta Cloud API.**
- [ ] **4.2 Fluxo de Aprovação.**

---

## 🚀 Sprint 5: Execução e Finalização (EM ANDAMENTO)
*Foco: Trabalho de campo e encerramento.*

- [ ] **5.1 Visão de Campo:** Interface operacional para colaboradores (sem valores).
- [ ] **5.2 Evidências Finais:** Upload de mídias pós-serviço e mudança de status.

---

## 📅 Sprint 6: Garantia e Polimento
...
