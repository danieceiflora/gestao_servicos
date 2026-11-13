"""Views de Expedição / Produção.

Function-based, como o resto do projeto. As views de mutação seguem o padrão da
casa (`services/views_finance.py`): `@require_POST`, e com `HX-Request`
devolvem o próprio fragmento re-renderizado, com fallback `redirect`.
"""

import hashlib
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from services.models import Product
from services.utils.bom import explode_bom

from . import services as prod
from .forms import DeliverForm, ProductionSettingsForm
from .models import (
    DeliveryMode, ProductionItem, ProductionOrder, ProductionSettings,
)
from .permissions import can_manage, can_operate, can_view

#: Colunas do painel. "Aguardando material" não é coluna: as ordens travadas
#: aparecem numa faixa destacada no topo, onde não precisam ser procuradas.
#:
#: As classes vêm inteiras daqui, não montadas no template: o Tailwind varre os
#: arquivos em busca de nomes literais e `bg-{{ tone }}-100` não seria gerado.
BOARD_COLUMNS = [
    (ProductionOrder.Status.AGUARDANDO, 'Aguardando',
     'bg-slate-100 text-slate-700', 'bg-slate-400'),
    (ProductionOrder.Status.EM_SEPARACAO, 'Em separação',
     'bg-amber-100 text-amber-800', 'bg-amber-400'),
    (ProductionOrder.Status.EM_PRODUCAO, 'Em produção',
     'bg-blue-100 text-blue-800', 'bg-blue-500'),
    (ProductionOrder.Status.PRONTO, 'Pronto',
     'bg-emerald-100 text-emerald-800', 'bg-emerald-500'),
]

ORIGIN_CHOICES = [('VENDA', 'Vendas'), ('OS', 'Ordens de serviço')]


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

def _read_filters(request):
    """Filtros do painel.

    Num POST de botão do painel os filtros chegam pelo corpo (`hx-include`
    manda o form de filtros junto), então a leitura precisa cobrir os dois.
    """
    src = request.POST if request.method == 'POST' else request.GET
    return {
        'origin': src.get('origin', '') or '',
        'delivery_mode': src.get('delivery_mode', '') or '',
        'priority': src.get('priority', '') or '',
        'search': (src.get('q', '') or '').strip(),
        'status': src.get('status', '') or '',
    }


def _filters_key(filters):
    raw = '|'.join(f'{k}={filters[k]}' for k in sorted(filters))
    return hashlib.md5(raw.encode('utf-8')).hexdigest()[:10]


def _board_context(request):
    filters = _read_filters(request)
    status = [filters['status']] if filters['status'] else None
    qs = prod.board_queryset(
        status=status,
        origin=filters['origin'],
        delivery_mode=filters['delivery_mode'],
        priority=filters['priority'],
        search=filters['search'],
    )
    orders = list(qs)

    blocked = [o for o in orders if o.status == ProductionOrder.Status.AGUARDANDO_MATERIAL]
    columns = []
    for value, label, badge_class, dot_class in BOARD_COLUMNS:
        column_orders = [o for o in orders if o.status == value]
        columns.append({
            'value': value, 'label': label,
            'badge_class': badge_class, 'dot_class': dot_class,
            'orders': column_orders, 'count': len(column_orders),
        })

    return {
        'filters': filters,
        'columns': columns,
        'blocked_orders': blocked,
        'total': len(orders),
        'board_version': prod.board_version(_filters_key(filters)),
        'origin_choices': ORIGIN_CHOICES,
        'delivery_choices': DeliveryMode.choices,
        'priority_choices': ProductionOrder.Priority.choices,
        'status_choices': ProductionOrder.Status.choices,
        'can_operate': can_operate(request.user),
        'can_manage': can_manage(request.user),
    }


@login_required
@user_passes_test(can_view)
def board(request):
    return render(request, 'producao/board.html', _board_context(request))


@login_required
@user_passes_test(can_view)
def board_partial(request):
    """Alvo do polling.

    Quando a versão recebida bate com a atual, responde 204 — o HTMX trata 204
    como "não trocar nada", então scroll, foco e ícones ficam intactos e a
    resposta é vazia.
    """
    filters = _read_filters(request)
    version = prod.board_version(_filters_key(filters))
    if request.GET.get('v') == version:
        return HttpResponse(status=204)
    return render(request, 'producao/partials/board_inner.html', _board_context(request))


# ---------------------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------------------

