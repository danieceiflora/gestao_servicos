// Service Worker Gestao Servicos
const CACHE_NAME = 'gestao-servicos-v1';

self.addEventListener('install', (event) => {
    console.log('[Service Worker] Install');
});

self.addEventListener('fetch', (event) => {
    // Estrategia Network-first ou simples bypass para evitar erros em dev
    event.respondWith(fetch(event.request));
});
