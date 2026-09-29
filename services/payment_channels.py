"""Availability by channel, independently of gateway capability."""
from django.db.models import Q
from services.models import PaymentMethod, Sale


def pos_methods():
    return PaymentMethod.objects.filter(ativo=True).exclude(
        pos_behavior=PaymentMethod.PosBehavior.DISABLED,
    ).order_by('descricao', 'pk')


def public_methods(config):
    methods = PaymentMethod.objects.filter(ativo=True, public_billing_enabled=True)
    allowed = Q(tipo_provedor='PIX', pix_type=PaymentMethod.PixType.STATIC,
                integra_gateway=False) & ~Q(pix_key='')
    if config.can_generate_charges:
        if config.pix_enabled:
            allowed |= Q(tipo_provedor='PIX', pix_type=PaymentMethod.PixType.DYNAMIC,
                         integra_gateway=True)
        if config.boleto_enabled:
            allowed |= Q(tipo_provedor='BOLETO', integra_gateway=True)
    return methods.filter(allowed).order_by('descricao', 'pk')


def public_generation_blocked(billing):
    return bool(billing.sale_id and billing.sale.origin == Sale.Origin.POS
                and billing.sale.status == Sale.Status.AGUARDANDO_PAGAMENTO)
