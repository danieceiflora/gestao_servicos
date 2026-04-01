// Service Worker Gestao Servicos
const CACHE_NAME = 'gestao-servicos-v1';

self.addEventListener('install', (event) => {
    console.log('[Service Worker] Install');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activate');
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Estrategia Network-first ou simples bypass para evitar erros em dev
    event.respondWith(fetch(event.request));
});

// 🔔 PUSH NOTIFICATIONS
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Push Received.');
    
    let notificationData = {
        title: 'Nova Notificação',
        body: 'Você tem uma nova mensagem',
        icon: '/static/dourados-calhas.png',
        badge: '/static/dourados-calhas.png',
        data: {
            url: '/'
        }
    };

    // Se veio dados do servidor
    if (event.data) {
        try {
            const data = event.data.json();
            notificationData = {
                title: data.title || notificationData.title,
                body: data.body || notificationData.body,
                icon: data.icon || notificationData.icon,
                badge: data.badge || notificationData.badge,
                tag: data.tag || 'notification',
                requireInteraction: data.requireInteraction || false,
                data: {
                    url: data.url || '/',
                    ...data.data
                }
            };
        } catch (e) {
            console.error('Erro ao parsear dados da notificação:', e);
        }
    }

    event.waitUntil(
        self.registration.showNotification(notificationData.title, notificationData)
    );
});

// Ao clicar na notificação
self.addEventListener('notificationclick', (event) => {
    console.log('[Service Worker] Notification click');
    
    event.notification.close();

    const urlToOpen = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Se já tem uma janela aberta, focar nela
                for (let client of clientList) {
                    if (client.url === urlToOpen && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Senão, abrir nova janela
                if (clients.openWindow) {
                    return clients.openWindow(urlToOpen);
                }
            })
    );
});

