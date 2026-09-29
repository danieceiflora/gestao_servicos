"""Persistent checkout. Lock order: session, sale, billing, installment, charge."""
from datetime import timedelta
from decimal import Decimal
import logging
import uuid

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.tz_utils import local_today
from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.gateways.base import ChargeData, ChargeRejected
from pagamentos.models import GatewayCharge, GatewayConfig, PosChargeAttempt
from pagamentos.settlement import PAID, apply_charge_status, refresh_billing
from services.models import (
    Billing, CashMovement, CashSession, Installment, PaymentMethod, Product,
    ProductVariant, Sale, SalePayment, StockMovement,
)
from services.payment_channels import pos_methods

logger = logging.getLogger(__name__)
WAIT = PaymentMethod.PosBehavior.WAIT_GATEWAY
PENDING = Sale.Status.AGUARDANDO_PAGAMENTO


def lock_sale(sale_id):
    """Call within atomic; also serializes checkout with cash closing."""
    session_id = Sale.objects.values_list('cash_session_id', flat=True).get(pk=sale_id)
    if session_id:
        CashSession.objects.select_for_update().get(pk=session_id)
    return Sale.objects.select_for_update().get(pk=sale_id)


def resolve_payment(row, client):
    from services.views_pos import _money
    method = pos_methods().filter(pk=row.get('method_id')).first()
    if not method:
        raise ValueError('Método não disponível no PDV.')
    amount = _money(row.get('amount'))
    tendered = _money(row.get('tendered'), amount)
    if amount <= 0 or tendered < amount or (method.tipo_provedor != 'DINHEIRO' and tendered != amount):
        raise ValueError('Valor de pagamento inválido.')
    dynamic = method.tipo_provedor == 'PIX' and method.pix_type == PaymentMethod.PixType.DYNAMIC
    behavior = WAIT if dynamic else method.pos_behavior
    if behavior == WAIT:
        config = GatewayConfig.load()
        if not dynamic or not method.integra_gateway or not config.can_generate_charges or not config.pix_enabled:
            raise ValueError('PIX integrado não está disponível. Verifique o método e o gateway.')
        document = ''.join(filter(str.isdigit, (client.document or '') if client else ''))
        if len(document) not in (11, 14):
            raise ValueError('Selecione um cliente cadastrado com CPF/CNPJ para gerar o PIX.')
    return method, amount, tendered, behavior


def record_manual(inst, sale, tendered):
    method = inst.payment_method
    fee = max(inst.amount * method.tarifa_porcentagem / Decimal('100'), method.tarifa_minima) + method.tarifa_fixa
    payment = SalePayment.objects.create(
        venda=sale, installment=inst, metodo_pagamento=method, valor_bruto=inst.amount,
        valor_tarifa=fee, valor_liquido=inst.amount-fee, amount_tendered=tendered,
        change_amount=tendered-inst.amount if method.tipo_provedor == 'DINHEIRO' else Decimal('0'),
        operator=sale.user, cash_session=sale.cash_session,
        data_previsao=local_today() + timedelta(days=method.prazo_recebimento),
    )
    inst.status, inst.paid_at = Installment.Status.PAGO, timezone.now()
    inst.save(update_fields=['status', 'paid_at'])
    CashMovement.objects.create(
        session=sale.cash_session, movement_type=CashMovement.MovementType.SALE,
        amount=inst.amount, payment_method=method, sale=sale, created_by=sale.user,
        notes=f'Pagamento #{payment.pk}',
    )


def add_parts(sale, rows, start_number=1):
    for number, (method, amount, tendered, behavior) in enumerate(rows, start_number):
        inst = Installment.objects.create(
            billing=sale.billing, installment_number=number, due_date=local_today(),
            amount=amount, payment_method=method, pos_payment_behavior=behavior,
        )
        if behavior == PaymentMethod.PosBehavior.RECEIVED_NOW:
            record_manual(inst, sale, tendered)


