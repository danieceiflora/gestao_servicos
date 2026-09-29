"""Coordinated cancellation; gateway confirmations survive partial failures."""
import logging
from dataclasses import dataclass
from functools import wraps

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect

from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.models import GatewayCharge, PosChargeAttempt
from pagamentos.settlement import PAID, apply_charge_status
from .models import Billing, Installment, Sale, SalePayment, StockMovement
from .pos_payments import lock_sale, _adopt_result

logger = logging.getLogger(__name__)
PAID_MESSAGE = 'Esta venda possui valores recebidos. Trate a devolução/estorno separadamente antes de cancelar.'


def has_receipts(sale):
    return (
        SalePayment.objects.filter(Q(venda=sale) | Q(installment__billing__sale=sale), valor_bruto__gt=0).exists()
        or Installment.objects.filter(billing__sale=sale, status__in=['PAGO', 'PARCIAL']).exists()
        or GatewayCharge.objects.filter(installment__billing__sale=sale, status__in=PAID).exists()
    )


def lock_open_installment(pk):
    """Must run inside atomic; same lock order as settlement and cancellation."""
    initial = Installment.objects.select_related('billing').get(pk=pk)
    sale = lock_sale(initial.billing.sale_id) if initial.billing.sale_id else None
    billing = Billing.objects.select_for_update().get(pk=initial.billing_id)
    inst = Installment.objects.select_for_update().get(pk=pk)
    if (sale and sale.status == Sale.Status.CANCELADO) or billing.status == Billing.Status.CANCELADO or inst.status == Installment.Status.CANCELADO:
        raise ValueError('Venda, conta a receber ou parcela cancelada. Não é possível registrar novas operações.')
    return inst


def guard_installment_payment(view):
    @wraps(view)
    def wrapped(request, pk):
        initial = get_object_or_404(Installment, pk=pk)
        with transaction.atomic():
            try:
                lock_open_installment(pk)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('billing_detail', pk=initial.billing_id)
            return view(request, pk)
    return wrapped


@dataclass
class CancellationResult:
    success: bool
    message: str


@transaction.atomic
def cancel_sale(sale_id, user):
    sale = lock_sale(sale_id)
    if sale.status == Sale.Status.CANCELADO:
        return CancellationResult(True, 'Esta venda já está cancelada.')
    billing = Billing.objects.select_for_update().filter(sale=sale).first()
    if billing:
        list(Installment.objects.select_for_update().filter(billing=billing).order_by('pk'))
    if has_receipts(sale):
        return CancellationResult(False, PAID_MESSAGE)

    gateway = AsaasGateway()
    # An in-flight/uncertain POS emission must not be left payable after cancellation.
    attempts = PosChargeAttempt.objects.select_for_update().filter(installment__billing__sale=sale, charge__isnull=True)
    for attempt in attempts:
        if attempt.state == PosChargeAttempt.State.REJECTED:
            continue
        try:
            result = gateway.find_charge_by_reference(str(attempt.reference))
            if result is None:
                return CancellationResult(False, 'Existe uma emissão de PIX ainda não conciliada. Use Verificar pagamento no PDV antes de cancelar.')
            _adopt_result(attempt.pk, result)
        except Exception:
            logger.exception('Falha ao conciliar emissão antes de cancelar venda %s', sale.pk)
            return CancellationResult(False, 'Não foi possível conciliar a emissão do PIX. A venda não foi cancelada.')

    charges = list(GatewayCharge.objects.select_for_update().filter(installment__billing__sale=sale).order_by('pk'))
    try:
        # Check all charges before deleting any, including overdue ones.
        for charge in charges:
            if charge.status in (GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED):
                continue
            result = gateway.get_charge(charge.external_id)
            apply_charge_status(charge.pk, result.status, result.net_value)
            charge.status = result.status
        if has_receipts(sale):
            return CancellationResult(False, PAID_MESSAGE)
        for charge in charges:
            if charge.status in (GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED):
                continue
            if charge.status not in (GatewayCharge.Status.PENDING, GatewayCharge.Status.OVERDUE):
                return CancellationResult(False, 'A cobrança não está em um estado que permita cancelamento. Verifique o gateway.')
            if not gateway.cancel_charge(charge.external_id):
                result = gateway.get_charge(charge.external_id)
                apply_charge_status(charge.pk, result.status, result.net_value)
                if result.status in PAID:
                    return CancellationResult(False, PAID_MESSAGE)
                if result.status != GatewayCharge.Status.CANCELLED:
                    return CancellationResult(False, 'O gateway não confirmou todos os cancelamentos. A venda permanece ativa; tente novamente para concluir. Cancelamentos já confirmados foram preservados.')
            apply_charge_status(charge.pk, GatewayCharge.Status.CANCELLED)
    except Exception:
        logger.exception('Falha no gateway ao cancelar venda %s', sale.pk)
        return CancellationResult(False, 'Não foi possível confirmar todos os cancelamentos no gateway. A venda permanece ativa; tente novamente para reconciliar e concluir. Cancelamentos já confirmados foram preservados.')

    if has_receipts(sale):
        return CancellationResult(False, PAID_MESSAGE)
    if sale.stock_reduced:
        for item in sale.items.select_related('product', 'variant').order_by('product_id', 'variant_id'):
            target = item.variant or item.product
            target = type(target).objects.select_for_update().get(pk=target.pk)
            target.increase_stock(item.quantity, user=user, reason=StockMovement.Reason.DEVOLUCAO,
                                  notes=f'Estorno Venda Cancelada: #{sale.number}')
    if billing:
        billing.installments.update(status=Installment.Status.CANCELADO)
        billing.status = Billing.Status.CANCELADO
        billing.save(update_fields=['status', 'updated_at'])
    sale.status = Sale.Status.CANCELADO
    sale.stock_reduced = False
    sale.save(update_fields=['status', 'stock_reduced', 'updated_at'])
    return CancellationResult(True, 'Venda, conta a receber e cobranças canceladas. Estoque estornado quando havia baixa.')
