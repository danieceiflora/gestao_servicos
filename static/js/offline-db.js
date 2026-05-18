/**
 * Gerenciador de Banco de Dados Offline (IndexedDB) utilizando Dexie.js
 * Este script lida com o armazenamento local das tarefas e a fila de sincronização.
 */

// Inicialização do Banco de Dados
const db = new Dexie("GestaoServicosDB");

// Definição do Schema
db.version(5).stores({
    tasks: 'id, service_order_id, status, scheduled_at',
    orders: 'id, number, status, client_property_id',
    properties: 'id, client_id',
    clients: 'id, name',
    checklist_items: 'id, service_id, template_id',
    checklist_responses: 'id, task_id, item_id, status',
    occurrences: '++id, task_id, category, occurrence_type',
    services: 'id',
    products: 'id',
    media: '++id, task_id, response_id, occurrence_id, status',
    sync_queue: '++id, type, status, timestamp',
    settings: 'key'
});

const OfflineDB = {
    /**
     * Realiza o bootstrap completo do app do técnico (Nova API)
     * Agora retorna as tarefas para permitir prefetch opcional.
     */
    async bootstrap() {
        if (!navigator.onLine) return false;
        
        const syncBanner = document.getElementById('banner-sincronizando');
        const syncBadge = document.getElementById('sync-badge');
        
        if (syncBanner) {
            syncBanner.classList.remove('hidden');
            syncBanner.style.display = 'flex';
        }
        if (syncBadge) {
            syncBadge.classList.remove('hidden');
            syncBadge.style.display = 'inline-flex';
        }
        
        try {
            console.log('🚀 Iniciando Bootstrap Offline-First...');
            const response = await fetch('/api/tecnico/bootstrap/');
            
            if (!response.ok) {
                let errorMsg = 'Falha ao baixar bootstrap';
                try {
                    const errorData = await response.json();
                    if (errorData.error) errorMsg += `: ${errorData.error}`;
                } catch (e) {}
                await db.settings.put({ key: 'bootstrap_error', value: errorMsg });
                throw new Error(errorMsg);
            }
            
            const data = await response.json();
            await db.settings.put({ key: 'bootstrap_error', value: null });

            // Busca alterações pendentes para não perdê-las ao sobrescrever do servidor
            const pendingItems = await db.sync_queue
                .where('status')
                .anyOf(['pending', 'error'])
                .toArray();

            const pendingByTaskId = new Map();
            pendingItems.forEach((item) => {
                const taskId = this.normalizeTaskIdFromItem(item);
                if (taskId) {
                    if (!pendingByTaskId.has(taskId)) pendingByTaskId.set(taskId, []);
                    pendingByTaskId.get(taskId).push(item);
                }
            });
            
            // Salva tudo no IndexedDB de uma vez
            await db.transaction('rw', [
                db.tasks, db.orders, db.properties, db.clients, 
                db.checklist_items, db.checklist_responses, 
                db.services, db.products, db.settings
            ], async () => {
                // Aplica estado pendente às tarefas que vieram do servidor
                const finalizedTasks = (data.tasks || []).map(serverTask => {
                    const taskId = String(serverTask.id);
                    const taskPending = pendingByTaskId.get(taskId) || [];
                    if (taskPending.length > 0) {
                        return this.applyPendingStateToTask(serverTask, null, taskPending);
                    }
                    return serverTask;
                });

                await db.tasks.clear();
                await db.tasks.bulkPut(finalizedTasks);
                
                await db.orders.clear();
                await db.orders.bulkPut(data.orders || []);
                
                await db.properties.clear();
                await db.properties.bulkPut(data.properties || []);
                
                await db.clients.clear();
                await db.clients.bulkPut(data.clients || []);
                
                await db.checklist_items.clear();
                await db.checklist_items.bulkPut(data.checklist_items || []);
                
                await db.checklist_responses.clear();
                await db.checklist_responses.bulkPut(data.checklist_responses || []);
                
                await db.services.clear();
                await db.services.bulkPut(data.services || []);
                
                await db.products.clear();
                await db.products.bulkPut(data.products || []);
                
                await db.settings.put({ key: 'last_sync', value: data.sync_token });
                await db.settings.put({ key: 'technician', value: data.technician });
                await db.settings.put({ key: 'config', value: data.config });
            });
            
            console.log('✅ Bootstrap concluído com sucesso.');
            return data.tasks;
        } catch (error) {
            console.error('❌ Erro no bootstrap:', error);
            await db.settings.put({ key: 'bootstrap_error', value: error.message || 'Falha ao baixar bootstrap' });
            return false;
        } finally {
            if (syncBanner) {
                syncBanner.classList.add('hidden');
                syncBanner.style.display = 'none';
            }
            if (syncBadge) {
                syncBadge.classList.add('hidden');
                syncBadge.style.display = 'none';
            }
        }
    },

    normalizeTaskIdFromItem(item) {
        if (!item || !item.payload) return null;
        if (item.payload.task_id) return String(item.payload.task_id);
        if (item.payload.url) {
            const match = item.payload.url.match(/\/equipe\/etapa\/([0-9a-fA-F-]{36})\//);
            if (match && match[1]) return String(match[1]);
        }
        return null;
    },

    applyPendingStateToTask(serverTask, localTask, pendingItems) {
        const mergedTask = { ...(serverTask || {}) };

        // Prioriza informações já salvas localmente para não "voltar" status ao recarregar do servidor.
        if (localTask) {
            mergedTask.started_at = localTask.started_at || mergedTask.started_at || null;
            mergedTask.finished_at = localTask.finished_at || mergedTask.finished_at || null;
            mergedTask.notes = localTask.notes || mergedTask.notes || '';
        }

        pendingItems
            .slice()
            .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
            .forEach((item) => {
                if (item.type === 'TASK_START') {
                    mergedTask.status = 'IN_PROGRESS';
                    mergedTask.started_at = item.payload?.started_at || mergedTask.started_at || new Date(item.timestamp || Date.now()).toISOString();
                } else if (item.type === 'TASK_FINISH') {
                    mergedTask.status = 'COMPLETED';
                    mergedTask.finished_at = item.payload?.finished_at || mergedTask.finished_at || new Date(item.timestamp || Date.now()).toISOString();
                    const queuedNotes = item.payload?.data?.notes;
                    if (queuedNotes) mergedTask.notes = queuedNotes;
                }
            });

        return mergedTask;
    },

    /**
     * Varre as tarefas do dia e faz o download preventivo do HTML de cada etapa
     * para que fiquem 100% disponíveis offline.
     */
    async prefetchEtapasHTML(tasks) {
        if (!tasks || !Array.isArray(tasks) || !navigator.onLine) return;

        console.log(`Iniciando pré-carregamento de layout para ${tasks.length} etapas...`);

        const cache = await caches.open('gestao-servicos-v5');

        for (const tarefa of tasks) {
            const urlPagina = `/equipe/etapa/${tarefa.id}/`;
            try {
                const response = await fetch(urlPagina);
                if (response.status === 200) {
                    await cache.put(urlPagina, response);
                    console.log(`Layout da Etapa ${tarefa.id} guardado com sucesso para uso offline.`);
                }
            } catch (err) {
                console.warn(`Não foi possível pré-carregar a tela da etapa ${tarefa.id}:`, err);
            }
        }
    },

    /**
     * Abordagem de Check-in: Baixa todos os dados de texto e telas necessários.
     * Agora utiliza o bootstrap unificado.
     */
    async realizarCheckInDiario() {
        try {
            console.log('⬇️ Iniciando Check-in Diário...');
            const tasks = await this.bootstrap();
            
            if (tasks && tasks.length > 0) {
                console.log(`📋 ${tasks.length} tarefas encontradas. Iniciando prefetch das telas...`);
                await this.prefetchEtapasHTML(tasks);
            }

            console.log('✅ Check-in diário concluído! Aplicativo pronto para uso 100% offline.');
            
            // Tenta atualizar a UI do App se ele estiver carregado
            if (typeof OfflineApp !== 'undefined' && OfflineApp.render) {
                await OfflineApp.render();
            }

        } catch (error) {
            console.error('Falha ao realizar o check-in diário:', error);
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

        const pendingItems = await db.sync_queue
            .where('status')
            .anyOf(['pending', 'error'])
            .toArray();

        if (pendingItems.length === 0) {
            this.updateUIStatus();
            return;
        }

        const syncBadge = document.getElementById('sync-badge');
        if (syncBadge) {
            syncBadge.classList.remove('hidden');
            syncBadge.style.display = 'inline-flex';
        }

        console.log(`🔄 Sincronizando ${pendingItems.length} pendências...`);

        try {
            const textChanges = pendingItems.filter(i => i.type !== 'MEDIA_UPLOAD');
            const mediaChanges = pendingItems.filter(i => i.type === 'MEDIA_UPLOAD');

            // 1. Envia mudanças de texto em lote
            if (textChanges.length > 0) {
                try {
                    const response = await fetch('/api/tecnico/sync/push/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCookie('csrftoken'),
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: JSON.stringify({ changes: textChanges })
                    });

                    if (response.ok) {
                        const ids = textChanges.map(i => i.id);
                        await db.sync_queue.bulkDelete(ids);
                        console.log(`✅ ${textChanges.length} mudanças de texto sincronizadas.`);
                    } else {
                        const errorData = await response.json().catch(() => ({}));
                        console.error('❌ Erro na sincronização de texto:', errorData);
                        
                        // Marca como erro para não ficar tentando em loop infinito se for erro de validação
                        const ids = textChanges.map(i => i.id);
                        await db.sync_queue.where('id').anyOf(ids).modify({ status: 'error' });
                    }
                } catch (err) {
                    console.error('💥 Falha crítica ao enviar lote de texto:', err);
                }
            }

            // 2. Envia mídias uma a uma
            for (const item of mediaChanges) {
                try {
                    const mediaRecord = await db.media.get(item.payload.media_id);
                    if (!mediaRecord) {
                        await db.sync_queue.delete(item.id);
                        continue;
                    }

                    const formData = new FormData();
                    formData.append('file', mediaRecord.blob);
                    formData.append('response_id', item.payload.response_id || '');

                    const response = await fetch(`/api/tecnico/etapa/${item.payload.task_id}/upload-media/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': this.getCookie('csrftoken'),
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: formData
                    });

                    if (response.ok) {
                        await db.media.update(mediaRecord.id, { status: 'synced' });
                        await db.sync_queue.delete(item.id);
                        console.log(`📸 Foto ${mediaRecord.id} enviada com sucesso.`);
                    } else {
                        await db.sync_queue.update(item.id, { status: 'error' });
                    }
                } catch (err) {
                    console.error(`Falha ao subir mídia ${item.payload.media_id}:`, err);
                }
            }
        } finally {
            if (syncBadge) {
                syncBadge.classList.add('hidden');
                syncBadge.style.display = 'none';
            }
            this.updateUIStatus();
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
        const btnSyncNow = document.getElementById('btn-sync-now');
        const onlineIndicator = document.getElementById('online-status-indicator');
        
        if (onlineIndicator) {
            if (navigator.onLine) {
                onlineIndicator.innerHTML = '<span class="flex h-2 w-2 rounded-full bg-green-500"></span> Online';
                onlineIndicator.className = 'text-[10px] font-medium text-green-600 flex items-center gap-1.5';
            } else {
                onlineIndicator.innerHTML = '<span class="flex h-2 w-2 rounded-full bg-orange-500 animate-pulse"></span> Offline';
                onlineIndicator.className = 'text-[10px] font-medium text-orange-600 flex items-center gap-1.5';
            }
        }

        const pendingCount = await db.sync_queue
            .where('status')
            .equals('pending')
            .count();
        
        const errorCount = await db.sync_queue
            .where('status')
            .equals('error')
            .count();

        if (syncBadge) {
            if (pendingCount > 0) {
                syncBadge.querySelector('.count').textContent = pendingCount;
                syncBadge.classList.remove('hidden');
                syncBadge.style.display = 'inline-flex';
            } else {
                syncBadge.classList.add('hidden');
                syncBadge.style.display = 'none';
            }
        }

        if (btnSyncNow) {
            if (errorCount > 0 && navigator.onLine) {
                btnSyncNow.classList.remove('hidden');
                btnSyncNow.style.display = 'inline-flex';
                btnSyncNow.onclick = () => this.processSyncQueue();
            } else {
                btnSyncNow.classList.add('hidden');
                btnSyncNow.style.display = 'none';
            }
        }
    }
};

// Event Listeners Globais para Conectividade
window.addEventListener('online', () => {
    console.log('🌐 Conexão restabelecida! Iniciando sincronização...');
    OfflineDB.updateUIStatus();
    OfflineDB.processSyncQueue();
});

window.addEventListener('offline', () => {
    OfflineDB.updateUIStatus();
});
