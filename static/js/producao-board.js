/* Painel de Expedição / Produção — pausa do polling e preservação de scroll.
 *
 * O polling é declarado no template com
 *   hx-trigger="every 20s[shouldPollBoard()]"
 * e o filtro de evento abaixo é o que decide se aquela batida acontece.
 * Quando nada mudou, a view responde 204 e o HTMX não troca nada — então a
 * maioria das batidas é um round-trip vazio.
 */
(function () {
    'use strict';

    /** Decide se vale atualizar agora. Global porque o hx-trigger a chama por nome. */
    window.shouldPollBoard = function shouldPollBoard() {
        if (document.visibilityState !== 'visible') return false;

        // Modal aberto: trocar o fundo embaixo do usuário é desorientador.
        if (document.querySelector('dialog[open]')) return false;

        // Usuário digitando ou com um select aberto.
        var active = document.activeElement;
        if (active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return false;

        return true;
    };

    var scrollMemo = {};

    function remember() {
        scrollMemo = {};
        document.querySelectorAll('#board-inner [data-keep-scroll]').forEach(function (el) {
            scrollMemo[el.dataset.keepScroll] = el.scrollTop;
        });
    }

    function restore() {
        document.querySelectorAll('#board-inner [data-keep-scroll]').forEach(function (el) {
            var saved = scrollMemo[el.dataset.keepScroll];
            if (saved != null) el.scrollTop = saved;
        });
    }

    function stamp() {
        var el = document.getElementById('poll-stamp');
        if (!el) return;
        var now = new Date();
        el.textContent = '· atualizado às ' +
            String(now.getHours()).padStart(2, '0') + ':' +
            String(now.getMinutes()).padStart(2, '0');
    }

    document.body.addEventListener('htmx:beforeSwap', function (event) {
        if (event.detail.target && event.detail.target.id === 'board-inner') remember();
    });

    document.body.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target && event.detail.target.id === 'board-inner') restore();
    });

    // Chamado pelo próprio partial depois de cada troca — o <script> inline do
    // board_inner.html reinicializa os ícones e avisa aqui.
    window.ProducaoBoard = {
        onSwap: function () {
            restore();
            stamp();
        }
    };

    // Volta do background: atualiza na hora em vez de esperar o próximo ciclo.
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && document.getElementById('board-inner')) {
            document.body.dispatchEvent(new CustomEvent('producao:refresh'));
        }
    });

    stamp();
})();
