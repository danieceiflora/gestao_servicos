/**
 * Gerenciador da Interface do App do Técnico (Offline-First SPA)
 */

const OfflineApp = {
    // Estado interno
    state: {
        currentView: 'list', // 'list', 'detail'
        currentTaskId: null,
        activeTab: 'info',
        filters: {
            status: 'all', // 'all', 'EM_ANDAMENTO', 'AGENDADO', 'CONCLUIDO'
            hideCompleted: false
        },
        camera: {
            stream: null,
            facingMode: 'environment',
            capturedBlobs: [],
            context: null // taskId, responseId, etc.
        },
        payment: {
            method: null,
            amount: 0
        },
        mediaViewer: {
            items: [],
            index: 0
        },
        detailRoot: null
    },

    // Inicialização
    async init() {
        console.log('📱 OfflineApp inicializando...');

        // Limpa mídias sincronizadas de sessões anteriores apenas para tarefas já concluídas.
        // Tarefas em andamento mantêm suas mídias locais para exibição (ocorrências, etc.)
        try {
            const completedTasks = await db.tasks.where('status').equals('CONCLUIDO').toArray();
            const completedIds = completedTasks.map(t => String(t.id));
            if (completedIds.length > 0) {
                await db.media
                    .where('task_id').anyOf(completedIds)
                    .and(item => item.status === 'synced')
                    .delete();
            }
        } catch (_) {}

        // Monitora mudanças na hash para navegação
        window.addEventListener('hashchange', () => this.handleRouting());

        // 1. Atualiza UI de status (Online/Offline)
        if (typeof OfflineDB !== 'undefined') {
            await OfflineDB.updateUIStatus();
        }

        // 2. Esconde o loading e mostra o app
        const loadingEl = document.getElementById('app-loading');
        const mainEl = document.getElementById('app-main');
        if (loadingEl) loadingEl.classList.add('hidden');
        if (mainEl) mainEl.classList.remove('hidden');

        await this.renderBootstrapError();

        // 3. Renderiza a view inicial baseada na rota ou padrão
        await this.handleRouting();

        // 4. Sincroniza em background após a UI estar visível
        if (typeof OfflineDB !== 'undefined' && navigator.onLine) {
            setTimeout(() => {
                OfflineDB.processSyncQueue()
                    .catch(err => console.error('Falha na sincronização em background:', err))
                    .finally(() => OfflineDB.realizarCheckInDiario());
            }, 200);
        }
    },

    /**
     * Trata o roteamento baseado na hash da URL
     */
    async handleRouting() {
        const hash = window.location.hash;
        console.log('Navegando via hash:', hash);

        if (hash.startsWith('#task/')) {
            const taskId = hash.split('/')[1];
            // Se já estamos no detalhe dessa task, não faz nada
            if (this.state.currentView === 'detail' && this.state.currentTaskId === taskId) return;
            await this.navigate('detail', { taskId: taskId }, false);
        } else {
            // Se já estamos na lista, não faz nada
            if (this.state.currentView === 'list') return;
            await this.navigate('list', {}, false);
        }
    },

    async renderBootstrapError() {
        const banner = document.getElementById('offline-error-banner');
        const messageEl = document.getElementById('offline-error-message');
        if (!banner || !messageEl) return;

        let errorMessage = null;
        try {
            const errorSetting = await db.settings.get('bootstrap_error');
            errorMessage = errorSetting ? errorSetting.value : null;
        } catch (e) {
            errorMessage = null;
        }

        if (errorMessage) {
            messageEl.textContent = errorMessage;
            banner.classList.remove('hidden');
            if (window.lucide) lucide.createIcons();
        } else {
            banner.classList.add('hidden');
            messageEl.textContent = '';
        }
    },

    // Roteamento simples
    async navigate(view, params = {}, updateHash = true) {
        this.state.currentView = view;
        this.state.currentTaskId = params.taskId || null;
        
        if (updateHash) {
            if (view === 'detail' && params.taskId) {
                window.location.hash = `task/${params.taskId}`;
            } else {
                window.location.hash = '';
            }
        }

        await this.render();
    },

    // Renderização principal
    _renderId: 0,
    async render() {
        const currentRenderId = ++this._renderId;
        const container = document.getElementById('view-container');
        const titleEl = document.getElementById('view-title');
        
        // Efeito de fade out
        container.style.opacity = '0';
        
        await new Promise(resolve => setTimeout(resolve, 50));
        
        if (this._renderId !== currentRenderId) return; // Cancela se uma nova renderização foi solicitada

        container.innerHTML = '';
        const iconEl = document.getElementById('header-icon');
        
        if (this.state.currentView === 'list') {
            titleEl.textContent = 'Minha Agenda';
            if (iconEl) iconEl.setAttribute('data-lucide', 'calendar');
            await this.renderTaskList(container);
        } else if (this.state.currentView === 'detail') {
            titleEl.textContent = 'Detalhes do Serviço';
            if (iconEl) iconEl.setAttribute('data-lucide', 'clipboard-list');
            await this.renderTaskDetail(container, this.state.currentTaskId);
        }
        
        if (this._renderId !== currentRenderId) return;

        // Efeito de fade in
        container.style.opacity = '1';
        
        // Re-inicializa ícones do Lucide
        if (window.lucide) lucide.createIcons();
    },

    // Renderiza a lista de tarefas
    async renderTaskList(container) {
        const tplList = document.getElementById('tpl-task-list').content.cloneNode(true);
        const listContainer = tplList.getElementById('task-list-container');
        
        // Configura eventos dos filtros
        const filterStatus = tplList.getElementById('filter-status');
        const filterHideCompleted = tplList.getElementById('filter-hide-completed');
        
        if (filterStatus) {
            filterStatus.value = this.state.filters.status;
            filterStatus.addEventListener('change', (e) => {
                this.state.filters.status = e.target.value;
                this.updateTaskListUI();
            });
        }
        
        if (filterHideCompleted) {
            filterHideCompleted.checked = this.state.filters.hideCompleted;
            filterHideCompleted.addEventListener('change', (e) => {
                this.state.filters.hideCompleted = e.target.checked;
                this.updateTaskListUI();
            });
        }
        
        container.appendChild(tplList);
        await this.updateTaskListUI();
    },

    async updateTaskListUI() {
        const listContainer = document.getElementById('task-list-container');
        if (!listContainer) return;
        
        const secInProgress = listContainer.querySelector('#section-in-progress');
        const listInProgress = secInProgress.querySelector('.task-list');
        const countInProgress = secInProgress.querySelector('.count');
        
        const secScheduled = listContainer.querySelector('#section-scheduled');
        const listScheduled = secScheduled.querySelector('.task-list');
        const countScheduled = secScheduled.querySelector('.count');
        
        const secCompleted = listContainer.querySelector('#section-completed');
        const listCompleted = secCompleted.querySelector('.task-list');
        const countCompleted = secCompleted.querySelector('.count');
        
        const emptyState = listContainer.querySelector('#empty-state-message');
        
        // Limpar listas
        listInProgress.innerHTML = '';
        listScheduled.innerHTML = '';
        listCompleted.innerHTML = '';
        
        // Busca tarefas
        let tasks = await db.tasks.orderBy('scheduled_at').reverse().toArray();
        
        // Aplicar filtros
        if (this.state.filters.hideCompleted) {
            tasks = tasks.filter(t => t.status !== 'CONCLUIDO');
        }
        if (this.state.filters.status !== 'all') {
            tasks = tasks.filter(t => t.status === this.state.filters.status);
        }
        
        let inProgressCount = 0;
        let scheduledCount = 0;
        let completedCount = 0;

        for (const task of tasks) {
            const itemEl = this.createTaskItem(task);
            
            if (task.status === 'EM_ANDAMENTO') {
                listInProgress.appendChild(itemEl);
                inProgressCount++;
            } else if (task.status === 'AGENDADO' || task.status === 'PARCIALMENTE_EXECUTADO' || task.status === 'NAO_EXECUTADO') {
                listScheduled.appendChild(itemEl);
                scheduledCount++;
            } else if (task.status === 'CONCLUIDO') {
                listCompleted.appendChild(itemEl);
                completedCount++;
            }
            // CANCELADO não aparece na listagem
        }
        
        // Atualizar Contadores
        countInProgress.textContent = inProgressCount;
        countScheduled.textContent = scheduledCount;
        countCompleted.textContent = completedCount;
        
        // Mostrar/Esconder seções
        if (inProgressCount > 0) secInProgress.classList.remove('hidden'); else secInProgress.classList.add('hidden');
        if (scheduledCount > 0) secScheduled.classList.remove('hidden'); else secScheduled.classList.add('hidden');
        if (completedCount > 0) secCompleted.classList.remove('hidden'); else secCompleted.classList.add('hidden');
        
        if (inProgressCount === 0 && scheduledCount === 0 && completedCount === 0) {
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
        }
        
        // Update icons
        if (window.lucide) lucide.createIcons();
    },

    // Cria um item da lista de tarefas
    createTaskItem(task) {
        const tplItem = document.getElementById('tpl-task-item').content.cloneNode(true);
        const card = tplItem.querySelector('.task-card');
        
        card.dataset.id = task.id;
        this.fillTaskItemData(card, task);

        card.addEventListener('click', () => {
            this.navigate('detail', { taskId: task.id });
        });

        return tplItem;
    },

    async fillTaskItemData(card, task) {
        let clientName = '';
        let addressText = '';
        let taskTypeText = '';

        if (task.source === 'MAINTENANCE') {
            clientName = task.client_name || '—';
            addressText = `Manutenção • ${task.asset_name || ''}`;
            taskTypeText = task.asset_name || 'Manutenção';
        } else {
            const order = await db.orders.get(task.service_order_id);
            const prop = order ? await db.properties.get(order.client_property_id) : null;
            const client = prop ? await db.clients.get(prop.client_id) : null;
            clientName = client ? client.name : '';
            if (order) addressText += `OS #${order.number} • `;
            if (prop) addressText += `${prop.address}, ${prop.number} - ${prop.neighborhood}`;
            taskTypeText = task.task_type;
        }

        card.querySelector('.client-name').textContent = clientName;
        card.querySelector('.property-address').textContent = addressText;
        card.querySelector('.task-type').textContent = taskTypeText;
        
        const dateScheduled = new Date(task.scheduled_at);

        const statusBadge = card.querySelector('.task-status-badge');
        statusBadge.textContent = this.translateStatus(task.status);
        
        // Reset classes
        card.className = 'task-card group relative block rounded-xl border border-slate-200 bg-white transition-all shadow-sm cursor-pointer active:scale-[0.98] border-l-4';
        statusBadge.className = 'task-status-badge inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold whitespace-nowrap';

        // Estilização consistente com a seção (Status)
        if (task.status === 'AGENDADO') {
            card.classList.add('border-l-blue-500', 'hover:border-blue-300');
            statusBadge.classList.add('bg-blue-50', 'text-blue-700');
        } else if (task.status === 'EM_ANDAMENTO') {
            card.classList.add('border-l-amber-500', 'hover:border-amber-300');
            statusBadge.classList.add('bg-amber-50', 'text-amber-700');
        } else if (task.status === 'CONCLUIDO') {
            card.classList.add('border-l-emerald-500', 'hover:border-emerald-300');
            statusBadge.classList.add('bg-emerald-50', 'text-emerald-700');
        } else if (task.status === 'PARCIALMENTE_EXECUTADO') {
            card.classList.add('border-l-orange-500', 'hover:border-orange-300');
            statusBadge.classList.add('bg-orange-50', 'text-orange-700');
        } else if (task.status === 'NAO_EXECUTADO') {
            card.classList.add('border-l-red-400', 'hover:border-red-300');
            statusBadge.classList.add('bg-red-50', 'text-red-700');
        } else {
            card.classList.add('border-l-slate-400');
            statusBadge.classList.add('bg-slate-100', 'text-slate-600');
        }

        // Datas - IHC: Neutralizadas para não misturar cores e focar no status principal
        const taskDatesContainer = card.querySelector('.task-dates');
        if (taskDatesContainer) {
            let datesHtml = `<div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium text-slate-500 bg-slate-50 border border-slate-100" title="Agendado">
                <i data-lucide="calendar" class="h-3 w-3"></i> 
                <span>Agendado: ${dateScheduled.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
            </div>`;
            
            if (task.started_at) {
                const dateStart = new Date(task.started_at);
                datesHtml += `<div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium text-slate-500 bg-slate-50 border border-slate-100" title="Iniciou">
                    <i data-lucide="play-circle" class="h-3 w-3"></i> 
                    <span>Iniciado: ${dateStart.toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>`;
            }
            if (task.finished_at) {
                const dateFinish = new Date(task.finished_at);
                datesHtml += `<div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium text-slate-500 bg-slate-50 border border-slate-100" title="Finalizou">
                    <i data-lucide="check-circle" class="h-3 w-3"></i> 
                    <span>Finalizado: ${dateFinish.toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>`;
            }
            
            taskDatesContainer.innerHTML = datesHtml;
            taskDatesContainer.classList.remove('hidden');
        }
    },

    translateStatus(status) {
        const map = {
            'AGENDADO': 'Agendado',
            'EM_ANDAMENTO': 'Em Execução',
            'CONCLUIDO': 'Finalizado',
            'CANCELADO': 'Cancelado',
            'PARCIALMENTE_EXECUTADO': 'Parcialmente Executado',
            'NAO_EXECUTADO': 'Não Executado',
        };
        return map[status] || status;
    },

    // ─── DETALHE COM ABAS ────────────────────────────────────────────────────

    async renderTaskDetail(container, taskId) {
        let task = await db.tasks.get(taskId);
        if (!task) {
            const allTasks = await db.tasks.toArray();
            task = allTasks.find(t => String(t.id) === String(taskId));
        }
        if (!task) {
            container.innerHTML = '<div class="p-10 text-center text-slate-500">Tarefa não encontrada.</div>';
            return;
        }

        const isMaintenance = task.source === 'MAINTENANCE';
        let order = null, prop = null, client = null;
        if (!isMaintenance) {
            order = await db.orders.get(task.service_order_id);
            prop = order ? await db.properties.get(order.client_property_id) : null;
            client = prop ? await db.clients.get(prop.client_id) : null;
        }

        const tplDetail = document.getElementById('tpl-task-detail').content.cloneNode(true);
        const root = tplDetail.querySelector('.detail-root');

        this.state.detailRoot = root;
        this.state.currentTaskId = taskId;

        this._fillDetailHeader(root, task, client, prop);
        this._setupTabs(root, taskId, isMaintenance);

        await this._initInfoTab(root, task, order, prop, client, taskId, isMaintenance);
        if (!isMaintenance) {
            await this._initItemsTab(root, task, order);
            await this._initChecklistTab(root, task, taskId);
        }
        await this._initMediaTab(root, task, taskId);
        await this._initOccurrencesTab(root, task, taskId);
        await this._initSignatureTab(root, task, taskId, order);
        await this._initHistoryTab(root, task, taskId);

        root.querySelector('#btn-back').addEventListener('click', () => {
            this.state.detailRoot = null;
            this.navigate('list');
        });

        container.appendChild(root);
        this._switchTab(root, 'info');
    },

    _fillDetailHeader(root, task, client, prop) {
        const clientNameEl = root.querySelector('.client-name');
        const addressEl = root.querySelector('.property-address');
        const statusBadge = root.querySelector('.task-status-badge');

        if (task.source === 'MAINTENANCE') {
            clientNameEl.textContent = task.client_name || '—';
            addressEl.textContent = task.asset_name || 'Manutenção';
        } else {
            clientNameEl.textContent = client ? client.name : '—';
            addressEl.textContent = prop ? prop.full_address : '';
        }

        statusBadge.textContent = this.translateStatus(task.status);
        if (task.status === 'AGENDADO') statusBadge.classList.add('bg-blue-50', 'text-blue-600', 'border-blue-100');
        else if (task.status === 'EM_ANDAMENTO') statusBadge.classList.add('bg-amber-50', 'text-amber-600', 'border-amber-100');
        else if (task.status === 'CONCLUIDO') statusBadge.classList.add('bg-emerald-50', 'text-emerald-600', 'border-emerald-100');
        else if (task.status === 'PARCIALMENTE_EXECUTADO') statusBadge.classList.add('bg-orange-50', 'text-orange-600', 'border-orange-100');
        else if (task.status === 'NAO_EXECUTADO') statusBadge.classList.add('bg-red-50', 'text-red-600', 'border-red-100');
    },

    _setupTabs(root, taskId, isMaintenance) {
        if (isMaintenance) {
            const hideFor = ['itens', 'checklist'];
            hideFor.forEach(tab => {
                const btn = root.querySelector(`.tab-btn[data-tab="${tab}"]`);
                if (btn) btn.classList.add('hidden');
            });
        }

        root.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this._switchTab(root, btn.dataset.tab);
            });
        });
    },

    _switchTab(root, tabName) {
        this.state.activeTab = tabName;

        root.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.toggle('hidden', panel.id !== `tab-panel-${tabName}`);
        });

        root.querySelectorAll('.tab-btn').forEach(btn => {
            const isActive = btn.dataset.tab === tabName;
            btn.classList.toggle('text-blue-600', isActive);
            btn.classList.toggle('border-blue-600', isActive);
            btn.classList.toggle('text-slate-500', !isActive);
            btn.classList.toggle('border-transparent', !isActive);
        });

        // Rola a aba ativa para o centro (scroll horizontal)
        const activeBtn = root.querySelector(`.tab-btn[data-tab="${tabName}"]`);
        if (activeBtn) {
            activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }

        // Lazy init do signature pad na primeira vez que a aba aparece
        if (tabName === 'assinatura' && !this._sigPadInited) {
            this._initSignaturePad(root);
        }

        if (window.lucide) lucide.createIcons();
    },

    async _initInfoTab(root, task, order, prop, client, taskId, isMaintenance) {
        const panel = root.querySelector('#tab-panel-info');

        // Card: Agendamento + tipo
        const date = new Date(task.scheduled_at);
        const formattedDate = date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
        const formattedTime = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        const taskTypeLabel = isMaintenance
            ? `${task.asset_category ? task.asset_category + ' • ' : ''}${task.asset_name || ''}`
            : (task.task_type || '');

        panel.innerHTML = `
            <div class="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm space-y-4">
                <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100">
                    <div class="flex items-center justify-center w-10 h-10 rounded-lg bg-white shadow-sm text-blue-500 shrink-0">
                        <i data-lucide="calendar" class="h-5 w-5"></i>
                    </div>
                    <div>
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-wider leading-none mb-0.5">Agendamento</p>
                        <p class="task-time text-sm font-bold text-slate-700">${formattedDate} • ${formattedTime}</p>
                        <p class="text-xs text-slate-500 mt-0.5">${taskTypeLabel}</p>
                    </div>
                </div>
                ${task.notes ? `
                <div class="p-3 rounded-xl bg-amber-50 border border-amber-100">
                    <p class="text-[10px] font-bold text-amber-700 uppercase tracking-wider mb-1">Observações</p>
                    <p class="text-sm text-amber-900 leading-relaxed">${task.notes}</p>
                </div>` : ''}
            </div>

            <div class="grid grid-cols-3 gap-2">
                <button type="button" id="info-btn-gps" class="flex flex-col items-center justify-center gap-1.5 px-2 py-3.5 min-h-[56px] rounded-xl bg-white border border-slate-200 hover:bg-slate-50 transition-colors shadow-sm">
                    <i data-lucide="navigation" class="h-5 w-5 text-blue-600"></i>
                    <span class="text-[10px] font-bold text-slate-600 uppercase">Navegar</span>
                </button>
                <button type="button" id="info-btn-update-gps" class="${isMaintenance ? 'hidden' : ''} flex flex-col items-center justify-center gap-1.5 px-2 py-3.5 min-h-[56px] rounded-xl bg-white border border-slate-200 hover:bg-slate-50 transition-colors shadow-sm">
                    <i data-lucide="map-pin" class="h-5 w-5 text-slate-500"></i>
                    <span class="text-[10px] font-bold text-slate-600 uppercase text-center leading-tight">Atualizar<br>GPS</span>
                </button>
                <a id="info-link-whatsapp" href="#" class="flex flex-col items-center justify-center gap-1.5 px-2 py-3.5 min-h-[56px] rounded-xl bg-emerald-50 border border-emerald-100 hover:bg-emerald-100 transition-colors shadow-sm" target="_blank">
                    <i data-lucide="message-circle" class="h-5 w-5 text-emerald-600"></i>
                    <span class="text-[10px] font-bold text-emerald-700 uppercase">WhatsApp</span>
                </a>
            </div>
        `;

        // GPS Navegar
        const btnGps = panel.querySelector('#info-btn-gps');
        const lat = isMaintenance ? (task.property_lat || '') : (prop ? (prop.latitude || '') : '');
        const lng = isMaintenance ? (task.property_lng || '') : (prop ? (prop.longitude || '') : '');
        const address = isMaintenance ? (task.property_address || '') : (prop ? prop.full_address : '');
        if (btnGps) {
            btnGps.dataset.gpsLat = lat;
            btnGps.dataset.gpsLng = lng;
            btnGps.dataset.gpsAddress = address;
            btnGps.dataset.gpsTrigger = 'true';
        }

        // GPS Update
        if (!isMaintenance) {
            const btnUpdateGps = panel.querySelector('#info-btn-update-gps');
            if (btnUpdateGps && prop) {
                btnUpdateGps.addEventListener('click', async () => {
                    if (!confirm('Deseja atualizar as coordenadas de GPS com sua localização atual?')) return;
                    if (!('geolocation' in navigator)) { alert('Geolocalização não suportada.'); return; }
                    const orig = btnUpdateGps.innerHTML;
                    btnUpdateGps.innerHTML = '<i data-lucide="loader-2" class="h-5 w-5 animate-spin text-slate-500"></i>';
                    if (window.lucide) lucide.createIcons();
                    navigator.geolocation.getCurrentPosition(async (pos) => {
                        prop.latitude = pos.coords.latitude;
                        prop.longitude = pos.coords.longitude;
                        await db.properties.put(prop);
                        await OfflineDB.enqueueSyncItem('PROPERTY_GPS_UPDATE', { property_id: prop.id, latitude: prop.latitude, longitude: prop.longitude });
                        if (btnGps) { btnGps.dataset.gpsLat = prop.latitude; btnGps.dataset.gpsLng = prop.longitude; }
                        alert('Coordenadas atualizadas!');
                        btnUpdateGps.innerHTML = orig;
                        if (window.lucide) lucide.createIcons();
                    }, () => {
                        alert('Erro ao obter localização.');
                        btnUpdateGps.innerHTML = orig;
                        if (window.lucide) lucide.createIcons();
                    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
                });
            }
        }

        // WhatsApp
        const linkWa = panel.querySelector('#info-link-whatsapp');
        if (linkWa) {
            let phone = isMaintenance ? task.client_phone : (client && client.phones && client.phones.length > 0 ? client.phones[0] : null);
            if (phone) {
                const clean = phone.replace(/\D/g, '');
                linkWa.href = `https://wa.me/${clean.length <= 11 ? '55' + clean : clean}`;
            } else {
                linkWa.classList.add('hidden');
            }
        }

        // Botão de Iniciar (se AGENDADO)
        if (task.status === 'AGENDADO') {
            const startBtn = document.createElement('button');
            startBtn.id = 'info-btn-start';
            startBtn.className = 'w-full group relative flex items-center justify-center gap-3 rounded-2xl bg-blue-600 p-5 text-base font-bold text-white hover:bg-blue-700 transition-all shadow-xl shadow-blue-200 active:scale-95 overflow-hidden mt-2';
            startBtn.innerHTML = `
                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000"></div>
                <i data-lucide="play" class="h-5 w-5 fill-white"></i>
                INICIAR SERVIÇO AGORA
            `;
            startBtn.onclick = () => this.startTask(task.id);
            panel.appendChild(startBtn);
        } else if (task.status === 'EM_ANDAMENTO') {
            const badge = document.createElement('div');
            badge.className = 'flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200';
            badge.innerHTML = `
                <span class="flex h-2.5 w-2.5 rounded-full bg-amber-500 animate-pulse shrink-0"></span>
                <span class="text-xs font-bold text-amber-800">Serviço em andamento</span>
            `;
            panel.appendChild(badge);
        } else if (task.status === 'CONCLUIDO') {
            const badge = document.createElement('div');
            badge.className = 'flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200';
            badge.innerHTML = `
                <i data-lucide="check-circle" class="h-4 w-4 text-emerald-600 shrink-0"></i>
                <span class="text-xs font-bold text-emerald-800">Serviço concluído</span>
            `;
            panel.appendChild(badge);
        }
    },

    async _initItemsTab(root, task, order) {
        const panel = root.querySelector('#tab-panel-itens');
        const items = await db.task_items.where('task_id').equals(String(task.id)).toArray();

        if (items.length === 0) {
            panel.innerHTML = `
                <div class="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                    <i data-lucide="package" class="h-8 w-8 text-slate-300 mx-auto mb-3"></i>
                    <p class="text-sm font-medium text-slate-500">Sem itens nesta etapa</p>
                    <p class="text-xs text-slate-400 mt-1">Os itens aparecerão aqui após a próxima sincronização.</p>
                </div>
            `;
            return;
        }

        const total = items.reduce((acc, i) => acc + parseFloat(i.total_price || 0), 0);

        panel.innerHTML = `
            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div class="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
                    <span class="text-xs font-bold text-slate-700 uppercase tracking-wide">Itens da Etapa</span>
                    <span class="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">${items.length} ${items.length === 1 ? 'item' : 'itens'}</span>
                </div>
                <div class="divide-y divide-slate-50">
                    ${items.map(item => `
                        <div class="px-4 py-3">
                            <p class="text-sm font-semibold text-slate-800">${item.description || '—'}</p>
                            <p class="text-[10px] text-slate-400 mt-0.5">${item.product_code ? `Cód: ${item.product_code} • ` : ''}Qtd: ${parseFloat(item.quantity || 1).toLocaleString('pt-BR')}</p>
                        </div>
                    `).join('')}
                </div>
                <div class="px-4 py-3 border-t border-slate-100 flex justify-between items-center bg-slate-50/60">
                    <span class="text-xs font-bold text-slate-500 uppercase tracking-wide">Total</span>
                    <span class="text-sm font-extrabold text-slate-900">R$ ${total.toFixed(2).replace('.', ',')}</span>
                </div>
            </div>
        `;
    },

    async _initChecklistTab(root, task, taskId) {
        const panel = root.querySelector('#tab-panel-checklist');
        const isCompleted = task.status === 'CONCLUIDO';

        const responses = await db.checklist_responses.where('task_id').equals(taskId).toArray();

        if (responses.length === 0) {
            panel.innerHTML = `
                <div class="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                    <i data-lucide="check-square" class="h-8 w-8 text-slate-300 mx-auto mb-3"></i>
                    <p class="text-sm font-medium text-slate-500">Sem checklist para esta etapa</p>
                </div>
            `;
            return;
        }

        await this.renderChecklist(panel, responses, isCompleted);
    },

    async _initMediaTab(root, task, taskId) {
        const panel = root.querySelector('#tab-panel-anexos');
        const isCompleted = task.status === 'CONCLUIDO';

        const mediaContainer = document.createElement('div');
        mediaContainer.id = 'tab-media-grid';
        mediaContainer.className = 'grid grid-cols-3 gap-2';
        panel.appendChild(mediaContainer);

        await this.renderOfflineMedia(mediaContainer, taskId, null);

        if (!isCompleted) {
            const btnRow = document.createElement('div');
            btnRow.className = 'flex gap-2';
            btnRow.innerHTML = `
                <button id="tab-btn-add-media" class="flex-1 flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 p-4 text-[10px] font-bold text-slate-500 hover:border-blue-300 hover:text-blue-600 transition-all bg-slate-50/50">
                    <i data-lucide="camera" class="h-4 w-4"></i> Tirar Fotos
                </button>
                <button id="tab-btn-add-video" class="flex-1 flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 p-4 text-[10px] font-bold text-slate-500 hover:border-blue-300 hover:text-blue-600 transition-all bg-slate-50/50">
                    <i data-lucide="video" class="h-4 w-4"></i> Gravar Vídeo
                </button>
            `;
            panel.appendChild(btnRow);
            panel.querySelector('#tab-btn-add-media').onclick = () => this.captureMedia(taskId, null, mediaContainer);
            panel.querySelector('#tab-btn-add-video').onclick = () => this.captureVideo(taskId, null, mediaContainer);
        } else {
            const mediaCount = await db.media.where('task_id').equals(taskId).count();
            if (mediaCount === 0) {
                panel.innerHTML = `
                    <div class="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                        <i data-lucide="camera-off" class="h-8 w-8 text-slate-300 mx-auto mb-3"></i>
                        <p class="text-sm font-medium text-slate-500">Nenhum anexo registrado</p>
                    </div>
                `;
            }
        }
    },

    async _initOccurrencesTab(root, task, taskId) {
        const panel = root.querySelector('#tab-panel-ocorrencias');
        const isCompleted = task.status === 'CONCLUIDO';

        // Banner de BLOCKING (será atualizado por _refreshOccurrencesTab)
        const blockingBanner = document.createElement('div');
        blockingBanner.id = 'tab-blocking-banner';
        blockingBanner.className = 'hidden items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200';
        blockingBanner.innerHTML = `
            <i data-lucide="shield-alert" class="h-5 w-5 text-red-600 shrink-0 mt-0.5"></i>
            <div>
                <p class="text-sm font-bold text-red-800">Impedimento registrado</p>
                <p class="text-xs text-red-600 mt-0.5">Este serviço possui uma ocorrência impeditiva. Revise antes de concluir.</p>
            </div>
        `;
        panel.appendChild(blockingBanner);

        // Lista de ocorrências
        const occList = document.createElement('div');
        occList.id = 'tab-occurrence-list';
        occList.className = 'space-y-2';
        panel.appendChild(occList);

        // Botão adicionar
        if (!isCompleted) {
            const btnAdd = document.createElement('button');
            btnAdd.id = 'tab-btn-add-occurrence';
            btnAdd.className = 'w-full flex items-center justify-center gap-2 rounded-xl bg-white border border-slate-200 py-2.5 px-4 text-sm font-bold text-slate-600 hover:bg-slate-50 transition-all shadow-sm active:scale-95';
            btnAdd.innerHTML = '<i data-lucide="plus-circle" class="h-4 w-4"></i> Registrar Ocorrência / Impedimento';
            btnAdd.onclick = () => this.openOccurrenceModal(taskId);
            panel.appendChild(btnAdd);
        }

        await this._refreshOccurrencesTab(taskId);
    },

    async _refreshOccurrencesTab(taskId) {
        const root = this.state.detailRoot;
        if (!root) return;

        const occList = root.querySelector('#tab-occurrence-list');
        const blockingBanner = root.querySelector('#tab-blocking-banner');
        const tabOccBadge = root.querySelector('#tab-occ-badge');

        if (occList) await this.renderOccurrences(occList, taskId);

        // Verifica IMPEDITIVA
        const occurrences = await db.occurrences.where('task_id').equals(taskId).toArray();
        const hasBlocking = occurrences.some(o => o.category === 'IMPEDITIVA');

        if (blockingBanner) {
            blockingBanner.classList.toggle('hidden', !hasBlocking);
            blockingBanner.classList.toggle('flex', hasBlocking);
        }
        if (tabOccBadge) tabOccBadge.classList.toggle('hidden', !hasBlocking);

        // Atualiza aviso na aba Assinatura
        const sigBlockingBanner = root.querySelector('#sig-blocking-banner');
        if (sigBlockingBanner) {
            sigBlockingBanner.classList.toggle('hidden', !hasBlocking);
            sigBlockingBanner.classList.toggle('flex', hasBlocking);
        }
    },

    async _initSignatureTab(root, task, taskId, order) {
        const panel = root.querySelector('#tab-panel-assinatura');
        const isCompleted = task.status === 'CONCLUIDO';

        if (task.status === 'AGENDADO') {
            panel.innerHTML = `
                <div class="flex flex-col items-center justify-center gap-4 py-12 text-center">
                    <div class="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center">
                        <i data-lucide="play-circle" class="h-8 w-8 text-slate-400"></i>
                    </div>
                    <div>
                        <p class="text-sm font-bold text-slate-700">Serviço não iniciado</p>
                        <p class="text-xs text-slate-400 mt-1">Inicie o serviço na aba Info antes de concluir.</p>
                    </div>
                    <button class="flex items-center gap-2 px-5 py-3 rounded-xl bg-blue-600 text-white text-sm font-bold active:scale-95 transition-all shadow-lg shadow-blue-200" onclick="OfflineApp._switchTab(OfflineApp.state.detailRoot, 'info')">
                        <i data-lucide="arrow-left" class="h-4 w-4"></i> Ir para Info
                    </button>
                </div>
            `;
            return;
        }

        if (isCompleted) {
            // Resumo de conclusão
            panel.innerHTML = `
                <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
                    <div class="flex items-center gap-2">
                        <div class="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center">
                            <i data-lucide="check-circle" class="h-4 w-4 text-emerald-600"></i>
                        </div>
                        <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wide">Serviço Finalizado</h3>
                    </div>
                    <div>
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Recebido por</p>
                        <p class="text-sm font-bold text-slate-900">${task.customer_name || '—'}</p>
                    </div>
                    ${task.technical_notes ? `
                    <div class="pt-3 border-t border-slate-50">
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Relatório</p>
                        <p class="text-sm text-slate-600 italic leading-relaxed">${task.technical_notes}</p>
                    </div>` : ''}
                    ${task.customer_signature ? `
                    <div class="pt-3 border-t border-slate-50">
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Assinatura</p>
                        <div class="rounded-xl border border-slate-100 bg-slate-50 p-3 flex items-center justify-center">
                            <img src="${task.customer_signature}" alt="Assinatura" class="max-h-28 w-auto object-contain filter grayscale contrast-125 mix-blend-multiply">
                        </div>
                    </div>` : ''}
                    ${task.payment_method && task.payment_amount ? `
                    <div class="pt-3 border-t border-slate-50 flex items-center gap-2">
                        <span class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">${task.payment_method}</span>
                        <p class="text-sm font-bold text-slate-900">R$ ${parseFloat(task.payment_amount).toFixed(2).replace('.', ',')}</p>
                    </div>` : ''}
                </div>
            `;
            return;
        }

        // Estado EM_ANDAMENTO: formulário de conclusão inline
        const balanceDue = order ? parseFloat(order.balance_due || 0) : 0;
        this._sigPadInited = false;

        panel.innerHTML = `
            <!-- Banner de Bloqueio (BLOCKING) -->
            <div id="sig-blocking-banner" class="hidden items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200">
                <i data-lucide="shield-alert" class="h-5 w-5 text-red-600 shrink-0 mt-0.5"></i>
                <div class="flex-1">
                    <p class="text-sm font-bold text-red-800">Impedimento registrado</p>
                    <p class="text-xs text-red-600 mt-0.5">Há uma ocorrência impeditiva. Você pode concluir parcialmente ou registrar como incompleto.</p>
                </div>
            </div>

            <!-- Toggle: Concluído / Incompleto -->
            <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div class="p-1 m-1.5 bg-slate-100 rounded-xl flex gap-1">
                    <button id="sig-toggle-complete" class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-xs font-bold transition-all bg-white text-emerald-700 shadow-sm" data-mode="complete">
                        <i data-lucide="check-circle" class="h-3.5 w-3.5"></i> Concluído
                    </button>
                    <button id="sig-toggle-incomplete" class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-xs font-bold transition-all text-slate-500" data-mode="incomplete">
                        <i data-lucide="alert-triangle" class="h-3.5 w-3.5"></i> Incompleto
                    </button>
                </div>
            </div>

            <!-- Painel: Concluído -->
            <div id="sig-panel-complete" class="space-y-4">
                <!-- Nome -->
                <div class="space-y-1.5">
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest">Nome de quem recebeu</label>
                    <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <i data-lucide="user" class="h-4 w-4 text-slate-400"></i>
                        </div>
                        <input type="text" id="sig-customer-name" class="w-full pl-10 rounded-xl border border-slate-200 bg-slate-50/50 text-sm py-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" placeholder="Ex: Maria Silva">
                    </div>
                </div>

                <!-- Relatório -->
                <div class="space-y-1.5">
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest">Relatório / Observações</label>
                    <textarea id="sig-notes" rows="3" class="w-full rounded-xl border border-slate-200 bg-slate-50/50 text-sm py-3 px-4 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none" placeholder="Descreva brevemente o que foi realizado..."></textarea>
                </div>

                <!-- Assinatura (opcional) -->
                <div class="space-y-1.5">
                    <div class="flex items-center justify-between">
                        <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest">Assinatura Digital <span class="normal-case font-normal text-slate-400">(opcional)</span></label>
                        <button id="sig-btn-clear" class="text-[10px] font-bold text-red-400 hover:text-red-600 uppercase tracking-wider">Limpar</button>
                    </div>
                    <div class="border-2 border-slate-100 rounded-2xl overflow-hidden bg-slate-50 relative group">
                        <canvas id="sig-canvas" class="w-full h-44 touch-none"></canvas>
                        <div id="sig-placeholder" class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none opacity-20 transition-opacity group-focus-within:opacity-0">
                            <i data-lucide="pen-tool" class="h-7 w-7 text-slate-400 mb-1.5"></i>
                            <p class="text-xs font-medium text-slate-500">Assine aqui</p>
                        </div>
                    </div>
                </div>

                <!-- Pagamento (se houver saldo) -->
                ${balanceDue > 0 ? `
                <div id="sig-payment-section" class="space-y-3 pt-4 border-t border-slate-100">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-slate-700 uppercase tracking-widest">Recebimento <span class="normal-case font-normal text-slate-400">(opcional)</span></h4>
                        <span class="text-sm font-black text-red-600">R$ ${balanceDue.toFixed(2).replace('.', ',')}</span>
                    </div>
                    <div id="sig-payment-methods-grid" class="grid grid-cols-3 gap-2">
                        <!-- Injetado via JS -->
                    </div>
                    <div id="sig-payment-details" class="hidden animate-in fade-in slide-in-from-top-2 duration-200">
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Valor Recebido</label>
                        <div class="relative">
                            <span class="absolute left-4 top-1/2 -translate-y-1/2 text-sm font-bold text-slate-400">R$</span>
                            <input type="number" step="0.01" id="sig-payment-amount" class="w-full pl-10 pr-4 py-4 rounded-2xl bg-slate-50 border-2 border-slate-100 text-lg font-black text-slate-900 focus:border-blue-500 transition-all outline-none" value="${balanceDue.toFixed(2)}" placeholder="0,00">
                        </div>
                    </div>
                </div>` : ''}

                <!-- Botão Confirmar -->
                <button id="sig-btn-confirm" class="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-white font-bold py-4 rounded-2xl shadow-xl shadow-slate-200 active:scale-95 transition-all">
                    <i data-lucide="check" class="h-5 w-5"></i>
                    CONFIRMAR E FINALIZAR
                </button>
            </div>

            <!-- Painel: Incompleto -->
            <div id="sig-panel-incomplete" class="hidden space-y-4">
                <div class="bg-amber-50 border border-amber-200 rounded-2xl p-5 space-y-3">
                    <div class="flex items-start gap-3">
                        <i data-lucide="alert-triangle" class="h-5 w-5 text-amber-600 shrink-0 mt-0.5"></i>
                        <div>
                            <p class="text-sm font-bold text-amber-900">Serviço não concluído</p>
                            <p class="text-xs text-amber-700 mt-1 leading-relaxed">Registre o impedimento na aba Ocorrências antes de salvar como incompleto. O gestor será notificado para revisar.</p>
                        </div>
                    </div>
                    <button class="w-full flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-700 text-white font-bold py-3 rounded-xl active:scale-95 transition-all" onclick="OfflineApp._switchTab(OfflineApp.state.detailRoot, 'ocorrencias')">
                        <i data-lucide="alert-triangle" class="h-4 w-4"></i> Ir para Ocorrências
                    </button>
                </div>

                <div class="space-y-1.5">
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest">Motivo / Relatório</label>
                    <textarea id="sig-incomplete-notes" rows="3" class="w-full rounded-xl border border-slate-200 bg-slate-50/50 text-sm py-3 px-4 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none resize-none" placeholder="Descreva o motivo da não conclusão..."></textarea>
                </div>

                <button id="sig-btn-register-incomplete" class="w-full flex items-center justify-center gap-2 bg-amber-600 hover:bg-amber-700 text-white font-bold py-4 rounded-2xl shadow-xl shadow-amber-200 active:scale-95 transition-all">
                    <i data-lucide="save" class="h-5 w-5"></i>
                    REGISTRAR COMO INCOMPLETO
                </button>
            </div>
        `;

        // Toggle complete/incomplete
        const btnToggleComplete = panel.querySelector('#sig-toggle-complete');
        const btnToggleIncomplete = panel.querySelector('#sig-toggle-incomplete');
        const panelComplete = panel.querySelector('#sig-panel-complete');
        const panelIncomplete = panel.querySelector('#sig-panel-incomplete');

        btnToggleComplete.onclick = () => {
            btnToggleComplete.classList.add('bg-white', 'text-emerald-700', 'shadow-sm');
            btnToggleComplete.classList.remove('text-slate-500');
            btnToggleIncomplete.classList.remove('bg-white', 'text-amber-700', 'shadow-sm');
            btnToggleIncomplete.classList.add('text-slate-500');
            panelComplete.classList.remove('hidden');
            panelIncomplete.classList.add('hidden');
        };

        btnToggleIncomplete.onclick = () => {
            btnToggleIncomplete.classList.add('bg-white', 'text-amber-700', 'shadow-sm');
            btnToggleIncomplete.classList.remove('text-slate-500');
            btnToggleComplete.classList.remove('bg-white', 'text-emerald-700', 'shadow-sm');
            btnToggleComplete.classList.add('text-slate-500');
            panelIncomplete.classList.remove('hidden');
            panelComplete.classList.add('hidden');
        };

        // Limpar assinatura
        const btnClear = panel.querySelector('#sig-btn-clear');
        if (btnClear) btnClear.onclick = () => { if (this.signaturePad) this.signaturePad.clear(); };

        // Pagamento
        if (balanceDue > 0) {
            const methodsGrid = panel.querySelector('#sig-payment-methods-grid');
            const detailsEl = panel.querySelector('#sig-payment-details');
            if (methodsGrid && detailsEl) await this._initPaymentGrid(methodsGrid, detailsEl);
        }

        // Botão Confirmar (concluído)
        const btnConfirm = panel.querySelector('#sig-btn-confirm');
        if (btnConfirm) btnConfirm.onclick = () => this._confirmFinish(taskId, panel);

        // Botão Registrar Incompleto
        const btnIncomplete = panel.querySelector('#sig-btn-register-incomplete');
        if (btnIncomplete) btnIncomplete.onclick = () => this._confirmIncomplete(taskId, panel);

        // Checa ocorrência impeditiva já existente
        const occurrences = await db.occurrences.where('task_id').equals(taskId).toArray();
        const hasBlocking = occurrences.some(o => o.category === 'IMPEDITIVA');
        const sigBlockingBanner = panel.querySelector('#sig-blocking-banner');
        if (sigBlockingBanner && hasBlocking) {
            sigBlockingBanner.classList.remove('hidden');
            sigBlockingBanner.classList.add('flex');
        }
    },

    _initSignaturePad(root) {
        const canvas = root ? root.querySelector('#sig-canvas') : document.getElementById('sig-canvas');
        if (!canvas) return;
        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        canvas.width = canvas.offsetWidth * ratio;
        canvas.height = canvas.offsetHeight * ratio;
        canvas.getContext('2d').scale(ratio, ratio);
        if (this.signaturePad) this.signaturePad.clear();
        this.signaturePad = new SignaturePad(canvas, { backgroundColor: 'rgb(248, 250, 252)' });
        this._sigPadInited = true;
    },

    async _initPaymentGrid(methodsGrid, detailsEl) {
        methodsGrid.innerHTML = '';
        const methods = await db.payment_methods.toArray();
        if (methods.length === 0) {
            methodsGrid.innerHTML = '<p class="col-span-full text-center text-[10px] text-slate-400 py-2">Nenhum método disponível.</p>';
            return;
        }
        this.state.payment.method = null;
        methods.forEach(method => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn-payment-method flex flex-col items-center justify-center gap-1.5 p-3 rounded-xl border-2 border-slate-100 bg-white hover:border-blue-200 transition-all active:scale-95';
            btn.dataset.method = method.descricao;
            let icon = 'credit-card';
            if (method.descricao.toUpperCase().includes('PIX')) icon = 'qr-code';
            if (method.descricao.toUpperCase().includes('DINHEIRO')) icon = 'banknote';
            btn.innerHTML = `
                <div class="p-1.5 rounded-lg bg-slate-50 text-slate-400">
                    <i data-lucide="${icon}" class="h-5 w-5"></i>
                </div>
                <span class="text-[9px] font-black uppercase tracking-tighter text-slate-600">${method.descricao}</span>
            `;
            btn.onclick = () => {
                const isSelected = btn.classList.contains('bg-blue-50');
                methodsGrid.querySelectorAll('.btn-payment-method').forEach(b => {
                    b.classList.remove('bg-blue-50', 'border-blue-500', 'text-blue-600');
                    b.querySelector('div').classList.replace('bg-blue-100', 'bg-slate-50');
                    b.querySelector('div').classList.replace('text-blue-600', 'text-slate-400');
                });
                if (isSelected) {
                    this.state.payment.method = null;
                    detailsEl.classList.add('hidden');
                } else {
                    btn.classList.add('bg-blue-50', 'border-blue-500', 'text-blue-600');
                    btn.querySelector('div').classList.replace('bg-slate-50', 'bg-blue-100');
                    btn.querySelector('div').classList.replace('text-slate-400', 'text-blue-600');
                    this.state.payment.method = btn.dataset.method;
                    detailsEl.classList.remove('hidden');
                }
            };
            methodsGrid.appendChild(btn);
        });
        if (window.lucide) lucide.createIcons();
    },

    async _confirmFinish(taskId, panel) {
        // Valida checklist obrigatório
        const responses = await db.checklist_responses.where('task_id').equals(taskId).toArray();
        const items = await db.checklist_items.toArray();
        const pendingRequired = [];
        for (const resp of responses) {
            const item = items.find(i => i.id === resp.item_id);
            if (item && item.is_required && !resp.status && !resp.completed) pendingRequired.push(item.name);
        }
        if (pendingRequired.length > 0) {
            alert(`Itens obrigatórios não preenchidos:\n\n- ${pendingRequired.join('\n- ')}`);
            return;
        }

        const customerName = panel.querySelector('#sig-customer-name')?.value || '';
        const notes = panel.querySelector('#sig-notes')?.value || '';
        const signatureBase64 = (this.signaturePad && !this.signaturePad.isEmpty()) ? this.signaturePad.toDataURL() : null;

        const paymentSection = panel.querySelector('#sig-payment-section');
        let paymentData = null;
        if (paymentSection) {
            const method = this.state.payment.method;
            const amountEl = panel.querySelector('#sig-payment-amount');
            const amount = parseFloat(amountEl ? amountEl.value : 0);
            if (method) {
                if (amount <= 0) { alert('Informe o valor recebido ou desmarque o método de pagamento.'); return; }
                paymentData = { method, amount };
            }
        }

        const now = new Date().toISOString();
        await db.tasks.update(taskId, {
            status: 'CONCLUIDO',
            finished_at: now,
            customer_name: customerName,
            customer_signature: signatureBase64,
            technical_notes: notes,
            payment_method: paymentData ? paymentData.method : null,
            payment_amount: paymentData ? paymentData.amount : null
        });

        const task = await db.tasks.get(taskId);
        if (task && task.source === 'MAINTENANCE') {
            await OfflineDB.enqueueSyncItem('MAINTENANCE_VISIT_FINISH', {
                visit_id: task.visit_id,
                finished_at: now,
                notes: notes
            });
        } else {
            await OfflineDB.enqueueSyncItem('TASK_FINISH', {
                task_id: taskId,
                finished_at: now,
                data: { customer_name: customerName, customer_signature: signatureBase64, notes, payment: paymentData }
            });
        }

        await this.navigate('list');
    },

    async _confirmIncomplete(taskId, panel) {
        const notes = panel.querySelector('#sig-incomplete-notes')?.value?.trim() || '';
        if (!notes) { alert('Descreva o motivo da não conclusão.'); return; }

        const now = new Date().toISOString();
        await db.tasks.update(taskId, { technical_notes: notes });
        await OfflineDB.enqueueSyncItem('TASK_INCOMPLETE', {
            task_id: taskId,
            data: { notes }
        });

        alert('Serviço registrado como incompleto. O gestor foi notificado.');
        await this.navigate('list');
    },

    async _initHistoryTab(root, task, taskId) {
        const panel = root.querySelector('#tab-panel-historico');
        const occurrences = await db.occurrences.where('task_id').equals(taskId).toArray();

        let html = '<div class="space-y-2">';

        // Eventos cronológicos
        const events = [];
        if (task.scheduled_at) events.push({ icon: 'calendar', color: 'blue', label: 'Agendado', time: task.scheduled_at });
        if (task.started_at) events.push({ icon: 'play-circle', color: 'amber', label: 'Iniciado', time: task.started_at });
        if (task.finished_at) events.push({ icon: 'check-circle', color: 'emerald', label: 'Finalizado', time: task.finished_at });

        for (const ev of events) {
            const d = new Date(ev.time);
            html += `
                <div class="flex items-center gap-3 p-3 bg-white rounded-xl border border-slate-100 shadow-sm">
                    <div class="w-8 h-8 rounded-full bg-${ev.color}-50 flex items-center justify-center shrink-0">
                        <i data-lucide="${ev.icon}" class="h-4 w-4 text-${ev.color}-600"></i>
                    </div>
                    <div>
                        <p class="text-xs font-bold text-slate-800">${ev.label}</p>
                        <p class="text-[10px] text-slate-400">${d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
                    </div>
                </div>
            `;
        }

        if (occurrences.length > 0) {
            html += `<p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest pt-2 pb-1">Ocorrências</p>`;
            for (const occ of occurrences) {
                const catColor = occ.category === 'IMPEDITIVA' ? 'red' : 'amber';
                html += `
                    <div class="flex items-start gap-3 p-3 bg-${catColor}-50 rounded-xl border border-${catColor}-100">
                        <i data-lucide="alert-triangle" class="h-4 w-4 text-${catColor}-600 mt-0.5 shrink-0"></i>
                        <div>
                            <p class="text-xs font-bold text-${catColor}-900">${this.translateOccType(occ.occurrence_type)}</p>
                            <p class="text-[10px] text-${catColor}-700 mt-0.5 leading-relaxed">${occ.description}</p>
                        </div>
                    </div>
                `;
            }
        }

        if (events.length === 0 && occurrences.length === 0) {
            html += `
                <div class="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                    <i data-lucide="clock" class="h-8 w-8 text-slate-300 mx-auto mb-3"></i>
                    <p class="text-sm font-medium text-slate-500">Sem histórico ainda</p>
                </div>
            `;
        }

        html += '</div>';
        panel.innerHTML = html;
    },

    // Manutenção reusa o mesmo template e os mesmos métodos
    async renderMaintenanceTaskDetail(container, task) {
        await this.renderTaskDetail(container, task.id);
    },

    // Assinatura digital
    signaturePad: null,
    _sigPadInited: false,

    // --- Lógica de Ocorrências ---

    async renderOccurrences(container, taskId) {
        const occurrences = await db.occurrences.where('task_id').equals(taskId).toArray();
        container.innerHTML = '';
        
        if (occurrences.length === 0) {
            container.innerHTML = '<p class="text-[10px] text-slate-400 text-center py-2">Nenhuma ocorrência registrada.</p>';
            return 0;
        }

        for (const occ of occurrences) {
            const tpl = document.getElementById('tpl-occurrence-item').content.cloneNode(true);
            tpl.querySelector('.occ-category').textContent = this.translateOccCategory(occ.category);
            tpl.querySelector('.occ-type').textContent = this.translateOccType(occ.occurrence_type);
            tpl.querySelector('.occ-description').textContent = occ.description;
            
            const mediaContainer = tpl.querySelector('.occ-media-container');
            await this.renderOfflineMedia(mediaContainer, taskId, null, occ.id);
            
            container.appendChild(tpl);
        }
        if (window.lucide) lucide.createIcons();
        return occurrences.length;
    },

    translateOccType(type) {
        const map = {
            'ATRASO': 'Atraso',
            'FALTA_MATERIAL': 'Falta de Material',
            'CLIENTE_AUSENTE': 'Cliente Ausente',
            'IMPEDIMENTO_LOCAL': 'Impedimento no Local',
            'ACIONAMENTO_GARANTIA': 'Acionamento de Garantia',
            'OUTRO': 'Outro'
        };
        return map[type] || type;
    },

    translateOccCategory(category) {
        const map = {
            'GERAL': 'Geral',
            'IMPEDITIVA': 'Impeditiva',
            'SOLICITACAO_MATERIAL': 'Solicitação de Material'
        };
        return map[category] || category;
    },

    async openOccurrenceModal(taskId) {
        const modal = document.getElementById('modal-occurrence');
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        document.getElementById('occ-description').value = '';
        
        // --- Gestão de Mídias Temporárias para a nova Ocorrência ---
        const tempId = `temp_${Date.now()}`;
        this.state.currentOccurrenceId = tempId;
        
        await this.refreshOccurrenceMediaGrid(taskId, tempId);

        const closeModal = async () => {
            await this.cleanupTempMedia(taskId, tempId);
            modal.classList.add('hidden');
        };
        document.getElementById('btn-close-occurrence').onclick = closeModal;
        const footerCancel = document.getElementById('btn-close-occurrence-footer');
        if (footerCancel) footerCancel.onclick = closeModal;
        document.getElementById('btn-confirm-occurrence').onclick = () => this.confirmOccurrence(taskId);
        
        if (window.lucide) lucide.createIcons();
    },

    async cleanupTempMedia(taskId, tempId) {
        const media = await db.media.where('task_id').equals(taskId).and(m => String(m.occurrence_id) === String(tempId)).toArray();
        for (const m of media) {
            await db.media.delete(m.id);
            // Também remove da fila de sincronização
            const pending = await db.sync_queue.where('type').equals('MEDIA_UPLOAD').and(q => q.payload.media_id === m.id).toArray();
            for (const q of pending) await db.sync_queue.delete(q.id);
        }
        if (typeof OfflineDB !== 'undefined') OfflineDB.updateUIStatus();
    },

    async refreshOccurrenceMediaGrid(taskId, tempId) {
        const grid = document.getElementById('occ-media-grid');
        if (!grid) return;
        
        await this.renderOfflineMedia(grid, taskId, null, tempId);
        
        // Re-insere o botão de adicionar ao final do grid
        const btn = document.createElement('button');
        btn.id = 'btn-occ-add-media';
        btn.className = 'aspect-square rounded-xl border-2 border-dashed border-slate-200 flex flex-col items-center justify-center gap-1 text-slate-400 hover:text-blue-500 hover:border-blue-200 hover:bg-blue-50 transition-all group';
        btn.innerHTML = `
            <i data-lucide="plus" class="h-6 w-6 group-hover:scale-110 transition-transform"></i>
            <span class="text-[10px] font-bold uppercase tracking-tighter">Adicionar</span>
        `;
        btn.onclick = () => this.captureMedia(taskId, null, grid, tempId);
        grid.appendChild(btn);
        
        // Atualiza contador no cabeçalho da seção
        const count = await db.media.where('task_id').equals(taskId).and(m => String(m.occurrence_id) === String(tempId)).count();
        const countEl = document.getElementById('occ-media-count');
        if (countEl) countEl.textContent = `${count} mídias`;

        if (window.lucide) lucide.createIcons();
    },

    async confirmOccurrence(taskId) {
        const category = document.getElementById('occ-category').value;
        const type = document.getElementById('occ-type').value;
        const description = document.getElementById('occ-description').value;

        if (!description) {
            alert('Por favor, descreva a ocorrência.');
            return;
        }

        const tempId = this.state.currentOccurrenceId;

        const occId = await db.occurrences.add({
            task_id: taskId,
            category,
            occurrence_type: type,
            description,
            status: 'REGISTRADA'
        });

        // --- Vincula mídias temporárias à ocorrência real ---
        if (tempId) {
            const media = await db.media.where('occurrence_id').equals(tempId).toArray();
            for (const m of media) {
                await db.media.update(m.id, { occurrence_id: occId });
                // Atualiza a fila de sincronização
                const pending = await db.sync_queue.where('type').equals('MEDIA_UPLOAD').toArray();
                for (const q of pending) {
                    if (q.payload.media_id === m.id) {
                        q.payload.occurrence_id = occId;
                        await db.sync_queue.put(q);
                    }
                }
            }
        }

        await OfflineDB.enqueueSyncItem('OCCURRENCE_CREATE', {
            task_id: taskId,
            data: { category, occurrence_type: type, description, local_occurrence_id: occId }
        });

        document.getElementById('modal-occurrence').classList.add('hidden');
        this.state.currentOccurrenceId = null;

        await this._refreshOccurrencesTab(taskId);

        // Re-renderiza a seção de ocorrências (compatibilidade com lista legada)
        const occurrenceList = document.getElementById('occurrence-list');
        if (occurrenceList) await this.renderOccurrences(occurrenceList, taskId);
    },

    // --- Lógica de Mídias Offline & Câmera ---
    
    async captureMedia(taskId, responseId, previewContainer, occurrenceId = null) {
        // Sprint 5: Tenta abrir a câmera customizada primeiro
        try {
            this.openCamera(taskId, responseId, previewContainer, occurrenceId);
        } catch (err) {
            console.warn('Câmera customizada falhou, usando fallback:', err);
            this.captureMediaFallback(taskId, responseId, previewContainer, occurrenceId, 'image/*');
        }
    },

    // Sprint 6: Captura de Vídeo via Câmera do Sistema
    async captureVideo(taskId, responseId, previewContainer, occurrenceId = null) {
        this.captureMediaFallback(taskId, responseId, previewContainer, occurrenceId, 'video/*');
    },

    captureMediaFallback(taskId, responseId, previewContainer, occurrenceId, accept = 'image/*,video/*') {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = accept;
        if (accept.includes('video')) input.capture = 'environment';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Salva o Blob
            const mediaId = await db.media.add({
                task_id: taskId,
                response_id: responseId || null,
                occurrence_id: occurrenceId || null,
                type: file.type,
                blob: file,
                status: 'pendente'
            });

            await OfflineDB.enqueueSyncItem('MEDIA_UPLOAD', {
                task_id: taskId,
                media_id: mediaId,
                response_id: responseId || null,
                occurrence_id: occurrenceId || null
            });

            if (occurrenceId && String(occurrenceId).startsWith('temp_')) {
                await this.refreshOccurrenceMediaGrid(taskId, occurrenceId);
            } else {
                this.renderOfflineMedia(previewContainer, taskId, responseId, occurrenceId);
            }
        };
        input.click();
    },

    // Sprint 5: Câmera Customizada com getUserMedia
    async openCamera(taskId, responseId, previewContainer, occurrenceId) {
        const modal = document.getElementById('modal-camera');
        const video = document.getElementById('camera-video');
        
        this.state.camera.capturedBlobs = [];
        this.state.camera.context = { taskId, responseId, previewContainer, occurrenceId };
        
        modal.classList.remove('hidden');
        document.getElementById('camera-preview-grid').innerHTML = '';
        this.updateCameraCount();

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: this.state.camera.facingMode },
                audio: false
            });
            video.srcObject = stream;
            this.state.camera.stream = stream;
        } catch (err) {
            console.error('getUserMedia error:', err);
            throw err;
        }

        // Eventos
        document.getElementById('btn-close-camera').onclick = () => this.closeCamera();
        document.getElementById('btn-capture-shot').onclick = () => this.captureShot();
        document.getElementById('btn-toggle-camera').onclick = () => this.toggleCamera();
        document.getElementById('btn-confirm-camera').onclick = () => this.confirmCamera();
        
        if (window.lucide) lucide.createIcons();
    },

    async captureShot() {
        const video = document.getElementById('camera-video');
        const canvas = document.getElementById('camera-canvas');
        const context = canvas.getContext('2d');

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        canvas.toBlob(async (blob) => {
            this.state.camera.capturedBlobs.push(blob);
            this.updateCameraCount();
            
            // Adiciona miniatura no grid live
            const url = URL.createObjectURL(blob);
            const img = document.createElement('img');
            img.src = url;
            img.className = 'w-12 h-12 rounded-lg object-cover border-2 border-white shadow-md animate-in zoom-in duration-200';
            document.getElementById('camera-preview-grid').prepend(img);
        }, 'image/jpeg', 0.8);
    },

    updateCameraCount() {
        document.getElementById('camera-count').textContent = `${this.state.camera.capturedBlobs.length} fotos`;
    },

    async toggleCamera() {
        this.state.camera.facingMode = this.state.camera.facingMode === 'user' ? 'environment' : 'user';
        if (this.state.camera.stream) {
            this.state.camera.stream.getTracks().forEach(t => t.stop());
        }
        const ctx = this.state.camera.context;
        await this.openCamera(ctx.taskId, ctx.responseId, ctx.previewContainer, ctx.occurrenceId);
    },

    async confirmCamera() {
        const { taskId, responseId, previewContainer, occurrenceId } = this.state.camera.context;
        
        for (const blob of this.state.camera.capturedBlobs) {
            const mediaId = await db.media.add({
                task_id: taskId,
                response_id: responseId || null,
                occurrence_id: occurrenceId || null,
                type: 'image/jpeg',
                blob: blob,
                status: 'pending'
            });

            await OfflineDB.enqueueSyncItem('MEDIA_UPLOAD', {
                task_id: taskId,
                media_id: mediaId,
                response_id: responseId || null,
                occurrence_id: occurrenceId || null
            });
        }

        if (occurrenceId && String(occurrenceId).startsWith('temp_')) {
            await this.refreshOccurrenceMediaGrid(taskId, occurrenceId);
        } else {
            this.renderOfflineMedia(previewContainer, taskId, responseId, occurrenceId);
        }
        this.closeCamera();
    },

    closeCamera() {
        if (this.state.camera.stream) {
            this.state.camera.stream.getTracks().forEach(t => t.stop());
        }
        document.getElementById('modal-camera').classList.add('hidden');
    },

    async renderOfflineMedia(container, taskId, responseId, occurrenceId = null) {
        // Pega se a task já foi concluída, a fim de bloquear exclusões em tarefas finalizadas
        const task = await db.tasks.get(taskId);
        const isCompleted = task ? task.status === 'CONCLUIDO' : false;

        let query = db.media.where('task_id').equals(taskId);
        
        const mediaItems = await query.toArray();
        const filteredItems = mediaItems.filter(item => {
            if (occurrenceId) return String(item.occurrence_id) === String(occurrenceId);
            if (responseId) return String(item.response_id) === String(responseId);
            return !item.response_id && !item.occurrence_id;
        });
        
        container.innerHTML = '';
        const mediaList = filteredItems.map(item => ({
            url: URL.createObjectURL(item.blob),
            isVideo: item.type.startsWith('video/')
        }));

        filteredItems.forEach((item, index) => {
            const media = mediaList[index];
            const div = document.createElement('div');

            const sizeClass = occurrenceId ? 'w-12 h-12 shrink-0' : 'w-full aspect-square';
            div.className = `relative ${sizeClass} rounded-xl overflow-hidden border border-slate-200 bg-slate-100 group cursor-pointer hover:shadow-md hover:ring-2 hover:ring-blue-400 transition-all active:scale-[0.98]`;

            if (media.isVideo) {
                div.innerHTML = `
                    <video src="${media.url}" class="w-full h-full object-cover"></video>
                    <div class="absolute inset-0 bg-black/40 flex items-center justify-center">
                        <i data-lucide="play" class="h-4 w-4 text-white"></i>
                    </div>
                `;
            } else {
                div.innerHTML = `
                    <img src="${media.url}" class="w-full h-full object-cover">
                `;
            }

            // Badge de status da sincronização
            const badgeWrapper = document.createElement('div');
            badgeWrapper.className = 'absolute top-0.5 right-0.5 z-10 pointer-events-none';
            badgeWrapper.innerHTML = `
                <span class="flex h-3 w-3 items-center justify-center rounded-full ${item.status === 'pending' ? 'bg-amber-500' : 'bg-emerald-500'} shadow-sm">
                    <i data-lucide="${item.status === 'pending' ? 'clock' : 'check'}" class="h-2.5 w-2.5 text-white"></i>
                </span>
            `;
            div.appendChild(badgeWrapper);

            div.onclick = () => this.openMediaViewer(mediaList, index);

            if (!isCompleted) {
                // Botão de exclusão FORA da imagem para não obstruir a miniatura
                const wrapper = document.createElement('div');
                const btnDelete = document.createElement('button');
                btnDelete.onclick = (e) => {
                    e.stopPropagation();
                    this.deleteMedia(item.id, taskId, container, responseId, occurrenceId);
                };

                if (occurrenceId) {
                    // Miniaturas pequenas: [img] [trash] lado a lado
                    wrapper.className = 'flex items-center gap-1.5';
                    btnDelete.className = 'h-7 w-7 shrink-0 flex items-center justify-center rounded-lg bg-red-50 border border-red-200 text-red-500 hover:bg-red-100 active:scale-95 transition-all';
                    btnDelete.innerHTML = '<i data-lucide="trash-2" class="h-3.5 w-3.5"></i>';
                } else {
                    // Miniaturas grandes: [img] com botão "Excluir" abaixo
                    wrapper.className = 'flex flex-col gap-1';
                    btnDelete.className = 'w-full flex items-center justify-center gap-1 py-0.5 rounded text-[10px] font-bold text-red-400 hover:text-red-600 transition-colors';
                    btnDelete.innerHTML = '<i data-lucide="trash-2" class="h-3 w-3"></i><span>Excluir</span>';
                }

                wrapper.appendChild(div);
                wrapper.appendChild(btnDelete);
                container.appendChild(wrapper);
            } else {
                container.appendChild(div);
            }
        });

        if (window.lucide) lucide.createIcons();
        return filteredItems.length;
    },

    // Sprint UX: Lógica de exclusão que permite liberdade antes de finalizar as coisas
    async deleteMedia(mediaId, taskId, container, responseId, occurrenceId) {
        if (!confirm('Deseja remover esta mídia antes de enviar?')) return;
        
        // Remove DB
        await db.media.delete(mediaId);
        
        // Remove Fila (Se ainda pendente)
        const pendingQueue = await db.sync_queue.where('type').equals('MEDIA_UPLOAD').toArray();
        const pendingItem = pendingQueue.find(i => String(i.payload.media_id) === String(mediaId));
        if (pendingItem) {
            await db.sync_queue.delete(pendingItem.id);
            if (typeof OfflineDB !== 'undefined') OfflineDB.updateUIStatus();
        }

        // Re-render
        if (occurrenceId && String(occurrenceId).startsWith('temp_')) {
            await this.refreshOccurrenceMediaGrid(taskId, occurrenceId);
        } else {
            this.renderOfflineMedia(container, taskId, responseId, occurrenceId);
        }
    },

    // Sprint UX: Visualizador tela cheia pra validar qualidade de imagem tirada e evitar frustrações
    openMediaViewer(mediaList, index) {
        this.state.mediaViewer.items = mediaList;
        this.state.mediaViewer.index = index;

        const modal = document.getElementById('modal-media-viewer');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        
        this.updateMediaViewerUI();

        document.getElementById('btn-close-viewer').onclick = () => {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.getElementById('media-viewer-display').innerHTML = ''; // Limpa pra não ficar segurando mémória
        };

        document.getElementById('btn-prev-media').onclick = (e) => {
            e.stopPropagation();
            this.navigateMedia(-1);
        };
        document.getElementById('btn-next-media').onclick = (e) => {
            e.stopPropagation();
            this.navigateMedia(1);
        };

        // Suporte a teclado
        const keyHandler = (e) => {
            if (e.key === 'ArrowLeft') this.navigateMedia(-1);
            if (e.key === 'ArrowRight') this.navigateMedia(1);
            if (e.key === 'Escape') closeModal();
        };

        const closeModal = () => {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.getElementById('media-viewer-display').innerHTML = '';
            document.removeEventListener('keydown', keyHandler);
        };

        document.getElementById('btn-close-viewer').onclick = closeModal;
        document.addEventListener('keydown', keyHandler);
    },

    navigateMedia(direction) {
        const newIndex = this.state.mediaViewer.index + direction;
        if (newIndex >= 0 && newIndex < this.state.mediaViewer.items.length) {
            this.state.mediaViewer.index = newIndex;
            this.updateMediaViewerUI();
        }
    },

    updateMediaViewerUI() {
        const { items, index } = this.state.mediaViewer;
        const current = items[index];
        const display = document.getElementById('media-viewer-display');
        const counter = document.getElementById('media-viewer-counter');
        const btnPrev = document.getElementById('btn-prev-media');
        const btnNext = document.getElementById('btn-next-media');

        if (!current) return;

        display.innerHTML = '';
        if (current.isVideo) {
            display.innerHTML = `<video src="${current.url}" controls autoplay playsinline class="max-w-full max-h-full rounded-xl shadow-2xl object-contain animate-in fade-in duration-300"></video>`;
        } else {
            display.innerHTML = `<img src="${current.url}" class="max-w-full max-h-full rounded-xl shadow-2xl object-contain animate-in fade-in zoom-in-95 duration-300">`;
        }

        counter.textContent = `${index + 1} / ${items.length}`;

        if (items.length > 1) {
            btnPrev.classList.toggle('hidden', index === 0);
            btnNext.classList.toggle('hidden', index === items.length - 1);
            counter.classList.remove('hidden');
        } else {
            btnPrev.classList.add('hidden');
            btnNext.classList.add('hidden');
            counter.classList.add('hidden');
        }

        if (window.lucide) lucide.createIcons();
    },

    // Ação de Iniciar Tarefa
    async startTask(taskId) {
        console.log(`🚀 Iniciando tarefa local: ${taskId}`);
        const now = new Date().toISOString();
        const task = await db.tasks.get(taskId);

        await db.tasks.update(taskId, { status: 'EM_ANDAMENTO', started_at: now });

        if (task && task.source === 'MAINTENANCE') {
            await OfflineDB.enqueueSyncItem('MAINTENANCE_VISIT_START', {
                visit_id: task.visit_id,
                started_at: now
            });
        } else {
            await OfflineDB.enqueueSyncItem('TASK_START', {
                task_id: taskId,
                started_at: now
            });
        }

        await this.render();
    },

    // Renderiza o checklist (Sprint 3: 3-state toggle)
    async renderChecklist(container, responses, disabled = false) {
        const taskId = this.state.currentTaskId;
        for (const resp of responses) {
            const item = await db.checklist_items.get(resp.item_id);
            if (!item) continue;

            const tplItem = document.getElementById('tpl-checklist-item').content.cloneNode(true);
            const itemEl = tplItem.querySelector('.checklist-item');
            
            tplItem.querySelector('.item-name').textContent = item.name;
            tplItem.querySelector('.item-description').textContent = item.description;
            
            const btnOk = tplItem.querySelector('.btn-check-ok');
            const btnNa = tplItem.querySelector('.btn-check-na');
            const btnProblem = tplItem.querySelector('.btn-check-problem');
            const evidenceDiv = tplItem.querySelector('.item-evidence');
            
            // Set initial state
            this.updateChecklistUI(itemEl, resp.status || (resp.completed ? 'OK' : null));

            const buttons = [btnOk, btnNa, btnProblem];
            buttons.forEach(btn => {
                if (disabled) {
                    btn.disabled = true;
                    btn.classList.add('opacity-50', 'cursor-not-allowed');
                } else {
                    btn.onclick = () => {
                        const status = btn.dataset.status;
                        this.updateChecklist(resp.id, { status, completed: status === 'OK' });
                        this.updateChecklistUI(itemEl, status);
                    };
                }
            });

            // Se tiver evidência
            if (item.evidence_type !== 'NONE') {
                if (item.evidence_type === 'TEXT') {
                    const textSection = evidenceDiv.querySelector('.type-text');
                    textSection.classList.remove('hidden');
                    const input = textSection.querySelector('.text-response');
                    input.value = resp.text_response || '';
                    if (disabled) input.disabled = true;
                    input.addEventListener('blur', (e) => {
                        this.updateChecklist(resp.id, { text_response: e.target.value });
                    });
                } else if (item.evidence_type === 'PHOTO' || item.evidence_type === 'VIDEO' || item.evidence_type === 'PHOTO_VIDEO') {
                    const photoSection = evidenceDiv.querySelector('.type-photo-video');
                    photoSection.classList.remove('hidden');
                    const btnPhoto = photoSection.querySelector('.btn-capture-photo');
                    const btnVideo = photoSection.querySelector('.btn-capture-video');
                    const previewContainer = photoSection.querySelector('.preview-container');

                    this.renderOfflineMedia(previewContainer, taskId, resp.id);

                    const showPhoto = item.evidence_type === 'PHOTO' || item.evidence_type === 'PHOTO_VIDEO';
                    const showVideo = item.evidence_type === 'VIDEO' || item.evidence_type === 'PHOTO_VIDEO';

                    if (!disabled) {
                        if (showPhoto) {
                            btnPhoto.classList.remove('hidden');
                            btnPhoto.onclick = () => this.captureMedia(taskId, resp.id, previewContainer);
                        }
                        if (showVideo) {
                            btnVideo.classList.remove('hidden');
                            btnVideo.onclick = () => this.captureVideo(taskId, resp.id, previewContainer);
                        }
                    }
                }
            }

            container.appendChild(tplItem);
        }
    },

    updateChecklistUI(itemEl, status) {
        const btnOk = itemEl.querySelector('.btn-check-ok');
        const btnNa = itemEl.querySelector('.btn-check-na');
        const btnProblem = itemEl.querySelector('.btn-check-problem');
        const evidenceDiv = itemEl.querySelector('.item-evidence');
        const indicator = itemEl.querySelector('.checklist-status-indicator');
        const indicatorDot = indicator.querySelector('span');

        // Reset
        [btnOk, btnNa, btnProblem].forEach(b => b.classList.remove('bg-white', 'shadow-sm', 'text-blue-600', 'text-slate-400', 'text-red-600'));
        evidenceDiv.classList.add('hidden');
        indicator.classList.add('hidden');

        if (!status) return;

        indicator.classList.remove('hidden');
        // A área de evidência aparece assim que qualquer estado for selecionado,
        // garantindo a "Revelação Progressiva". O conteúdo interno já é condicionado pelo evidence_type.
        evidenceDiv.classList.remove('hidden');

        if (status === 'OK') {
            btnOk.classList.add('bg-white', 'shadow-sm', 'text-blue-600');
            indicatorDot.className = 'flex h-2 w-2 rounded-full bg-emerald-500';
        } else if (status === 'NA') {
            btnNa.classList.add('bg-white', 'shadow-sm', 'text-slate-400');
            indicatorDot.className = 'flex h-2 w-2 rounded-full bg-slate-300';
        } else if (status === 'PROBLEM') {
            btnProblem.classList.add('bg-white', 'shadow-sm', 'text-red-600');
            indicatorDot.className = 'flex h-2 w-2 rounded-full bg-red-500 animate-pulse';
        }
    },

    // Atualiza item do checklist no DB local e na fila
    async updateChecklist(responseId, data) {
        console.log(`item checklist ${responseId} atualizado:`, data);
        
        // 1. Atualiza IndexedDB
        await db.checklist_responses.update(responseId, data);
        
        const resp = await db.checklist_responses.get(responseId);

        // 2. Enfileira para o servidor
        await OfflineDB.enqueueSyncItem('CHECKLIST_UPDATE', {
            task_id: resp.task_id,
            data: {
                response_id: responseId,
                ...data
            }
        });
    }
};

// Inicializa o app
document.addEventListener('DOMContentLoaded', () => {
    OfflineApp.init();
});
