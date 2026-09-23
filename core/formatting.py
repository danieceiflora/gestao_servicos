from decimal import Decimal, InvalidOperation


def decimal_from_display(value):
    """Converte números canônicos ou já localizados em Decimal."""
    if isinstance(value, Decimal):
        return value
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    raw = str(value).strip().replace('R$', '').replace('\xa0', '').replace(' ', '')
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def format_money_br(value, include_symbol=False):
    """Formata dinheiro em pt-BR sem depender do locale do sistema operacional."""
    amount = decimal_from_display(value)
    if amount is None:
        return ''
    rendered = format(amount, ',.2f').replace(',', '\0').replace('.', ',').replace('\0', '.')
    return f'R$ {rendered}' if include_symbol else rendered
