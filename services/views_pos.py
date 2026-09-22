import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import (
    CashClosingCount, CashMovement, CashRegister, CashSession, Client,
    Installment, PaymentMethod, Product, ProductVariant, Sale, SaleItem,
    SalePayment, SaleSettings, StockMovement,
)


def _can_operate(user):
    return user.is_manager or user.has_perm('services.operate_pos')


def _can_manage(user):
    return user.is_manager or user.has_perm('services.manage_pos_registers')


def _money(value, default='0'):
    try:
        return Decimal(str(value if value not in (None, '') else default).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ValueError('Valor monetário inválido.')


def _open_session(user):
    return CashSession.objects.select_related('register', 'operator').filter(operator=user, status=CashSession.Status.OPEN).first()


def _cash_method():
    return PaymentMethod.objects.filter(ativo=True, tipo_provedor='DINHEIRO').first()


@login_required
def pos_home(request):
    if not _can_operate(request.user):
        return HttpResponseForbidden('Você não tem permissão para acessar o Frente de Caixa.')
    session = _open_session(request.user)
    drafts = Sale.objects.filter(origin=Sale.Origin.POS, status=Sale.Status.RASCUNHO, cash_session=session).prefetch_related('items__product', 'items__variant') if session else []
    draft_payloads = [{
        'id': sale.pk, 'number': sale.number, 'client_id': str(sale.client_id or ''),
        'client_name': sale.client.display_name if sale.client else '',
        'discount': str(sale.discount), 'surcharge': str(sale.surcharge),
        'items': [{'product_id': i.product_id, 'variant_id': i.variant_id, 'name': str(i.variant or i.product),
                   'quantity': str(i.quantity), 'price': str(i.unit_price), 'discount': str(i.discount)} for i in sale.items.all()],
    } for sale in drafts]
    sale_settings = SaleSettings.get()
    return render(request, 'services/pos/index.html', {
        'session': session,
        'registers': CashRegister.objects.filter(is_active=True),
        'payment_methods': PaymentMethod.objects.filter(ativo=True).exclude(pos_behavior=PaymentMethod.PosBehavior.DISABLED),
        'clients': Client.objects.order_by('name'),
        'drafts': drafts, 'draft_payloads': draft_payloads,
        'repeated_item_behavior': sale_settings.repeated_item_behavior,
        'closing_expected': _expected_by_method(session) if session and session.register.closing_mode == CashRegister.ClosingMode.ASSISTED else [],
    })


@login_required
@require_POST
def pos_open(request):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    if _open_session(request.user):
        messages.warning(request, 'Você já possui um caixa aberto.')
        return redirect('pos_home')
    register = get_object_or_404(CashRegister, pk=request.POST.get('register'), is_active=True)
    amount = _money(request.POST.get('opening_amount'))
    with transaction.atomic():
        session = CashSession.objects.create(register=register, operator=request.user, opening_amount=amount)
        CashMovement.objects.create(session=session, movement_type=CashMovement.MovementType.OPENING,
                                    amount=amount, payment_method=_cash_method(), created_by=request.user,
                                    notes='Fundo de abertura')
    messages.success(request, f'{register.name} aberto com sucesso.')
    return redirect('pos_home')


@login_required
def pos_product_search(request):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    q = request.GET.get('q', '').strip()
    products = Product.objects.filter(is_active=True)
    if q:
        from django.db.models import Q
        products = products.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(barcode__icontains=q) |
                                   Q(variants__code__icontains=q) | Q(variants__barcode__icontains=q)).distinct()
    data = []
    for product in products.order_by('name')[:30]:
        variants = [{'id': v.pk, 'name': v.name, 'price': str(product.default_unit_price + v.additional_price), 'stock': str(v.current_stock), 'barcode': v.barcode or v.code or ''}
                    for v in product.variants.filter(is_active=True)]
        data.append({'id': product.pk, 'name': product.name, 'code': product.barcode or product.code or '',
                     'price': str(product.default_unit_price), 'stock': str(product.current_stock), 'variants': variants})
    return JsonResponse({'products': data})


