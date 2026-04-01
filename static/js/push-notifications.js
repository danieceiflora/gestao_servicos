/**
 * Gerenciamento de Notificações Push
 */
const PushManager = (function() {
    let swRegistration = null;

    // Converte a chave VAPID de base64 para Uint8Array
    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    // Inicializa o Service Worker e verifica permissões
    async function init(vapidPublicKey) {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.log('Notificações Push não são suportadas neste navegador.');
            return;
        }

        try {
            swRegistration = await navigator.serviceWorker.register('/static/js/serviceworker.js');
            
            if (Notification.permission === 'default') {
                showPermissionBanner(vapidPublicKey);
            } else if (Notification.permission === 'granted') {
                checkAndRefreshSubscription(vapidPublicKey);
            }
        } catch (error) {
            console.error('Erro ao inicializar Push Manager:', error);
        }
    }

    // Exibe um banner discreto solicitando a ativação
    function showPermissionBanner(vapidPublicKey) {
        if (document.getElementById('push-permission-banner')) return;

        const banner = document.createElement('div');
        banner.id = 'push-permission-banner';
        banner.className = 'fixed top-4 left-4 right-4 z-[100] bg-slate-900 text-white p-4 rounded-2xl shadow-2xl flex items-center justify-between gap-4 animate-in slide-in-from-top duration-500';
        banner.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="p-2 bg-blue-500 rounded-lg">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
                </div>
                <div>
                    <p class="text-sm font-bold">Ativar Alertas?</p>
                    <p class="text-[10px] text-slate-400 font-medium">Receba avisos de novas OS em tempo real.</p>
                </div>
            </div>
            <div class="flex gap-2">
                <button id="btn-push-not-now" class="px-3 py-1.5 text-[10px] font-bold text-slate-400 hover:text-white transition-colors">Depois</button>
                <button id="btn-push-enable" class="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-bold rounded-lg transition-all shadow-lg">Ativar</button>
            </div>
        `;
        document.body.appendChild(banner);

        document.getElementById('btn-push-enable').addEventListener('click', () => {
            banner.remove();
            requestPermission(vapidPublicKey);
        });

        document.getElementById('btn-push-not-now').addEventListener('click', () => {
            banner.remove();
        });
    }

    // Solicita permissão ao usuário
    async function requestPermission(vapidPublicKey) {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
            console.log('Permissão concedida!');
            subscribeUser(vapidPublicKey);
        } else {
            console.log('Permissão negada ou fechada.');
        }
    }

    // Subscreve o usuário no Push Service
    async function subscribeUser(vapidPublicKey) {
        try {
            const subscription = await swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
            });

            // Enviar para o servidor Django
            await sendSubscriptionToServer(subscription);
            console.log('Usuário inscrito com sucesso no Push.');
        } catch (error) {
            console.error('Falha ao inscrever o usuário:', error);
        }
    }

    // Verifica se a subscription local bate com a do navegador
    async function checkAndRefreshSubscription(vapidPublicKey) {
        const subscription = await swRegistration.pushManager.getSubscription();
        if (subscription) {
            // Opcional: Verificar no localStorage se já enviamos esta sub recentemente
            // Por enquanto, enviamos para garantir que o vínculo usuário <-> dispositivo esteja ativo
            await sendSubscriptionToServer(subscription);
        } else {
            // Perdeu a sub mas tem permissão? Subscreve de novo
            subscribeUser(vapidPublicKey);
        }
    }

    // Envia o objeto JSON da subscription para a view do Django
    async function sendSubscriptionToServer(subscription) {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        
        try {
            const response = await fetch('/notifications/subscribe/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(subscription.toJSON())
            });

            if (!response.ok) {
                console.error('Erro ao salvar subscription no servidor Django');
            }
        } catch (error) {
            console.error('Erro de rede ao enviar subscription:', error);
        }
    }

    return {
        init: init
    };
})();
