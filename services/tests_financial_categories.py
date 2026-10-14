from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .forms import ExpenseForm
from .models import Expense, ExpenseInstallment, FinancialCategory, RecurrenceRule, Supplier, User


class FinancialCategoryHierarchyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='category_admin', password='test-password')
        self.client.force_login(self.user)
        self.parent = FinancialCategory.objects.create(name='Operacional', category_type='SAIDA')
        self.child = FinancialCategory.objects.create(name='Transporte', parent=self.parent)

    def test_category_validation_and_protected_parent(self):
        self.assertEqual(str(self.child), 'Operacional / Transporte')
        self.assertEqual(self.child.category_type, 'SAIDA')

        with self.assertRaises(ValidationError):
            FinancialCategory.objects.create(name='Combustível', parent=self.child)

        self.parent.parent = self.child
        with self.assertRaises(ValidationError):
            self.parent.save()
        self.parent.parent = None

        self.parent.category_type = 'ENTRADA'
        with self.assertRaises(ValidationError):
            self.parent.save()
        self.parent.category_type = 'SAIDA'

        with self.assertRaises(ProtectedError):
            self.parent.delete()

    def test_admin_creates_subcategory_inline_with_parent_type(self):
        income = FinancialCategory.objects.create(name='Receitas', category_type='ENTRADA')
        response = self.client.post(
            reverse('admin:services_financialcategory_change', args=[income.pk]),
            {
                'name': income.name,
                'category_type': income.category_type,
                'parent': '',
                'subcategories-TOTAL_FORMS': '1',
                'subcategories-INITIAL_FORMS': '0',
                'subcategories-MIN_NUM_FORMS': '0',
                'subcategories-MAX_NUM_FORMS': '1000',
                'subcategories-0-name': 'Serviços',
                '_save': 'Salvar',
            },
        )
        self.assertEqual(response.status_code, 302, response.context.get('errors') if response.context else '')
        subcategory = income.subcategories.get(name='Serviços')
        self.assertEqual(subcategory.category_type, 'ENTRADA')

    def test_expense_form_uses_one_category_field_for_parent_or_child(self):
        other = FinancialCategory.objects.create(name='Administrativo', category_type='SAIDA')
        FinancialCategory.objects.create(name='Escritório', parent=other)
        supplier = Supplier.objects.create(name='Fornecedor de teste')
        form_data = {
            'supplier': supplier.pk,
            'category': self.child.pk,
            'description': 'Despesa de teste',
            'total_amount': '10.00',
            'issue_date': '2026-10-13',
            'installments_count': '1',
        }

        form = ExpenseForm(form_data)
        self.assertTrue(form.is_valid(), form.errors)
        expense = form.save()
        self.assertEqual(expense.category, self.child)

        edit_form = ExpenseForm(instance=expense)
        self.assertEqual(edit_form['category'].value(), self.child.pk)
        self.assertIn('data-parent-id="%s"' % self.parent.pk, str(edit_form['category']))

        form_data['category'] = self.parent.pk
        form = ExpenseForm(form_data, instance=expense)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().category, self.parent)

        form_data['category'] = ''
        form = ExpenseForm(form_data, instance=expense)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().category)

        form_data['category'] = '999999'
        self.assertFalse(ExpenseForm(form_data).is_valid())

        response = self.client.get(reverse('expense_create'))
        self.assertContains(response, 'data-category-picker')
        self.assertContains(response, 'financial-category-picker.js')

    def test_list_and_export_filter_parent_and_subcategory(self):
        other = FinancialCategory.objects.create(name='Administrativo', category_type='SAIDA')
        supplier = Supplier.objects.create(name='Fornecedor de teste')
        due_date = date.today() + timedelta(days=10)

        def installment(description, category, recurrence_rule=None):
            expense = Expense.objects.create(
                supplier=supplier, category=category, description=description,
                total_amount=Decimal('10.00'),
            )
            return ExpenseInstallment.objects.create(
                expense=expense, recurrence_rule=recurrence_rule,
                installment_number='1/1', amount=Decimal('10.00'), due_date=due_date,
            )

        direct = installment('Direta', self.parent)
        nested = installment('Filha', self.child)
        rule = RecurrenceRule.objects.create(
            supplier=supplier, category=self.child, description='Recorrente',
            amount=Decimal('10.00'), frequency='MENSAL', start_date=due_date,
        )
        recurring = installment('Outra categoria na despesa', other, rule)
        installment('Fora do grupo', other)

        response = self.client.get(reverse('expense_list'), {'category': self.parent.pk})
        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            {item.pk for item in response.context['installments']},
            {direct.pk, nested.pk, recurring.pk},
        )

        response = self.client.get(reverse('expense_list'), {'category': self.child.pk})
        self.assertSetEqual(
            {item.pk for item in response.context['installments']},
            {nested.pk, recurring.pk},
        )

        response = self.client.get(reverse('expense_installments_export'), {'category': self.parent.pk})
        self.assertEqual(response.status_code, 200)
        rows = list(load_workbook(BytesIO(response.content)).active.values)
        self.assertEqual(len(rows), 5)  # Cabeçalho, três lançamentos e total.
        self.assertSetEqual(
            {row[2] for row in rows[1:-1]},
            {'Direta', 'Filha', 'Recorrente'},
        )
        self.assertIn('Operacional / Transporte', [row[3] for row in rows[1:-1]])
