from django import template

from core.formatting import format_money_br


register = template.Library()


@register.filter
def money_br(value):
    """Exibe somente a parte numérica de um valor monetário: 1.000,50."""
    return format_money_br(value)


@register.filter
def brl(value):
    """Exibe um valor monetário completo: R$ 1.000,50."""
    return format_money_br(value, include_symbol=True)
