"""Domínio de Expedição / Produção.

Toda mutação de ordem ou item passa por aqui. Os models não recalculam status
no `save()` de propósito: `ServiceItem.save()` faz isso e, por causa disso,
salvar um formset de 20 itens produz 20 saves da OS em cascata.

REGRAS INVIOLÁVEIS
------------------
* `update_status()` nunca chama `sync_items()`.
* `sync_items()` chama `update_status()` uma única vez, no final.
* Saves de item usam `update_fields=[...]`.
* A OP nasce já no status correto: a sincronização calcula os itens, deriva o
  status e faz um save. Sem flip de status na mesma transação, não há
  notificação duplicada.

PROPRIEDADE DOS CAMPOS DE `ProductionItem`
------------------------------------------
A sincronização manda em: `quantity`, `description`, `product`, `variant`.
A sincronização NUNCA toca: `quantity_done`, `status`, `started_at`,
`finished_at`, `finished_by`, `notes`.

Sem essa disciplina, um `update_or_create(defaults={...tudo...})` zera o
progresso do turno da oficina.
"""

import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q, Sum
from django.utils import timezone

from services.models import Product, Sale, ServiceOrderTask

from .models import (
    DeliveryMode, ProductionEvent, ProductionItem, ProductionOrder,
    ProductionSettings,
)

logger = logging.getLogger(__name__)

#: Tipos de etapa de OS que representam trabalho físico.
PRODUCTION_TASK_TYPES = (
    ServiceOrderTask.TaskType.EXECUCAO,
    ServiceOrderTask.TaskType.GARANTIA,
    ServiceOrderTask.TaskType.RETORNO,
)

#: Status de venda que nunca entram na fila: enquanto a venda é rascunho suas
#: linhas ainda são apagadas e recriadas (`views_pos._save_cart`), e o vínculo
#: por `source_key` se perderia.
BLOCKED_SALE_TRIGGERS = (Sale.Status.RASCUNHO, Sale.Status.CANCELADO)


# ---------------------------------------------------------------------------
# Elegibilidade de item
# ---------------------------------------------------------------------------

def _is_eligible_product(product, scope):
    """Produto representa trabalho físico de separação/preparo?"""
    if product is None:
        return False
    if product.type == Product.Type.SERVICO:
        return False
    if product.unit_type in (Product.UnitType.MAO_OBRA, Product.UnitType.HORA):
        return False
    if scope == ProductionSettings.ItemScope.SOMENTE_PREPARO:
        return bool(product.requires_finishing) or product.format == Product.Format.COM_COMPOSICAO
    return True


def _rows_from_sale(sale, scope):
    rows = []
    items = sale.items.select_related('product', 'variant').all()
    for item in items:
        if not _is_eligible_product(item.product, scope):
            continue
        rows.append({
            'source_key': f'sale_item:{item.pk}',
            'sale_item': item,
            'service_item': None,
            'product': item.product,
            'variant': item.variant,
            'description': _describe(item.product, item.variant),
            'quantity': Decimal(item.quantity or 0),
        })
    return rows


def _rows_from_task(task, scope):
    rows = []
    items = task.items.select_related('product').all()
    for item in items:
        if not _is_eligible_product(item.product, scope):
            continue
        rows.append({
            'source_key': f'service_item:{item.pk}',
            'sale_item': None,
            'service_item': item,
            'product': item.product,
            'variant': None,  # ServiceItem não tem variação
            'description': (item.description or '').strip() or _describe(item.product, None),
            'quantity': Decimal(item.quantity or 0),
        })
    return rows


def _describe(product, variant):
    name = product.name if product else 'Item'
    return f'{name} — {variant.name}' if variant else name


# ---------------------------------------------------------------------------
# Sincronização a partir da origem
# ---------------------------------------------------------------------------

def should_sync_sale(sale, settings=None):
    settings = settings or ProductionSettings.load()
    if not settings.enabled:
        return False
    if sale.status in BLOCKED_SALE_TRIGGERS:
        return False
    if settings.skip_sale_linked_to_order and sale.service_order_id:
        # A OP da etapa é a canônica; senão o mesmo material entra duas vezes
        # na fila e o separador separa duas vezes.
        return False
    return sale.status in (settings.sale_trigger_statuses or [])


