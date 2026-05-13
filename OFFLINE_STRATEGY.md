# Estratégia de Funcionamento Offline - App do Instalador

Este documento descreve a arquitetura e os procedimentos técnicos para permitir que os técnicos (instaladores) utilizem a aplicação em áreas sem conectividade, garantindo a persistência dos dados e a sincronização posterior com o servidor.

## 1. Tecnologias Principais

-   **Service Worker:** Gerenciamento de cache de recursos estáticos (Shell da App) e interceptação de requisições.
-   **IndexedDB:** Banco de dados NoSQL no navegador para armazenamento estruturado de tarefas, checklists e mídias.
-   **Background Sync API / Manual Sync:** Mecanismo para enviar dados pendentes quando a conexão for restabelecida.
-   **Dexie.js (Recomendado):** Biblioteca wrapper para facilitar o uso do IndexedDB.

## 2. Fluxo de Trabalho (Workflow)

### A. Sincronização Inicial (Ao Abrir o App com Internet)
1.  O App verifica a conectividade.
2.  Se online, faz uma requisição para um novo endpoint API `GET /api/equipe/agenda-do-dia/`.
3.  O servidor retorna um JSON completo contendo:
    -   Lista de Tarefas (Tasks) do dia.
    -   Detalhes da Ordem de Serviço vinculada.
    -   Checklists associados a cada tarefa.
    -   Dados do Cliente e Imóvel.
4.  O App salva/atualiza esses dados no **IndexedDB**.
5.  O Service Worker garante que os arquivos HTML, CSS e JS necessários para renderizar essas páginas estejam no **Cache Storage**.

### B. Operação Offline
1.  O técnico acessa as tarefas. Se falhar a requisição de rede, o frontend busca os dados no **IndexedDB**.
2.  **Ações Offline:**
    -   *Iniciar Tarefa:* Salva o `started_at` localmente no IndexedDB e marca a tarefa como "pending_sync".
    -   *Preencher Checklist:* Salva as respostas (texto e booleanos) no IndexedDB.
    -   *Capturar Mídias:* Salva fotos/vídeos como **Blobs** no IndexedDB.
    -   *Registrar Ocorrências/Pagamentos:* Salva os dados no IndexedDB.
3.  Cada ação gera uma entrada em uma tabela de **Outbox** (Fila de Sincronização) no IndexedDB.

### C. Sincronização de Retorno (Ao Recuperar Internet)
1.  O App detecta o evento `online`.
2.  Percorre a fila de **Outbox** no IndexedDB.
3.  Envia cada ação pendente para o servidor na ordem correta (FIFO).
4.  **Tratamento de Mídia:** Upload de arquivos grandes deve ser feito com cuidado, possivelmente um por um, com retry em caso de falha.
5.  Após confirmação do servidor (200 OK), a entrada é removida do **Outbox** e o status local no IndexedDB é atualizado.

## 3. Estrutura de Dados no IndexedDB

Sugerimos as seguintes "tables" no IndexedDB:

-   `tasks`: Cache das tarefas do dia.
-   `checklist_responses`: Respostas pendentes ou salvas.
-   `medias`: Blobs de fotos e vídeos capturados offline.
-   `sync_queue`: Fila de requisições (Ex: `{ url: '...', method: 'POST', body: {...}, timestamp: ... }`).

## 4. Detalhamento Técnico da API e Frontend

### Endpoint: `GET /api/equipe/agenda-do-dia/`
Este endpoint deve retornar um JSON estruturado para alimentar o IndexedDB.
```json
{
  "date": "2026-05-13",
  "technician": "João Silva",
  "tasks": [
    {
      "id": "uuid-da-tarefa",
      "type": "EXECUÇÃO",
      "status": "PENDENTE",
      "scheduled_at": "2026-05-13T08:00:00Z",
      "order_details": {
        "id": "uuid-da-os",
        "number": "1234",
        "client_name": "Empresa X",
        "address": "Rua A, 100",
        "gps": {"lat": -23.5, "lng": -46.6}
      },
      "checklist": [
        {
          "response_id": 101,
          "item_id": 5,
          "description": "Verificar fiação",
          "is_required": true,
          "evidence_type": "PHOTO",
          "completed": false
        }
      ]
    }
  ]
}
```

### Script de Sincronização (`offline-db.js`)
Exemplo de como o `Dexie` seria inicializado:
```javascript
const db = new Dexie('InstallerDB');
db.version(1).stores({
  tasks: 'id, status',
  sync_queue: '++id, method, url'
});

async function syncOfflineData() {
  const pending = await db.sync_queue.toArray();
  for (const item of pending) {
    try {
      const response = await fetch(item.url, {
        method: item.method,
        body: item.body,
        headers: { 'Content-Type': 'application/json' }
      });
      if (response.ok) await db.sync_queue.delete(item.id);
    } catch (e) {
      console.warn("Falha ao sincronizar item", item.id);
    }
  }
}
```

## 5. UI/UX Offline

-   **Indicador de Status:** Mostrar visualmente se o app está "Online" ou "Modo Offline" no header da `base_equipe.html`.
-   **Contador de Sincronização:** Exibir quantos itens estão aguardando envio (ex: "3 fotos pendentes") em um badge fixo.
-   **Feedback de Sucesso:** Notificar o usuário quando a sincronização for concluída via `Toast` ou similar.

## 6. Próximos Passos Sugeridos

1.  **Implementar API:** Criar o endpoint `agenda-do-dia` no Django (`views_equipe.py`).
2.  **Integrar Dexie.js:** Adicionar a biblioteca e o script de inicialização do banco.
3.  **Refatorar Views Frontend:** Adaptar o `task_detail.html` para ler do IndexedDB se a rede falhar.
4.  **Lógica de Interceptação:** Adicionar listener de `online`/`offline` para disparar a sincronização.
5.  **Atualizar Service Worker:** Configurar o cache estático para as rotas da equipe.
