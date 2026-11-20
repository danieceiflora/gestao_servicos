/* UI da ajuda: ampliação de prints e posição de leitura, sem persistência. */
(() => {
    'use strict';

    const guide = document.querySelector('[data-help-guide]');
    if (!guide) return;

    const dialog = guide.querySelector('#help-print-dialog');
    const dialogImage = dialog?.querySelector('[data-help-dialog-image]');
    const dialogTitle = dialog?.querySelector('#help-print-dialog-title');
    let opener = null;

    if (dialog && dialogImage && dialogTitle && typeof dialog.showModal === 'function') {
        guide.querySelectorAll('button[data-help-enlarge]').forEach(button => {
            button.hidden = false;
        });

        guide.addEventListener('click', event => {
            const trigger = event.target.closest('[data-help-enlarge]');
            if (!trigger || !guide.contains(trigger)) return;
            // Não interceptar abrir-em-nova-aba ou downloads do link sem JS.
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
            const source = trigger.dataset.helpImageUrl || trigger.getAttribute('href');
            if (!source) return;
            let url;
            try {
                url = new URL(source, document.baseURI);
            } catch (_) {
                return;
            }
            if (url.protocol !== 'https:' && url.protocol !== 'http:') return;

            event.preventDefault();
            opener = trigger;
            dialogImage.alt = trigger.dataset.helpImageAlt || 'Print do tutorial';
            dialogTitle.textContent = trigger.dataset.helpImageLabel || 'Print ampliado';
            dialogImage.src = url.href;
            if (!dialog.open) dialog.showModal();
            document.documentElement.classList.add('help-print-open');
            const scrollArea = dialog.querySelector('.help-print-scroll');
            if (scrollArea) {
                scrollArea.scrollTop = 0;
                scrollArea.scrollLeft = 0;
            }
        });

        dialog.addEventListener('click', event => {
            if (event.target.closest('[data-help-close]')) dialog.close();
        });
        // Esc é tratado pelo próprio <dialog>; "close" também restaura o foco.
        dialog.addEventListener('close', () => {
            document.documentElement.classList.remove('help-print-open');
            dialogImage.removeAttribute('src');
            dialogImage.alt = '';
            if (opener?.isConnected) opener.focus({ preventScroll: true });
            opener = null;
        });
        window.addEventListener('pagehide', () => {
            if (dialog.open) dialog.close();
            document.documentElement.classList.remove('help-print-open');
        });
    }

    const steps = Array.from(guide.querySelectorAll('[data-help-step]'));
    const links = Array.from(guide.querySelectorAll('[data-help-step-link]'));
    const progress = guide.querySelector('#help-progress');
    const progressContainer = guide.querySelector('[data-help-progress]');
    if (!steps.length || !progress || !progressContainer) return;

    let frame = null;
    const updateReadingPosition = () => {
        frame = null;
        const readingLine = Math.min(window.innerHeight * 0.3, 180);
        const first = steps[0].getBoundingClientRect();
        const last = steps[steps.length - 1].getBoundingClientRect();
        // O último passo nem sempre alcança a linha de leitura: a página acaba
        // antes. Nesse limite, considerar o fim da sequência visível.
        const atPageEnd = window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
        const span = Math.max(last.bottom - first.top, 1);
        const percentage = atPageEnd ? 100 : Math.round(Math.min(1, Math.max(0, (readingLine - first.top) / span)) * 100);
        progress.value = percentage;
        progress.textContent = `${percentage}%`;
        let activeIndex = 0;
        steps.forEach((step, index) => {
            if (step.getBoundingClientRect().top <= readingLine) activeIndex = index;
        });
        if (atPageEnd) activeIndex = steps.length - 1;
        links.forEach((link, index) => {
            if (index === activeIndex) link.setAttribute('aria-current', 'step');
            else link.removeAttribute('aria-current');
        });
    };
    const scheduleUpdate = () => {
        if (frame === null) frame = window.requestAnimationFrame(updateReadingPosition);
    };
    progressContainer.hidden = false;
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate, { passive: true });
    window.addEventListener('pageshow', scheduleUpdate);
    window.addEventListener('hashchange', scheduleUpdate);
    guide.addEventListener('load', scheduleUpdate, true);
    guide.addEventListener('toggle', scheduleUpdate, true);
    updateReadingPosition();
})();
