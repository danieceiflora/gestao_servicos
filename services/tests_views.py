from django.test import TestCase, Client
from django.urls import reverse
from .models import Client as ServiceClient, Property, ServiceOrder, User

class ServiceOrderListViewTest(TestCase):
    def setUp(self):
        self.client_obj = Client()
        self.user = User.objects.create_user(
            username='admin',
            password='password123',
            role=User.Roles.ADMIN
        )
        self.client_obj.login(username='admin', password='password123')
        
        self.service_client = ServiceClient.objects.create(name="João Silva")
        self.property = Property.objects.create(
            client=self.service_client,
            address="Rua das Flores",
            number="123",
            neighborhood="Centro",
            city="São Paulo",
            state="SP"
        )
        self.order1 = ServiceOrder.objects.create(
            client_property=self.property,
            description="Service 1"
        )
        
        self.service_client2 = ServiceClient.objects.create(name="Maria Souza")
        self.property2 = Property.objects.create(
            client=self.service_client2,
            address="Avenida Paulista",
            number="1000",
            neighborhood="Bela Vista",
            city="São Paulo",
            state="SP"
        )
        self.order2 = ServiceOrder.objects.create(
            client_property=self.property2,
            description="Service 2"
        )

    def test_view_url_exists_at_desired_location(self):
        response = self.client_obj.get('/ordens/')
        self.assertEqual(response.status_code, 200)

    def test_view_accessible_by_name(self):
        response = self.client_obj.get(reverse('service_order_list'))
        self.assertEqual(response.status_code, 200)

    def test_search_by_client_name(self):
        response = self.client_obj.get(reverse('service_order_list'), {'q': 'João'})
        self.assertEqual(len(response.context['orders']), 1)
        self.assertEqual(response.context['orders'][0], self.order1)

    def test_search_by_address(self):
        response = self.client_obj.get(reverse('service_order_list'), {'q': 'Paulista'})
        self.assertEqual(len(response.context['orders']), 1)
        self.assertEqual(response.context['orders'][0], self.order2)

    def test_search_no_results(self):
        response = self.client_obj.get(reverse('service_order_list'), {'q': 'Nonexistent'})
        self.assertEqual(len(response.context['orders']), 0)
        self.assertContains(response, "Nenhuma ordem encontrada")
