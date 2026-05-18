# Estratégia Offline-First para Técnicos

## 🎯 Objetivo
Criar uma experiência fluida e totalmente funcional (offline-first) para os técnicos em campo. A aplicação deve ser capaz de operar sem internet (visualizar OS, iniciar, adicionar evidências, preencher formulários e finalizar), gravando as alterações localmente e sincronizando em segundo plano quando a conexão for restabelecida.

## 🏗️ Arquitetura Proposta
1. **Página Única (SPA em Template Django):** Criaremos um novo template dedicado (ex: `templates/services/equipe/offline_app.html`) que funcionará como uma Single Page Application simplificada. Toda a navegação entre a lista de OS e o detalhe ocorrerá via JavaScript ocultando e mostrando divs, evitando reloads da página.
2. **Armazenamento Local:** Utilizaremos `IndexedDB` (possivelmente utilizando uma lib leve como `localForage` ou `Dexie.js`, ou até mesmo puro se preferirmos sem dependências) para armazenar:
   - Os dados das OS do dia/período.
   - Uma fila de sincronização (Sync Queue) com as ações pendentes (mudança de status, evidências, assinaturas, etc).
3. **API REST (Django):** 
   - Endpoint de Leitura (`GET`): Para buscar os dados completos do técnico (OS, propriedades, clientes) necessários para o dia.
   - Endpoint de Escrita/Sincronização (`POST`): Para processar a fila de ações realizadas em modo offline.

## 🏃 Plano de Sprints

### Sprint 1: Estrutura Base e Rotas API
* **Backend:** 
  * Criar as rotas da API em `services/urls.py` ou `services/api/` para fornecer o JSON completo das OS (`GET /api/tecnico/tarefas/`).
  * Criar a rota de sincronização (`POST /api/tecnico/sync/`).
* **Frontend:**
  * Criar o novo template `templates/services/equipe/offline_app.html`.
  * Estruturar o layout HTML básico (sem grandes preocupações visuais) com seções ocultáveis para "Lista de OS" e "Detalhe da OS".
  * Registrar esse template no roteamento do Django.

### Sprint 2: Armazenamento Local e Renderização
* **JavaScript / IndexedDB:**
  * Criar o script gerenciador do IndexedDB (ex: `static/js/offline-app.js`).
  * Ao carregar a página (estando online), fazer o fetch na API e salvar/atualizar o IndexedDB.
  * Criar as funções de renderização do HTML utilizando **exclusivamente os dados locais do IndexedDB**.
  * Fazer o roteamento na tela (clicar na OS na lista, abrir o detalhe populado com os dados locais).

### Sprint 3: Interações do Técnico (In-App)
* **Ações Offline:**
  * Implementar as ações no painel de detalhe:
    * Botão "Iniciar Serviço".
    * Formulários de Check-list (se aplicável), Relatório e Assinatura.
    * Anexo de Fotos/Vídeos (salvando blobs/base64 no IndexedDB).
    * Botão "Finalizar Serviço".
* **Fila de Sincronização:**
  * Toda ação realizada vai atualizar a base local de visualização e adicionar um registro (evento) na "Fila de Sincronização" do IndexedDB.

### Sprint 4: Sincronizador (Sync Manager)
* **Comunicação com o Backend:**
  * Criar a rotina JavaScript que escuta a volta da internet (`window.addEventListener('online', sync)`) ou que roda periodicamente.
  * O Sync Manager vai ler a "Fila de Sincronização" e enviar os pacotes para a rota `POST /api/tecnico/sync/`.
  * Atualizar o status local caso a resposta do servidor seja de sucesso.
* **Backend (Sincronização):**
  * Lógica no Django para receber os eventos (mudança de status, gravação de imagem/blob em model de evidência) e aplicar no banco de dados real.

### Sprint 5: Refinamento de UI e UX
* **Feedback Visual:**
  * Adicionar indicadores de conexão (Online/Offline).
  * Adicionar indicadores de sincronização ("3 tarefas pendentes de envio").
  * Estilizar e organizar a tela utilizando o Tailwind, trazendo para o padrão profissional (`shadcn`) definido no `GEMINI.md`.

---
*Aguardando aprovação para iniciarmos a Sprint 1.*