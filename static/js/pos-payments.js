/* Persistent PIX checkout. The server is the authority for all received values. */
(() => {
    const config = window.POS_PAYMENT_CONFIG;
    const storageKey = `pos-checkout-${config.sessionId}`;
    let busy = false, currentId = config.pendingId, timer, lastData, replacing = false;
    let checkoutKey = localStorage.getItem(storageKey);
    const dialog = document.createElement('dialog');
    dialog.id = 'pix-checkout-dialog';
    dialog.className = 'fixed inset-0 z-[100] m-auto max-h-[calc(100dvh-2rem)] w-[min(620px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl backdrop:bg-slate-950/60';
    dialog.addEventListener('cancel', event => event.preventDefault());
    document.body.append(dialog);
    const heading = document.createElement('h2');
    heading.className = 'text-xl font-bold text-slate-900';
    const notice = document.createElement('p');
    notice.className = 'my-3 text-sm text-slate-600';
    notice.setAttribute('role', 'status');
    const parts = document.createElement('div');
    parts.className = 'space-y-3';
    const actions = document.createElement('div');
    actions.className = 'mt-4 flex flex-wrap gap-2';
    dialog.append(heading, notice, parts, actions);

    const button = (label, action) => {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = 'rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold';
        element.textContent = label;
        element.addEventListener('click', action);
        return element;
    };
    const text = (parent, value, tag = 'p') => {
        const element = document.createElement(tag);
        element.textContent = value;
        parent.append(element);
        return element;
    };
    const url = kind => config[`${kind}Url`].replace('/0/', `/${currentId}/`);
    async function request(endpoint, payload) {
        const options = payload === undefined ? {} : {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
            body: JSON.stringify(payload),
        };
        const response = await fetch(endpoint, options);
        const data = await response.json();
        if (!response.ok) {
            const error = new Error(data.error || 'Não foi possível consultar o pagamento.');
            error.status = response.status;
            throw error;
        }
        return data;
    }
    function open() {
        document.getElementById('payment-dialog')?.close();
        if (!dialog.open) dialog.showModal();
    }
    function render(data) {
        lastData = data;
        currentId = data.sale_id;
        open();
        heading.textContent = `Recebimento da venda #${data.number}`;
        notice.textContent = `Recebido: ${brl(Number(data.received))} · Saldo: ${brl(Number(data.remaining))}`;
        parts.replaceChildren();
        actions.replaceChildren();
        if (data.finalized || data.status === 'CANCELADO') {
            clearTimeout(timer);
            localStorage.removeItem(storageKey);
            notice.textContent = data.finalized ? 'Venda finalizada. Recebimentos confirmados.' : 'Venda cancelada.';
            if (data.receipt_url) {
                const receipt = document.createElement('a');
                receipt.href = data.receipt_url;
                receipt.target = '_blank';
                receipt.rel = 'noopener';
                receipt.className = 'rounded-xl bg-emerald-600 px-4 py-2 text-white';
                receipt.textContent = 'Abrir comprovante';
                actions.append(receipt);
            }
            actions.append(button('Voltar ao caixa', () => location.reload()));
            return;
        }
        data.parts.forEach(part => {
            const card = document.createElement('div');
            card.className = 'space-y-2 rounded-xl border border-slate-200 p-4';
            card.dataset.installmentId = part.id;
            text(card, `${part.method} — ${brl(Number(part.amount))}`, 'strong');
            text(card, part.paid ? 'Recebido' : part.behavior === 'RECEIVABLE' ? 'Conta a receber' : 'Aguardando pagamento');
            if (!part.paid && part.behavior === 'WAIT_GATEWAY') {
                if (part.message) text(card, part.message);
                if (part.expires_at) text(card, `Validade do código: ${new Date(part.expires_at).toLocaleString('pt-BR')}`);
                if (part.charge_status === 'CANCELLED') text(card, 'PIX cancelado. Escolha outra forma para este saldo.');
                else {
                    if (part.qr_code) {
                        const image = document.createElement('img');
                        image.src = `data:image/png;base64,${part.qr_code}`;
                        image.alt = `QR Code PIX de ${brl(Number(part.amount))}`;
                        image.width = image.height = 220;
                        card.append(image);
                    }
                    if (part.copy_paste) {
                        const code = document.createElement('textarea');
                        code.value = part.copy_paste;
                        code.readOnly = true;
                        code.className = 'w-full rounded-lg border p-2 text-xs';
                        code.setAttribute('aria-label', 'PIX copia e cola');
                        card.append(code, button('Copiar PIX', async () => {
                            try { await navigator.clipboard.writeText(part.copy_paste); notice.textContent = 'PIX copiado.'; }
                            catch { code.focus(); code.select(); notice.textContent = 'Selecione e copie o código PIX.'; }
                        }));
                    }
                }
                card.append(button('Trocar forma deste saldo', () => replacement(part)));
            }
            parts.append(card);
        });
        actions.append(button('Verificar pagamento', () => mutate('verify', {})));
        if (Number(data.received) === 0) actions.append(button('Cancelar venda', () => {
            if (confirm('Cancelar as cobranças pendentes e esta venda?')) mutate('cancel', {});
        }));
        schedule();
    }
    function schedule() {
        clearTimeout(timer);
        if (lastData?.finalized || lastData?.status === 'CANCELADO') return;
        timer = setTimeout(poll, 3000);
    }
    async function poll() {
        if (busy || replacing) return schedule();
        try {
            const data = await request(url('status'));
            if (!busy && !replacing) render(data);
            else schedule();
        }
        catch { notice.textContent = 'Conexão interrompida. O pagamento continua sendo acompanhado; tentando novamente…'; schedule(); }
    }
    async function mutate(kind, payload) {
        if (busy) return;
        busy = true;
        clearTimeout(timer);
        dialog.setAttribute('aria-busy', 'true');
        dialog.querySelectorAll('button').forEach(element => element.disabled = true);
        notice.textContent = 'Aguarde…';
        try { replacing = false; render(await request(url(kind), payload)); }
        catch (error) { notice.textContent = error.message; }
        finally {
            busy = false;
            dialog.removeAttribute('aria-busy');
            dialog.querySelectorAll('button').forEach(element => element.disabled = false);
            schedule();
        }
    }
    function replacement(part) {
        if (busy) return;
        replacing = true;
        clearTimeout(timer);
        parts.replaceChildren();
        actions.replaceChildren();
        notice.textContent = `Trocar somente ${brl(Number(part.amount))}. Os valores já recebidos serão preservados. Confirme apenas valores manuais que você já recebeu.`;
        const rows = document.createElement('div');
        rows.className = 'space-y-3';
        parts.append(rows);
        const add = value => {
            const row = document.createElement('div');
            row.className = 'flex flex-wrap gap-2';
            const method = document.createElement('select');
            method.setAttribute('aria-label', 'Nova forma de pagamento');
            METHODS.forEach(m => method.add(new Option(m.name, m.id)));
            const amount = document.createElement('input');
            amount.type = 'number'; amount.step = '0.01'; amount.min = '0.01'; amount.value = value;
            amount.setAttribute('aria-label', 'Valor da nova forma');
            const tendered = document.createElement('input');
            tendered.type = 'number'; tendered.step = '0.01'; tendered.value = value;
            tendered.setAttribute('aria-label', 'Valor recebido');
            for (const input of [method, amount, tendered]) input.className = 'rounded-lg border p-2 w-full';
            row.append(method, amount, tendered, button('Remover', () => row.remove()));
            row.payment = () => ({method_id: method.value, amount: amount.value, tendered: tendered.value});
            rows.append(row);
        };
        add(part.amount);
        actions.append(button('Adicionar forma', () => add('0.00')),
            button('Confirmar troca e recebimentos', () => mutate('replace', {
                installment_id: part.id, payments: [...rows.children].map(row => row.payment()),
            })), button('Voltar', () => { replacing = false; render(lastData); }));
    }
    window.PosCheckout = {
        isBusy: () => busy || Boolean(currentId),
        async start(payload) {
            if (busy || currentId) return;
            busy = true;
            if (!checkoutKey) {
                checkoutKey = crypto.randomUUID();
                localStorage.setItem(storageKey, checkoutKey);
            }
            const submit = document.querySelector('#payment-dialog button[onclick="saveSale(\'finalize\')"]');
            if (submit) { submit.disabled = true; submit.textContent = 'Aguarde…'; }
            try { render(await request(config.startUrl, {...payload, checkout_key: checkoutKey})); }
            catch (error) {
                if (error.status === 400) { localStorage.removeItem(storageKey); checkoutKey = null; }
                alert(`${error.message}\nSe a conexão caiu, tente novamente para recuperar o mesmo recebimento.`);
            }
            finally {
                busy = false;
                if (submit) { submit.disabled = false; submit.textContent = 'Finalizar venda'; }
            }
        },
    };
    if (currentId) {
        open();
        heading.textContent = 'Recuperando recebimento…';
        poll();
    } else if (checkoutKey) {
        busy = true;
        open();
        heading.textContent = 'Recuperando recebimento…';
        const recover = async () => {
            try {
                const data = await request(config.recoverUrl.replace('00000000-0000-0000-0000-000000000000', checkoutKey));
                if (data.found === false) {
                    localStorage.removeItem(storageKey);
                    checkoutKey = null;
                    dialog.close();
                } else render(data);
                busy = false;
            } catch {
                notice.textContent = 'Não foi possível recuperar o recebimento. Tentando novamente…';
                setTimeout(recover, 3000);
            }
        };
        recover();
    }
})();
