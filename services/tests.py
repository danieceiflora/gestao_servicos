from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch

from integracoes.models import SystemConfig
from .forms import SaleForm
from .models import (
	Client, Professional, Property, ServiceItem, ServiceOrder,
	ServiceOrderTask, ServiceOrderTeam, User, Product, Sale, SaleItem,
	SaleSettings,
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