def _save_cart(payload, session, user, finalize):
    items_data = payload.get('items') or []
    if not items_data:
        raise ValueError('Adicione ao menos um produto.')
    sale_id = payload.get('sale_id')
    sale = None
    if sale_id:
        sale = Sale.objects.select_for_update().filter(pk=sale_id, cash_session=session, status=Sale.Status.RASCUNHO).first()
        if not sale:
            raise ValueError('Comanda não encontrada ou não pode mais ser alterada.')
        sale.items.all().delete()
    client_id = payload.get('client_id') or None
    client = Client.objects.filter(pk=client_id).first() if client_id else None
    discount = _money(payload.get('discount'))
    surcharge = _money(payload.get('surcharge'))
    if not sale:
        sale = Sale.objects.create(user=user, client=client, status=Sale.Status.RASCUNHO,
                                   sale_type=Sale.SaleType.PRESENCIAL, origin=Sale.Origin.POS,
                                   cash_session=session, stock_reduced=False)
    else:
        sale.client = client
    subtotal = Decimal('0')
    saved_items = []
    for row in items_data:
        product = Product.objects.select_for_update().get(pk=row['product_id'], is_active=True)
        variant = None
        if row.get('variant_id'):
            variant = ProductVariant.objects.select_for_update().get(pk=row['variant_id'], product=product, is_active=True)
        quantity = _money(row.get('quantity'))
        if quantity <= 0:
            raise ValueError('A quantidade dos produtos deve ser positiva.')
        unit_price = product.default_unit_price + (variant.additional_price if variant else Decimal('0'))
        item_discount = _money(row.get('discount'))
        if item_discount < 0 or item_discount > quantity * unit_price:
            raise ValueError(f'Desconto inválido para {product.name}.')
        item = SaleItem.objects.create(sale=sale, product=product, variant=variant, quantity=quantity,
                                       unit_price=unit_price, discount=item_discount)
        subtotal += item.subtotal
        saved_items.append(item)
    total = (subtotal - discount + surcharge).quantize(Decimal('0.01'))
    if total < 0:
        raise ValueError('O total da venda não pode ser negativo.')
    sale.discount, sale.surcharge, sale.total_amount = discount, surcharge, total
    if not finalize:
        sale.save()
        return sale

    payments = payload.get('payments') or []
    applied_total = sum((_money(p.get('amount')) for p in payments), Decimal('0'))
    if applied_total != total:
        raise ValueError('A soma das formas de pagamento deve ser igual ao total da venda.')
    installments = []
    resolved = []
    for row in payments:
        method = PaymentMethod.objects.get(pk=row['method_id'], ativo=True)
        if method.pos_behavior == PaymentMethod.PosBehavior.DISABLED:
            raise ValueError(f'{method.descricao} não está disponível no PDV.')
        amount = _money(row.get('amount'))
        tendered = _money(row.get('tendered'), amount)
        change = tendered - amount if method.tipo_provedor == 'DINHEIRO' else Decimal('0')
        if tendered < amount or (method.tipo_provedor != 'DINHEIRO' and tendered != amount):
            raise ValueError(f'Valor recebido inválido para {method.descricao}.')
        installments.append({'amount': amount, 'due_date': timezone.localdate(), 'payment_method_id': method.pk})
        resolved.append((method, amount, tendered, change))
    sale._pending_installments_data = installments
    sale.status = Sale.Status.FINALIZADA
    sale.stock_reduced = True
    sale.save()
    billing = sale.billing
    installments_by_method = {}
    for inst in billing.installments.all():
        installments_by_method.setdefault(inst.payment_method_id, []).append(inst)
    for item in saved_items:
        target = item.variant if item.variant else item.product
        target.reduce_stock(item.quantity, user=user, reason=StockMovement.Reason.VENDA_DIRETA,
                            notes=f'Frente de Caixa — Venda #{sale.number}')
    for method, amount, tendered, change in resolved:
        inst = installments_by_method[method.pk].pop(0)
        if method.pos_behavior == PaymentMethod.PosBehavior.RECEIVED_NOW:
            fee = max(amount * method.tarifa_porcentagem / Decimal('100'), method.tarifa_minima) + method.tarifa_fixa
            payment = SalePayment.objects.create(
                venda=sale, installment=inst, metodo_pagamento=method, valor_bruto=amount,
                valor_tarifa=fee, valor_liquido=amount-fee, amount_tendered=tendered,
                change_amount=change, operator=user, cash_session=session,
                data_previsao=timezone.localdate() + timedelta(days=method.prazo_recebimento),
            )
            inst.status, inst.paid_at = Installment.Status.PAGO, timezone.now()
            inst.save(update_fields=['status', 'paid_at'])
            CashMovement.objects.create(session=session, movement_type=CashMovement.MovementType.SALE,
                                        amount=amount, payment_method=method, sale=sale, created_by=user,
                                        notes=f'Pagamento #{payment.pk}')
    if billing.get_remaining_balance() <= 0:
        billing.status = billing.Status.PAGO
        billing.save(update_fields=['status', 'updated_at'])
    return sale