def should_sync_task(task, settings=None):
    settings = settings or ProductionSettings.load()
    if not settings.enabled:
        return False
    if task.task_type not in PRODUCTION_TASK_TYPES:
        return False
    if settings.require_task_approval and task.requires_client_approval and not task.is_approved:
        return False
    return task.status in (settings.task_trigger_statuses or [])


def sync_from_sale(sale, *, user=None, settings=None):
    """Cria ou sincroniza a OP de uma venda. Devolve a OP, ou None."""
    settings = settings or ProductionSettings.load()
    rows = _rows_from_sale(sale, settings.item_scope)
    existing = ProductionOrder.objects.filter(sale=sale).first()
    if not rows and existing is None:
        return None
    if existing is None:
        existing = _create_order(
            sale=sale,
            source_status=sale.status,
            delivery_mode=_default_delivery_mode_for_sale(sale, settings),
            due_date=sale.delivery_date,
        )
    return _apply_rows(existing, rows, source_status=sale.status, user=user)


def sync_from_task(task, *, user=None, settings=None):
    """Cria ou sincroniza a OP de uma etapa de OS. Devolve a OP, ou None.

    A granularidade por etapa é o que dispensa a heurística de itens clonados
    do orçamento: os itens da OP são exatamente os itens desta etapa.
    """
    settings = settings or ProductionSettings.load()
    rows = _rows_from_task(task, settings.item_scope)
    existing = ProductionOrder.objects.filter(service_order_task=task).first()
    if not rows and existing is None:
        return None
    if existing is None:
        existing = _create_order(
            service_order_task=task,
            source_status=task.status,
            delivery_mode=settings.default_delivery_mode_order,
            due_date=task.scheduled_at.date() if task.scheduled_at else None,
        )
    return _apply_rows(existing, rows, source_status=task.status, user=user)


def _default_delivery_mode_for_sale(sale, settings):
    if (sale.delivery_address or '').strip():
        return DeliveryMode.ENVIO
    return settings.default_delivery_mode_sale


def _create_order(**kwargs):
    """Cria a OP tolerando corrida: o OneToOne da origem é a trava."""
    try:
        with transaction.atomic():
            return ProductionOrder.objects.create(**kwargs)
    except IntegrityError:
        lookup = {k: v for k, v in kwargs.items() if k in ('sale', 'service_order_task')}
        order = ProductionOrder.objects.filter(**lookup).first()
        if order is None:
            raise
        return order


@transaction.atomic
def _apply_rows(order, rows, *, source_status, user=None):
    """Reconcilia os itens da OP com as linhas da origem.

    `select_for_update` evita que dois saves concorrentes criem itens
    duplicados antes da UniqueConstraint pegar (o que viraria um 500 no meio
    da edição da venda).
    """
    order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
    if order.is_terminal:
        # OP entregue ou cancelada não é mais sincronizada.
        return order

    by_key = {i.source_key: i for i in order.items.all() if i.source_key}
    seen = set()

    for row in rows:
        key = row['source_key']
        seen.add(key)
        item = by_key.get(key)
        if item is None:
            ProductionItem.objects.create(
                production_order=order,
                source_key=key,
                sale_item=row['sale_item'],
                service_item=row['service_item'],
                product=row['product'],
                variant=row['variant'],
                description=row['description'],
                quantity=row['quantity'],
            )
            continue
        _update_existing_item(order, item, row, user)

    for key, item in by_key.items():
        if key in seen or item.status == ProductionItem.Status.CANCELADO:
            continue
        _handle_removed_item(order, item, user)

    order.source_status = source_status
    order.save(update_fields=['source_status', 'updated_at'])
    update_status(order, user=user)
    return order


