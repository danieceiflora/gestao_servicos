"""Entrada automática na fila de Expedição / Produção.

SEM `pre_save`. A detecção de transição não usa `_old_status` em memória: a OP
guarda `source_status`, e o handler é idempotente — "o status atual está na
lista configurada? já existe OP? então cria ou sincroniza". Isso também o torna
imune ao duplo save de `sale_create`, que grava a venda como RASCUNHO e depois
com o status final na mesma transação.

DEBOUNCE POR TRANSAÇÃO. `ServiceItem.save()` chama
`service_order.update_status()`, que termina em `self.save()` — salvar um
formset de 20 itens produz 20 saves da OS. O bucket thread-local colapsa isso
em uma sincronização por commit.

`transaction.on_commit` é obrigatório por dois motivos: o primeiro save de
`sale_create` é `created=True` com zero itens, e `views_pos._save_cart` apaga e
recria todos os `SaleItem` no meio da transação.
"""

import logging
import threading

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.models import Sale, ServiceOrder, ServiceOrderTask

from . import services as prod
from .models import ProductionOrder, ProductionSettings

logger = logging.getLogger(__name__)

SALE = 'sale'
TASK = 'task'
ORDER = 'order'

_pending = threading.local()


def _schedule(kind, pk):
    """Enfileira para drenar no commit.

    `on_commit` é registrado em cada save; só a primeira drenagem faz
    trabalho, as seguintes encontram o bucket vazio. Registrar sempre (em vez
    de só na primeira vez) é o que mantém isto correto depois de um rollback,
    que descarta os callbacks mas não o bucket.
    """
    bucket = getattr(_pending, 'ids', None)
    if bucket is None:
        bucket = _pending.ids = set()
    bucket.add((kind, str(pk)))
    transaction.on_commit(_drain)


def _drain():
    bucket = getattr(_pending, 'ids', None)
    if not bucket:
        return
    _pending.ids = set()
    handlers = {SALE: _handle_sale, TASK: _handle_task, ORDER: _handle_service_order}
    for kind, pk in bucket:
        try:
            handlers[kind](pk)
        except Exception:
            logger.exception('Falha ao sincronizar produção (%s=%s)', kind, pk)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_sale(pk):
    sale = Sale.objects.filter(pk=pk).first()
    if sale is None:
        return

    order = ProductionOrder.objects.filter(sale=sale).first()
    if sale.status == Sale.Status.CANCELADO:
        # Cancelar vale mesmo com o módulo desligado: não deixa OP fantasma.
        if order is not None:
            prod.cancel_order(order, reason='Venda cancelada')
        return

    settings = ProductionSettings.load()
    if not settings.enabled:
        return
    if prod.should_sync_sale(sale, settings):
        prod.sync_from_sale(sale, settings=settings)
    elif order is not None:
        # A OP já existe e a venda saiu do status de gatilho (ex.: voltou para
        # um status anterior). Mantém a fila coerente com o pedido atual.
        prod.sync_from_sale(sale, settings=settings)


def _handle_task(pk):
    task = ServiceOrderTask.objects.filter(pk=pk).select_related('service_order').first()
    if task is None:
        return

    order = ProductionOrder.objects.filter(service_order_task=task).first()
    cancelled = (
        task.status == ServiceOrderTask.TaskStatus.CANCELADO
        or task.service_order.status == ServiceOrder.Status.CANCELADO
    )
    if cancelled:
        if order is not None:
            prod.cancel_order(order, reason='Etapa ou OS cancelada')
        return

    settings = ProductionSettings.load()
    if not settings.enabled:
        return
    if prod.should_sync_task(task, settings) or order is not None:
        prod.sync_from_task(task, settings=settings)


def _handle_service_order(pk):
    """OS cancelada cancela as OPs de todas as suas etapas."""
    order_os = ServiceOrder.objects.filter(pk=pk).first()
    if order_os is None or order_os.status != ServiceOrder.Status.CANCELADO:
        return
    for op in ProductionOrder.objects.filter(service_order=order_os).exclude(
        status__in=ProductionOrder.TERMINAL_STATUSES
    ):
        prod.cancel_order(op, reason='Ordem de serviço cancelada')


# ---------------------------------------------------------------------------
# Receivers
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Sale, dispatch_uid='producao_sale_saved')
def sale_saved(sender, instance, **kwargs):
    _schedule(SALE, instance.pk)


@receiver(post_save, sender=ServiceOrderTask, dispatch_uid='producao_task_saved')
def task_saved(sender, instance, **kwargs):
    _schedule(TASK, instance.pk)


@receiver(post_save, sender=ServiceOrder, dispatch_uid='producao_order_saved')
def service_order_saved(sender, instance, **kwargs):
    # Só interessa o cancelamento; `_handle_service_order` sai cedo no resto.
    _schedule(ORDER, instance.pk)
