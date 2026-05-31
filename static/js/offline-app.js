/**
 * Gerenciador da Interface do App do Técnico (Offline-First SPA)
 */

const OfflineApp = {
    // Estado interno
    state: {
        currentView: 'list', // 'list', 'detail'
        currentTaskId: null,
        filters: {
            status: 'all', // 'all', 'IN_PROGRESS', 'SCHEDULED', 'COMPLETED'
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
        }
    },

    // Inicialização
    async init() {
        console.log('📱 OfflineApp inicializando...');
        
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
            tasks = tasks.filter(t => t.status !== 'COMPLETED');
        }
        if (this.state.filters.status !== 'all') {
            tasks = tasks.filter(t => t.status === this.state.filters.status);
        }
        
        let inProgressCount = 0;
        let scheduledCount = 0;
        let completedCount = 0;

        for (const task of tasks) {
            const itemEl = this.createTaskItem(task);
            
            if (task.status === 'IN_PROGRESS') {
                listInProgress.appendChild(itemEl);
                inProgressCount++;
            } else if (task.status === 'SCHEDULED') {
                listScheduled.appendChild(itemEl);
                scheduledCount++;
            } else if (task.status === 'COMPLETED') {
                listCompleted.appendChild(itemEl);
                completedCount++;
            }
            // Outros status como CANCELLED não aparecem na listagem conforme o fluxo principal
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
        const order = await db.orders.get(task.service_order_id);
        const prop = order ? await db.properties.get(order.client_property_id) : null;
        const client = prop ? await db.clients.get(prop.client_id) : null;

        if (client) card.querySelector('.client-name').textContent = client.name;
        
        let addressText = '';
        if (order) addressText += `OS #${order.number} • `;
        if (prop) addressText += `${prop.address}, ${prop.number} - ${prop.neighborhood}`;
        card.querySelector('.property-address').textContent = addressText;
        
        card.querySelector('.task-type').textContent = task.task_type;
        
        const dateScheduled = new Date(task.scheduled_at);

        const statusBadge = card.querySelector('.task-status-badge');
        statusBadge.textContent = this.translateStatus(task.status);
        
        // Reset classes
        card.className = 'task-card group relative block rounded-xl border border-slate-200 bg-white transition-all shadow-sm cursor-pointer active:scale-[0.98] border-l-4';
        statusBadge.className = 'task-status-badge inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold whitespace-nowrap';

        // Estilização consistente com a seção (Status)
        if (task.status === 'SCHEDULED') {
            card.classList.add('border-l-blue-500', 'hover:border-blue-300');
            statusBadge.classList.add('bg-blue-50', 'text-blue-700');
        } else if (task.status === 'IN_PROGRESS') {
            card.classList.add('border-l-amber-500', 'hover:border-amber-300');
            statusBadge.classList.add('bg-amber-50', 'text-amber-700');
        } else if (task.status === 'COMPLETED') {
            card.classList.add('border-l-emerald-500', 'hover:border-emerald-300');
            statusBadge.classList.add('bg-emerald-50', 'text-emerald-700');
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
            'SCHEDULED': 'Agendado',
            'IN_PROGRESS': 'Em Execução',
            'COMPLETED': 'Finalizado',
            'CANCELLED': 'Cancelado'
        };
        return map[status] || status;
    },

    // Renderiza o detalhe da tarefa (Detalhes do Serviço)
    async renderTaskDetail(container, taskId) {
        let task = await db.tasks.get(taskId);
        
        if (!task) {
            const allTasks = await db.tasks.toArray();
            task = allTasks.find(t => String(t.id) === String(taskId));
        }

        if (!task) {
            container.innerHTML = '<div class="p-10 text-center">Tarefa não encontrada.</div>';
            return;
        }

        const order = await db.orders.get(task.service_order_id);
        const prop = order ? await db.properties.get(order.client_property_id) : null;
        const client = prop ? await db.clients.get(prop.client_id) : null;

        const tplDetail = document.getElementById('tpl-task-detail').content.cloneNode(true);
        
        // 1. Dados Básicos
        if (client) {
            tplDetail.querySelector('.client-name').textContent = client.name;
            const phone = client.phones && client.phones.length > 0 ? client.phones[0] : null;
            if (phone) {
                const cleanPhone = phone.replace(/\D/g, '');
                const waPhone = cleanPhone.length <= 11 ? `55${cleanPhone}` : cleanPhone;
                const linkWa = tplDetail.querySelector('.link-whatsapp');
                if (linkWa) linkWa.href = `https://wa.me/${waPhone}`;
            } else {
                const linkWa = tplDetail.querySelector('.link-whatsapp');
                if (linkWa) linkWa.classList.add('hidden', 'pointer-events-none');
            }
        }
        
        if (prop) {
            tplDetail.querySelector('.property-address').textContent = prop.full_address;
            
            const btnGps = tplDetail.querySelector('.btn-gps-trigger');
            if (btnGps) {
                btnGps.dataset.gpsLat = prop.latitude || '';
                btnGps.dataset.gpsLng = prop.longitude || '';
                btnGps.dataset.gpsAddress = prop.full_address;
            }

            const btnUpdateGps = tplDetail.querySelector('.btn-update-gps');
            if (btnUpdateGps) {
                btnUpdateGps.addEventListener('click', async () => {
                    if (!confirm("Deseja atualizar as coordenadas de GPS com sua localização atual?")) return;
                    if (!("geolocation" in navigator)) {
                        alert("Geolocalização não suportada no seu navegador.");
                        return;
                    }

                    const originalHtml = btnUpdateGps.innerHTML;
                    btnUpdateGps.innerHTML = '<i data-lucide="loader-2" class="h-5 w-5 animate-spin text-slate-500"></i><span class="text-[10px] font-bold text-slate-600 uppercase text-center leading-tight">Aguarde</span>';
                    if (window.lucide) lucide.createIcons();

                    navigator.geolocation.getCurrentPosition(
                        async (position) => {
                            const lat = position.coords.latitude;
                            const lng = position.coords.longitude;

                            try {
                                // 1. Atualiza no IndexedDB
                                prop.latitude = lat;
                                prop.longitude = lng;
                                await db.properties.put(prop);

                                // 2. Enfileira Sincronização (será processado pelo OfflineDB)
                                await OfflineDB.enqueueSyncItem('PROPERTY_GPS_UPDATE', {
                                    property_id: prop.id,
                                    latitude: lat,
                                    longitude: lng
                                });

                                // 3. Atualiza os atributos do botão Navegar, se existir
                                if (btnGps) {
                                    btnGps.dataset.gpsLat = lat;
                                    btnGps.dataset.gpsLng = lng;
                                }

                                alert("Coordenadas atualizadas e salvas para sincronização!");
                            } catch(e) {
                                console.error('Erro ao atualizar coordenadas:', e);
                                alert("Erro interno ao tentar salvar as coordenadas.");
                            } finally {
                                btnUpdateGps.innerHTML = originalHtml;
                                if (window.lucide) lucide.createIcons();
                            }
                        },
                        (error) => {
                            alert("Erro ao obter localização. Verifique as permissões do navegador.");
                            btnUpdateGps.innerHTML = originalHtml;
                            if (window.lucide) lucide.createIcons();
                        },
                        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                    );
                });
            }
        }

        // Status Badge
        const statusBadge = tplDetail.querySelector('.task-status-badge');
        statusBadge.textContent = this.translateStatus(task.status);
        if (task.status === 'SCHEDULED') statusBadge.classList.add('bg-blue-50', 'text-blue-600', 'border-blue-100');
        else if (task.status === 'IN_PROGRESS') statusBadge.classList.add('bg-amber-50', 'text-amber-600', 'border-amber-100');
        else if (task.status === 'COMPLETED') statusBadge.classList.add('bg-emerald-50', 'text-emerald-600', 'border-emerald-100');

        // Dados da Task
        tplDetail.querySelector('.task-type').textContent = task.task_type;
        const date = new Date(task.scheduled_at);
        
        // Formatação elegante: ex: "25 de Maio • 14:30"
        const formattedDate = date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
        const formattedTime = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        
        tplDetail.querySelector('.task-time').textContent = `${formattedDate} • ${formattedTime}`;

        if (task.notes) {
            tplDetail.querySelector('.task-notes-container').classList.remove('hidden');
            tplDetail.querySelector('.task-notes').textContent = task.notes;
        }

        // --- CONTROLE DE ESTADOS DO WORKFLOW ---
        const startSection = tplDetail.querySelector('#workflow-start-section');
        const activeSection = tplDetail.querySelector('#workflow-active-section');
        const btnStart = tplDetail.querySelector('#btn-start-task');
        const btnFinish = tplDetail.querySelector('#btn-finish-task');
        const btnAddMedia = tplDetail.querySelector('#btn-add-media');
        const btnAddVideo = tplDetail.querySelector('#btn-add-video');
        const mediaContainer = tplDetail.querySelector('#task-media-container');
        const btnAddOccurrence = tplDetail.querySelector('#btn-add-occurrence');
        const btnAddOccurrencePre = tplDetail.querySelector('#btn-add-occurrence-pre');
        const occurrenceList = tplDetail.querySelector('#occurrence-list');
        const occurrencesSection = tplDetail.querySelector('#occurrences-section-card');

        const isCompleted = task.status === 'COMPLETED';

        // --- Ocorrências (Sempre processado) ---
        const occCount = await this.renderOccurrences(occurrenceList, taskId);
        if (isCompleted && occCount === 0) {
            if (occurrencesSection) occurrencesSection.classList.add('hidden');
        } else if (occurrencesSection) {
            occurrencesSection.classList.remove('hidden');
        }

        if (!isCompleted) {
            if (btnAddOccurrence) btnAddOccurrence.onclick = () => this.openOccurrenceModal(taskId);
            if (btnAddOccurrencePre) btnAddOccurrencePre.onclick = () => this.openOccurrenceModal(taskId);
        } else {
            if (btnAddOccurrence) btnAddOccurrence.classList.add('hidden');
            if (btnAddOccurrencePre) btnAddOccurrencePre.classList.add('hidden');
        }

        if (task.status === 'SCHEDULED') {
            startSection.classList.remove('hidden');
            activeSection.classList.add('hidden');
            btnStart.onclick = () => this.startTask(taskId);
        } else if (task.status === 'IN_PROGRESS' || task.status === 'COMPLETED') {
            startSection.classList.add('hidden');
            
            // A seção ativa contém Checklist e Mídias
            activeSection.classList.remove('hidden');
            
            if (isCompleted) {
                // --- Preenchimento do Resumo de Finalização ---
                const completedSection = tplDetail.querySelector('#workflow-completed-section');
                if (completedSection) {
                    completedSection.classList.remove('hidden');
                    
                    completedSection.querySelector('#detail-customer-name').textContent = task.customer_name || 'Não informado';
                    
                    const notesContainer = completedSection.querySelector('#detail-completed-notes-container');
                    const notesEl = completedSection.querySelector('#detail-completed-notes');
                    if (task.technical_notes) {
                        notesContainer.classList.remove('hidden');
                        notesEl.textContent = task.technical_notes;
                    }

                    // Assinatura
                    const sigImg = completedSection.querySelector('#detail-signature-img');
                    const noSig = completedSection.querySelector('#detail-no-signature');
                    if (task.customer_signature) {
                        sigImg.src = task.customer_signature;
                        sigImg.classList.remove('hidden');
                        noSig.classList.add('hidden');
                    } else {
                        sigImg.classList.add('hidden');
                        noSig.classList.remove('hidden');
                    }

                    // Pagamento
                    const paymentSection = completedSection.querySelector('#detail-completed-payment');
                    if (task.payment_method && task.payment_amount) {
                        paymentSection.classList.remove('hidden');
                        const badge = paymentSection.querySelector('#detail-payment-method-badge');
                        const valueEl = paymentSection.querySelector('#detail-payment-value');
                        
                        const methodMap = { 'CASH': 'Dinheiro', 'CREDIT_CARD': 'Cartão', 'PIX': 'PIX' };
                        badge.textContent = methodMap[task.payment_method] || task.payment_method;
                        valueEl.textContent = `R$ ${parseFloat(task.payment_amount).toFixed(2)}`;
                    }

                    // Status de Sincronismo (Opcional se o elemento existir)
                    const syncMsg = completedSection.querySelector('#detail-sync-status-msg');
                    if (syncMsg) {
                        const pendingQueue = await db.sync_queue.where('type').equals('TASK_FINISH').toArray();
                        const isPending = pendingQueue.some(i => String(i.payload.task_id) === String(taskId));
                        
                        if (isPending) {
                            syncMsg.innerHTML = '<i data-lucide="cloud-off" class="h-3 w-3"></i> Aguardando conexão para enviar';
                            syncMsg.className = 'mt-1 text-xs font-semibold text-amber-600 flex items-center justify-center gap-1.5';
                        } else {
                            syncMsg.innerHTML = '<i data-lucide="cloud-check" class="h-3 w-3"></i> Sincronizado com o servidor';
                            syncMsg.className = 'mt-1 text-xs font-semibold text-emerald-600 flex items-center justify-center gap-1.5';
                        }
                    }
                }
            }
            
            // Checklist
            const responses = await db.checklist_responses.where('task_id').equals(taskId).toArray();
            const checklistSection = tplDetail.querySelector('#checklist-section');
            if (responses.length > 0) {
                checklistSection.classList.remove('hidden');
                const checklistContainer = tplDetail.querySelector('#checklist-container');
                await this.renderChecklist(checklistContainer, responses, isCompleted);
            } else if (isCompleted) {
                checklistSection.classList.add('hidden');
            }

            // Mídias
            const mediaCount = await this.renderOfflineMedia(mediaContainer, taskId, null);
            const mediaSection = tplDetail.querySelector('#media-section-card');
            if (isCompleted && mediaCount === 0) {
                mediaSection.classList.add('hidden');
            } else {
                mediaSection.classList.remove('hidden');
            }

            if (!isCompleted) {
                btnAddMedia.onclick = () => this.captureMedia(taskId, null, mediaContainer);
                btnAddVideo.onclick = () => this.captureVideo(taskId, null, mediaContainer);
            } else {
                btnAddMedia.classList.add('hidden');
                btnAddVideo.classList.add('hidden');
            }

            // Finalização
            if (!isCompleted) {
                btnFinish.onclick = () => this.openFinishModal(taskId);
            } else {
                btnFinish.classList.add('hidden');
                // Esconde o container do botão de finalizar para não sobrar espaço em branco
                if (btnFinish.parentElement) btnFinish.parentElement.classList.add('hidden');
            }
        }

        tplDetail.querySelector('#btn-back').addEventListener('click', () => this.navigate('list'));
        
        container.appendChild(tplDetail);
    },

    // --- Lógica de Finalização ---
    signaturePad: null,

    async openFinishModal(taskId) {
        const modal = document.getElementById('modal-finish');
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        const task = await db.tasks.get(taskId);
        const order = await db.orders.get(task.service_order_id);

        // Limpar campos
        document.getElementById('finish-customer-name').value = '';
        document.getElementById('finish-notes').value = '';
        
        // Pagamento (Sprint 7)
        const paymentSection = document.getElementById('finish-payment-section');
        const balanceDue = order ? parseFloat(order.balance_due || 0) : 0;
        
        if (balanceDue > 0) {
            paymentSection.classList.remove('hidden');
            document.getElementById('finish-balance-due').textContent = `R$ ${balanceDue.toFixed(2)}`;
            document.getElementById('finish-payment-amount').value = balanceDue.toFixed(2);
            this.initPaymentLogic();
        } else {
            paymentSection.classList.add('hidden');
        }

        // Inicializar Signature Pad
        const canvas = document.getElementById('signature-pad');
        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        canvas.width = canvas.offsetWidth * ratio;
        canvas.height = canvas.offsetHeight * ratio;
        canvas.getContext("2d").scale(ratio, ratio);

        if (this.signaturePad) this.signaturePad.clear();
        this.signaturePad = new SignaturePad(canvas, {
            backgroundColor: 'rgb(248, 250, 252)'
        });

        // Eventos do Modal
        document.getElementById('btn-close-finish').onclick = () => modal.classList.add('hidden');
        document.getElementById('btn-clear-signature').onclick = () => this.signaturePad.clear();
        document.getElementById('btn-confirm-finish').onclick = () => this.confirmFinish(taskId);
        
        if (window.lucide) lucide.createIcons();
    },

    async initPaymentLogic() {
        const methodsContainer = document.getElementById('finish-payment-methods-grid');
        const details = document.getElementById('payment-details');
        
        if (!methodsContainer) return;

        // Limpa e busca métodos reais do DB
        methodsContainer.innerHTML = '';
        const methods = await db.payment_methods.toArray();
        
        if (methods.length === 0) {
            methodsContainer.innerHTML = '<p class="col-span-full text-center text-[10px] text-slate-400 py-4">Nenhum método de pagamento disponível.</p>';
            return;
        }

        this.state.payment.method = null;

        methods.forEach(method => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn-payment-method flex flex-col items-center justify-center gap-2 p-4 rounded-2xl border-2 border-slate-100 bg-white hover:border-blue-200 transition-all active:scale-95';
            btn.dataset.method = method.descricao; // Usamos a descrição/código para sync
            
            // Ícone genérico (pode ser melhorado com mapeamento)
            let icon = 'credit-card';
            if (method.descricao.toUpperCase().includes('PIX')) icon = 'qr-code';
            if (method.descricao.toUpperCase().includes('DINHEIRO')) icon = 'banknote';

            btn.innerHTML = `
                <div class="p-2 rounded-xl bg-slate-50 text-slate-400">
                    <i data-lucide="${icon}" class="h-6 w-6"></i>
                </div>
                <span class="text-[10px] font-black uppercase tracking-tighter text-slate-600">${method.descricao}</span>
            `;

            btn.onclick = () => {
                const isSelected = btn.classList.contains('bg-blue-50');
                
                // Limpar seleções
                methodsContainer.querySelectorAll('.btn-payment-method').forEach(b => {
                    b.classList.remove('bg-blue-50', 'border-blue-500', 'text-blue-600');
                    b.querySelector('div').classList.replace('bg-blue-100', 'bg-slate-50');
                    b.querySelector('div').classList.replace('text-blue-600', 'text-slate-400');
                });
                
                if (isSelected) {
                    this.state.payment.method = null;
                    details.classList.add('hidden');
                } else {
                    btn.classList.add('bg-blue-50', 'border-blue-500', 'text-blue-600');
                    btn.querySelector('div').classList.replace('bg-slate-50', 'bg-blue-100');
                    btn.querySelector('div').classList.replace('text-slate-400', 'text-blue-600');
                    this.state.payment.method = btn.dataset.method;
                    details.classList.remove('hidden');
                }
            };
            methodsContainer.appendChild(btn);
        });

        if (window.lucide) lucide.createIcons();
    },

    async confirmFinish(taskId) {
        // Sprint 8: Validação de Itens Obrigatórios
        const responses = await db.checklist_responses.where('task_id').equals(taskId).toArray();
        const items = await db.checklist_items.toArray();
        
        let pendingRequired = [];
        for (const resp of responses) {
            const item = items.find(i => i.id === resp.item_id);
            // Considera preenchido se tiver um status (nova ação) ou completed (veio salvo do backend)
            const isFilled = resp.status || resp.completed;
            if (item && item.is_required && !isFilled) {
                pendingRequired.push(item.name);
            }
        }

        if (pendingRequired.length > 0) {
            alert(`Atenção: Os seguintes itens obrigatórios não foram preenchidos:\n\n- ${pendingRequired.join('\n- ')}`);
            document.getElementById('modal-finish').classList.add('hidden');
            return;
        }

        if (this.signaturePad.isEmpty()) {
            alert('Por favor, peça ao cliente para assinar.');
            return;
        }

        const customerName = document.getElementById('finish-customer-name').value;
        if (!customerName) {
            alert('Por favor, informe o nome de quem recebeu.');
            return;
        }

        // Validação de pagamento se visível (Opcional - Sprint UX)
        const paymentSection = document.getElementById('finish-payment-section');
        let paymentData = null;
        if (!paymentSection.classList.contains('hidden')) {
            const method = this.state.payment.method;
            const amount = parseFloat(document.getElementById('finish-payment-amount').value || 0);
            
            // Se um método foi selecionado, o valor passa a ser obrigatório
            if (method) {
                if (amount <= 0) {
                    alert('Por favor, informe o valor recebido para o método selecionado ou desmarque o pagamento.');
                    return;
                }
                paymentData = { method, amount };
            }
            // Se nenhum método foi selecionado, paymentData continua null e o fluxo segue
        }

        const signatureBase64 = this.signaturePad.toDataURL();
        const notes = document.getElementById('finish-notes').value;
        const now = new Date().toISOString();

        console.log(`🏁 Finalizando tarefa local: ${taskId}`);

        // 1. Atualiza IndexedDB
        await db.tasks.update(taskId, {
            status: 'COMPLETED',
            finished_at: now,
            customer_name: customerName,
            customer_signature: signatureBase64,
            technical_notes: notes,
            payment_method: paymentData ? paymentData.method : null,
            payment_amount: paymentData ? paymentData.amount : null
        });

        // 2. Enfileira Sincronização
        await OfflineDB.enqueueSyncItem('TASK_FINISH', {
            task_id: taskId,
            finished_at: now,
            data: {
                customer_name: customerName,
                customer_signature: signatureBase64,
                notes: notes,
                payment: paymentData
            }
        });

        // 3. Fecha modal e volta para a lista
        document.getElementById('modal-finish').classList.add('hidden');
        await this.navigate('list');
    },

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
            tpl.querySelector('.occ-category').textContent = occ.category;
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
            'DELAY': 'Atraso',
            'MATERIAL_MISSING': 'Falta de Material',
            'CUSTOMER_ABSENT': 'Cliente Ausente',
            'IMPEDIMENT': 'Impedimento no Local',
            'WARRANTY_ISSUE': 'Garantia',
            'OTHER': 'Outro'
        };
        return map[type] || type;
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

        document.getElementById('btn-close-occurrence').onclick = async () => {
            await this.cleanupTempMedia(taskId, tempId);
            modal.classList.add('hidden');
        };
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
            status: 'REGISTERED'
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
        
        // Re-renderiza a seção de ocorrências
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
                status: 'pending'
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
        const isCompleted = task ? task.status === 'COMPLETED' : false;

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
            
            // Ajusta tamanho se for em ocorrência
            const sizeClass = occurrenceId ? 'w-12 h-12' : 'w-full aspect-square';
            // Sprint UX: adicionado hover, scale effect e cursor pointer pra incentivar clique na visualização
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

            // Excluir mídia (UX/IHC: Controle do usuário) - Exibe apenas se a OS não estiver finalizada
            if (!isCompleted) {
                const btnDelete = document.createElement('button');
                btnDelete.className = 'absolute bottom-1 left-1 h-10 w-10 bg-red-600/90 rounded-full flex items-center justify-center shadow-sm hover:bg-red-700 active:scale-95 transition-all text-white backdrop-blur-sm z-10';
                btnDelete.innerHTML = '<i data-lucide="trash-2" class="h-4 w-4"></i>';
                btnDelete.onclick = (e) => {
                    e.stopPropagation(); // Evita abrir o visualizador da foto ao assinar o botao
                    this.deleteMedia(item.id, taskId, container, responseId, occurrenceId);
                };
                div.appendChild(btnDelete);
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

            // Abre o visualizador ao clicar
            div.onclick = () => this.openMediaViewer(mediaList, index);

            container.appendChild(div);
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
        
        // 1. Atualiza no IndexedDB
        await db.tasks.update(taskId, {
            status: 'IN_PROGRESS',
            started_at: now
        });

        // 2. Adiciona à fila de sincronização
        await OfflineDB.enqueueSyncItem('TASK_START', {
            task_id: taskId,
            started_at: now
        });

        // 3. Re-renderiza a tela para mostrar o botão de finalizar
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
                    const btnCapture = photoSection.querySelector('.btn-capture');
                    const previewContainer = photoSection.querySelector('.preview-container');
                    
                    this.renderOfflineMedia(previewContainer, taskId, resp.id);
                    
                    if (disabled) btnCapture.classList.add('hidden');
                    else btnCapture.onclick = () => this.captureMedia(taskId, resp.id, previewContainer);
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