@login_required
@require_POST
def pos_save_sale(request):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    try:
        payload = json.loads(request.body)
        with transaction.atomic():
            session = CashSession.objects.select_for_update().filter(pk=payload.get('session_id'), operator=request.user, status=CashSession.Status.OPEN).first()
            if not session:
                raise ValueError('Abra um caixa antes de realizar a venda.')
            sale = _save_cart(payload, session, request.user, payload.get('action') == 'finalize')
        return JsonResponse({'ok': True, 'number': sale.number, 'sale_id': sale.pk,
                             'finalized': sale.status == Sale.Status.FINALIZADA,
                             'receipt_url': f'/pdv/vendas/{sale.number}/comprovante/'})
    except (ValueError, KeyError, Product.DoesNotExist, ProductVariant.DoesNotExist, PaymentMethod.DoesNotExist) as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
@require_POST
def pos_cancel_sale(request, pk):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    with transaction.atomic():
        sale = Sale.objects.select_for_update().filter(
            pk=pk,
            origin=Sale.Origin.POS,
            user=request.user,
            cash_session__operator=request.user,
            cash_session__status=CashSession.Status.OPEN,
        ).first()
        if not sale:
            return JsonResponse({'error': 'Comanda não encontrada nesta sessão de caixa.'}, status=404)
        if sale.status != Sale.Status.RASCUNHO:
            return JsonResponse({'error': 'Apenas comandas pendentes podem ser canceladas.'}, status=400)
        sale.status = Sale.Status.CANCELADO
        sale.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'ok': True, 'number': sale.number})


@login_required
@require_POST
def pos_movement(request):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    session = _open_session(request.user)
    if not session:
        messages.error(request, 'Nenhum caixa aberto.')
        return redirect('pos_home')
    kind = request.POST.get('type')
    allowed = {'SUPPLY': CashMovement.MovementType.SUPPLY, 'WITHDRAWAL': CashMovement.MovementType.WITHDRAWAL}
    if kind not in allowed:
        messages.error(request, 'Movimento inválido.')
        return redirect('pos_home')
    amount = _money(request.POST.get('amount'))
    if amount <= 0:
        messages.error(request, 'Informe um valor positivo.')
        return redirect('pos_home')
    CashMovement.objects.create(session=session, movement_type=allowed[kind],
                                amount=amount if kind == 'SUPPLY' else -amount,
                                payment_method=_cash_method(), created_by=request.user,
                                notes=request.POST.get('notes', '')[:255])
    messages.success(request, 'Movimentação registrada.')
    return redirect('pos_home')


def _expected_by_method(session):
    rows = session.movements.values('payment_method_id', 'payment_method__descricao').annotate(total=Sum('amount')).order_by('payment_method__descricao')
    return list(rows)


@login_required
@require_POST
def pos_close(request):
    if not _can_operate(request.user):
        return JsonResponse({'error': 'Sem permissão.'}, status=403)
    with transaction.atomic():
        session = CashSession.objects.select_for_update().filter(pk=request.POST.get('session_id'), operator=request.user, status=CashSession.Status.OPEN).first()
        if not session:
            messages.error(request, 'Sessão não encontrada.')
            return redirect('pos_home')
        if session.sales.filter(status=Sale.Status.RASCUNHO).exists():
            messages.error(request, 'Finalize ou cancele as comandas pendentes antes de fechar.')
            return redirect('pos_home')
        for row in _expected_by_method(session):
            declared = _money(request.POST.get(f"declared_{row['payment_method_id'] or 'cash'}"))
            CashClosingCount.objects.update_or_create(session=session, payment_method_id=row['payment_method_id'], defaults={
                'expected_amount': row['total'], 'declared_amount': declared, 'difference': declared-row['total']})
        session.status = CashSession.Status.PENDING_APPROVAL
        session.closed_at = timezone.now()
        session.closing_notes = request.POST.get('notes', '')
        session.save(update_fields=['status', 'closed_at', 'closing_notes'])
    messages.success(request, 'Caixa enviado para conferência.')
    return redirect('pos_home')


