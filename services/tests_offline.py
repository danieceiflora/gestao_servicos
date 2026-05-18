from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Professional, ServiceOrder, ServiceOrderTask, Property, Client as ServiceClient
from django.utils import timezone

User = get_user_model()

class OfflineAPITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tech1', password='password123', role='COLLABORATOR')
        self.professional = Professional.objects.create(user=self.user, name='Technician One', phone='123456')
        
        self.client_obj = ServiceClient.objects.create(name='John Doe')
        self.property_obj = Property.objects.create(client=self.client_obj, address='Street 1', neighborhood='Neighborhood 1', city='City', state='ST')
        
        self.order = ServiceOrder.objects.create(client_property=self.property_obj)
        self.task = ServiceOrderTask.objects.create(
            service_order=self.order,
            task_type='EXECUTION',
            scheduled_at=timezone.now()
        )
        self.task.team_members.create(professional=self.professional)

    def test_bootstrap_requires_login(self):
        client = Client()
        response = client.get(reverse('api_tecnico_bootstrap'))
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_bootstrap_returns_data(self):
        client = Client()
        client.login(username='tech1', password='password123')
        response = client.get(reverse('api_tecnico_bootstrap'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('sync_token', data)
        self.assertIn('tasks', data)
        self.assertEqual(len(data['tasks']), 1)
        self.assertEqual(data['tasks'][0]['id'], str(self.task.id))
        self.assertIn('orders', data)
        self.assertIn('clients', data)
        self.assertIn('properties', data)
        self.assertEqual(data['technician']['name'], 'Technician One')

    def test_offline_app_renders(self):
        client = Client()
        client.login(username='tech1', password='password123')
        response = client.get(reverse('equipe_offline_app'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'offline-app-root')
