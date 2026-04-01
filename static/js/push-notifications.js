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
            // Registrar Service Worker (o path deve bater com o configurado no PWA_SERVICE_WORKER_PATH)
            swRegistration = await navigator.serviceWorker.register('/static/js/serviceworker.js');
            
            // Verificar se já temos permissão
            if (Notification.permission === 'default') {
                // Solicitar permissão apenas se ainda não foi decidido
                console.log('Solicitando permissão para notificações...');
                requestPermission(vapidPublicKey);
            } else if (Notification.permission === 'granted') {
                // Se já tem permissão, garante que a subscription está atualizada no servidor
                checkAndRefreshSubscription(vapidPublicKey);
            }
        } catch (error) {
            console.error('Erro ao inicializar Push Manager:', error);
        }
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
