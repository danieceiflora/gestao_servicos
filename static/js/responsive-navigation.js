(() => {
    const root = document.getElementById('mobile-menu');
    const button = document.getElementById('mobile-menu-button');
    const drawer = document.getElementById('mobile-menu-drawer');
    const overlay = document.getElementById('mobile-menu-overlay');
    const closeButton = document.getElementById('mobile-menu-close');
    if (!root || !button || !drawer || !overlay || !closeButton) return;

    let previousOverflow = '';
    const focusable = () => [...drawer.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')];
    const isOpen = () => root.getAttribute('aria-hidden') === 'false';

    function openMenu() {
        previousOverflow = document.body.style.overflow;
        root.classList.remove('invisible');
        root.setAttribute('aria-hidden', 'false');
        button.setAttribute('aria-expanded', 'true');
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(() => {
            drawer.classList.remove('-translate-x-full');
            overlay.classList.remove('opacity-0');
            drawer.focus();
        });
    }

    function closeMenu(restoreFocus = true) {
        if (!isOpen()) return;
        drawer.classList.add('-translate-x-full');
        overlay.classList.add('opacity-0');
        root.setAttribute('aria-hidden', 'true');
        button.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = previousOverflow;
        window.setTimeout(() => root.classList.add('invisible'), 200);
        if (restoreFocus) button.focus();
    }

    button.addEventListener('click', openMenu);
    overlay.addEventListener('click', () => closeMenu());
    closeButton.addEventListener('click', () => closeMenu());
    drawer.querySelectorAll('a[href]').forEach(link => link.addEventListener('click', () => closeMenu(false)));
    document.addEventListener('keydown', event => {
        if (!isOpen()) return;
        if (event.key === 'Escape') return closeMenu();
        if (event.key !== 'Tab') return;
        const items = focusable();
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 1280) closeMenu(false);
    });
})();
