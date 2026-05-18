# Estratégia Offline-First -- Painel do Técnico

## 🎯 Objetivo

Criar uma experiência fluida e totalmente funcional (**offline-first**)
para os técnicos em campo.

A aplicação deve operar sem internet, permitindo:

-   Visualizar OS
-   Iniciar atendimento
-   Adicionar evidências
-   Preencher formulários e checklists
-   Capturar assinatura
-   Finalizar atendimento
-   Sincronizar automaticamente quando houver conexão

O painel do técnico será um **Mini SPA / App Shell dentro do Django**,
mantendo o restante do sistema online convencional.

------------------------------------------------------------------------

# 🏗️ Arquitetura Proposta

## 1. Mini SPA (App Shell em Template Django)

Criar um template dedicado:

``` text
templates/services/equipe/offline_app.html
```

Este template funcionará como um **App Shell**.

Características:

-   Django entrega o shell inicial
-   Navegação controlada por JavaScript
-   Sem reload entre Lista de OS e Detalhes
-   Interface guiada pelo cliente (client-driven UI)

Fluxo:

``` text
Django → App Shell → IndexedDB → UI
```

------------------------------------------------------------------------

## 2. IndexedDB como Fonte Principal

O dispositivo é a fonte principal de dados.

O servidor atua como:

-   sincronizador
-   backup
-   coordenação

Toda renderização da interface ocorrerá **exclusivamente via
IndexedDB**.

Sugestão:

-   Dexie.js (recomendado)
-   ou IndexedDB puro

Estrutura inicial:

``` text
os
clientes
formularios
config
sync_queue
```

------------------------------------------------------------------------

## 3. Metadados de Sincronização

Cada entidade local deve possuir metadados para controle.

Exemplo:

``` json
{
  "id": 123,
  "sync_status": "clean",
  "updated_local": "2026-05-18T10:00:00",
  "updated_server": "2026-05-18T09:30:00",
  "local_uuid": "uuid-local"
}
```

Campos:

  Campo            Função
  ---------------- -------------------------
  sync_status      clean / pending / error
  updated_local    ordem local
  updated_server   pull sync
  local_uuid       objetos criados offline

------------------------------------------------------------------------

## 4. Sync Queue

Toda alteração gera um evento local.

Não sincronizar JSON inteiro da OS.

Sincronizar operações.

Store:

``` text
sync_queue
```

Estrutura:

``` json
{
  "id": 1,
  "entity": "os",
  "entity_id": 123,
  "action": "update",
  "payload": {},
  "created_at": "",
  "retry_count": 0,
  "status": "pending"
}
```

Fluxo:

``` text
Usuário edita
↓
Atualiza IndexedDB
↓
Cria item na sync_queue
↓
Servidor sincroniza depois
```

------------------------------------------------------------------------

## 5. API REST (Django)

Separar sincronização em duas direções.

## Bootstrap Inicial

``` text
GET /api/tecnico/bootstrap/
```

Retorna:

-   técnico
-   OS atribuídas
-   clientes
-   formulários
-   configurações
-   sync token

Exemplo:

``` json
{
  "sync_token":"2026-05-18T10:00",
  "tecnico":{},
  "tarefas":[],
  "clientes":[],
  "formularios":[],
  "config":[]
}
```

------------------------------------------------------------------------

## Pull Sync (Servidor → Técnico)

Atualizações vindas do servidor.

``` text
GET /api/tecnico/sync/pull/?since=token
```

Retorna:

-   novas OS
-   cancelamentos
-   reatribuições
-   alterações remotas

------------------------------------------------------------------------

## Push Sync (Técnico → Servidor)

Envio das pendências.

``` text
POST /api/tecnico/sync/push/
```

Payload:

``` json
{
  "changes":[]
}
```

------------------------------------------------------------------------

## 6. Fotos e Evidências

Não utilizar Base64.

Utilizar:

``` text
Blob / File
```

salvos diretamente no IndexedDB.

Motivos:

-   menor tamanho
-   melhor performance
-   upload simplificado