@transaction.atomic
def start_checkout(payload, user):
    from services.views_pos import _save_cart
    try:
        key = uuid.UUID(str(payload.get('checkout_key', '')))
    except ValueError:
        raise ValueError('Identificador do recebimento inválido. Atualize a página.')
    session = CashSession.objects.select_for_update().filter(
        pk=payload.get('session_id'), operator=user, status=CashSession.Status.OPEN,
    ).first()
    if not session:
        raise ValueError('Abra um caixa antes de receber.')
    existing = Sale.objects.filter(pos_checkout_key=key).first()
    if existing:
        if existing.cash_session_id != session.pk or existing.user_id != user.pk:
            raise ValueError('Recebimento não pertence a esta sessão.')
        return existing
    if session.sales.filter(status=PENDING).exists():
        raise ValueError('Conclua o recebimento pendente antes de iniciar outra venda.')
    sale = _save_cart(payload, session, user, False)
    rows = [resolve_payment(row, sale.client) for row in payload.get('payments', [])]
    if not rows or sum((r[1] for r in rows), Decimal('0')) != sale.total_amount:
        raise ValueError('A soma das formas de pagamento deve ser igual ao total da venda.')
    sale.pos_checkout_key, sale.status = key, PENDING
    sale.save(update_fields=['pos_checkout_key', 'status', 'updated_at'])
    if Billing.objects.filter(sale=sale).exists():
        raise ValueError('Esta venda já possui faturamento. Verifique antes de receber no caixa.')
    Billing.objects.create(sale=sale, client=sale.client, total_amount=sale.total_amount)
    add_parts(sale, rows)
    refresh_billing(sale.billing)
    finish_if_ready(sale)
    return sale


def finish_if_ready(sale):
    """Caller holds the sale lock. Deferred receivables do not block checkout."""
    if sale.status != PENDING:
        return
    unpaid = sale.billing.installments.exclude(status__in=[Installment.Status.PAGO, Installment.Status.CANCELADO])
    if unpaid.exclude(pos_payment_behavior=PaymentMethod.PosBehavior.RECEIVABLE).exists():
        return
    if not sale.stock_reduced:
        for item in sale.items.order_by('product_id', 'variant_id', 'pk'):
            target = (ProductVariant.objects.select_for_update().get(pk=item.variant_id) if item.variant_id
                      else Product.objects.select_for_update().get(pk=item.product_id))
            target.reduce_stock(item.quantity, user=sale.user, reason=StockMovement.Reason.VENDA_DIRETA,
                                notes=f'Frente de Caixa — Venda #{sale.number}')
        sale.stock_reduced = True
    sale.status = Sale.Status.FINALIZADA
    sale.save(update_fields=['status', 'stock_reduced', 'updated_at'])


def _adopt_result(attempt_id, result):
    with transaction.atomic():
        initial = PosChargeAttempt.objects.select_related('installment__billing').get(pk=attempt_id)
        lock_sale(initial.installment.billing.sale_id)
        attempt = PosChargeAttempt.objects.select_for_update().get(pk=attempt_id)
        inst = attempt.installment
        if result.method != 'PIX' or result.amount != inst.amount:
            raise ValueError('A cobrança encontrada não corresponde ao pagamento. Verifique a conciliação.')
        defaults = {field: getattr(result, field) for field in (
            'amount', 'due_date', 'pix_qrcode', 'pix_copy_paste', 'pix_expiration_date',
            'invoice_url', 'invoice_number', 'net_value',
        )}
        charge, _ = GatewayCharge.objects.get_or_create(external_id=result.external_id, defaults={
            **defaults, 'installment': inst, 'payment_method': inst.payment_method,
            'config': GatewayConfig.load(), 'method': 'PIX',
        })
        if charge.installment_id != inst.pk:
            raise ValueError('Cobrança já vinculada a outro pagamento.')
        artifact_fields = ('pix_qrcode', 'pix_copy_paste', 'pix_expiration_date', 'invoice_url', 'invoice_number')
        for field in artifact_fields:
            value = getattr(result, field)
            if value:
                setattr(charge, field, value)
        charge.save(update_fields=artifact_fields)
        attempt.charge, attempt.state, attempt.message = charge, PosChargeAttempt.State.CREATED, ''
        attempt.save(update_fields=['charge', 'state', 'message'])
        apply_charge_status(charge.pk, result.status, result.net_value)
        return charge


