/**
 * Gerenciador da Interface do App do Técnico (Offline-First SPA)
 */

const OfflineApp = {
    // Estado interno
    state: {
        currentView: 'list', // 'list', 'detail'
        currentTaskId: null,
    },

    // Inicialização
    async init() {
        console.log('📱 OfflineApp inicializando...');
        
        // 1. Atualiza UI de status (Online/Offline)
        if (typeof OfflineDB !== 'undefined') {
            await OfflineDB.updateUIStatus();
            
            // 2. Tenta sincronizar e fazer check-in completo se estiver online
            if (navigator.onLine) {
                // Tenta processar fila pendente antes de baixar novos dados
                await OfflineDB.processSyncQueue();
                // Faz o bootstrap e prefetch das telas
                await OfflineDB.realizarCheckInDiario();
            }
        }

        // 3. Esconde o loading e mostra o app
        const loadingEl = document.getElementById('app-loading');
        const mainEl = document.getElementById('app-main');
        if (loadingEl) loadingEl.classList.add('hidden');
        if (mainEl) mainEl.classList.remove('hidden');

        // 4. Renderiza a view inicial com o que tivermos no IndexedDB
        await this.render();
    },

    // Roteamento simples
    async navigate(view, params = {}) {
        this.state.currentView = view;
        this.state.currentTaskId = params.taskId || null;
        await this.render();
    },

    // Renderização principal
    async render() {
        const container = document.getElementById('view-container');
        const titleEl = document.getElementById('view-title');
        container.innerHTML = '';

        if (this.state.currentView === 'list') {
            titleEl.textContent = 'Minha Agenda';
            await this.renderTaskList(container);
        } else if (this.state.currentView === 'detail') {
            titleEl.textContent = 'Detalhes da Etapa';
            await this.renderTaskDetail(container, this.state.currentTaskId);
        }
    },

    // Renderiza a lista de tarefas
    async renderTaskList(container) {
        const tplList = document.getElementById('tpl-task-list').content.cloneNode(true);
        const listContainer = tplList.getElementById('task-list-container');
        
        // Busca tarefas no IndexedDB
        const tasks = await db.tasks.orderBy('scheduled_at').toArray();
        
        if (tasks.length === 0) {
            listContainer.innerHTML = '<div class="text-center py-10 text-slate-500">Nenhuma tarefa encontrada.</div>';
        } else {
            for (const task of tasks) {
                const itemEl = this.createTaskItem(task);
                listContainer.appendChild(itemEl);
            }
        }

        container.appendChild(tplList);
    },

    // Cria um item da lista de tarefas
    createTaskItem(task) {
        const tplItem = document.getElementById('tpl-task-item').content.cloneNode(true);
        const card = tplItem.querySelector('.task-card');
        
        // Busca dados relacionados (Order e Property)
        // Nota: Em uma app real, poderíamos fazer um join ou carregar tudo no início
        card.dataset.id = task.id;
        
        // Tenta preencher dados básicos (mesmo que assíncronos)
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
        if (prop) card.querySelector('.property-address').textContent = `${prop.address}, ${prop.number}`;
        
        card.querySelector('.task-type').textContent = task.task_type; // Pode usar um map de tradução aqui
        
        const date = new Date(task.scheduled_at);
        card.querySelector('.task-time').textContent = date.toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
        });

        const statusBadge = card.querySelector('.task-status-badge');
        statusBadge.textContent = task.status;
        
        // Estilização do badge baseada no status
        if (task.status === 'SCHEDULED') {
            statusBadge.classList.add('bg-blue-100', 'text-blue-800');
        } else if (task.status === 'IN_PROGRESS') {
            statusBadge.classList.add('bg-amber-100', 'text-amber-800');
        } else if (task.status === 'COMPLETED') {
            statusBadge.classList.add('bg-emerald-100', 'text-emerald-800');
        } else {
            statusBadge.classList.add('bg-slate-100', 'text-slate-800');
        }
    },

    // Renderiza o detalhe da tarefa
    async renderTaskDetail(container, taskId) {
        console.log(`🔍 Buscando detalhes da tarefa: ${taskId}`);
        
        // Tenta buscar pelo ID direto
        let task = await db.tasks.get(taskId);
        
        // Fallback: busca manual caso o índice esteja estranho
        if (!task) {
            const allTasks = await db.tasks.toArray();
            task = allTasks.find(t => String(t.id) === String(taskId));
        }

        if (!task) {
            console.error(`❌ Tarefa ${taskId} não encontrada no IndexedDB.`);
            container.innerHTML = `
                <div class="text-center py-10 px-4">
                    <div class="bg-red-50 text-red-800 p-4 rounded-xl border border-red-100">
                        <p class="font-bold">Tarefa não encontrada</p>
                        <p class="text-xs mt-1">ID: ${taskId}</p>
                    </div>
                    <button onclick="OfflineApp.navigate('list')" class="mt-4 text-blue-600 font-bold text-sm">← Voltar para a lista</button>
                </div>
            `;
            return;
        }

        console.log('✅ Tarefa encontrada:', task);
        const order = await db.orders.get(task.service_order_id);
        const prop = order ? await db.properties.get(order.client_property_id) : null;
        const client = prop ? await db.clients.get(prop.client_id) : null;

        const tplDetail = document.getElementById('tpl-task-detail').content.cloneNode(true);
        
        // Preenche dados do cliente e endereço
        if (client) {
            tplDetail.querySelector('.client-name').textContent = client.name;
            const phone = client.phones && client.phones.length > 0 ? client.phones[0] : null;
            if (phone) {
                tplDetail.querySelector('.link-phone').href = `tel:${phone}`;
            } else {
                tplDetail.querySelector('.link-phone').classList.add('hidden');
            }
        }
        
        if (prop) {
            tplDetail.querySelector('.property-address').textContent = prop.full_address;
            const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(prop.full_address)}`;
            tplDetail.querySelector('.link-maps').href = mapUrl;
        }

        // Status Badge
        const statusBadge = tplDetail.querySelector('.task-status-badge');
        statusBadge.textContent = task.status;
        if (task.status === 'SCHEDULED') statusBadge.classList.add('bg-blue-100', 'text-blue-800');
        else if (task.status === 'IN_PROGRESS') statusBadge.classList.add('bg-amber-100', 'text-amber-800');
        else if (task.status === 'COMPLETED') statusBadge.classList.add('bg-emerald-100', 'text-emerald-800');

        // Dados da Task
        tplDetail.querySelector('.task-type').textContent = task.task_type;
        const date = new Date(task.scheduled_at);
        tplDetail.querySelector('.task-time').textContent = date.toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
        });

        if (task.notes) {
            tplDetail.querySelector('.task-notes-container').classList.remove('hidden');
            tplDetail.querySelector('.task-notes').textContent = task.notes;
        }

        // Checklist
        const responses = await db.checklist_responses.where('task_id').equals(taskId).toArray();
        if (responses.length > 0) {
            tplDetail.querySelector('#checklist-section').classList.remove('hidden');
            const checklistContainer = tplDetail.querySelector('#checklist-container');
            await this.renderChecklist(checklistContainer, responses);
        }

        // Botões de Ação
        const btnStart = tplDetail.querySelector('#btn-start-task');
        const btnFinish = tplDetail.querySelector('#btn-finish-task');

        if (task.status === 'IN_PROGRESS') {
            btnStart.classList.add('hidden');
            btnFinish.classList.remove('opacity-50', 'cursor-not-allowed');
            btnFinish.removeAttribute('disabled');
            btnFinish.addEventListener('click', () => this.openFinishModal(taskId));
        } else if (task.status === 'COMPLETED') {
            btnStart.classList.add('hidden');
            btnFinish.classList.add('hidden');
        }

        // Eventos
        tplDetail.querySelector('#btn-back').addEventListener('click', () => this.navigate('list'));
        
        if (btnStart && task.status === 'SCHEDULED') {
            btnStart.addEventListener('click', () => this.startTask(taskId));
        }

        container.appendChild(tplDetail);
        
        // Re-inicializa ícones do Lucide
        if (window.lucide) lucide.createIcons();
    },

    // --- Lógica de Finalização ---
    signaturePad: null,

    openFinishModal(taskId) {
        const modal = document.getElementById('modal-finish');
        modal.classList.remove('hidden');
        modal.classList.add('flex');

        // Limpar campos
        document.getElementById('finish-customer-name').value = '';
        document.getElementById('finish-notes').value = '';

        // Inicializar Signature Pad
        const canvas = document.getElementById('signature-pad');
        
        // Ajustar tamanho do canvas para o container
        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        canvas.width = canvas.offsetWidth * ratio;
        canvas.height = canvas.offsetHeight * ratio;
        canvas.getContext("2d").scale(ratio, ratio);

        if (this.signaturePad) this.signaturePad.clear();
        this.signaturePad = new SignaturePad(canvas, {
            backgroundColor: 'rgb(248, 250, 252)' // slate-50
        });

        // Eventos do Modal
        document.getElementById('btn-close-finish').onclick = () => modal.classList.add('hidden');
        document.getElementById('btn-clear-signature').onclick = () => this.signaturePad.clear();
        
        document.getElementById('btn-confirm-finish').onclick = () => this.confirmFinish(taskId);
        
        if (window.lucide) lucide.createIcons();
    },

    async confirmFinish(taskId) {
        if (this.signaturePad.isEmpty()) {
            alert('Por favor, peça ao cliente para assinar.');
            return;
        }

        const customerName = document.getElementById('finish-customer-name').value;
        if (!customerName) {
            alert('Por favor, informe o nome de quem recebeu.');
            return;
        }

        const signatureBase64 = this.signaturePad.toDataURL(); // Salva como PNG base64
        const notes = document.getElementById('finish-notes').value;
        const now = new Date().toISOString();

        console.log(`🏁 Finalizando tarefa local: ${taskId}`);

        // 1. Atualiza IndexedDB
        await db.tasks.update(taskId, {
            status: 'COMPLETED',
            finished_at: now,
            customer_name: customerName,
            customer_signature: signatureBase64,
            technical_notes: notes // Salva notas se houver campo
        });

        // 2. Enfileira Sincronização
        await OfflineDB.enqueueSyncItem('TASK_FINISH', {
            task_id: taskId,
            finished_at: now,
            data: {
                customer_name: customerName,
                customer_signature: signatureBase64,
                notes: notes
            }
        });

        // 3. Fecha modal e volta para a lista
        document.getElementById('modal-finish').classList.add('hidden');
        await this.navigate('list');
    },

    // --- Lógica de Mídias Offline ---
    
    async captureEvidence(taskId, responseId, previewContainer) {
        // Criar um input de arquivo dinâmico ou usar a câmera global
        // Para PWAs, o mais confiável é o input com capture="environment"
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.capture = 'environment';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            console.log(`📸 Capturando foto para checklist ${responseId}...`);
            
            // 1. Salva o Blob no IndexedDB
            const mediaId = await db.media.add({
                task_id: taskId,
                response_id: responseId,
                type: file.type,
                blob: file,
                status: 'pending'
            });

            // 2. Enfileira sincronização
            await OfflineDB.enqueueSyncItem('MEDIA_UPLOAD', {
                task_id: taskId,
                media_id: mediaId,
                response_id: responseId
            });

            // 3. Atualiza miniaturas
            this.renderOfflineMedia(previewContainer, taskId, responseId);
        };

        input.click();
    },

    async renderOfflineMedia(container, taskId, responseId) {
        const mediaItems = await db.media
            .where('response_id').equals(responseId)
            .toArray();
        
        container.innerHTML = '';
        mediaItems.forEach(item => {
            const url = URL.createObjectURL(item.blob);
            const div = document.createElement('div');
            div.className = 'relative w-16 h-16 rounded-lg overflow-hidden border border-slate-200';
            div.innerHTML = `
                <img src="${url}" class="w-full h-full object-cover">
                <div class="absolute inset-0 bg-black/20 flex items-center justify-center">
                    <i data-lucide="${item.status === 'pending' ? 'clock' : 'check'}" class="h-4 w-4 text-white"></i>
                </div>
            `;
            container.appendChild(div);
        });

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

    // Renderiza o checklist
    async renderChecklist(container, responses) {
        for (const resp of responses) {
            const item = await db.checklist_items.get(resp.item_id);
            if (!item) continue;

            const tplItem = document.getElementById('tpl-checklist-item').content.cloneNode(true);
            const card = tplItem.querySelector('.checklist-card');
            
            card.querySelector('.item-name').textContent = item.name;
            card.querySelector('.item-description').textContent = item.description;
            
            const checkbox = tplItem.querySelector('.check-completed');
            checkbox.checked = resp.completed;
            
            // Evento de completar item
            checkbox.addEventListener('change', (e) => {
                this.updateChecklist(resp.id, { completed: e.target.checked });
            });

            // Se tiver evidência
            if (item.evidence_type !== 'NONE') {
                const evidenceDiv = tplItem.querySelector('.item-evidence');
                evidenceDiv.classList.remove('hidden');
                
                if (item.evidence_type === 'TEXT') {
                    const textarea = evidenceDiv.querySelector('.type-text');
                    textarea.classList.remove('hidden');
                    const input = textarea.querySelector('.text-response');
                    input.value = resp.text_response || '';
                    
                    // Evento de atualizar texto (com debounce seria melhor, mas vamos direto por enquanto)
                    input.addEventListener('blur', (e) => {
                        this.updateChecklist(resp.id, { text_response: e.target.value });
                    });
                } else if (item.evidence_type === 'PHOTO' || item.evidence_type === 'VIDEO') {
                    const photoDiv = evidenceDiv.querySelector('.type-photo-video');
                    photoDiv.classList.remove('hidden');
                    
                    const btnCapture = photoDiv.querySelector('.btn-capture');
                    
                    // Container para miniaturas
                    const previewContainer = document.createElement('div');
                    previewContainer.className = 'flex flex-wrap gap-2 mt-2';
                    photoDiv.appendChild(previewContainer);
                    
                    // Renderiza fotos já salvas localmente
                    this.renderOfflineMedia(previewContainer, taskId, resp.id);

                    btnCapture.onclick = () => this.captureEvidence(taskId, resp.id, previewContainer);
                }
            }

            container.appendChild(tplItem);
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
