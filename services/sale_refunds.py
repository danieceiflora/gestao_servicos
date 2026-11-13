"""Financial consequences of approved returns and manual refund records."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.models import GatewayCharge
from pagamentos.settlement import PAID, apply_charge_status, refresh_billing
from .models import Billing, Installment, SalePayment, SaleRefund, SaleRefundPayment, SaleReturn, StockMovement
from .pos_payments import lock_sale


def sale_receipts(sale):
    return SalePayment.objects.filter(Q(venda=sale) | Q(installment__billing__sale=sale)).distinct().aggregate(
        total=Sum('valor_bruto'))['total'] or Decimal('0.00')


def _cancel_return_charges(sale_id):
    """Persist each confirmed remote change so a later retry can reconcile safely."""
    charge_ids = list(GatewayCharge.objects.filter(
        installment__billing__sale_id=sale_id,
        status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.OVERDUE],
    ).values_list('pk', flat=True))
    if not charge_ids:
        return
    gateway = AsaasGateway()
    for charge_id in charge_ids:
        charge = GatewayCharge.objects.get(pk=charge_id)
        if charge.status not in (GatewayCharge.Status.PENDING, GatewayCharge.Status.OVERDUE):
            continue
        result = gateway.get_charge(charge.external_id)
        apply_charge_status(charge.pk, result.status, result.net_value)
        charge.refresh_from_db(fields=['status'])
        if charge.status in PAID or charge.status in (GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED):
            continue
        if not gateway.cancel_charge(charge.external_id):
            result = gateway.get_charge(charge.external_id)
            apply_charge_status(charge.pk, result.status, result.net_value)
            if result.status not in (*PAID, GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED):
                raise ValueError('O gateway não confirmou o cancelamento da cobrança. Tente novamente após conciliá-la.')
        else:
            apply_charge_status(charge.pk, GatewayCharge.Status.CANCELLED)


def approve_return(return_id, user):
    initial = SaleReturn.objects.select_related('sale').get(pk=return_id)
    if initial.sale.status == initial.sale.Status.CANCELADO or initial.status != SaleReturn.Status.PENDENTE:
        raise ValueError('Esta devolução não pode mais ser aprovada.')
    _cancel_return_charges(initial.sale_id)
    return _approve_return_local(return_id, user)


@transaction.atomic
def _approve_return_local(return_id, user):
    initial = SaleReturn.objects.select_related('sale').get(pk=return_id)
    sale = lock_sale(initial.sale_id)
    ret = SaleReturn.objects.select_for_update().get(pk=return_id)
    if sale.status == sale.Status.CANCELADO or ret.status != SaleReturn.Status.PENDENTE:
        raise ValueError('Esta devolução não pode mais ser aprovada.')

    billing = Billing.objects.select_for_update().filter(sale=sale).first()
    installments = list(Installment.objects.select_for_update().filter(billing=billing).order_by('-due_date', '-pk')) if billing else []
    if GatewayCharge.objects.filter(installment__billing__sale=sale,
                                    status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.OVERDUE]).exists():
        raise ValueError('Há uma cobrança aberta no gateway. Tente aprovar novamente após conciliá-la.')
    remaining_return = ret.total_refund
    reduction = Decimal('0.00')
    for inst in installments:
        if remaining_return <= 0:
            break
        paid = inst.get_total_paid()
        available = max(inst.amount - paid, Decimal('0.00')) if inst.status != Installment.Status.CANCELADO else Decimal('0.00')
        amount = min(available, remaining_return)
        if not amount:
            continue
        new_amount = inst.amount - amount
        inst.amount = new_amount
        if new_amount == 0:
            inst.status = Installment.Status.CANCELADO
        elif new_amount <= paid:
            inst.status = Installment.Status.PAGO
        inst.save(update_fields=['amount', 'status'])
        reduction += amount
        remaining_return -= amount

    if not billing:
        previous_reductions = SaleRefund.objects.filter(sale=sale).aggregate(total=Sum('balance_reduction'))['total'] or Decimal('0.00')
        implicit_open = max(sale.total_amount - sale_receipts(sale) - previous_reductions, Decimal('0.00'))
        implicit_reduction = min(remaining_return, implicit_open)
        reduction += implicit_reduction
        remaining_return -= implicit_reduction
    remaining_return = min(remaining_return, max(
        sale_receipts(sale) - (SaleRefund.objects.filter(sale=sale).aggregate(total=Sum('due_amount'))['total'] or Decimal('0.00')),
        Decimal('0.00'),
    ))
    if billing:
        if not billing.installments.exclude(status=Installment.Status.CANCELADO).exists():
            billing.status = Billing.Status.CANCELADO
            billing.save(update_fields=['status', 'updated_at'])
        else:
            refresh_billing(billing)
    for item in ret.items.select_related('sale_item__product', 'sale_item__variant'):
        if item.restock and sale.stock_reduced:
            target = item.sale_item.variant or item.sale_item.product
            target = type(target).objects.select_for_update().get(pk=target.pk)
            target.increase_stock(item.quantity, user=user, reason=StockMovement.Reason.DEVOLUCAO,
                                  notes=f'Devolução #{ret.pk} — Venda #{sale.number}',
                                  explode_composition=True)
    ret.status = SaleReturn.Status.APROVADA
    ret.save(update_fields=['status'])
    return SaleRefund.objects.create(
        sale=sale, sale_return=ret, kind=SaleRefund.Kind.RETURN,
        due_amount=remaining_return, balance_reduction=reduction, created_by=user,
    )


@transaction.atomic
def record_refund_payment(refund_id, *, amount, method, paid_at, reference, notes, user):
    refund = SaleRefund.objects.select_for_update().get(pk=refund_id)
    if refund.review_required:
        raise ValueError('Confira o valor desta devolução histórica antes de registrar o estorno.')
    if amount <= 0 or amount > refund.remaining_amount:
        raise ValueError('O valor deve ser positivo e não pode ultrapassar o saldo do estorno.')
    return SaleRefundPayment.objects.create(
        refund=refund, amount=amount, method=method, paid_at=paid_at,
        reference=reference, notes=notes, created_by=user,
    )
