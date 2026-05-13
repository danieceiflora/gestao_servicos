/**
 * Gerenciador de Banco de Dados Offline (IndexedDB) utilizando Dexie.js
 * Este script lida com o armazenamento local das tarefas e a fila de sincronização.
 */

// Inicialização do Banco de Dados
const db = new Dexie("GestaoServicosDB");

// Definição do Schema
db.version(1).stores({
    tasks: 'id, status, scheduled_at', // Cache de tarefas
    sync_queue: '++id, type, status, timestamp', // Fila de sincronização (Outbox)
    settings: 'key' // Configurações locais (ex: data da última sincronização)
});

const OfflineDB = {
    /**
     * Sincroniza a agenda do dia do servidor para o IndexedDB
     */
    async syncAgendaFromServer() {
        if (!navigator.onLine) return;

        try {
            const response = await fetch('/api/equipe/agenda-do-dia/');
            if (!response.ok) throw new Error('Erro ao buscar agenda');
            
            const data = await response.json();
            
            // Limpa tarefas antigas do dia e salva as novas
            await db.tasks.clear();
            await db.tasks.bulkAdd(data.tasks);
            
            await db.settings.put({ key: 'last_sync', value: new Date().toISOString() });
            
            console.log('Agenda sincronizada com sucesso:', data.tasks.length, 'tarefas');
            this.updateUIStatus();
            return data;
        } catch (error) {
            console.error('Falha na sincronização da agenda:', error);
        }
    },

    /**
     * Adiciona uma ação à fila de sincronização
     */
    async enqueueSyncItem(type, payload) {
        await db.sync_queue.add({
            type,
            payload,
            status: 'pending',
            timestamp: new Date().getTime()
        });
        this.updateUIStatus();
        
        if (navigator.onLine) {
            this.processSyncQueue();
        }
    },

    /**
     * Processa a fila de sincronização enviando os itens para o servidor
     */
    async processSyncQueue() {
        if (!navigator.onLine) return;

        const pendingItems = await db.sync_queue.where('status').equals('pending').toArray();
        if (pendingItems.length === 0) return;

        console.log(`Processando fila de sincronização: ${pendingItems.length} itens pendentes`);

        for (const item of pendingItems) {
            try {
                let success = false;
                
                // Lógica de envio baseada no tipo de ação
                switch (item.type) {
                    case 'TASK_START':
                        success = await this.sendToServer(`/equipe/etapa/${item.payload.task_id}/iniciar/`, 'POST');
                        break;
                    case 'TASK_FINISH':
                        success = await this.sendToServer(`/equipe/etapa/${item.payload.task_id}/finalizar/`, 'POST', item.payload.data);
                        break;
                    case 'CHECKLIST_UPDATE':
                        success = await this.sendToServer(`/equipe/etapa/${item.payload.task_id}/checklist/atualizar/`, 'POST', item.payload.data);
                        break;
                    // Adicionar outros tipos conforme necessário (Mídias, Ocorrências, etc)
                }

                if (success) {
                    await db.sync_queue.delete(item.id);
                } else {
                    // Marca como erro para tentar novamente depois ou alertar o usuário
                    await db.sync_queue.update(item.id, { status: 'error' });
                }
            } catch (error) {
                console.error('Erro ao processar item da fila:', error);
            }
        }
        this.updateUIStatus();
    },

    /**
     * Helper para requisições fetch com CSRF token
     */
    async sendToServer(url, method, data = null) {
        const headers = {
            'X-CSRFToken': this.getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        };

        let body = null;
        if (data) {
            if (data instanceof FormData) {
                body = data;
            } else {
                body = JSON.stringify(data);
                headers['Content-Type'] = 'application/json';
            }
        }

        try {
            const response = await fetch(url, { method, headers, body });
            return response.ok;
        } catch (e) {
            return false;
        }
    },

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    },

    /**
     * Atualiza elementos da interface sobre o status de sincronização
     */
    async updateUIStatus() {
        const syncBadge = document.getElementById('sync-pending-badge');
        const onlineIndicator = document.getElementById('online-status-indicator');
        
        // Atualiza indicador online/offline
        if (onlineIndicator) {
            if (navigator.onLine) {
                onlineIndicator.innerHTML = '<span class="flex h-2 w-2 rounded-full bg-green-500"></span> Online';
                onlineIndicator.className = 'text-[10px] font-medium text-green-600 flex items-center gap-1.5';
            } else {
                onlineIndicator.innerHTML = '<span class="flex h-2 w-2 rounded-full bg-orange-500 animate-pulse"></span> Offline';
                onlineIndicator.className = 'text-[10px] font-medium text-orange-600 flex items-center gap-1.5';
            }
        }

        // Atualiza badge de itens pendentes
        if (syncBadge) {
            const count = await db.sync_queue.where('status').equals('pending').count();
            if (count > 0) {
                syncBadge.textContent = count;
                syncBadge.classList.remove('hidden');
            } else {
                syncBadge.classList.add('hidden');
            }
        }
    }
};

// Event Listeners para Conectividade
window.addEventListener('online', () => {
    OfflineDB.updateUIStatus();
    OfflineDB.processSyncQueue();
});

window.addEventListener('offline', () => {
    OfflineDB.updateUIStatus();
});

// Inicialização ao carregar a página
document.addEventListener('DOMContentLoaded', () => {
    OfflineDB.updateUIStatus();
    // Tenta sincronizar agenda se estiver online
    if (navigator.onLine) {
        OfflineDB.syncAgendaFromServer();
    }
});
