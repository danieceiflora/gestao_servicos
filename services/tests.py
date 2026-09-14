from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from integracoes.models import SystemConfig
from .models import (
	Client, Professional, Property, ServiceItem, ServiceOrder,
	ServiceOrderTask, ServiceOrderTeam, User,
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
