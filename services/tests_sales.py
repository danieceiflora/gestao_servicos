from django.test import TestCase, Client
from django.urls import reverse
from .models import Sale, SaleItem, Product, User, Client as ServiceClient
from decimal import Decimal

class SaleModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='seller',
            password='password123',
            role=User.Roles.COLLABORATOR
        )
        self.service_client = ServiceClient.objects.create(name="João Silva")
        self.product = Product.objects.create(
            name="Produto Teste",
            default_unit_price=Decimal('10.00'),
            current_stock=Decimal('100.00')
        )

    def test_sale_creation_sequential_number(self):
        sale1 = Sale.objects.create(user=self.user, client=self.service_client)
        sale2 = Sale.objects.create(user=self.user, client=self.service_client)
        
        self.assertEqual(sale1.number, 1001)
        self.assertEqual(sale2.number, 1002)

    def test_sale_item_subtotal(self):
        sale = Sale.objects.create(user=self.user, client=self.service_client)
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=Decimal('2.00'),
            unit_price=Decimal('10.00'),
            discount=Decimal('2.00')
        )
        self.assertEqual(item.subtotal, Decimal('18.00'))

    def test_sale_null_handling(self):
        sale = Sale.objects.create(
            user=self.user, 
            client=self.service_client,
            discount=None,
            surcharge=None
        )
        self.assertEqual(sale.discount, Decimal('0.00'))
        self.assertEqual(sale.surcharge, Decimal('0.00'))
