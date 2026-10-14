(function () {
    'use strict';

    function normalize(value) {
        return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
    }

    function makeButton(className, label, onClick) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        button.textContent = label;
        button.addEventListener('click', onClick);
        return button;
    }

    function initPicker(select) {
        if (select.dataset.categoryEnhanced !== undefined) return;
        const entries = Array.from(select.options).filter(option => option.value).map(option => ({
            id: option.value,
            name: option.dataset.categoryName || option.textContent.trim(),
            parentId: option.dataset.parentId || '',
            label: option.textContent.trim(),
        }));
        const roots = entries.filter(entry => !entry.parentId).sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
        const children = new Map();
        for (const entry of entries.filter(item => item.parentId)) {
            if (!children.has(entry.parentId)) children.set(entry.parentId, []);
            children.get(entry.parentId).push(entry);
        }
        for (const group of children.values()) {
            group.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'financial-category-picker';
        if (select.dataset.categoryPickerWidth === 'filter') {
            wrapper.classList.add('financial-category-picker--filter');
        }
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);

        const trigger = makeButton('financial-category-picker__trigger', '', () => {
            if (menu.hidden) open();
            else close();
        });
        trigger.id = (select.id || select.name) + '-picker';
        trigger.setAttribute('aria-haspopup', 'dialog');
        trigger.setAttribute('aria-expanded', 'false');
        const label = document.createElement('span');
        label.className = 'financial-category-picker__value';
        const chevron = document.createElement('span');
        chevron.className = 'financial-category-picker__chevron';
        chevron.setAttribute('aria-hidden', 'true');
        chevron.textContent = '⌄';
        trigger.append(label, chevron);
        wrapper.appendChild(trigger);

        const menu = document.createElement('div');
        menu.className = 'financial-category-picker__menu';
        menu.id = trigger.id + '-menu';
        menu.setAttribute('role', 'dialog');
        menu.setAttribute('aria-label', 'Selecionar categoria');
        menu.hidden = true;
        trigger.setAttribute('aria-controls', menu.id);
        const search = document.createElement('input');
        search.type = 'search';
        search.className = 'financial-category-picker__search';
        search.placeholder = 'Buscar categoria...';
        search.setAttribute('aria-label', 'Buscar categoria');
        const results = document.createElement('div');
        results.className = 'financial-category-picker__results';
        results.setAttribute('role', 'group');
        results.setAttribute('aria-label', 'Categorias');
        menu.append(search, results);
        document.body.appendChild(menu);

        const expanded = new Set();
        const selected = entries.find(entry => entry.id === select.value);
        if (selected && selected.parentId) expanded.add(selected.parentId);

        function updateLabel() {
            const option = select.selectedOptions[0];
            label.textContent = option && option.value ? option.textContent.trim() :
                (select.dataset.categoryPlaceholder || 'Sem categoria');
            trigger.title = label.textContent;
        }

        function positionMenu() {
            if (menu.hidden) return;
            const rect = trigger.getBoundingClientRect();
            const below = window.innerHeight - rect.bottom - 8;
            const above = rect.top - 8;
            const showAbove = below < 180 && above > below;
            const height = Math.max(100, Math.min(340, showAbove ? above : below));
            const width = Math.min(Math.max(rect.width, 280), window.innerWidth - 16);
            menu.style.width = width + 'px';
            menu.style.maxHeight = height + 'px';
            menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + 'px';
            menu.style.top = (showAbove ? rect.top - height - 4 : rect.bottom + 4) + 'px';
        }

        function close(restoreFocus) {
            menu.hidden = true;
            trigger.setAttribute('aria-expanded', 'false');
            if (restoreFocus) trigger.focus();
        }

        function choose(value) {
            select.value = value;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            updateLabel();
            close(true);
        }

        function addChoice(entry, isChild) {
            const choice = makeButton('financial-category-picker__choice', entry.name, () => choose(entry.id));
            choice.dataset.categoryId = entry.id;
            choice.setAttribute('aria-pressed', String(select.value === entry.id));
            if (isChild) choice.classList.add('financial-category-picker__choice--child');
            return choice;
        }

        function render() {
            const query = normalize(search.value.trim());
            results.replaceChildren();

            if (!query) {
                const empty = makeButton('financial-category-picker__choice',
                    select.options[0].textContent.trim(), () => choose(''));
                empty.setAttribute('aria-pressed', String(!select.value));
                results.appendChild(empty);
            }

            let visibleCategories = 0;
            for (const root of roots) {
                const group = children.get(root.id) || [];
                const rootMatches = normalize(root.name).includes(query);
                const matchingChildren = query && !rootMatches ?
                    group.filter(child => normalize(child.name).includes(query)) : group;
                if (query && !rootMatches && !matchingChildren.length) continue;
                visibleCategories += 1 + matchingChildren.length;

                const row = document.createElement('div');
                row.className = 'financial-category-picker__row';
                const isExpanded = query ? true : expanded.has(root.id);
                if (group.length) {
                    const toggle = makeButton('financial-category-picker__toggle', isExpanded ? '▾' : '▸', () => {
                        if (expanded.has(root.id)) expanded.delete(root.id);
                        else expanded.add(root.id);
                        render();
                        const replacement = Array.from(results.querySelectorAll('.financial-category-picker__toggle'))
                            .find(item => item.dataset.categoryId === root.id);
                        if (replacement) replacement.focus();
                    });
                    toggle.dataset.categoryId = root.id;
                    toggle.setAttribute('aria-expanded', String(isExpanded));
                    toggle.setAttribute('aria-label', (isExpanded ? 'Recolher ' : 'Expandir ') + root.name);
                    row.appendChild(toggle);
                } else {
                    const spacer = document.createElement('span');
                    spacer.className = 'financial-category-picker__spacer';
                    spacer.setAttribute('aria-hidden', 'true');
                    row.appendChild(spacer);
                }
                row.appendChild(addChoice(root, false));
                results.appendChild(row);

                if (isExpanded) {
                    for (const child of matchingChildren) {
                        const childRow = document.createElement('div');
                        childRow.className = 'financial-category-picker__row financial-category-picker__row--child';
                        childRow.appendChild(addChoice(child, true));
                        results.appendChild(childRow);
                    }
                }
            }

            if (!visibleCategories && query) {
                const empty = document.createElement('p');
                empty.className = 'financial-category-picker__empty';
                empty.textContent = 'Nenhuma categoria encontrada.';
                results.appendChild(empty);
            }
        }

        function open() {
            document.querySelectorAll('.financial-category-picker__menu:not([hidden])').forEach(other => {
                if (other !== menu) other.dispatchEvent(new Event('category-picker-close'));
            });
            search.value = '';
            render();
            menu.hidden = false;
            trigger.setAttribute('aria-expanded', 'true');
            positionMenu();
            search.focus();
        }

        menu.addEventListener('category-picker-close', () => close());
        search.addEventListener('input', render);
        select.addEventListener('change', updateLabel);
        trigger.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                if (menu.hidden) open();
            } else if (event.key === 'Escape') close();
        });
        menu.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close(true);
            } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                const choices = Array.from(results.querySelectorAll('.financial-category-picker__choice'));
                const index = choices.indexOf(document.activeElement);
                const next = event.key === 'ArrowDown' ? Math.min(index + 1, choices.length - 1) : index - 1;
                if (next >= 0 && choices[next]) choices[next].focus();
                else search.focus();
                event.preventDefault();
            } else if (event.key === 'Enter' && document.activeElement === search) {
                const first = search.value.trim() && results.querySelector('.financial-category-picker__choice');
                if (first) first.click();
                event.preventDefault();
            } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
                const active = document.activeElement;
                const root = roots.find(item => item.id === active.dataset.categoryId);
                if (root && children.has(root.id)) {
                    if (event.key === 'ArrowRight') expanded.add(root.id);
                    else expanded.delete(root.id);
                    render();
                    const choice = Array.from(results.querySelectorAll('.financial-category-picker__choice'))
                        .find(item => item.dataset.categoryId === root.id);
                    if (choice) choice.focus();
                    event.preventDefault();
                }
            }
        });
        document.addEventListener('pointerdown', event => {
            if (!menu.hidden && !menu.contains(event.target) && !trigger.contains(event.target)) close();
        });
        document.addEventListener('focusin', event => {
            if (!menu.hidden && !menu.contains(event.target) && event.target !== trigger) close();
        });
        window.addEventListener('scroll', positionMenu, true);
        window.addEventListener('resize', positionMenu);

        select.dataset.categoryEnhanced = '';
        select.classList.add('financial-category-picker__native');
        const externalLabel = select.id && document.querySelector('label[for="' + CSS.escape(select.id) + '"]');
        if (externalLabel) externalLabel.htmlFor = trigger.id;
        updateLabel();
    }

    function initAll() {
        document.querySelectorAll('select[data-category-picker]').forEach(initPicker);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
    else initAll();
})();
