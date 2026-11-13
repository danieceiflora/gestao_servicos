"""Integração com o motor de notificações e com o menu.

As mensagens são opcionais por construção: sem nenhuma `NotificationConfig`
cadastrada, nada é enviado. O que estes testes protegem é o contrário — que,
com uma regra cadastrada, o disparo aconteça uma única vez, depois do commit,
e que o formulário de regra seja realmente usável para este modelo.
"""

from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from integracoes.models import NotificationConfig
from integracoes.utils import get_mappable_fields
from services.models import (
    Client as ServiceClient, Product, Sale, SaleItem, User,
)

from producao import services as prod
from producao.models import ProductionOrder, ProductionSettings


class NotificationRegistrationTests(TestCase):
    """Os seis pontos de registro são listas e if/elif hardcoded."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='x', is_staff=True, role=User.Roles.ADMIN,
        )
        self.client.force_login(self.staff)

    def test_model_is_offered_as_choice(self):
        self.assertIn('ProductionOrder', dict(NotificationConfig.MODEL_CHOICES))

    def test_status_choices_endpoint_is_populated(self):
        """Sem o ramo em ajax_get_status_choices a regra fica inutilizável."""
        response = self.client.get(
            reverse('integracoes:ajax_get_status_choices'),
            {'model_name': 'ProductionOrder'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [c[0] for c in response.context['choices']],
            [c[0] for c in ProductionOrder.Status.choices],
        )
        self.assertContains(response, 'PRONTO')

    def test_phone_fields_are_phones_only(self):
        """Sem o ramo only_phones a função devolveria a lista curada inteira."""
        phones = get_mappable_fields('ProductionOrder', only_phones=True)
        self.assertEqual(
            [p[0] for p in phones], ['client_phone', 'technician_phone'],
        )

    def test_curated_fields_exist_and_resolve(self):
        from integracoes.utils import resolve_field_path

        client_obj = ServiceClient.objects.create(name='Cliente Teste')
        produto = Product.objects.create(
            name='Chapa', current_stock=Decimal('10.0000'),
            default_unit_price=Decimal('10.00'),
        )
        config = ProductionSettings.load()
        config.enabled = True
        config.sale_trigger_statuses = [Sale.Status.PRONTO]
        config.save()

        sale = Sale.objects.create(user=self.staff, client=client_obj, status=Sale.Status.PRONTO)
        SaleItem.objects.create(
            sale=sale, product=produto, quantity=Decimal('1'), unit_price=Decimal('10.00'),
        )
        order = prod.sync_from_sale(sale)

        paths = [p for p, _ in get_mappable_fields('ProductionOrder')]
        self.assertIn('number', paths)
        self.assertIn('origin_label', paths)
        for path in paths:
            if path.startswith('__config__.'):
                continue
            # Não deve explodir; valor nulo é aceitável.
            resolve_field_path(order, path)

    def test_production_order_is_not_in_generic_signal_list(self):
        """Estar nos dois lugares dobraria o envio."""
        from integracoes.signals import DYNAMIC_NOTIFICATION_MODELS
        self.assertNotIn(
            'ProductionOrder',
            [m.__name__ for m in DYNAMIC_NOTIFICATION_MODELS],
        )


class NotificationDispatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='gerente', password='x', role=User.Roles.MANAGER)
        self.client_obj = ServiceClient.objects.create(name='Cliente Teste')
        self.produto = Product.objects.create(
            name='Chapa', current_stock=Decimal('50.0000'), default_unit_price=Decimal('10.00'),
        )
        config = ProductionSettings.load()
        config.enabled = True
        config.sale_trigger_statuses = [Sale.Status.PRONTO]
        config.save()

    def make_order(self, item_count=1):
        sale = Sale.objects.create(user=self.user, client=self.client_obj, status=Sale.Status.PRONTO)
        for _ in range(item_count):
            SaleItem.objects.create(
                sale=sale, product=self.produto, quantity=Decimal('1'), unit_price=Decimal('10.00'),
            )
        return prod.sync_from_sale(sale)

    def test_dispatch_is_per_status_change_and_after_commit(self):
        """Concluir 5 itens muda o status duas vezes, não cinco."""
        order = self.make_order(item_count=5)

        with mock.patch('integracoes.utils.dispatch_dynamic_notification') as send:
            with self.captureOnCommitCallbacks(execute=True):
                for item in order.items.all():
                    prod.finish_item(item, user=self.user)
                # Nada pode sair antes do commit: um rollback deixaria a
                # mensagem já enviada.
                self.assertEqual(send.call_count, 0)

        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.PRONTO)

        # A OP passou por AGUARDANDO -> EM_SEPARACAO -> PRONTO, mas é UMA
        # transição commitada. Despachar as duas mandaria a mensagem de
        # "pronto" duas vezes, porque o motor filtra a regra pelo status
        # atual do objeto.
        self.assertEqual(send.call_count, 1)
        call = send.call_args_list[0]
        self.assertEqual(call.args[1], 'MUDANCA_STATUS')
        self.assertEqual(call.kwargs['old_status'], ProductionOrder.Status.AGUARDANDO)
        self.assertEqual(call.args[0].status, ProductionOrder.Status.PRONTO)

    def test_round_trip_in_one_transaction_does_not_notify(self):
        order = self.make_order()
        item = order.items.first()
        with mock.patch('integracoes.utils.dispatch_dynamic_notification') as send:
            with self.captureOnCommitCallbacks(execute=True):
                prod.finish_item(item, user=self.user)
                prod.reopen_item(item, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.AGUARDANDO)
        send.assert_not_called()

    def test_no_rule_means_no_message(self):
        """A opcionalidade é nativa: sem regra o motor sai cedo."""
        self.assertFalse(NotificationConfig.objects.filter(model_name='ProductionOrder').exists())
        order = self.make_order()
        with mock.patch('integracoes.chatwoot_client.ChatwootClient') as chatwoot:
            with self.captureOnCommitCallbacks(execute=True):
                prod.finish_item(order.items.first(), user=self.user)
        chatwoot.assert_not_called()

    def test_dispatch_failure_does_not_break_the_action(self):
        order = self.make_order()
        with mock.patch(
            'integracoes.utils.dispatch_dynamic_notification',
            side_effect=RuntimeError('chatwoot fora do ar'),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                prod.finish_item(order.items.first(), user=self.user)

        order.refresh_from_db()
        self.assertEqual(order.status, ProductionOrder.Status.PRONTO)


class MenuTests(TestCase):
    def test_operator_sees_menu_entry(self):
        user = User.objects.create_user(
            username='oficina', password='x', role=User.Roles.COLLABORATOR,
        )
        user.user_permissions.add(
            Permission.objects.get(
                codename='operate_production', content_type__app_label='producao',
            )
        )
        self.client.force_login(User.objects.get(pk=user.pk))
        response = self.client.get(reverse('producao:board'))
        self.assertContains(response, reverse('producao:board'))
        self.assertContains(response, 'Expedição / Produção')
