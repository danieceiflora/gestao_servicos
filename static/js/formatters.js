(function (global) {
    'use strict';

    const moneyFormatter = new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });

    function parseDisplayNumber(value) {
        if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
        if (value === null || value === undefined || value === '') return 0;
        let raw = String(value).trim().replace(/R\$|\s/g, '');
        if (raw.includes(',')) raw = raw.replace(/\./g, '').replace(',', '.');
        const parsed = Number(raw);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatMoneyBR(value, includeSymbol = false) {
        const rendered = moneyFormatter.format(parseDisplayNumber(value));
        return includeSymbol ? `R$ ${rendered}` : rendered;
    }

    global.parseDisplayNumber = parseDisplayNumber;
    global.formatMoneyBR = formatMoneyBR;
    global.formatBRL = value => formatMoneyBR(value, true);
})(window);