def _update_existing_item(order, item, row, user):
    """Atualiza só os campos de que a sincronização é dona."""
    changed = []

    # Troca de produto na mesma linha é outro trabalho: cancela e recria.
    # A source_key sai do item antigo (liberando a UniqueConstraint) e vai para
    # o novo; o antigo fica como registro histórico cancelado.
    if item.product_id != getattr(row['product'], 'pk', None):
        _log(order, item, user, message=(
            f'Produto da linha mudou — item substituído ({item.description})'
        ))
        item.status = ProductionItem.Status.CANCELADO
        item.source_key = ''
        item.save(update_fields=['status', 'source_key', 'updated_at'])
        ProductionItem.objects.create(
            production_order=order,
            source_key=row['source_key'],
            sale_item=row['sale_item'],
            service_item=row['service_item'],
            product=row['product'],
            variant=row['variant'],
            description=row['description'],
            quantity=row['quantity'],
        )
        return

    new_qty = row['quantity']
    if item.quantity != new_qty:
        if new_qty < item.quantity_done:
            # Jamais truncar o que já foi produzido — sinaliza para revisão.
            item.needs_review = True
            changed.append('needs_review')
            _log(order, item, user, message=(
                f'Quantidade na origem ({new_qty}) é menor que a já produzida '
                f'({item.quantity_done}) — revisar'
            ))
        elif (new_qty > item.quantity
                and item.status == ProductionItem.Status.CONCLUIDO
                and item.quantity_done < new_qty):
            item.status = ProductionItem.Status.PENDENTE
            item.finished_at = None
            changed += ['status', 'finished_at']
            _log(order, item, user, message=(
                f'Quantidade aumentou para {new_qty} — item reaberto'
            ))
        else:
            _log(order, item, user, message=f'Quantidade ajustada para {new_qty}')
        item.quantity = new_qty
        changed.append('quantity')

    for field, value in (
        ('description', row['description']),
        ('variant', row['variant']),
        ('sale_item', row['sale_item']),
        ('service_item', row['service_item']),
    ):
        if getattr(item, field) != value:
            setattr(item, field, value)
            changed.append(field)

    if changed:
        item.save(update_fields=changed + ['updated_at'])


def _handle_removed_item(order, item, user):
    """Linha saiu da origem. Nunca apaga trabalho já feito."""
    untouched = (
        item.status == ProductionItem.Status.PENDENTE
        and item.quantity_done == 0
        and not item.started_at
    )
    if untouched:
        item.delete()
        return
    item.status = ProductionItem.Status.CANCELADO
    item.save(update_fields=['status', 'updated_at'])
    _log(order, item, user, message=(
        f'Item removido do pedido depois de iniciado: {item.description}'
    ))


def cancel_order(order, *, user=None, reason=''):
    """Cancela a OP e os itens que ainda não foram concluídos."""
    with transaction.atomic():
        order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == ProductionOrder.Status.CANCELADO:
            return order
        order.items.exclude(
            status__in=[ProductionItem.Status.CONCLUIDO, ProductionItem.Status.CANCELADO]
        ).update(status=ProductionItem.Status.CANCELADO, updated_at=timezone.now())
        _apply_status(order, ProductionOrder.Status.CANCELADO, user=user,
                      message=reason or 'Origem cancelada')
    return order


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def derive_status(order):
    """Status da OP a partir dos seus itens. Não persiste nada."""
    S = ProductionOrder.Status
    if order.is_terminal:
        return order.status
    if order.waiting_material:
        return S.AGUARDANDO_MATERIAL

    items = order.active_items
    if not items:
        return S.AGUARDANDO
    if all(i.status == ProductionItem.Status.CONCLUIDO for i in items):
        return S.PRONTO

    in_progress = [i for i in items if i.status == ProductionItem.Status.EM_ANDAMENTO]
    if in_progress:
        if any(i.kind != ProductionItem.Kind.SEPARACAO for i in in_progress):
            return S.EM_PRODUCAO
        return S.EM_SEPARACAO
    if any(i.status == ProductionItem.Status.CONCLUIDO for i in items):
        return S.EM_SEPARACAO
    return S.AGUARDANDO


def update_status(order, *, user=None):
    """Recalcula e persiste o status da OP. NUNCA chama a sincronização."""
    new_status = derive_status(order)
    if new_status == order.status:
        return order
    _apply_status(order, new_status, user=user)
    return order


def _apply_status(order, new_status, *, user=None, message=''):
    previous = order.status
    order.status = new_status
    order.save(update_fields=['status', 'updated_at'])
    _log(order, None, user, from_status=previous, to_status=new_status, message=message)
    _dispatch_status_notification(order, previous, new_status)


