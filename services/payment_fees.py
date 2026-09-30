"""Tarifa por transação e snapshot da regra aplicada."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


CENT = Decimal('0.01')


def product_terms(product_code):
    return settings.INTEGRATED_PAYMENT_PRODUCTS.get(product_code)


def terms_for_method(method):
    product = product_terms(method.integrated_product) if method.integra_gateway else None
    if product:
        return {
            'product': method.integrated_product,
            'percent': str(product['percent']), 'minimum': str(product['minimum']),
            'maximum': str(product['maximum']), 'fixed': '0',
        }
    return {
        'product': '', 'percent': str(method.tarifa_porcentagem),
        'minimum': str(method.tarifa_minima), 'maximum': str(method.tarifa_maxima),
        'fixed': str(method.tarifa_fixa),
    }


def calculate_fee(amount, terms):
    amount = Decimal(str(amount))
    percentage = amount * Decimal(terms['percent']) / Decimal('100')
    variable = max(percentage, Decimal(terms['minimum']))
    maximum = Decimal(terms['maximum'])
    if maximum:
        variable = min(variable, maximum)
    fee = (variable + Decimal(terms['fixed'])).quantize(CENT, rounding=ROUND_HALF_UP)
    return min(max(fee, Decimal('0')), amount)
