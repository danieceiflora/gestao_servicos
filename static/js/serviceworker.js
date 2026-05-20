const CACHE_NAME = 'gestao-servicos-v6'; // Subimos a versão para aplicar as correções

// 🔓 Adicione aqui os caminhos das telas/menus principais que o técnico acessa
const ASSETS_TO_CACHE = [
    '/',
    '/app/',
    '/static/dist/output.css',
    '/static/js/offline-db.js',
    '/static/js/offline-app.js',
    '/static/dourados-calhas.png',
    '/manifest.json',
    'https://unpkg.com/lucide@latest',
    'https://unpkg.com/dexie@latest/dist/dexie.js',
    'https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js',
    
    // Deixamos pré-cacheado os esqueletos dos menus mais comuns:
    '/orders/calendar/',
];

// Instalação do Service Worker
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Install');
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            // Em vez de cache.addAll() que aborta tudo se um único arquivo der erro (404),
            // tentamos adicionar um por um de forma segura.
            for (const asset of ASSETS_TO_CACHE) {
                try {
                    // Para CDNs externos lidamos com no-cors para evitar falha de CORS estrito no cacheamento
                    const request = new Request(asset, { mode: asset.startsWith('http') ? 'no-cors' : 'cors' });
                    const response = await fetch(request);
                    if (response && (response.ok || response.type === 'opaque')) {
                        await cache.put(request, response);
                    }
                } catch (e) {
                    console.warn(`[Service Worker] Falha ao fazer pré-cache de: ${asset}`, e);
                }
            }
        })
    );
    self.skipWaiting();
});

// Ativação e limpeza de caches antigos
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

// Interceptação de requisições (Onde a mágica offline acontece)
self.addEventListener('fetch', (event) => {
    // 1. IGNORAR requisições que não sejam GET
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // 2. BYPASS apenas para o manifest.json
    if (url.pathname.endsWith('manifest.json')) {
        return; 
    }

    // 3. IGNORAR rotas administrativas internas do Django
    if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/accounts/')) {
        return;
    }

    // 4. APIs de Dados: Network First (Tenta internet, se falhar devolve cache)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .catch(() =>
                    caches.match(event.request).then((cachedResponse) => {
                        if (cachedResponse) return cachedResponse;
                        return new Response(JSON.stringify({ offline: true }), {
                            status: 503,
                            statusText: 'Service Unavailable',
                            headers: { 'Content-Type': 'application/json' }
                        });
                    })
                )
        );
        return;
    }

    // 5. CORREÇÃO DE NAVEGAÇÃO E ASSETS: Network-First com salvamento em Cache Dinâmico
    // Isso garante que mudanças de menu não quebrem e que o layout seja atualizado online
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Se a página retornou com sucesso, salvamos uma cópia atualizada no cache
                if (response && (response.ok || response.type === 'opaque')) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        try {
                            cache.put(event.request, responseClone);
                        } catch (e) {
                            console.warn('[Service Worker] Falha ao salvar cache dinamico:', e);
                        }
                    });
                }
                return response;
            })
            .catch(() => {
                // Se o fetch falhar (Sem Internet), tenta entregar o layout guardado
                return caches.match(event.request).then((cachedResponse) => {
                    if (cachedResponse) return cachedResponse;
                    
                    // Se o técnico tentar acessar um menu que nunca abriu antes estando offline,
                    // redirecionamos ele de forma amigável para a página principal
                    if (event.request.mode === 'navigate') {
                        return caches.match('/').then((fallback) => {
                            if (fallback) return fallback;
                            return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
                        });
                    }
                    
                    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
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

