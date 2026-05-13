// Service Worker Gestao Servicos
const CACHE_NAME = 'gestao-servicos-v2';
const ASSETS_TO_CACHE = [
    '/',
    '/static/dist/output.css',
    '/static/js/offline-db.js',
    '/static/dourados-calhas.png',
    'https://unpkg.com/lucide@latest',
    'https://unpkg.com/dexie@latest/dist/dexie.js',
    'https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js'
];

self.addEventListener('install', (event) => {
    console.log('[Service Worker] Install');
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activate');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Estratégia para APIs: Network First
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // Estratégia para Assets/Páginas: Stale-While-Revalidate ou Cache First
    event.respondWith(
        caches.match(event.request).then((response) => {
            return response || fetch(event.request).then((fetchResponse) => {
                // Opcional: Adicionar novas páginas ao cache dinamicamente
                return fetchResponse;
            });
        })
    );
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