def _detail_context(request, order):
    items = list(
        order.items.select_related('product', 'variant', 'finished_by')
        .order_by('status', 'id')
    )
    composed_ids = [i.product_id for i in items if i.product_id]
    demand = prod.outstanding_demand(composed_ids)

    rows = []
    for item in items:
        components = []
        if item.product and item.product.format == Product.Format.COM_COMPOSICAO:
            for component, required in explode_bom(item.product, item.quantity_pending or item.quantity):
                components.append({
                    'product': component,
                    'required': required,
                    'stock': component.current_stock,
                    'reserved': demand.get(component.pk, 0),
                })
        rows.append({'item': item, 'components': components})

    return {
        'order': order,
        'rows': rows,
        'events': order.events.select_related('user', 'production_item')[:50],
        'deliver_form': DeliverForm(),
        'technician_users': order.technician_users,
        'can_operate': can_operate(request.user),
        'can_manage': can_manage(request.user),
        'priority_choices': ProductionOrder.Priority.choices,
    }


@login_required
@user_passes_test(can_view)
def order_detail(request, number):
    order = get_object_or_404(
        ProductionOrder.objects.select_related(
            'sale', 'sale__client', 'service_order', 'service_order_task',
            'service_order__client_property__client',
        ),
        number=number,
    )
    return render(request, 'producao/order_detail.html', _detail_context(request, order))


# ---------------------------------------------------------------------------
# Mutações
# ---------------------------------------------------------------------------

def _respond(request, order):
    """Devolve o fragmento que o cliente pediu, ou redireciona.

    As mutações alvejam a mesma região que o polling troca, então não existe
    corrida entre clique e atualização automática — por construção.
    """
    if request.headers.get('HX-Request'):
        if request.POST.get('scope') == 'board':
            return render(request, 'producao/partials/board_inner.html', _board_context(request))
        order.refresh_from_db()
        return render(request, 'producao/partials/order_body.html', _detail_context(request, order))
    return redirect('producao:order_detail', number=order.number)


def _get_item(pk):
    return get_object_or_404(
        ProductionItem.objects.select_related('production_order'), pk=pk,
    )


@login_required
@user_passes_test(can_operate)
@require_POST
def item_start(request, pk):
    item = _get_item(pk)
    prod.start_item(item, user=request.user)
    return _respond(request, item.production_order)


@login_required
@user_passes_test(can_operate)
@require_POST
def item_finish(request, pk):
    item = _get_item(pk)
    raw = (request.POST.get('quantity_done') or '').replace(',', '.').strip()
    quantity_done = None
    if raw:
        try:
            quantity_done = Decimal(raw)
        except (InvalidOperation, ValueError):
            quantity_done = None
    prod.finish_item(item, user=request.user, quantity_done=quantity_done)
    return _respond(request, item.production_order)


@login_required
@user_passes_test(can_operate)
@require_POST
def item_reopen(request, pk):
    item = _get_item(pk)
    prod.reopen_item(item, user=request.user)
    return _respond(request, item.production_order)


@login_required
@user_passes_test(can_operate)
@require_POST
def order_waiting_material(request, number):
    order = get_object_or_404(ProductionOrder, number=number)
    waiting = request.POST.get('waiting') == '1'
    prod.set_waiting_material(
        order, user=request.user, waiting=waiting,
        note=request.POST.get('note', ''),
    )
    return _respond(request, order)


@login_required
@user_passes_test(can_operate)
@require_POST
def order_priority(request, number):
    order = get_object_or_404(ProductionOrder, number=number)
    priority = request.POST.get('priority')
    if priority in dict(ProductionOrder.Priority.choices):
        prod.set_priority(order, priority, user=request.user)
    return _respond(request, order)


@login_required
@user_passes_test(can_operate)
@require_POST
def order_deliver(request, number):
    order = get_object_or_404(ProductionOrder, number=number)
    form = DeliverForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Verifique os dados da saída.')
        return _respond(request, order)

    received_by_user = None
    if order.delivery_mode == DeliveryMode.TECNICO:
        user_id = request.POST.get('received_by_user')
        if user_id:
            from services.models import User
            received_by_user = User.objects.filter(pk=user_id).first()

    order, error = prod.deliver(
        order, user=request.user,
        received_by_user=received_by_user,
        **form.cleaned_data,
    )
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Saída da OP #{order.number} registrada.')
    return _respond(request, order)


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(can_manage)
def settings_view(request):
    config = ProductionSettings.load()
    if request.method == 'POST':
        form = ProductionSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configurações de expedição salvas.')
            return redirect('producao:settings')
    else:
        form = ProductionSettingsForm(instance=config)
    return render(request, 'producao/settings.html', {'form': form, 'config': config})
