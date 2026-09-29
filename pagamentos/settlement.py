"""Shared, idempotent settlement for webhooks and explicit reconciliation."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from pagamentos.models import GatewayCharge
from services.models import Billing, CashMovement, Installment, PaymentMethod, Sale, SalePayment

PAID = (GatewayCharge.Status.RECEIVED, GatewayCharge.Status.CONFIRMED)


@transaction.atomic
def apply_charge_status(charge_id, status, net_value=None):
    initial = GatewayCharge.objects.select_related('installment__billing').get(pk=charge_id)
    sale = None
    if initial.installment.billing.sale_id:
        from services.pos_payments import lock_sale
        sale = lock_sale(initial.installment.billing.sale_id)
    billing = Billing.objects.select_for_update().get(pk=initial.installment.billing_id)
    inst = Installment.objects.select_for_update().get(pk=initial.installment_id)
    charge = GatewayCharge.objects.select_for_update().get(pk=charge_id)
    # A delayed pending/cancelled event cannot undo a confirmed receipt.
    if charge.status in PAID and status not in (*PAID, GatewayCharge.Status.REFUNDED):
        return charge
    charge.status = status
    if net_value is not None:
        charge.net_value = Decimal(str(net_value))
    if status in PAID and not charge.paid_at:
        charge.paid_at = timezone.now()
    charge.save(update_fields=['status', 'paid_at', 'net_value', 'updated_at'])
    if status not in PAID:
        return charge

    method = charge.payment_method
    if method is None and inst.payment_method and inst.payment_method.tipo_provedor == charge.method:
        method = inst.payment_method
    if method is None:
        method = PaymentMethod.objects.filter(tipo_provedor=charge.method).order_by('pk').first()
    if method is None:
        raise ValueError('Não há método cadastrado para conciliar esta cobrança.')

    payment = SalePayment.objects.filter(gateway_charge=charge).first()
    if payment is None:
        # Adopt the historical automatic receipt instead of paying the installment twice.
        payment = SalePayment.objects.filter(
            installment=inst, is_gateway_auto=True, gateway_charge__isnull=True,
        ).first()
        if payment:
            payment.gateway_charge = charge
            payment.save(update_fields=['gateway_charge'])
        else:
            net = charge.net_value if charge.net_value is not None else charge.amount
            is_pos = bool(sale and sale.origin == Sale.Origin.POS)
            payment = SalePayment.objects.create(
                gateway_charge=charge, installment=inst, venda=sale,
                metodo_pagamento=method, valor_bruto=charge.amount,
                valor_tarifa=max(charge.amount - net, Decimal('0')), valor_liquido=net,
                data_pagamento=charge.paid_at, data_previsao=charge.paid_at.date(),
                is_gateway_auto=True, operator=sale.user if is_pos else None,
                cash_session=sale.cash_session if is_pos else None,
            )
            if is_pos:
                CashMovement.objects.create(
                    session=sale.cash_session, movement_type=CashMovement.MovementType.SALE,
                    amount=charge.amount, payment_method=method, sale=sale,
                    created_by=sale.user, notes=f'PIX confirmado — pagamento #{payment.pk}',
                )
    inst.status, inst.paid_at = Installment.Status.PAGO, charge.paid_at
    if net_value is not None:
        payment.valor_liquido = charge.net_value
        payment.valor_tarifa = max(charge.amount - charge.net_value, Decimal('0'))
        payment.save(update_fields=['valor_liquido', 'valor_tarifa'])
    inst.save(update_fields=['status', 'paid_at'])
    refresh_billing(billing)
    if sale and sale.pos_checkout_key:
        from services.pos_payments import finish_if_ready
        finish_if_ready(sale)
    return charge


def refresh_billing(billing):
    active = billing.installments.exclude(status=Installment.Status.CANCELADO)
    if not active.exclude(status=Installment.Status.PAGO).exists() or billing.get_remaining_balance() <= 0:
        billing.status = Billing.Status.PAGO
    elif billing.get_total_paid() > 0:
        billing.status = Billing.Status.PARCIAL
    else:
        billing.status = Billing.Status.PENDENTE
    billing.save(update_fields=['status', 'updated_at'])