def issue_pix(installment_id, *, reconcile=False):
    with transaction.atomic():
        initial = Installment.objects.select_related('billing').get(pk=installment_id)
        sale = lock_sale(initial.billing.sale_id)
        inst = Installment.objects.select_for_update().get(pk=installment_id)
        if sale.status != PENDING or inst.status in (Installment.Status.PAGO, Installment.Status.CANCELADO):
            return
        attempt, created = PosChargeAttempt.objects.get_or_create(installment=inst)
        if attempt.charge_id:
            charge = attempt.charge
            if not reconcile:
                return
            reference = None
        else:
            charge = None
            reference = str(attempt.reference)
            if not created and attempt.state != PosChargeAttempt.State.REJECTED:
                if not reconcile:
                    return
                create = False
            else:
                create = True
                attempt.state, attempt.started_at, attempt.message = PosChargeAttempt.State.PROCESSING, timezone.now(), ''
                attempt.save(update_fields=['state', 'started_at', 'message'])
    gateway = AsaasGateway()
    try:
        if charge:
            result = gateway.get_charge(charge.external_id)
            _adopt_result(attempt.pk, result)
            return
        if not create:
            result = gateway.find_charge_by_reference(reference)
            if result:
                _adopt_result(attempt.pk, result)
            else:
                PosChargeAttempt.objects.filter(pk=attempt.pk, charge__isnull=True).update(
                    message='Emissão ainda não localizada. Verifique novamente; não gere outro PIX.',
                )
            return
        config = GatewayConfig.load()
        if not config.can_generate_charges or not config.pix_enabled:
            raise ChargeRejected('PIX não disponível no gateway.')
        result = gateway.create_charge(ChargeData(
            customer_name=sale.client.name, customer_document=''.join(filter(str.isdigit, sale.client.document)),
            customer_email=sale.client.emails.values_list('email', flat=True).first() or '',
            description=f'Venda #{sale.number} — pagamento {inst.installment_number}',
            amount=inst.amount, due_date=inst.due_date, method='PIX', external_reference=reference,
        ), wallet_id=config.wallet_id)
        _adopt_result(attempt.pk, result)
    except Exception as exc:
        logger.exception('Falha no PIX do PDV, tentativa %s', attempt.reference)
        rejected = isinstance(exc, ChargeRejected) and not charge and create
        PosChargeAttempt.objects.filter(pk=attempt.pk, charge__isnull=True).update(
            state=PosChargeAttempt.State.REJECTED if rejected else PosChargeAttempt.State.UNKNOWN,
            message=('Emissão recusada. Verifique o cadastro e tente novamente.' if rejected else
                     'Não foi possível confirmar a emissão. Use Verificar pagamento antes de prosseguir.'),
        )
        if charge:
            raise ValueError('Não foi possível consultar o PIX agora. Tente novamente.') from exc


def ensure_pix(sale_id, *, reconcile=False):
    ids = list(Installment.objects.filter(billing__sale_id=sale_id, pos_payment_behavior=WAIT)
               .exclude(status__in=[Installment.Status.PAGO, Installment.Status.CANCELADO])
               .values_list('pk', flat=True))
    for inst_id in ids:
        issue_pix(inst_id, reconcile=reconcile)