def _dispatch_status_notification(order, from_status, to_status):
    """Agenda a notificação configurada para depois do commit.

    O disparo é explícito, não via `post_save`: o receiver genérico de
    `integracoes` despacha dentro da transação (chamada HTTP ao Chatwoot e
    geração de PDF antes do commit), o que num tablet de oficina seria um
    request lento a cada clique — e um rollback posterior deixaria a mensagem
    já enviada. `ProductionOrder` também não entra em
    `DYNAMIC_NOTIFICATION_MODELS`, para não dobrar o envio.

    Sem nenhuma `NotificationConfig` cadastrada, nada é enviado.
    """
    pk, old = order.pk, from_status

    def _send():
        try:
            from integracoes.utils import dispatch_dynamic_notification
            fresh = ProductionOrder.objects.filter(pk=pk).first()
            if fresh:
                dispatch_dynamic_notification(fresh, 'MUDANCA_STATUS', old_status=old)
        except Exception:
            logger.exception('Falha ao notificar mudança de status da OP %s', pk)

    transaction.on_commit(_send)


def _log(order, item=None, user=None, *, from_status='', to_status='', message=''):
    ProductionEvent.objects.create(
        production_order=order, production_item=item, user=user,
        from_status=from_status or '', to_status=to_status or '',
        message=message[:255],
    )


# ---------------------------------------------------------------------------
# Ações do operador
# ---------------------------------------------------------------------------

def start_item(item, *, user=None):
    with transaction.atomic():
        item = ProductionItem.objects.select_related('production_order').select_for_update().get(pk=item.pk)
        if item.status != ProductionItem.Status.PENDENTE:
            return item
        item.status = ProductionItem.Status.EM_ANDAMENTO
        item.started_at = item.started_at or timezone.now()
        item.save(update_fields=['status', 'started_at', 'updated_at'])
        _log(item.production_order, item, user, message=f'Iniciado: {item.description}')
        update_status(item.production_order, user=user)
    return item


def finish_item(item, *, user=None, quantity_done=None):
    with transaction.atomic():
        item = ProductionItem.objects.select_related('production_order').select_for_update().get(pk=item.pk)
        item.quantity_done = Decimal(quantity_done) if quantity_done is not None else item.quantity
        item.status = ProductionItem.Status.CONCLUIDO
        item.finished_at = timezone.now()
        item.finished_by = user
        item.started_at = item.started_at or item.finished_at
        item.save(update_fields=[
            'quantity_done', 'status', 'finished_at', 'finished_by', 'started_at', 'updated_at',
        ])
        _log(item.production_order, item, user, message=f'Concluído: {item.description}')
        update_status(item.production_order, user=user)
    return item


def reopen_item(item, *, user=None):
    with transaction.atomic():
        item = ProductionItem.objects.select_related('production_order').select_for_update().get(pk=item.pk)
        item.status = ProductionItem.Status.PENDENTE
        item.finished_at = None
        item.finished_by = None
        item.needs_review = False
        item.save(update_fields=['status', 'finished_at', 'finished_by', 'needs_review', 'updated_at'])
        _log(item.production_order, item, user, message=f'Reaberto: {item.description}')
        update_status(item.production_order, user=user)
    return item


def set_waiting_material(order, *, user=None, waiting=True, note=''):
    """Flag manual do operador — o módulo não detecta falta de saldo sozinho."""
    with transaction.atomic():
        order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
        if order.is_terminal:
            return order
        order.waiting_material = waiting
        order.waiting_material_note = (note or '')[:255] if waiting else ''
        order.save(update_fields=['waiting_material', 'waiting_material_note', 'updated_at'])
        _log(order, None, user, message=(
            f'Aguardando material: {note}' if waiting else 'Material resolvido'
        ))
        # `derive_status` dá prioridade ao flag, então isto já reflete a mudança.
        update_status(order, user=user)
    return order


