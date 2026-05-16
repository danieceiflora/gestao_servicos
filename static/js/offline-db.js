/**
 * Gerenciador de Banco de Dados Offline (IndexedDB) utilizando Dexie.js
 * Este script lida com o armazenamento local das tarefas e a fila de sincronização.
 */

// Inicialização do Banco de Dados
const db = new Dexie("GestaoServicosDB");

// Definição do Schema
// Caso adicione mais menus (ex: historico), basta acrescentar a tabela aqui separada por vírgula.
db.version(1).stores({
    tasks: 'id, status, scheduled_at',            // Cache de tarefas (Agenda)
    history: 'id, status, finished_at',          // Cache para a tela de histórico (Exemplo)
    sync_queue: '++id, type, status, timestamp', // Fila de sincronização (Outbox)
    settings: 'key'                              // Configurações locais e timestamps de sincronia
});

const OfflineDB = {
    /**
     * Varre as tarefas do dia e faz o download preventivo do HTML de cada etapa
     * para que fiquem 100% disponíveis offline.
     * @param {Array} tasks - Lista de tarefas que veio da API da agenda
     */
    async prefetchEtapasHTML(tasks) {
        if (!tasks || !Array.isArray(tasks) || !navigator.onLine) return;

        console.log(`Iniciando pré-carregamento de layout para ${tasks.length} etapas...`);

        // Abre o cache do Service Worker diretamente pelo JavaScript da página
        const cache = await caches.open('gestao-servicos-v4');

        for (const tarefa of tasks) {
            // Monte a URL exata da página que o técnico vai precisar acessar em campo
            // Ajuste o padrão da URL conforme o seu urls.py do Django (ex: /equipe/etapa/1/)
            const urlPagina = `/equipe/etapa/${tarefa.id}/`;

            try {
                // Faz o disparo silencioso em background para baixar o HTML da tela
                const response = await fetch(urlPagina);
                
                if (response.status === 200) {
                    // Guarda o esqueleto/HTML da página no cache do Service Worker
                    await cache.put(urlPagina, response);
                    console.log(`Layout da Etapa ${tarefa.id} guardado com sucesso para uso offline.`);
                }
            } catch (err) {
                console.warn(`Não foi possível pré-carregar a tela da etapa ${tarefa.id}:`, err);
            }
        }
    },

    /**
     * Abordagem de Check-in: Baixa todos os dados de texto e telas necessários 
     * para o dia de trabalho do técnico de uma só vez.
     */
    async realizarCheckInDiario() {
        const syncBanner = document.getElementById('banner-sincronizando');
        try {
            if (syncBanner) syncBanner.classList.remove('hidden');
            
            // 1. Baixa os dados textuais de todos os menus importantes e salva no Dexie
            // Usamos a nossa função genérica que criamos antes
            console.log('⬇️ Baixando dados dos menus...');
            const tarefas = await this.syncDataFromServer('/api/equipe/agenda-do-dia/', 'tasks', 'tasks');
            
            // Exemplo: se tiver menu de histórico, já atualiza também
            // await this.syncDataFromServer('/api/equipe/historico-servicos/', 'history', 'history_list');

            // 2. Com as tarefas em mãos, faz o pré-carregamento (prefetch) dos HTMLs das etapas
            if (tarefas && tarefas.length > 0) {
                console.log(`📋 ${tarefas.length} tarefas encontradas. Iniciando download das telas...`);
                await this.prefetchEtapasHTML(tarefas);
            }

            console.log('✅ Check-in diário concluído! Aplicativo pronto para uso 100% offline.');
            
            // 3. Atualiza a tela do usuário com os dados novos
            if (typeof carregarTelaAgenda === 'function') {
                carregarTelaAgenda();
            }

        } catch (error) {
            console.error('Falha ao realizar o check-in diário:', error);
        } finally {
            if (syncBanner) syncBanner.classList.add('hidden');
        }
    },

    /**
     * Função genérica para baixar dados de uma API e salvar em uma tabela no Dexie
     */
    async syncDataFromServer(url, tableName, stateKey) {
        if (!navigator.onLine) return null;
        try {
            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                const itemList = data[stateKey] || [];
                
                await db[tableName].clear();
                if (itemList.length > 0) {
                    // Usar bulkPut no lugar de bulkAdd previne o ConstraintError, 
                    // pois ele fará update (upsert) se houverem chaves/IDs duplicados na lista do servidor.
                    await db[tableName].bulkPut(itemList);
                }
                return itemList;
            }
        } catch (error) {
            console.error(`Erro ao sincronizar ${tableName}:`, error);
        }
        return null;
    },
    /**
     * Retorna a Agenda de forma inteligente (Online -> API + Cache / Offline -> Dexie)
     */
    async getAgenda() {
        if (navigator.onLine) {
            const dadosAtualizados = await this.syncDataFromServer('/api/equipe/agenda-do-dia/', 'tasks', 'tasks');
            if (dadosAtualizados) return dadosAtualizados;
        }
        console.log('Buscando Agenda do armazenamento local offline...');
        return await db.tasks.toArray();
    },

    /**
     * Mantido por compatibilidade com suas chamadas legadas
     */
    async syncAgendaFromServer() {
        return await this.syncDataFromServer('/api/equipe/agenda-do-dia/', 'tasks', 'tasks');
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

        // CORREÇÃO: Busca tanto os itens 'pending' quanto os marcados com 'error' para re-tentar o envio automático
        const pendingItems = await db.sync_queue
            .where('status')
            .anyOf(['pending', 'error'])
            .toArray();

        if (pendingItems.length === 0) return;

        console.log(`Processando fila de sincronização: ${pendingItems.length} itens pendentes/com erro`);

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
                    case 'GENERIC_FORM_UPLOAD':
                        success = await this.sendToServer(item.payload.url, 'POST', item.payload.data);
                        break;
                }

                if (success) {
                    await db.sync_queue.delete(item.id);
                } else {
                    // Atualiza para 'error' para evitar travar o loop atual, mas será processado no próximo ciclo de internet
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
                // Converte o objeto plano para FormData para manter compatibilidade com request.POST do Django
                body = new FormData();
                for (const key in data) {
                    if (Array.isArray(data[key])) {
                        data[key].forEach(val => body.append(key, val));
                    } else {
                        body.append(key, data[key]);
                    }
                }
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

        // Atualiza badge de itens pendentes (conta tanto novos quanto erros acumulados)
        if (syncBadge) {
            const count = await db.sync_queue
                .where('status')
                .anyOf(['pending', 'error'])
                .count();

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
    console.log('🌐 Conexão restabelecida! Técnico online. Iniciando sincronização dos dados locais com o servidor...');
    OfflineDB.updateUIStatus();
    OfflineDB.processSyncQueue();
});

window.addEventListener('offline', () => {
    OfflineDB.updateUIStatus();
});

// Inicialização ao carregar a página
document.addEventListener('DOMContentLoaded', () => {
    OfflineDB.updateUIStatus();
    
    // Roda a sincronização inteligente da agenda
    OfflineDB.getAgenda();
});

// Inicialização automática ao abrir o app
document.addEventListener('DOMContentLoaded', async () => {
    OfflineDB.updateUIStatus();
    
    // Sempre tenta limpar a fila pendente quando a tela carrega (pode ser que a internet tenha voltado enquanto o app estava fechado)
    OfflineDB.processSyncQueue();
    
    if (navigator.onLine) {
        console.log('🔄 Técnico Online: Iniciando sincronização diária obrigatória...');
        
        // Executa a carga completa de dados e layouts em background
        await OfflineDB.realizarCheckInDiario();
    } else {
        console.log('📴 Técnico Offline: Carregando dados salvos no dispositivo.');
        // Se estiver sem rede, apenas garante a renderização com o que já tem no Dexie
        if (typeof carregarTelaAgenda === 'function') carregarTelaAgenda();
    }
});