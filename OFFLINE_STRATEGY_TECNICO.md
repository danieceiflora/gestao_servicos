# Estratégia Offline-First - Painel do Técnico

Este documento descreve a arquitetura e o funcionamento da estratégia offline-first implementada para o app do técnico. Utilize este guia como referência para manutenção e restauração de comportamento em caso de regressões.

## 🏗️ Arquitetura Geral

O sistema utiliza uma abordagem de **SPA (Single Page Application)** dentro do ecossistema Django, onde o servidor fornece o "shell" da aplicação e o JavaScript (Vanilla + Dexie.js) gerencia o estado, os dados e a sincronização.

### Componentes Principais:
1.  **IndexedDB (Dexie.js):** Banco de dados local no navegador que serve como fonte da verdade (*Ground Truth*) para a UI.
2.  **Sync Queue (Fila de Sincronização):** Tabela no IndexedDB que armazena todas as operações (Criação, Edição, Upload) que ainda não foram confirmadas pelo servidor.
3.  **Bootstrap API:** Endpoint Django que fornece a carga inicial de dados necessária para o funcionamento offline.
4.  **Background Sync:** Lógica que processa a fila de sincronização assim que detecta conectividade.

---

## 💾 Esquema do Banco de Dados (IndexedDB)

Atualmente na **Versão 3**, o esquema está definido no arquivo `static/js/offline-db.js`:

```javascript
db.version(3).stores({
    tasks: 'id, service_order_id, status, scheduled_at',
    orders: 'id, number, status, client_property_id',
    properties: 'id, client_id',
    clients: 'id, name',
    checklist_items: 'id, service_id, template_id',
    checklist_responses: 'id, task_id, item_id',
    services: 'id',
    products: 'id',
    media: '++id, task_id, response_id, status', // Cache local de mídias
    sync_queue: '++id, type, status, timestamp', // Fila de sincronização
    settings: 'key'
});
```

---

## 🔄 Ciclo de Vida da Sincronização

### 1. Bootstrap (Carga Inicial)
Ao iniciar o app (ou fazer check-in), o sistema chama `/api/tecnico/bootstrap/`.
- **Merge Inteligente:** O sistema busca itens pendentes na `sync_queue` ANTES de sobrescrever as tarefas locais. Se uma tarefa tem alterações locais não sincronizadas, estas são aplicadas sobre o objeto vindo do servidor (`applyPendingStateToTask`).

### 2. Captura de Dados (Offline)
Qualquer ação do usuário (iniciar tarefa, responder checklist, anexar foto) segue o fluxo:
1.  Atualiza o registro na tabela correspondente do IndexedDB (ex: `tasks`).
2.  Cria um registro na `sync_queue` com o `type` (PATCH, POST, MEDIA_UPLOAD) e o `payload`.
3.  Tenta disparar o processamento da fila (`OfflineDB.processSyncQueue()`).

### 3. Processamento da Fila
A fila processa os itens sequencialmente para manter a integridade referencial.
- **Tipos de Operação:**
    - `POST`/`PATCH`: Envia JSON via fetch.
    - `MEDIA_UPLOAD`: Converte o Blob (armazenado na tabela `media`) em `FormData` para upload via `multipart/form-data`.
- **Tratamento de Erros:** Itens que falham por erro de rede (502, 503, timeout) ficam com status `error` e são reprocessados na próxima tentativa. Erros de negócio (400, 403) devem ser analisados (ver "Problemas Conhecidos").

---

## 📸 Gerenciamento de Mídias (Fotos e Vídeos)

As mídias são tratadas de forma especial devido ao seu tamanho e formato.

### Fluxo de Upload:
1.  O arquivo é capturado e armazenado como `Blob` na tabela `media` do IndexedDB.
2.  Um item `MEDIA_UPLOAD` é adicionado à `sync_queue`.
3.  O backend (`api_tecnico_upload_media`) recebe o arquivo.
    - **Importante:** Se `response_id` estiver presente, a mídia é vinculada a uma resposta de checklist (`ChecklistResponseMedia`). Caso contrário, é vinculada diretamente à tarefa (`ServiceMedia`).

### Modelo de Dados (Django):
O modelo `ServiceMedia` **não possui** o campo `description`. O upload deve conter apenas:
- `file`: O arquivo binário.
- `task_id`: UUID da tarefa.
- `response_id`: (Opcional) UUID da resposta do checklist.

---

## 🛠️ Como Restaurar se Algo Quebrar

### 1. Verifique a Versão do Schema
Se você adicionar campos aos modelos Django que precisam estar disponíveis offline, aumente a versão do Dexie em `offline-db.js` e atualize o bootstrap.

### 2. Verifique o "Merge" de Sincronização
Se as tarefas estiverem "resetando" para o estado antigo ao recarregar a página, o problema provavelmente está na função `applyPendingStateToTask` ou `normalizeTaskIdFromItem`. Essas funções garantem que o estado local prevaleça sobre o servidor enquanto a sincronização não termina.

### 3. Erro 400 em Uploads
Sempre verifique se os argumentos passados para `.create()` no Django batem com os campos do model. Exemplo corrigido em `services/views_offline.py`:
```python
# Correto
ServiceMedia.objects.create(
    task=task,
    file=file_obj
)
# Errado (causa 400 Bad Request)
ServiceMedia.objects.create(task=task, file=file_obj, description="...")
```

### 4. Depuração no Navegador
- **Application Tab > IndexedDB:** Visualize o estado atual das tarefas e da fila de sincronização.
- **Console:** Filtre por `🚀`, `✅` ou `❌` para ver o log do fluxo offline.

---
*Documentação gerada em 18 de Maio de 2026.*