def deliver(order, *, user=None, delivered_to='', received_by_user=None,
            carrier='', tracking_code='', delivery_notes=''):
    """Fecha a OP. Só a partir de PRONTO, e sem mexer em estoque."""
    with transaction.atomic():
        order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != ProductionOrder.Status.PRONTO:
            return order, 'A ordem precisa estar Pronta para registrar a saída.'
        order.delivered_at = timezone.now()
        order.delivered_to = (delivered_to or '')[:255]
        order.received_by_user = received_by_user
        order.carrier = (carrier or '')[:120]
        order.tracking_code = (tracking_code or '')[:120]
        order.delivery_notes = delivery_notes or ''
        order.save(update_fields=[
            'delivered_at', 'delivered_to', 'received_by_user', 'carrier',
            'tracking_code', 'delivery_notes', 'updated_at',
        ])
        _apply_status(order, ProductionOrder.Status.ENTREGUE, user=user,
                      message=f'Saída registrada ({order.get_delivery_mode_display()})')
    return order, None


def set_priority(order, priority, *, user=None):
    with transaction.atomic():
        order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
        order.priority = priority
        order.save(update_fields=['priority', 'updated_at'])
        _log(order, None, user, message=f'Prioridade: {order.get_priority_display()}')
    return order


# ---------------------------------------------------------------------------
# Leitura para o painel
# ---------------------------------------------------------------------------

def board_version(filters_key=''):
    """Assinatura curta do estado do painel.

    O polling manda a versão que já tem; se nada mudou, a view responde 204 e
    o HTMX não troca nada — scroll, foco e ícones ficam intactos.
    """
    agg = ProductionOrder.objects.filter(status__in=ProductionOrder.ACTIVE_STATUSES).aggregate(
        n=Count('id'), m=Max('updated_at'), im=Max('items__updated_at'),
    )
    def stamp(value):
        return value.strftime('%Y%m%d%H%M%S%f') if value else '0'
    return f"{filters_key}:{agg['n']}:{stamp(agg['m'])}:{stamp(agg['im'])}"


def outstanding_demand(product_ids):
    """Quantidade ainda não produzida, por produto, nas OPs abertas.

    Alimenta o indicador honesto de disponibilidade: o saldo do produto já
    reflete a baixa do pedido, então mostrar só `current_stock` prometeria
    material que outra ordem da fila já vai consumir.
    """
    if not product_ids:
        return {}
    rows = (
        ProductionItem.objects
        .filter(
            product_id__in=product_ids,
            production_order__status__in=ProductionOrder.ACTIVE_STATUSES,
        )
        .exclude(status__in=[ProductionItem.Status.CONCLUIDO, ProductionItem.Status.CANCELADO])
        .values('product_id')
        .annotate(pending=Sum(F('quantity') - F('quantity_done')))
    )
    return {r['product_id']: (r['pending'] or Decimal('0')) for r in rows}


def board_queryset(*, status=None, origin=None, delivery_mode=None,
                   priority=None, search='', waiting_material=None):
    qs = (
        ProductionOrder.objects
        .select_related(
            'sale', 'sale__client', 'service_order', 'service_order_task',
            'service_order__client_property', 'service_order__client_property__client',
        )
        .prefetch_related('items', 'items__product')
    )
    if status:
        qs = qs.filter(status__in=status if isinstance(status, (list, tuple)) else [status])
    else:
        qs = qs.filter(status__in=ProductionOrder.ACTIVE_STATUSES)
    if origin == 'VENDA':
        qs = qs.filter(sale__isnull=False)
    elif origin == 'OS':
        qs = qs.filter(service_order_task__isnull=False)
    if delivery_mode:
        qs = qs.filter(delivery_mode=delivery_mode)
    if priority:
        qs = qs.filter(priority=priority)
    if waiting_material is not None:
        qs = qs.filter(waiting_material=waiting_material)
    if search:
        search = search.strip()
        filters = (
            Q(items__description__icontains=search)
            | Q(sale__client__name__icontains=search)
            | Q(service_order__client_property__client__name__icontains=search)
            | Q(delivered_to__icontains=search)
        )
        if search.isdigit():
            n = int(search)
            filters |= Q(number=n) | Q(sale__number=n) | Q(service_order__number=n)
        qs = qs.filter(filters).distinct()
    return qs
