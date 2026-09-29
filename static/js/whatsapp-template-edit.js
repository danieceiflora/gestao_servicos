(() => {
    const form = document.getElementById('template-edit-form');
    if (!form) return;
    const state = JSON.parse(document.getElementById('editor-state').textContent);
    const template = JSON.parse(document.getElementById('template-data').textContent);
    const byId = id => document.getElementById(id);
    const buttonsLocked = byId('button-editor').dataset.locked === 'true';
    const named = template.parameter_format === 'NAMED';
    let buttons = state.buttons;
    let submitting = false;
    let initialSnapshot;
    const examples = new Map();
    const variableKeys = text => {
        const keys = [...new Set([...text.matchAll(/\{\{([^{}]+)\}\}/g)].map(m => m[1]))];
        return keys.every(k => /^\d+$/.test(k)) ? keys.sort((a, b) => Number(a) - Number(b)) : keys;
    };
    variableKeys(state.body_text).forEach((key, i) => examples.set(key, state.body_examples[i] || ''));
    ['header_type', 'header_text', 'header_example', 'body_text'].forEach(key => {
        if (key === 'header_type' && ![...byId(key).options].some(o => o.value === state[key])) {
            byId(key).add(new Option(state[key], state[key]));
        }
        byId(key).value = state[key];
    });
    const fieldClass = 'w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm';
    function field(parent, labelText, value, change, options = {}) {
        const label = document.createElement('label');
        label.className = 'block text-sm text-slate-700 space-y-1';
        const caption = document.createElement('span');
        caption.textContent = labelText;
        const input = document.createElement('input');
        input.className = fieldClass;
        input.value = typeof value === 'string' ? value : '';
        Object.assign(input, options);
        input.addEventListener('input', () => { change(input.value); update(); });
        label.append(caption, input);
        parent.append(label);
        return input;
    }
    function renderExamples() {
        const keys = variableKeys(byId('body_text').value);
        const list = byId('examples-list');
        if (list.dataset.keys !== JSON.stringify(keys)) {
            list.replaceChildren();
            keys.forEach(key => field(list, `Exemplo para {{${key}}}`, examples.get(key) || '',
                value => examples.set(key, value), {required: true, disabled: byId('body_text').readOnly}));
            list.dataset.keys = JSON.stringify(keys);
        }
        byId('body-examples-container').hidden = !keys.length;
        byId('body-examples-json').value = JSON.stringify(keys.map(key => examples.get(key) || ''));
    }
    function renderButtons() {
        const list = byId('button-editor');
        list.replaceChildren();
        buttons.forEach((button, index) => {
            const row = document.createElement('div');
            row.className = 'p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3';
            if (buttonsLocked) {
                row.textContent = `${button.text || ''} (${button.type})`;
                list.append(row);
                return;
            }
            const label = document.createElement('label');
            label.textContent = `Tipo do botão ${index + 1}`;
            const select = document.createElement('select');
            select.className = fieldClass;
            [['URL', 'Link'], ['PHONE_NUMBER', 'Telefone'], ['QUICK_REPLY', 'Resposta rápida']].forEach(([v, text]) => select.add(new Option(text, v)));
            select.value = button.type;
            select.addEventListener('change', () => {
                buttons[index] = {type: select.value, text: button.text};
                renderButtons(); update();
            });
            label.append(select); row.append(label);
            field(row, 'Texto do botão', button.text, v => { button.text = v; }, {required: true, maxLength: 25});
            if (button.type === 'URL') {
                field(row, 'URL (use {{1}} no final para um link dinâmico)', button.url, v => { button.url = v; }, {required: true, maxLength: 2000});
                field(row, 'URL completa de exemplo (para link dinâmico)', (button.example || [])[0], v => { button.example = [v]; });
            } else if (button.type === 'PHONE_NUMBER') {
                field(row, 'Telefone com código do país (ex.: +5511999999999)', button.phone_number, v => { button.phone_number = v; }, {required: true, type: 'tel'});
            }
            const actions = document.createElement('div');
            actions.className = 'flex gap-3';
            [['Subir', -1], ['Descer', 1], ['Remover', 0]].forEach(([text, delta]) => {
                const action = document.createElement('button');
                action.type = 'button'; action.textContent = text;
                action.className = 'text-sm text-blue-700 disabled:opacity-50';
                action.disabled = delta !== 0 && (index + delta < 0 || index + delta >= buttons.length);
                action.addEventListener('click', () => {
                    if (delta) [buttons[index], buttons[index + delta]] = [buttons[index + delta], buttons[index]];
                    else buttons.splice(index, 1);
                    renderButtons(); update();
                });
                actions.append(action);
            });
            row.append(actions); list.append(row);
        });
        if (byId('add-button')) byId('add-button').disabled = buttons.length >= 10;
    }
    function snapshot() {
        return JSON.stringify([...new FormData(form).entries()].map(([key, value]) =>
            [key, value instanceof File ? (value.name ? [value.name, value.size, value.lastModified] : '') : value]));
    }
    function update() {
        renderExamples();
        const kind = byId('header_type').value;
        const media = ['IMAGE', 'VIDEO', 'DOCUMENT'].includes(kind);
        byId('header-text-fields').hidden = kind !== 'TEXT';
        byId('header-media-fields').hidden = !media;
        const hasHeaderVariable = variableKeys(byId('header_text').value).length > 0;
        byId('header-example-field').hidden = !hasHeaderVariable;
        byId('header_text').required = kind === 'TEXT';
        byId('header_example').required = kind === 'TEXT' && hasHeaderVariable;
        byId('header_file').required = media && kind !== (template.components.find(c => c.type === 'HEADER') || {}).format;
        byId('header_file').accept = {IMAGE: 'image/jpeg,image/png', VIDEO: 'video/mp4,video/3gpp', DOCUMENT: 'application/pdf'}[kind] || '';
        byId('media-help').textContent = (kind === (template.components.find(c => c.type === 'HEADER') || {}).format
            ? 'Sem novo arquivo, o exemplo atual será mantido. ' : 'Selecione um novo arquivo de exemplo. ')
            + ({IMAGE: 'JPG ou PNG, até 5 MB.', VIDEO: 'MP4 ou 3GP, até 16 MB.', DOCUMENT: 'PDF, até 100 MB.'}[kind] || '');
        byId('preview-header').classList.toggle('hidden', kind !== 'TEXT');
        byId('preview-header').textContent = byId('header_text').value.replace(/\{\{([^{}]+)\}\}/g, match => byId('header_example').value || match);
        byId('preview-header-media').classList.toggle('hidden', !media);
        byId('preview-header-media').textContent = media ? (byId('header_file').files[0]?.name || {IMAGE: 'Imagem', VIDEO: 'Vídeo', DOCUMENT: 'Documento'}[kind]) : '';
        byId('preview-body').textContent = byId('body_text').value.replace(/\{\{([^{}]+)\}\}/g, (match, key) => examples.get(key) || match);
        byId('char-count').textContent = `${byId('body_text').value.length} / 1024`;
        const preview = byId('preview-buttons');
        preview.replaceChildren();
        preview.classList.toggle('hidden', !buttons.length);
        buttons.forEach(button => {
            const item = document.createElement('div');
            item.className = 'p-2.5 text-center text-sm font-semibold text-blue-500';
            item.textContent = button.text || 'Texto do botão'; preview.append(item);
        });
        byId('buttons-json').value = JSON.stringify(buttons);
        byId('submit-btn').disabled = submitting || (form.dataset.retry !== 'true' && snapshot() === initialSnapshot);
    }
    byId('add-button')?.addEventListener('click', () => {
        if (buttons.length >= 10) return;
        buttons.push({type: 'URL', text: '', url: ''}); renderButtons(); update();
    });
    form.querySelectorAll('[data-insert-variable]').forEach(button => button.addEventListener('click', () => {
        const body = byId('body_text');
        const key = named ? `variavel_${button.dataset.insertVariable}` : button.dataset.insertVariable;
        body.setRangeText(`{{${key}}}`, body.selectionStart, body.selectionEnd, 'end');
        body.focus(); update();
    }));
    byId('header_type').addEventListener('change', () => { byId('header_file').value = ''; });
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('submit', event => {
        if (submitting) { event.preventDefault(); return; }
        update(); submitting = true;
        byId('submit-btn').disabled = true;
        byId('submit-btn').textContent = 'Aguarde…';
        form.setAttribute('aria-busy', 'true');
    });
    window.addEventListener('pageshow', () => {
        submitting = false; form.removeAttribute('aria-busy');
        byId('submit-btn').textContent = 'Enviar para Revisão'; update();
    });
    const footer = template.components.find(c => c.type === 'FOOTER');
    if (footer?.text) { byId('preview-footer').textContent = footer.text; byId('preview-footer').classList.remove('hidden'); }
    renderButtons(); update(); initialSnapshot = snapshot(); update();
})();