def cancel_pending_pix(inst):
    """Called with checkout locked. A failure keeps the old installment payable."""
    attempt = PosChargeAttempt.objects.filter(installment=inst).first()
    if not attempt or attempt.state == PosChargeAttempt.State.REJECTED:
        return True
    if not attempt.charge_id:
        raise ValueError('A emissão ainda precisa ser conciliada. Use Verificar pagamento.')
    charge = attempt.charge
    if charge.status in PAID:
        apply_charge_status(charge.pk, charge.status, charge.net_value)
        return False
    if charge.status == GatewayCharge.Status.CANCELLED:
        return True
    gateway = AsaasGateway()
    result = gateway.get_charge(charge.external_id)
    if result.status in PAID:
        apply_charge_status(charge.pk, result.status, result.net_value)
        return False
    if result.status == GatewayCharge.Status.CANCELLED or gateway.cancel_charge(charge.external_id):
        apply_charge_status(charge.pk, GatewayCharge.Status.CANCELLED)
        return True
    result = gateway.get_charge(charge.external_id)
    if result.status in PAID:
        apply_charge_status(charge.pk, result.status, result.net_value)
        return False
    raise ValueError('Não foi possível confirmar o cancelamento do PIX. Verifique novamente.')


@transaction.atomic
def replace_part(sale_id, installment_id, payments):
    sale = lock_sale(sale_id)
    if sale.status != PENDING:
        raise ValueError('A venda não está aguardando pagamento.')
    inst = sale.billing.installments.select_for_update().filter(pk=installment_id).first()
    if not inst or inst.status in (Installment.Status.PAGO, Installment.Status.CANCELADO):
        raise ValueError('Somente valores ainda não recebidos podem ser substituídos.')
    rows = [resolve_payment(row, sale.client) for row in payments]
    if not rows or sum((r[1] for r in rows), Decimal('0')) != inst.amount:
        raise ValueError('A soma deve corresponder ao saldo desta parte.')
    if inst.pos_payment_behavior == WAIT and not cancel_pending_pix(inst):
        return sale  # Commit the competing payment; do not replace it.
    inst.status = Installment.Status.CANCELADO
    inst.save(update_fields=['status'])
    last = sale.billing.installments.order_by('-installment_number').first().installment_number
    add_parts(sale, rows, last + 1)
    refresh_billing(sale.billing)
    finish_if_ready(sale)
    return sale


@transaction.atomic
def cancel_checkout(sale_id):
    sale = lock_sale(sale_id)
    if sale.status != PENDING or sale.billing.get_total_paid() > 0:
        raise ValueError('Não é possível cancelar uma venda com recebimentos. Troque apenas o saldo pendente.')
    for inst in sale.billing.installments.exclude(status=Installment.Status.CANCELADO):
        if inst.pos_payment_behavior == WAIT and not cancel_pending_pix(inst):
            return sale
    sale.billing.installments.update(status=Installment.Status.CANCELADO)
    Billing.objects.filter(pk=sale.billing.pk).update(status=Billing.Status.CANCELADO)
    sale.status = Sale.Status.CANCELADO
    sale.save(update_fields=['status', 'updated_at'])
    return sale


def checkout_data(sale):
    sale.refresh_from_db()
    parts = []
    for inst in sale.billing.installments.select_related('payment_method').exclude(status=Installment.Status.CANCELADO).order_by('installment_number'):
        attempt = PosChargeAttempt.objects.select_related('charge').filter(installment=inst).first()
        charge = attempt.charge if attempt else None
        parts.append({
            'id': inst.pk, 'method': inst.payment_method.descricao, 'amount': str(inst.amount),
            'paid': inst.status == Installment.Status.PAGO, 'behavior': inst.pos_payment_behavior,
            'charge_status': charge.status if charge else '', 'message': attempt.message if attempt else '',
            'qr_code': charge.pix_qrcode if charge else '', 'copy_paste': charge.pix_copy_paste if charge else '',
            'expires_at': charge.pix_expiration_date.isoformat() if charge and charge.pix_expiration_date else None,
        })
    finalized = sale.status == Sale.Status.FINALIZADA
    return {
        'ok': True, 'sale_id': sale.pk, 'number': sale.number, 'status': sale.status,
        'finalized': finalized, 'parts': parts, 'total': str(sale.total_amount),
        'received': str(sale.billing.get_total_paid()), 'remaining': str(sale.billing.get_remaining_balance()),
        'receipt_url': reverse('pos_receipt', args=[sale.number]) if finalized else None,
    }
