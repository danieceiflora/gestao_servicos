"""Sincronização da ordem de produção com o documento de origem.

A parte mais frágil do módulo: três caminhos de edição deletam linhas de
origem de verdade (`views_pos._save_cart` apaga e recria todos os SaleItem, o
formset de `sale_detail` deleta, e `ServiceItem.delete()` existe). O matching
é por `source_key`, nunca pela FK, e a sincronização não pode destruir
trabalho já feito na oficina.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from services.models import (
    Client as ServiceClient, Product, ProductComposition, Property, Sale,
    SaleItem, ServiceItem, ServiceOrder, ServiceOrderTask, StockMovement, User,
)

from producao import services as prod
from producao.models import ProductionItem, ProductionOrder, ProductionSettings


def make_product(name, **kwargs):
    kwargs.setdefault('current_stock', Decimal('100.0000'))
    kwargs.setdefault('default_unit_price', Decimal('10.00'))
    return Product.objects.create(name=name, **kwargs)


class SyncBaseTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='oficina', password='x')
        self.client_obj = ServiceClient.objects.create(name='Cliente Teste')
        self.settings = ProductionSettings.load()
        self.settings.enabled = True
        self.settings.sale_trigger_statuses = [Sale.Status.PRONTO]
        self.settings.task_trigger_statuses = [ServiceOrderTask.TaskStatus.AGENDADO]
        self.settings.save()

        self.chapa = make_product('Chapa', type=Product.Type.MATERIA_PRIMA)
        self.composto = make_product('Calha Montada', format=Product.Format.COM_COMPOSICAO)
        ProductComposition.objects.create(
            parent=self.composto, component=self.chapa, quantity=Decimal('2'),
        )
        self.simples = make_product('Parafuso')
        self.servico = make_product('Instalação', type=Product.Type.SERVICO)

    def make_sale(self, status=Sale.Status.PRONTO, items=None, **kwargs):
        sale = Sale.objects.create(user=self.user, client=self.client_obj, status=status, **kwargs)
        for product, qty in (items or []):
            SaleItem.objects.create(
                sale=sale, product=product, quantity=Decimal(qty),
                unit_price=Decimal('10.00'),
            )
        return sale


class SaleSyncTests(SyncBaseTestCase):
    def test_creates_order_with_eligible_items(self):
        sale = self.make_sale(items=[(self.composto, 2), (self.simples, 5), (self.servico, 1)])
        order = prod.sync_from_sale(sale)

        self.assertIsNotNone(order)
        self.assertEqual(order.items.count(), 2)  # serviço fica fora
        self.assertEqual(
            sorted(order.items.values_list('description', flat=True)),
            ['Calha Montada', 'Parafuso'],
        )
        self.assertEqual(order.status, ProductionOrder.Status.AGUARDANDO)
        self.assertEqual(order.source_status, Sale.Status.PRONTO)

    def test_idempotent(self):
        sale = self.make_sale(items=[(self.composto, 2)])
        first = prod.sync_from_sale(sale)
        prod.sync_from_sale(sale)
        prod.sync_from_sale(sale)

        self.assertEqual(ProductionOrder.objects.count(), 1)
        self.assertEqual(first.items.count(), 1)

    def test_scope_somente_preparo(self):
        self.settings.item_scope = ProductionSettings.ItemScope.SOMENTE_PREPARO
        self.settings.save()
        sale = self.make_sale(items=[(self.composto, 1), (self.simples, 1)])
        order = prod.sync_from_sale(sale)
        self.assertEqual(
            list(order.items.values_list('description', flat=True)), ['Calha Montada'],
        )

    def test_scope_somente_preparo_includes_requires_finishing(self):
        self.settings.item_scope = ProductionSettings.ItemScope.SOMENTE_PREPARO
        self.settings.save()
        chapa_cortada = make_product('Chapa para corte', requires_finishing=True)
        sale = self.make_sale(items=[(chapa_cortada, 1), (self.simples, 1)])
        order = prod.sync_from_sale(sale)
        self.assertEqual(
            list(order.items.values_list('description', flat=True)), ['Chapa para corte'],
        )
        self.assertEqual(order.items.first().kind, ProductionItem.Kind.ACABAMENTO)

    def test_no_eligible_items_creates_nothing(self):
        sale = self.make_sale(items=[(self.servico, 1)])
        self.assertIsNone(prod.sync_from_sale(sale))
        self.assertEqual(ProductionOrder.objects.count(), 0)

    def test_delivery_mode_from_delivery_address(self):
        sale = self.make_sale(items=[(self.simples, 1)], delivery_address='Rua X')
        self.assertEqual(prod.sync_from_sale(sale).delivery_mode, 'ENVIO')
        outra = self.make_sale(items=[(self.simples, 1)])
        self.assertEqual(prod.sync_from_sale(outra).delivery_mode, 'RETIRADA')

    def test_due_date_from_sale(self):
        import datetime
        sale = self.make_sale(items=[(self.simples, 1)], delivery_date=datetime.date(2026, 12, 1))
        self.assertEqual(prod.sync_from_sale(sale).due_date, datetime.date(2026, 12, 1))


class SaleSyncReconciliationTests(SyncBaseTestCase):
    """A tabela de reconciliação do plano, um teste por linha."""

    def setUp(self):
        super().setUp()
        self.sale = self.make_sale(items=[(self.composto, 2), (self.simples, 5)])
        self.order = prod.sync_from_sale(self.sale)
        self.item_composto = self.order.items.get(description='Calha Montada')
        self.item_simples = self.order.items.get(description='Parafuso')

    def test_new_line_creates_pending_item(self):
        SaleItem.objects.create(
            sale=self.sale, product=self.chapa, quantity=Decimal('3'),
            unit_price=Decimal('5.00'),
        )
        prod.sync_from_sale(self.sale)
        novo = self.order.items.get(description='Chapa')
        self.assertEqual(novo.status, ProductionItem.Status.PENDENTE)
        self.assertEqual(novo.quantity, Decimal('3.0000'))

    def test_quantity_increase_reopens_finished_item(self):
        prod.finish_item(self.item_simples, user=self.user)
        line = SaleItem.objects.get(sale=self.sale, product=self.simples)
        line.quantity = Decimal('8')
        line.save()

        prod.sync_from_sale(self.sale)
        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.quantity, Decimal('8.0000'))
        self.assertEqual(self.item_simples.quantity_done, Decimal('5.0000'))
        self.assertEqual(self.item_simples.status, ProductionItem.Status.PENDENTE)

    def test_quantity_decrease_above_done_keeps_status(self):
        prod.finish_item(self.item_simples, user=self.user, quantity_done=Decimal('2'))
        line = SaleItem.objects.get(sale=self.sale, product=self.simples)
        line.quantity = Decimal('3')
        line.save()

        prod.sync_from_sale(self.sale)
        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.quantity, Decimal('3.0000'))
        self.assertEqual(self.item_simples.status, ProductionItem.Status.CONCLUIDO)
        self.assertFalse(self.item_simples.needs_review)

    def test_quantity_below_done_never_truncates_and_flags_review(self):
        prod.finish_item(self.item_simples, user=self.user)  # done = 5
        line = SaleItem.objects.get(sale=self.sale, product=self.simples)
        line.quantity = Decimal('2')
        line.save()

        prod.sync_from_sale(self.sale)
        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.quantity, Decimal('2.0000'))
        self.assertEqual(self.item_simples.quantity_done, Decimal('5.0000'))
        self.assertTrue(self.item_simples.needs_review)

    def test_product_swap_cancels_old_and_creates_new(self):
        prod.start_item(self.item_simples, user=self.user)
        line = SaleItem.objects.get(sale=self.sale, product=self.simples)
        line.product = self.chapa
        line.save()

        prod.sync_from_sale(self.sale)
        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.status, ProductionItem.Status.CANCELADO)
        self.assertEqual(self.item_simples.source_key, '')
        novo = self.order.items.get(source_key=f'sale_item:{line.pk}')
        self.assertEqual(novo.product_id, self.chapa.pk)
        self.assertEqual(novo.status, ProductionItem.Status.PENDENTE)

    def test_removed_untouched_item_is_deleted(self):
        pk = self.item_simples.pk
        SaleItem.objects.filter(sale=self.sale, product=self.simples).delete()
        prod.sync_from_sale(self.sale)
        self.assertFalse(ProductionItem.objects.filter(pk=pk).exists())

    def test_removed_started_item_is_cancelled_not_deleted(self):
        prod.start_item(self.item_simples, user=self.user)
        SaleItem.objects.filter(sale=self.sale, product=self.simples).delete()
        prod.sync_from_sale(self.sale)

        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.status, ProductionItem.Status.CANCELADO)
        self.assertTrue(self.order.events.filter(message__icontains='removido do pedido').exists())

    def test_price_change_is_ignored(self):
        line = SaleItem.objects.get(sale=self.sale, product=self.simples)
        line.unit_price = Decimal('999.00')
        line.discount = Decimal('5.00')
        line.save()
        prod.sync_from_sale(self.sale)
        self.assertEqual(self.order.items.count(), 2)

    def test_pos_delete_and_recreate_keeps_order_but_relinks(self):
        """`_save_cart` apaga e recria as linhas: as antigas somem da origem."""
        prod.start_item(self.item_simples, user=self.user)
        self.sale.items.all().delete()
        SaleItem.objects.create(
            sale=self.sale, product=self.simples, quantity=Decimal('5'),
            unit_price=Decimal('10.00'),
        )
        prod.sync_from_sale(self.sale)

        self.assertEqual(ProductionOrder.objects.count(), 1)
        # O item iniciado é preservado como cancelado; o novo nasce pendente.
        self.item_simples.refresh_from_db()
        self.assertEqual(self.item_simples.status, ProductionItem.Status.CANCELADO)
        self.assertEqual(
            self.order.items.filter(status=ProductionItem.Status.PENDENTE).count(), 1,
        )


class TaskSyncTests(SyncBaseTestCase):
    def setUp(self):
        super().setUp()
        self.property = Property.objects.create(
            client=self.client_obj, address='Rua A', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        self.order_os = ServiceOrder.objects.create(
            client_property=self.property, description='Instalação',
        )

    def make_task(self, task_type=ServiceOrderTask.TaskType.EXECUCAO,
                  status=ServiceOrderTask.TaskStatus.AGENDADO, **kwargs):
        kwargs.setdefault('scheduled_at', timezone.now())
        return ServiceOrderTask.objects.create(
            service_order=self.order_os, task_type=task_type, status=status, **kwargs,
        )

    def test_one_order_per_task(self):
        execucao = self.make_task()
        ServiceItem.objects.create(
            service_order=self.order_os, task=execucao, product=self.composto,
            quantity=Decimal('2'), unit_price=Decimal('10.00'),
        )
        garantia = self.make_task(task_type=ServiceOrderTask.TaskType.GARANTIA)
        ServiceItem.objects.create(
            service_order=self.order_os, task=garantia, product=self.simples,
            quantity=Decimal('1'), unit_price=Decimal('5.00'),
        )

        op1 = prod.sync_from_task(execucao)
        op2 = prod.sync_from_task(garantia)

        self.assertNotEqual(op1.pk, op2.pk)
        self.assertEqual(ProductionOrder.objects.count(), 2)
        self.assertEqual(list(op1.items.values_list('description', flat=True)), ['Calha Montada'])
        self.assertEqual(list(op2.items.values_list('description', flat=True)), ['Parafuso'])

    def test_budget_items_never_enter_production(self):
        """Itens de orçamento são clonados para a execução; a OP é por etapa,
        então os itens do orçamento simplesmente não aparecem."""
        orcamento = self.make_task(task_type=ServiceOrderTask.TaskType.ORCAMENTO)
        ServiceItem.objects.create(
            service_order=self.order_os, task=orcamento, product=self.composto,
            quantity=Decimal('3'), unit_price=Decimal('10.00'),
        )
        execucao = self.make_task()
        # Clone parcial: só 2 das 3 unidades viraram execução.
        ServiceItem.objects.create(
            service_order=self.order_os, task=execucao, product=self.composto,
            quantity=Decimal('2'), unit_price=Decimal('10.00'),
        )

        self.assertFalse(prod.should_sync_task(orcamento))
        op = prod.sync_from_task(execucao)
        self.assertEqual(op.items.count(), 1)
        self.assertEqual(op.items.first().quantity, Decimal('2.0000'))

    def test_items_without_task_are_invisible_to_production(self):
        """ServiceItem com task=None (orçamento geral) nunca entra na fila."""
        execucao = self.make_task()
        ServiceItem.objects.create(
            service_order=self.order_os, task=None, product=self.simples,
            quantity=Decimal('4'), unit_price=Decimal('5.00'),
        )
        ServiceItem.objects.create(
            service_order=self.order_os, task=execucao, product=self.composto,
            quantity=Decimal('1'), unit_price=Decimal('10.00'),
        )
        op = prod.sync_from_task(execucao)
        self.assertEqual(list(op.items.values_list('description', flat=True)), ['Calha Montada'])

    def test_delivery_mode_defaults_to_tecnico(self):
        execucao = self.make_task()
        ServiceItem.objects.create(
            service_order=self.order_os, task=execucao, product=self.simples,
            quantity=Decimal('1'), unit_price=Decimal('5.00'),
        )
        self.assertEqual(prod.sync_from_task(execucao).delivery_mode, 'TECNICO')

    def test_should_sync_task_respects_approval(self):
        execucao = self.make_task(requires_client_approval=True, is_approved=False)
        self.assertFalse(prod.should_sync_task(execucao))
        execucao.is_approved = True
        self.assertTrue(prod.should_sync_task(execucao))

    def test_should_sync_task_ignores_non_production_types(self):
        orcamento = self.make_task(task_type=ServiceOrderTask.TaskType.ORCAMENTO)
        self.assertFalse(prod.should_sync_task(orcamento))


class TriggerEligibilityTests(SyncBaseTestCase):
    def test_disabled_module_blocks_everything(self):
        self.settings.enabled = False
        self.settings.save()
        sale = self.make_sale(items=[(self.simples, 1)])
        self.assertFalse(prod.should_sync_sale(sale))

    def test_draft_never_triggers(self):
        self.settings.sale_trigger_statuses = [Sale.Status.RASCUNHO, Sale.Status.PRONTO]
        self.settings.save()
        sale = self.make_sale(status=Sale.Status.RASCUNHO, items=[(self.simples, 1)])
        self.assertFalse(prod.should_sync_sale(sale))

    def test_status_outside_list_does_not_trigger(self):
        sale = self.make_sale(status=Sale.Status.EM_ANDAMENTO, items=[(self.simples, 1)])
        self.assertFalse(prod.should_sync_sale(sale))

    def test_sale_linked_to_service_order_is_skipped(self):
        prop = Property.objects.create(
            client=self.client_obj, address='Rua A', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        os_order = ServiceOrder.objects.create(client_property=prop, description='x')
        sale = self.make_sale(items=[(self.simples, 1)], service_order=os_order)
        self.assertFalse(prod.should_sync_sale(sale))

        self.settings.skip_sale_linked_to_order = False
        self.settings.save()
        self.assertTrue(prod.should_sync_sale(sale))


class StockPremiseTests(SyncBaseTestCase):
    """A premissa central: produção não é documento de estoque."""

    def test_no_stock_movement_in_full_lifecycle(self):
        sale = self.make_sale(items=[(self.composto, 2), (self.simples, 5)])
        before = StockMovement.objects.count()

        order = prod.sync_from_sale(sale)
        for item in order.items.all():
            prod.start_item(item, user=self.user)
            prod.finish_item(item, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.PRONTO)

        order, error = prod.deliver(order, user=self.user, delivered_to='Cliente')
        self.assertIsNone(error)
        self.assertEqual(order.status, ProductionOrder.Status.ENTREGUE)

        self.assertEqual(StockMovement.objects.count(), before)

    def test_no_stock_movement_on_cancel(self):
        sale = self.make_sale(items=[(self.simples, 1)])
        order = prod.sync_from_sale(sale)
        before = StockMovement.objects.count()
        prod.cancel_order(order, user=self.user, reason='Venda cancelada')
        self.assertEqual(StockMovement.objects.count(), before)
