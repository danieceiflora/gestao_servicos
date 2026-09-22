from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch
import json

from integracoes.models import SystemConfig
from .forms import SaleForm
from .models import (
	Client, Professional, Property, ServiceItem, ServiceOrder,
	ServiceOrderTask, ServiceOrderTeam, User, Product, Sale, SaleItem,
	SaleSettings, CashRegister, CashSession, CashClosingCount, PaymentMethod, Billing,
)


class PublicPolicyPagesTests(TestCase):
	def test_privacy_policy_page_loads(self):
		response = self.client.get(reverse('privacy_policy'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Política de Privacidade')

	def test_data_deletion_policy_page_loads(self):
		response = self.client.get(reverse('data_deletion_policy'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Exclusão de Dados do Usuário')

	def test_terms_of_service_page_loads(self):
		response = self.client.get(reverse('terms_of_service'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Termos de Serviço')


class TechnicianAppSettingsTests(TestCase):
	def test_setting_defaults_to_enabled(self):
		self.assertTrue(SystemConfig.load().technician_can_view_order_values)

	def test_staff_can_update_setting(self):
		staff = User.objects.create_user(username='staff', password='x', is_staff=True)
		self.client.force_login(staff)

		response = self.client.post(reverse('technician_app_settings'), {})

		self.assertRedirects(response, reverse('technician_app_settings'))
		self.assertFalse(SystemConfig.load().technician_can_view_order_values)

	def test_non_staff_cannot_access_setting(self):
		user = User.objects.create_user(username='colaborador-config', password='x')
		self.client.force_login(user)

		response = self.client.get(reverse('technician_app_settings'))

		self.assertNotEqual(response.status_code, 200)


class TechnicianBootstrapOrderValuesTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='tecnico-bootstrap', password='x')
		self.professional = Professional.objects.create(
			user=self.user,
			name='Técnico Teste',
			phone='67999999999',
		)
		client = Client.objects.create(name='Cliente Teste')
		property_obj = Property.objects.create(
			client=client,
			address='Rua Teste',
			neighborhood='Centro',
			city='Dourados',
			state='MS',
		)
		self.order = ServiceOrder.objects.create(client_property=property_obj)
		self.task = ServiceOrderTask.objects.create(
			service_order=self.order,
			task_type=ServiceOrderTask.TaskType.EXECUCAO,
			scheduled_at=timezone.now(),
		)
		ServiceOrderTeam.objects.create(task=self.task, professional=self.professional)
		ServiceItem.objects.create(
			service_order=self.order,
			task=self.task,
			description='Serviço sigiloso',
			quantity=Decimal('2'),
			unit_price=Decimal('75.00'),
		)
		self.client.force_login(self.user)

	def test_enabled_setting_includes_order_values(self):
		response = self.client.get(reverse('api_tecnico_bootstrap'))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload['config']['technician_can_view_order_values'])
		self.assertEqual(payload['orders'][0]['total_value'], '150.00')
		self.assertIn('balance_due', payload['orders'][0])
		self.assertEqual(payload['task_items'][0]['unit_price'], '75.00')
		self.assertEqual(payload['task_items'][0]['total_price'], '150.00')

	def test_disabled_setting_omits_all_order_values(self):
		config = SystemConfig.load()
		config.technician_can_view_order_values = False
		config.save()

		response = self.client.get(reverse('api_tecnico_bootstrap'))

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertFalse(payload['config']['technician_can_view_order_values'])
		self.assertTrue(payload['orders'][0]['has_balance_due'])
		for field in ('total_value', 'total_paid', 'balance_due'):
			self.assertNotIn(field, payload['orders'][0])
		for field in ('unit_price', 'total_price'):
			self.assertNotIn(field, payload['task_items'][0])
		self.assertEqual(payload['billings'], [])
		self.assertEqual(payload['installments'], [])


class SaleStatusSaveTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='gerente-vendas',
			password='x',
			role=User.Roles.MANAGER,
		)
		self.product = Product.objects.create(
			name='Produto Teste',
			code='PROD-STATUS-1',
			default_unit_price=Decimal('25.00'),
			current_stock=Decimal('10.0000'),
		)
		self.client.force_login(self.user)

	def _payload(self, status, **extra):
		payload = {
			'client': '',
			'status': status,
			'sale_type': Sale.SaleType.PRESENCIAL,
			'discount': '0.00',
			'surcharge': '0.00',
			'indicador_presenca': '1',
			'modalidade_frete': '9',
			'forma_pagamento_sefaz': '01',
			'commission_rate': '0',
			'items-TOTAL_FORMS': '1',
			'items-INITIAL_FORMS': '0',
			'items-MIN_NUM_FORMS': '1',
			'items-MAX_NUM_FORMS': '1000',
			'items-0-product': str(self.product.pk),
			'items-0-quantity': '2',
			'items-0-unit_price': '25.00',
			'items-0-discount': '0.00',
		}
		payload.update(extra)
		return payload

	def test_main_save_respects_draft_status(self):
		response = self.client.post(
			reverse('sale_create'),
			self._payload(Sale.Status.RASCUNHO),
		)

		self.assertEqual(response.status_code, 302)
		sale = Sale.objects.get()
		self.assertEqual(sale.status, Sale.Status.RASCUNHO)
		self.assertTrue(sale.can_be_edited())
		self.assertFalse(sale.stock_reduced)
		self.assertFalse(hasattr(sale, 'billing'))
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, Decimal('10.0000'))

	def test_sale_accepts_repeated_product_as_independent_lines(self):
		payload = self._payload(Sale.Status.RASCUNHO)
		payload.update({
			'items-TOTAL_FORMS': '2',
			'items-0-quantity': '1',
			'items-1-product': str(self.product.pk),
			'items-1-quantity': '3',
			'items-1-unit_price': '25.00',
			'items-1-discount': '5.00',
		})

		response = self.client.post(reverse('sale_create'), payload)

		self.assertEqual(response.status_code, 302)
		sale = Sale.objects.get()
		self.assertEqual(sale.items.count(), 2)
		self.assertEqual(
			list(sale.items.order_by('pk').values_list('quantity', flat=True)),
			[Decimal('1.00'), Decimal('3.00')],
		)
		self.assertEqual(sale.total_amount, Decimal('95.00'))

	def test_sale_form_receives_repeated_item_setting(self):
		settings = SaleSettings.get()
		settings.repeated_item_behavior = SaleSettings.RepeatedItemBehavior.SUM_QUANTITY
		settings.save(update_fields=['repeated_item_behavior'])

		response = self.client.get(reverse('sale_create'))

		self.assertEqual(response.context['repeated_item_behavior'], 'SUM_QUANTITY')
		self.assertContains(response, "const REPEATED_ITEM_BEHAVIOR = 'SUM_QUANTITY'")

	def test_repeated_item_setting_defaults_to_separate_and_can_be_changed(self):
		settings = SaleSettings.get()
		self.assertEqual(
			settings.repeated_item_behavior,
			SaleSettings.RepeatedItemBehavior.SEPARATE_LINES,
		)

		response = self.client.post(reverse('sale_settings'), {
			'billing_trigger_status': SaleSettings.BillingTrigger.FINALIZADA,
			'repeated_item_behavior': SaleSettings.RepeatedItemBehavior.SUM_QUANTITY,
		}, follow=True)

		self.assertRedirects(response, reverse('sale_settings'))
		self.assertContains(response, 'Configurações de vendas salvas com sucesso.', count=1)
		settings.refresh_from_db()
		self.assertEqual(
			settings.repeated_item_behavior,
			SaleSettings.RepeatedItemBehavior.SUM_QUANTITY,
		)

	def test_save_as_draft_overrides_selected_status(self):
		self.client.post(
			reverse('sale_create'),
			self._payload(Sale.Status.PRONTO, save_as_draft='1'),
		)

		sale = Sale.objects.get()
		self.assertEqual(sale.status, Sale.Status.RASCUNHO)
		self.assertFalse(sale.stock_reduced)

	def test_non_draft_status_is_preserved_and_reduces_stock(self):
		self.client.post(
			reverse('sale_create'),
			self._payload(Sale.Status.PRONTO),
		)

		sale = Sale.objects.get()
		self.assertEqual(sale.status, Sale.Status.PRONTO)
		self.assertTrue(sale.stock_reduced)
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, Decimal('8.0000'))

	def test_editing_back_to_draft_restores_stock(self):
		sale = Sale.objects.create(user=self.user, status=Sale.Status.PRONTO, stock_reduced=True)
		item = SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=Decimal('2'),
			unit_price=Decimal('25.00'),
		)
		self.product.current_stock = Decimal('8.0000')
		self.product.save(update_fields=['current_stock'])
		payload = self._payload(Sale.Status.RASCUNHO)
		payload.update({'items-INITIAL_FORMS': '1', 'items-0-id': str(item.pk)})

		response = self.client.post(reverse('sale_detail', args=[sale.number]), payload)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('sale_list'))
		sale.refresh_from_db()
		self.assertEqual(sale.status, Sale.Status.RASCUNHO)
		self.assertFalse(sale.stock_reduced)
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, Decimal('10.0000'))

	def test_cancelled_is_not_an_editable_form_choice(self):
		choices = dict(SaleForm().fields['status'].choices)
		self.assertNotIn(Sale.Status.CANCELADO, choices)

	def test_sale_type_is_saved_and_can_be_edited(self):
		self.client.post(
			reverse('sale_create'),
			self._payload(Sale.Status.RASCUNHO, sale_type=Sale.SaleType.DISTANCIA),
		)
		sale = Sale.objects.get()
		self.assertEqual(sale.sale_type, Sale.SaleType.DISTANCIA)

		item = sale.items.get()
		payload = self._payload(Sale.Status.RASCUNHO, sale_type=Sale.SaleType.PRESENCIAL)
		payload.update({'items-INITIAL_FORMS': '1', 'items-0-id': str(item.pk)})
		self.client.post(reverse('sale_detail', args=[sale.number]), payload)

		sale.refresh_from_db()
		self.assertEqual(sale.sale_type, Sale.SaleType.PRESENCIAL)

	def test_duplicate_copies_sale_type(self):
		sale = Sale.objects.create(
			user=self.user,
			status=Sale.Status.RASCUNHO,
			sale_type=Sale.SaleType.DISTANCIA,
		)
		SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=Decimal('1'),
			unit_price=Decimal('25.00'),
		)

		response = self.client.post(reverse('sale_duplicate', args=[sale.number]))

		self.assertEqual(response.status_code, 302)
		duplicate = Sale.objects.exclude(pk=sale.pk).get()
		self.assertEqual(duplicate.sale_type, Sale.SaleType.DISTANCIA)


class SaleBillingStatusTransitionTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='signal-venda', password='x')

	@patch('services.signals.create_billing_for_sale')
	def test_billing_runs_only_when_entering_configured_status(self, create_billing):
		create_billing.return_value = None
		SaleSettings.objects.create(billing_trigger_status=SaleSettings.BillingTrigger.PRONTO)
		sale = Sale.objects.create(user=self.user, status=Sale.Status.RASCUNHO)

		sale.status = Sale.Status.PRONTO
		sale.save()
		sale.save()

		create_billing.assert_called_once()

	@patch('services.signals.create_billing_for_sale')
	def test_manual_setting_never_creates_billing(self, create_billing):
		SaleSettings.objects.create(billing_trigger_status=SaleSettings.BillingTrigger.MANUAL)
		sale = Sale.objects.create(user=self.user, status=Sale.Status.RASCUNHO)

		sale.status = Sale.Status.FINALIZADA
		sale.save()

		create_billing.assert_not_called()
class PosCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='caixa', password='test', role=User.Roles.MANAGER, phone='')
        self.register = CashRegister.objects.create(code='CX01', name='Caixa principal')
        self.session = CashSession.objects.create(register=self.register, operator=self.user, opening_amount=Decimal('50'))
        self.product = Product.objects.create(name='Produto PDV', code='PDV-1', default_unit_price=Decimal('10'), current_stock=Decimal('1'))
        self.cash = PaymentMethod.objects.create(descricao='Dinheiro', tipo_provedor='DINHEIRO', codigo_sefaz='01')
        self.client.force_login(self.user)

    def _payload(self, **changes):
        payload = {
            'session_id': self.session.pk, 'action': 'finalize', 'discount': '0', 'surcharge': '0',
            'items': [{'product_id': self.product.pk, 'quantity': '2', 'discount': '0'}],
            'payments': [{'method_id': self.cash.pk, 'amount': '20', 'tendered': '30'}],
        }
        payload.update(changes)
        return payload

    def test_finalize_allows_negative_stock_and_registers_change(self):
        response = self.client.post(reverse('pos_save_sale'), data=json.dumps(self._payload()), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        sale = Sale.objects.get(number=response.json()['number'])
        self.assertEqual(sale.origin, Sale.Origin.POS)
        self.assertEqual(sale.status, Sale.Status.FINALIZADA)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('-1'))
        payment = sale.payments.get()
        self.assertEqual(payment.change_amount, Decimal('10'))
        self.assertEqual(payment.amount_tendered, Decimal('30'))
        self.assertEqual(sale.cash_movements.get().amount, Decimal('20'))
        self.assertEqual(sale.billing.status, Billing.Status.PAGO)

    def test_rejects_payment_total_different_from_sale(self):
        payload = self._payload(payments=[{'method_id': self.cash.pk, 'amount': '19', 'tendered': '19'}])
        response = self.client.post(reverse('pos_save_sale'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sale.objects.filter(origin=Sale.Origin.POS).exists())

    def test_suspend_does_not_reduce_stock_or_create_billing(self):
        payload = self._payload(action='suspend', payments=[])
        response = self.client.post(reverse('pos_save_sale'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        sale = Sale.objects.get(number=response.json()['number'])
        self.assertEqual(sale.status, Sale.Status.RASCUNHO)
        self.assertFalse(hasattr(sale, 'billing'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('1'))

    def test_cancel_pending_pos_sale_keeps_audit_and_does_not_change_stock(self):
        suspended = self.client.post(
            reverse('pos_save_sale'),
            data=json.dumps(self._payload(action='suspend', payments=[])),
            content_type='application/json',
        )
        sale = Sale.objects.get(pk=suspended.json()['sale_id'])

        response = self.client.post(reverse('pos_cancel_sale', args=[sale.pk]))

        self.assertEqual(response.status_code, 200, response.content)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELADO)
        self.assertEqual(sale.items.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('1'))

        close_response = self.client.post(reverse('pos_close'), {'session_id': self.session.pk})
        self.assertRedirects(close_response, reverse('pos_home'))
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.PENDING_APPROVAL)

    def test_cancel_pos_sale_rejects_sale_from_another_operator(self):
        other = User.objects.create_user(username='outro-caixa', password='test', role=User.Roles.MANAGER, phone='')
        other_session = CashSession.objects.create(register=self.register, operator=other)
        sale = Sale.objects.create(
            user=other, origin=Sale.Origin.POS, cash_session=other_session,
            status=Sale.Status.RASCUNHO,
        )

        response = self.client.post(reverse('pos_cancel_sale', args=[sale.pk]))

        self.assertEqual(response.status_code, 404)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.RASCUNHO)

    def test_pos_preserves_repeated_product_as_independent_lines(self):
        payload = self._payload(
            action='suspend',
            payments=[],
            items=[
                {'product_id': self.product.pk, 'quantity': '1', 'discount': '0'},
                {'product_id': self.product.pk, 'quantity': '2', 'discount': '1'},
            ],
        )

        response = self.client.post(
            reverse('pos_save_sale'), data=json.dumps(payload), content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        sale = Sale.objects.get(number=response.json()['number'])
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.total_amount, Decimal('29.00'))

    def test_pos_receives_repeated_item_setting(self):
        settings = SaleSettings.get()
        settings.repeated_item_behavior = SaleSettings.RepeatedItemBehavior.SUM_QUANTITY
        settings.save(update_fields=['repeated_item_behavior'])

        response = self.client.get(reverse('pos_home'))

        self.assertEqual(response.context['repeated_item_behavior'], 'SUM_QUANTITY')
        self.assertContains(response, "const REPEATED_ITEM_BEHAVIOR='SUM_QUANTITY'")

    def test_close_is_blocked_with_pending_cart(self):
        self.client.post(reverse('pos_save_sale'), data=json.dumps(self._payload(action='suspend', payments=[])), content_type='application/json')
        response = self.client.post(reverse('pos_close'), {'session_id': self.session.pk})
        self.assertRedirects(response, reverse('pos_home'))
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.OPEN)

    def test_close_sends_open_session_to_approval(self):
        response = self.client.post(reverse('pos_close'), {
            'session_id': self.session.pk,
            'notes': 'Fechamento do turno',
        })

        self.assertRedirects(response, reverse('pos_home'))
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.PENDING_APPROVAL)
        self.assertEqual(self.session.closing_notes, 'Fechamento do turno')
        self.assertIsNotNone(self.session.closed_at)

    def test_pos_renders_searchable_client_picker(self):
        response = self.client.get(reverse('pos_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="client-search"')
        self.assertContains(response, reverse('client_create'))

    def test_client_api_searches_name_cpf_and_cnpj(self):
        Client.objects.create(name='Maria da Silva', client_type='PF', cpf='123.456.789-00')
        Client.objects.create(name='Empresa Exemplo', trade_name='Loja Central', client_type='PJ', cnpj='12.345.678/0001-90')

        by_name = self.client.get(reverse('api_get_clients'), {'q': 'Maria'}).json()
        by_cpf = self.client.get(reverse('api_get_clients'), {'q': '789-00'}).json()
        by_cnpj = self.client.get(reverse('api_get_clients'), {'q': '678/0001'}).json()

        self.assertEqual(by_name[0]['name'], 'Maria da Silva')
        self.assertEqual(by_cpf[0]['document'], '123.456.789-00')
        self.assertEqual(by_cnpj[0]['name'], 'Loja Central')

    def test_sessions_page_renders_metrics_and_divergence(self):
        self.session.status = CashSession.Status.PENDING_APPROVAL
        self.session.closed_at = timezone.now()
        self.session.save(update_fields=['status', 'closed_at'])
        CashClosingCount.objects.create(
            session=self.session, payment_method=self.cash,
            expected_amount=Decimal('50'), declared_amount=Decimal('45'), difference=Decimal('-5'),
        )

        response = self.client.get(reverse('pos_sessions'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sessões recentes')
        self.assertContains(response, 'Com divergência')
        self.assertEqual(response.context['stats']['pending'], 1)
        self.assertEqual(response.context['stats']['divergent'], 1)
        self.assertEqual(response.context['sessions'][0].total_difference, Decimal('-5'))
        self.assertContains(response, 'type="hidden" name="action" value="approve"')
        self.assertContains(response, 'type="hidden" name="action" value="reopen"')

    def test_sessions_page_requires_report_permission(self):
        collaborator = User.objects.create_user(username='sem-relatorio', password='test', phone='')
        self.client.force_login(collaborator)
        response = self.client.get(reverse('pos_sessions'))
        self.assertEqual(response.status_code, 403)

    def test_approve_closing_updates_status_and_available_actions(self):
        self.session.status = CashSession.Status.PENDING_APPROVAL
        self.session.closed_at = timezone.now()
        self.session.save(update_fields=['status', 'closed_at'])

        response = self.client.post(
            reverse('pos_session_action', args=[self.session.pk]),
            {'action': 'approve'}, follow=True,
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.CLOSED)
        self.assertEqual(self.session.approved_by, self.user)
        self.assertContains(response, 'Reabrir')
        self.assertNotContains(response, '>Aprovar</button>')

    def test_reopen_returns_session_to_open_and_removes_actions(self):
        self.session.status = CashSession.Status.PENDING_APPROVAL
        self.session.closed_at = timezone.now()
        self.session.save(update_fields=['status', 'closed_at'])
        CashClosingCount.objects.create(
            session=self.session, payment_method=self.cash,
            expected_amount=Decimal('50'), declared_amount=Decimal('50'), difference=Decimal('0'),
        )

        response = self.client.post(
            reverse('pos_session_action', args=[self.session.pk]),
            {'action': 'reopen'}, follow=True,
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.OPEN)
        self.assertIsNone(self.session.closed_at)
        self.assertFalse(self.session.closing_counts.exists())
        self.assertContains(response, 'Sem ações disponíveis')

    def test_reopen_is_blocked_when_same_operator_has_another_open_session(self):
        self.session.status = CashSession.Status.CLOSED
        self.session.closed_at = timezone.now()
        self.session.save(update_fields=['status', 'closed_at'])
        other_session = CashSession.objects.create(
            register=self.register, operator=self.user, opening_amount=Decimal('0'),
        )

        response = self.client.post(
            reverse('pos_session_action', args=[self.session.pk]),
            {'action': 'reopen'}, follow=True,
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, CashSession.Status.CLOSED)
        self.assertContains(response, 'já possui outra sessão aberta neste caixa')
        self.assertEqual(other_session.status, CashSession.Status.OPEN)
