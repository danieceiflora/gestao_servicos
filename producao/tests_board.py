"""Views do painel, permissões e entrada automática pelos signals."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from services.models import (
    Client as ServiceClient, Product, Property, Sale, SaleItem, ServiceItem,
    ServiceOrder, ServiceOrderTask, User,
)

from producao import services as prod
from producao.models import ProductionItem, ProductionOrder, ProductionSettings


class BoardTestMixin:
    def setUp(self):
        self.manager = User.objects.create_user(
            username='gerente', password='x', role=User.Roles.MANAGER,
        )
        self.operador = User.objects.create_user(
            username='oficina', password='x', role=User.Roles.COLLABORATOR,
        )
        self.estranho = User.objects.create_user(
            username='outro', password='x', role=User.Roles.COLLABORATOR,
        )
        self.client_obj = ServiceClient.objects.create(name='Cliente Teste')

        self.config = ProductionSettings.load()
        self.config.enabled = True
        self.config.sale_trigger_statuses = [Sale.Status.PRONTO]
        self.config.task_trigger_statuses = [ServiceOrderTask.TaskStatus.AGENDADO]
        self.config.save()

        self.produto = Product.objects.create(
            name='Chapa', current_stock=Decimal('50.0000'),
            default_unit_price=Decimal('10.00'),
        )

    def grant(self, user, codename):
        from django.contrib.auth.models import Permission
        user.user_permissions.add(
            Permission.objects.get(codename=codename, content_type__app_label='producao')
        )
        return User.objects.get(pk=user.pk)  # limpa o cache de permissões

    def make_order(self, status=Sale.Status.PRONTO, quantity='3'):
        sale = Sale.objects.create(user=self.manager, client=self.client_obj, status=status)
        SaleItem.objects.create(
            sale=sale, product=self.produto, quantity=Decimal(quantity),
            unit_price=Decimal('10.00'),
        )
        return prod.sync_from_sale(sale), sale


class PermissionTests(BoardTestMixin, TestCase):
    def test_anonymous_redirected(self):
        response = self.client.get(reverse('producao:board'))
        self.assertEqual(response.status_code, 302)

    def test_plain_collaborator_denied(self):
        self.client.force_login(self.estranho)
        self.assertEqual(self.client.get(reverse('producao:board')).status_code, 302)

    def test_collaborator_with_operate_permission_sees_board(self):
        """O público do painel é COLABORADOR, para quem is_manager é False."""
        user = self.grant(self.operador, 'operate_production')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('producao:board')).status_code, 200)

    def test_operate_permission_does_not_grant_settings(self):
        user = self.grant(self.operador, 'operate_production')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('producao:settings')).status_code, 302)

    def test_manager_sees_everything(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('producao:board')).status_code, 200)
        self.assertEqual(self.client.get(reverse('producao:settings')).status_code, 200)

    def test_view_permission_is_read_only(self):
        user = self.grant(self.estranho, 'view_productionorder')
        self.client.force_login(user)
        order, _ = self.make_order()
        self.assertEqual(self.client.get(reverse('producao:board')).status_code, 200)
        item = order.items.first()
        response = self.client.post(reverse('producao:item_start', args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, ProductionItem.Status.PENDENTE)


class BoardViewTests(BoardTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.manager)

    def test_pages_do_not_leak_template_comments(self):
        """`{# #}` do Django só vale em UMA linha; em duas vira texto na tela."""
        order, _ = self.make_order()
        for url in (
            reverse('producao:board'),
            reverse('producao:order_detail', args=[order.number]),
            reverse('producao:settings'),
        ):
            with self.subTest(url=url):
                body = self.client.get(url).content.decode()
                self.assertNotIn('{#', body)
                self.assertNotIn('#}', body)

    def test_board_lists_order(self):
        order, _ = self.make_order()
        response = self.client.get(reverse('producao:board'))
        self.assertContains(response, f'OP #{order.number}')

    def test_board_partial_204_when_version_matches(self):
        self.make_order()
        page = self.client.get(reverse('producao:board'))
        version = page.context['board_version']

        unchanged = self.client.get(reverse('producao:board_partial'), {'v': version})
        self.assertEqual(unchanged.status_code, 204)
        self.assertEqual(unchanged.content, b'')

    def test_board_partial_200_after_change(self):
        order, _ = self.make_order()
        version = self.client.get(reverse('producao:board')).context['board_version']

        prod.start_item(order.items.first(), user=self.manager)

        changed = self.client.get(reverse('producao:board_partial'), {'v': version})
        self.assertEqual(changed.status_code, 200)
        self.assertContains(changed, f'OP #{order.number}')

    def test_board_version_changes_with_filters(self):
        self.make_order()
        a = self.client.get(reverse('producao:board')).context['board_version']
        b = self.client.get(reverse('producao:board'), {'origin': 'OS'}).context['board_version']
        self.assertNotEqual(a, b)

    def test_blocked_orders_are_visible_outside_columns(self):
        """Ordem travada não pode desaparecer do painel por não ter coluna."""
        order, _ = self.make_order()
        prod.set_waiting_material(order, user=self.manager, note='bobina 0,43')
        response = self.client.get(reverse('producao:board'))
        self.assertEqual(len(response.context['blocked_orders']), 1)
        self.assertContains(response, 'bobina 0,43')

    def test_item_actions_via_htmx_return_detail_fragment(self):
        order, _ = self.make_order()
        item = order.items.first()
        response = self.client.post(
            reverse('producao:item_finish', args=[item.pk]),
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="order-body"')
        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.PRONTO)

    def test_board_scope_action_returns_board_fragment(self):
        order, _ = self.make_order()
        prod.set_waiting_material(order, user=self.manager, note='x')
        response = self.client.post(
            reverse('producao:order_waiting_material', args=[order.number]),
            {'waiting': '0', 'scope': 'board'},
            HTTP_HX_REQUEST='true',
        )
        self.assertContains(response, 'id="board-inner"')

    def test_detail_shows_bom_as_picking_list(self):
        from services.models import ProductComposition
        componente = Product.objects.create(
            name='Bobina', current_stock=Decimal('5.0000'), default_unit_price=Decimal('1.00'),
        )
        composto = Product.objects.create(
            name='Calha', format=Product.Format.COM_COMPOSICAO,
            current_stock=Decimal('10.0000'), default_unit_price=Decimal('20.00'),
        )
        ProductComposition.objects.create(parent=composto, component=componente, quantity=Decimal('4'))

        sale = Sale.objects.create(user=self.manager, client=self.client_obj, status=Sale.Status.PRONTO)
        SaleItem.objects.create(sale=sale, product=composto, quantity=Decimal('2'), unit_price=Decimal('20.00'))
        order = prod.sync_from_sale(sale)

        response = self.client.get(reverse('producao:order_detail', args=[order.number]))
        self.assertContains(response, 'Bobina')
        components = response.context['rows'][0]['components']
        self.assertEqual(components[0]['required'], Decimal('8'))

    def test_deliver_requires_pronto(self):
        order, _ = self.make_order()
        self.client.post(reverse('producao:order_deliver', args=[order.number]), {'delivered_to': 'X'})
        order.refresh_from_db()
        self.assertNotEqual(order.status, ProductionOrder.Status.ENTREGUE)

    def test_deliver_records_tracking_for_envio(self):
        order, _ = self.make_order()
        order.delivery_mode = 'ENVIO'
        order.save(update_fields=['delivery_mode'])
        prod.finish_item(order.items.first(), user=self.manager)

        self.client.post(reverse('producao:order_deliver', args=[order.number]), {
            'delivered_to': 'Cliente', 'carrier': 'Correios', 'tracking_code': 'BR123',
        })
        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.ENTREGUE)
        self.assertEqual(order.tracking_code, 'BR123')


class SettingsViewTests(BoardTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.manager)

    def test_draft_is_not_offered_as_trigger(self):
        response = self.client.get(reverse('producao:settings'))
        values = [c[0] for c in response.context['form'].fields['sale_trigger_statuses'].choices]
        self.assertNotIn(Sale.Status.RASCUNHO, values)
        self.assertNotIn(Sale.Status.CANCELADO, values)

    def test_enabled_without_any_trigger_is_rejected(self):
        response = self.client.post(reverse('producao:settings'), {
            'enabled': 'on', 'item_scope': 'TODOS',
            'default_delivery_mode_sale': 'RETIRADA', 'default_delivery_mode_order': 'TECNICO',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())

    def test_save_persists_trigger_lists(self):
        response = self.client.post(reverse('producao:settings'), {
            'enabled': 'on',
            'sale_trigger_statuses': ['PRONTO', 'ATENDIDO'],
            'task_trigger_statuses': ['AGENDADO'],
            'item_scope': 'SOMENTE_PREPARO',
            'default_delivery_mode_sale': 'ENVIO',
            'default_delivery_mode_order': 'TECNICO',
        })
        self.assertEqual(response.status_code, 302)
        config = ProductionSettings.load()
        self.assertEqual(sorted(config.sale_trigger_statuses), ['ATENDIDO', 'PRONTO'])
        self.assertEqual(config.task_trigger_statuses, ['AGENDADO'])


class SignalTriggerTests(BoardTestMixin, TestCase):
    """Entrada automática. O duplo save de `sale_create` só aparece pela view."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.manager)

    def test_sale_in_trigger_status_creates_order_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            sale = Sale.objects.create(
                user=self.manager, client=self.client_obj, status=Sale.Status.RASCUNHO,
            )
            SaleItem.objects.create(
                sale=sale, product=self.produto, quantity=Decimal('2'),
                unit_price=Decimal('10.00'),
            )
            sale.status = Sale.Status.PRONTO
            sale.save()

        self.assertEqual(ProductionOrder.objects.count(), 1)
        self.assertEqual(ProductionOrder.objects.first().items.count(), 1)

    def test_draft_sale_creates_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            sale = Sale.objects.create(
                user=self.manager, client=self.client_obj, status=Sale.Status.RASCUNHO,
            )
            SaleItem.objects.create(
                sale=sale, product=self.produto, quantity=Decimal('2'),
                unit_price=Decimal('10.00'),
            )
        self.assertEqual(ProductionOrder.objects.count(), 0)

    def test_disabled_module_creates_nothing(self):
        self.config.enabled = False
        self.config.save()
        with self.captureOnCommitCallbacks(execute=True):
            sale = Sale.objects.create(
                user=self.manager, client=self.client_obj, status=Sale.Status.PRONTO,
            )
            SaleItem.objects.create(
                sale=sale, product=self.produto, quantity=Decimal('1'),
                unit_price=Decimal('10.00'),
            )
        self.assertEqual(ProductionOrder.objects.count(), 0)

    def test_cancelled_sale_cancels_order(self):
        order, sale = self.make_order()
        with self.captureOnCommitCallbacks(execute=True):
            sale.status = Sale.Status.CANCELADO
            sale.save()
        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.CANCELADO)

    def test_task_creates_its_own_order(self):
        prop = Property.objects.create(
            client=self.client_obj, address='Rua A', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        os_order = ServiceOrder.objects.create(client_property=prop, description='Instalação')
        with self.captureOnCommitCallbacks(execute=True):
            task = ServiceOrderTask.objects.create(
                service_order=os_order, task_type=ServiceOrderTask.TaskType.EXECUCAO,
                status=ServiceOrderTask.TaskStatus.AGENDADO, scheduled_at=timezone.now(),
            )
            ServiceItem.objects.create(
                service_order=os_order, task=task, product=self.produto,
                quantity=Decimal('4'), unit_price=Decimal('10.00'),
            )
        self.assertEqual(ProductionOrder.objects.count(), 1)
        op = ProductionOrder.objects.first()
        self.assertEqual(op.service_order_task_id, task.pk)
        self.assertEqual(op.service_order_id, os_order.pk)
        self.assertEqual(op.items.count(), 1)

    def test_many_item_saves_collapse_into_one_sync(self):
        """O debounce impede uma sincronização por save em cascata da OS."""
        prop = Property.objects.create(
            client=self.client_obj, address='Rua A', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        os_order = ServiceOrder.objects.create(client_property=prop, description='x')
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            task = ServiceOrderTask.objects.create(
                service_order=os_order, task_type=ServiceOrderTask.TaskType.EXECUCAO,
                status=ServiceOrderTask.TaskStatus.AGENDADO, scheduled_at=timezone.now(),
            )
            for _ in range(5):
                ServiceItem.objects.create(
                    service_order=os_order, task=task, product=self.produto,
                    quantity=Decimal('1'), unit_price=Decimal('10.00'),
                )
        # Muitos callbacks registrados, mas um único drenou o bucket.
        self.assertGreater(len(callbacks), 1)
        self.assertEqual(ProductionOrder.objects.count(), 1)
        self.assertEqual(ProductionOrder.objects.first().items.count(), 5)

    def test_cancelled_service_order_cancels_task_orders(self):
        prop = Property.objects.create(
            client=self.client_obj, address='Rua A', neighborhood='Centro',
            city='Dourados', state='MS',
        )
        os_order = ServiceOrder.objects.create(client_property=prop, description='x')
        with self.captureOnCommitCallbacks(execute=True):
            task = ServiceOrderTask.objects.create(
                service_order=os_order, task_type=ServiceOrderTask.TaskType.EXECUCAO,
                status=ServiceOrderTask.TaskStatus.AGENDADO, scheduled_at=timezone.now(),
            )
            ServiceItem.objects.create(
                service_order=os_order, task=task, product=self.produto,
                quantity=Decimal('1'), unit_price=Decimal('10.00'),
            )
        op = ProductionOrder.objects.get()

        with self.captureOnCommitCallbacks(execute=True):
            os_order.status = ServiceOrder.Status.CANCELADO
            os_order.save()

        op.refresh_from_db()
        self.assertEqual(op.status, ProductionOrder.Status.CANCELADO)