Sincronização:

``` text
multipart/form-data
```

------------------------------------------------------------------------

## 7. Service Worker

Necessário para funcionamento offline do app.

Cache:

-   HTML shell
-   CSS
-   JS
-   ícones
-   fontes

Sem Service Worker:

-   IndexedDB pode existir
-   mas o aplicativo não abre offline

------------------------------------------------------------------------

## 8. Estratégia de Sincronização

O Sync Manager terá três gatilhos.

### A. Evento Online

``` js
window.addEventListener('online', sync)
```

------------------------------------------------------------------------

### B. Timer

Execução periódica.

Exemplo:

``` text
30–60 segundos
```

------------------------------------------------------------------------

### C. Após ação do usuário

Exemplo:

-   iniciar OS
-   finalizar
-   anexar evidência

Após salvar local:

``` text
trySync()
```

Essa combinação aumenta confiabilidade.

------------------------------------------------------------------------

# 🏃 Roadmap de Sprints

## Sprint 1 --- Base Offline e API

### Backend

Criar:

``` text
GET /api/tecnico/bootstrap/
GET /api/tecnico/sync/pull/
POST /api/tecnico/sync/push/
```

Estruturar:

-   serializers
-   contratos JSON
-   tokens de sync

------------------------------------------------------------------------

### Frontend

Criar:

``` text
templates/services/equipe/offline_app.html
```

Estruturar:

-   shell básico
-   lista OS
-   detalhe OS
-   navegação client-side

------------------------------------------------------------------------

### IndexedDB

Criar schema inicial:

``` text
os
clientes
formularios
config
sync_queue
```

Com:

-   metadata
-   sync_status
-   timestamps

------------------------------------------------------------------------

## Sprint 2 --- Local DB + Service Worker + Renderização

### Service Worker

Implementar cache:

-   shell
-   assets
-   ícones
-   JS

------------------------------------------------------------------------

### IndexedDB

Ao abrir online:

``` text
bootstrap → IndexedDB
```

Salvar:

-   OS
-   clientes
-   formulários

------------------------------------------------------------------------

### Renderização

Toda UI deve consumir:

``` text
somente IndexedDB
```

Sem dependência direta da API.

------------------------------------------------------------------------

### UX Inicial

Adicionar indicadores simples:

-   online/offline
-   pendências de sync

------------------------------------------------------------------------

## Sprint 3 --- Interações Offline

Implementar:

-   iniciar serviço
-   checklist
-   relatório
-   assinatura
-   observações
-   evidências

Fluxo:

``` text
ação
↓
IndexedDB
↓
sync_queue
```

Sem depender da internet.

------------------------------------------------------------------------

### Evidências

Salvar:

``` text
Blob/File
```

no IndexedDB.

------------------------------------------------------------------------

## Sprint 4 --- Sync Manager Completo

## Push

Ler:

``` text
sync_queue
```

Enviar:

``` text
POST /sync/push/
```

Processar:

-   retries
-   falhas
-   status

------------------------------------------------------------------------

## Pull

Executar:

``` text
GET /sync/pull/
```

Atualizar localmente:

-   novas OS
-   mudanças servidor
-   cancelamentos

------------------------------------------------------------------------

## Backend Django

Aplicar eventos:

-   mudança de status
-   imagens
-   relatórios
-   assinatura

Persistir no banco real.

------------------------------------------------------------------------

## Sprint 5 --- Refinamento de UX

Melhorar experiência:

-   feedback visual
-   loading states
-   badges de sincronização
-   mensagens de erro
-   UX mobile

Indicadores:

-   Online
-   Offline
-   Sincronizando
-   Pendente
-   Erro

------------------------------------------------------------------------

# ✅ Resultado Esperado

O técnico terá um aplicativo capaz de:

-   abrir sem internet
-   consultar OS localmente
-   trabalhar normalmente em campo
-   salvar instantaneamente
-   sincronizar automaticamente

Enquanto o restante do ERP permanece online convencional.