@login_required
def pos_receipt(request, number):
    sale = get_object_or_404(Sale.objects.prefetch_related('items__product', 'payments__metodo_pagamento'), number=number, origin=Sale.Origin.POS)
    if sale.user_id != request.user.id and not _can_manage(request.user):
        return HttpResponseForbidden('Você não tem permissão para acessar este comprovante.')
    from fiscal.models import NFeConfig
    return render(request, 'services/pos/receipt.html', {'sale': sale, 'nfe_config': NFeConfig.load()})


@login_required
@never_cache
def pos_sessions(request):
    if not _can_manage(request.user) and not request.user.has_perm('services.view_pos_reports'):
        return HttpResponseForbidden('Você não tem permissão para visualizar o controle de caixa.')
    base_sessions = CashSession.objects.all()
    totals = base_sessions.aggregate(
        open=Count('pk', filter=Q(status=CashSession.Status.OPEN)),
        pending=Count('pk', filter=Q(status=CashSession.Status.PENDING_APPROVAL)),
        closed=Count('pk', filter=Q(status=CashSession.Status.CLOSED)),
    )
    totals['divergent'] = base_sessions.annotate(
        divergence_count=Count('closing_counts', filter=~Q(closing_counts__difference=0)),
    ).filter(divergence_count__gt=0).count()
    sessions = list(base_sessions.select_related('register', 'operator', 'approved_by').prefetch_related(
        'closing_counts__payment_method',
    )[:100])
    for session in sessions:
        counts = list(session.closing_counts.all())
        session.expected_total = sum((row.expected_amount for row in counts), Decimal('0'))
        session.declared_total = sum((row.declared_amount for row in counts), Decimal('0'))
        session.total_difference = sum((row.difference for row in counts), Decimal('0'))
    return render(request, 'services/pos/sessions.html', {'sessions': sessions, 'stats': totals})


@login_required
@require_POST
def pos_session_action(request, pk):
    if not (request.user.is_manager or request.user.has_perm('services.approve_pos_closing')):
        return HttpResponseForbidden('Você não tem permissão para aprovar ou reabrir caixas.')
    action = request.POST.get('action')
    with transaction.atomic():
        session = get_object_or_404(CashSession.objects.select_for_update(), pk=pk)
        if action == 'approve':
            if session.status != CashSession.Status.PENDING_APPROVAL:
                messages.warning(request, 'Esta sessão não está aguardando aprovação.')
            else:
                session.status = CashSession.Status.CLOSED
                session.approved_by = request.user
                session.approved_at = timezone.now()
                session.save(update_fields=['status', 'approved_by', 'approved_at'])
                messages.success(request, f'Fechamento do caixa {session.register.name} aprovado.')
        elif action == 'reopen':
            if session.status not in [CashSession.Status.PENDING_APPROVAL, CashSession.Status.CLOSED]:
                messages.warning(request, 'Esta sessão já está aberta e não precisa ser reaberta.')
            elif CashSession.objects.filter(
                register=session.register,
                operator=session.operator,
                status=CashSession.Status.OPEN,
            ).exclude(pk=session.pk).exists():
                messages.error(
                    request,
                    f'{session.operator.get_full_name() or session.operator.username} já possui outra sessão aberta neste caixa.',
                )
            else:
                session.closing_counts.all().delete()
                session.status = CashSession.Status.OPEN
                session.closed_at = None
                session.approved_by = None
                session.approved_at = None
                session.save(update_fields=['status', 'closed_at', 'approved_by', 'approved_at'])
                messages.success(request, f'Caixa {session.register.name} reaberto com sucesso.')
        else:
            messages.error(request, 'Ação de caixa inválida.')
    return redirect('pos_sessions')
