from django.test import TestCase
from django.urls import reverse


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
