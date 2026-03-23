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
- [ ] **3.4 Designação de Equipe (Administrador):**
  - [ ] Vincular múltiplos colaboradores a uma Ordem de Serviço.
  - [ ] Definir a função específica (Técnico, Ajudante, etc) para cada colaborador na execução daquela OS.

---

## 🚀 Sprint 4: Cadastro de Instaladores e Colaboradores (EM DEFINIÇÃO)
*Foco: Gestão da força de trabalho e competências.*

- [ ] **4.1 Estrutura de Dados do Profissional:**
  - [ ] Modelo `Professional` (Nome, CPF, Telefone, E-mail - espelhando campos do Cliente).
  - [ ] Sistema de Funções (Técnico, Ajudante, etc) com suporte a múltiplas funções por pessoa.
- [ ] **4.2 Gestão de Disponibilidade:**
  - [ ] Modelo para Grade de Horários (Dias da semana e intervalos de disponibilidade).
- [ ] **4.3 Interfaces de Gestão:**
  - [ ] CRUD de Instaladores (Lista, Cadastro e Edição).
  - [ ] Interface visual para marcação de disponibilidade.

---

## 🚀 Sprint 5: Execução e Finalização (EM ANDAMENTO)
*Foco: Trabalho de campo e encerramento.*

- [ ] **5.1 Visão de Campo:** Interface operacional para colaboradores (sem exibição de valores).
- [ ] **5.2 Evidências Finais:** Upload de mídias pós-serviço (antes/depois) e mudança de status.
- [ ] **5.3 Assinatura Digital:** Captura de assinatura do cliente no encerramento (opcional).

---

## 📅 Sprint 6: Garantia e Polimento
- [ ] **6.1 Fluxo de Garantia:** Acompanhamento de serviços finalizados.
- [ ] **6.2 Dashboard Administrativo:** Gráficos de produtividade e faturamento.
- [ ] **6.3 Refatoração UI/UX:** Ajustes finais de navegação PWA.

---

## ⏳ Sprint 7: Integração WhatsApp & Aprovação (POSTERGADA)
*Foco: Comunicação oficial via API e automação.*

- [ ] **7.1 Configuração Meta Cloud API:** Templates de mensagens automáticas.
- [ ] **7.2 Link de Aprovação:** Página externa para cliente aprovar/rejeitar orçamento via link.
