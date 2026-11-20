// Conteúdo contextual só em memória: nunca é embutido no shell offline.
(() => {
    if (window.helpContextInitialized) return;
    window.helpContextInitialized = true;
    const requests = new WeakMap();

    function clear(details, message) {
        requests.get(details)?.abort();
        requests.delete(details);
        const panel = details.querySelector('[data-help-context-panel]');
        if (panel) {
            panel.textContent = message;
            panel.removeAttribute('aria-busy');
        }
    }

    async function load(details) {
        if (!details.open) return;
        const panel = details.querySelector('[data-help-context-panel]');
        if (!panel) return;
        clear(details, 'Consultando os tutoriais...');
        if (!navigator.onLine) {
            panel.textContent = 'Conecte-se à internet para consultar a ajuda desta tela.';
            return;
        }
        const controller = new AbortController();
        requests.set(details, controller);
        panel.setAttribute('aria-busy', 'true');
        try {
            const url = new URL(details.dataset.helpContextUrl, window.location.origin);
            if (url.origin !== window.location.origin || !url.pathname.startsWith('/ajuda/')) throw new Error('Invalid help endpoint');
            const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
            if (response.redirected || response.status === 401 || response.status === 403) {
                throw new Error('Session expired');
            }
            if (!response.ok) throw new Error('Help unavailable');
            const html = await response.text();
            if (requests.get(details) !== controller || !details.open) return;
            // HTML do nosso template autenticado, com conteúdo editorial escapado.
            panel.innerHTML = html;
            if (window.lucide) window.lucide.createIcons();
        } catch (error) {
            if (error.name !== 'AbortError' && requests.get(details) === controller) {
                panel.textContent = 'Não foi possível consultar a ajuda. Confira a conexão e sua sessão e feche e abra este painel para tentar novamente.';
            }
        } finally {
            if (requests.get(details) === controller) {
                requests.delete(details);
                panel.removeAttribute('aria-busy');
            }
        }
    }

    document.addEventListener('toggle', event => {
        const details = event.target;
        if (!details.matches?.('details[data-help-context-url]')) return;
        if (details.open) load(details);
        else clear(details, 'Conecte-se à internet para consultar a ajuda desta tela.');
    }, true);

    // Retirar títulos da memória ao sair, inclusive antes de entrar no bfcache.
    window.addEventListener('pagehide', () => {
        document.querySelectorAll('details[data-help-context-url]').forEach(details => {
            clear(details, 'Conecte-se à internet para consultar a ajuda desta tela.');
            details.open = false;
        });
    });
    window.addEventListener('offline', () => {
        document.querySelectorAll('details[data-help-context-url]').forEach(details => clear(details, 'Conecte-se à internet para consultar a ajuda desta tela.'));
    });
    window.addEventListener('online', () => {
        document.querySelectorAll('details[data-help-context-url][open]').forEach(load);
    });
})();
