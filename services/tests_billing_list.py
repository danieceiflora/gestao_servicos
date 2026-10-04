from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.tz_utils import local_today, safe_make_aware
from services.models import Billing, Client, Installment, User


class BillingListTests(TestCase):
    def setUp(self):
        user = User.objects.create_superuser(username='billing-list-admin', password='secret')
        self.client.force_login(user)
        self.customer = Client.objects.create(name='Cliente Lista')
        self.today = local_today()
        self.url = reverse('billing_list')

    def make_billing(self, days_ago, status=Billing.Status.PENDENTE):
        billing = Billing.objects.create(
            client=self.customer, total_amount=Decimal('100.00'), status=status,
        )
        created = safe_make_aware(datetime.combine(self.today - timedelta(days=days_ago), time(12)))
        Billing.objects.filter(pk=billing.pk).update(created_at=created)
        return billing

    def test_default_period_includes_today_and_previous_six_days(self):
        today = self.make_billing(0)
        six_days_ago = self.make_billing(6)
        self.make_billing(7)
        self.make_billing(-1)

        response = self.client.get(self.url)

        self.assertEqual(
            {billing.pk for billing in response.context['billings']},
            {today.pk, six_days_ago.pk},
        )
        self.assertEqual(response.context['date_from'], (self.today - timedelta(days=6)).isoformat())
        self.assertEqual(response.context['date_to'], self.today.isoformat())

    def test_custom_and_unbounded_periods_combine_with_status_and_search(self):
        old_paid = self.make_billing(20, Billing.Status.PAGO)
        self.make_billing(20, Billing.Status.PENDENTE)
        self.make_billing(1, Billing.Status.PAGO)

        query = {
            'date_from': (self.today - timedelta(days=21)).isoformat(),
            'date_to': (self.today - timedelta(days=19)).isoformat(),
            'status': Billing.Status.PAGO,
            'q': str(old_paid.number),
        }
        response = self.client.get(self.url, query)
        self.assertEqual([billing.pk for billing in response.context['billings']], [old_paid.pk])
        self.assertIn(
            f'date_from={query["date_from"]}&amp;date_to={query["date_to"]}',
            response.content.decode(),
        )
        self.assertIn(
            f'?status=&amp;date_from={query["date_from"]}&amp;date_to={query["date_to"]}&amp;q={old_paid.number}',
            response.content.decode(),
        )

        response = self.client.get(self.url, {'date_from': '', 'date_to': ''})
        self.assertEqual(response.context['billings'].count(), 3)
        self.assertEqual(response.context['date_from'], '')
        self.assertEqual(response.context['date_to'], '')

        response = self.client.get(self.url, {
            'date_from': '', 'date_to': (self.today - timedelta(days=19)).isoformat(),
        })
        self.assertEqual(response.context['billings'].count(), 2)

    def test_discount_deadline_is_shown_on_desktop_and_mobile(self):
        billing = self.make_billing(0)
        deadline = self.today + timedelta(days=2)
        Installment.objects.create(
            billing=billing, installment_number=1, amount=Decimal('100.00'),
            due_date=self.today + timedelta(days=5), discount_type=Installment.DiscountType.FIXED,
            discount_value=Decimal('10.00'), discount_deadline=deadline,
        )

        response = self.client.get(self.url)

        self.assertContains(response, 'Vencimento com desconto', count=2)
        self.assertContains(response, deadline.strftime('%d/%m/%Y'), count=2)

    def test_reversed_period_shows_validation_message(self):
        self.make_billing(0)
        response = self.client.get(self.url, {
            'date_from': self.today.isoformat(),
            'date_to': (self.today - timedelta(days=1)).isoformat(),
        })
        self.assertContains(response, 'A data inicial não pode ser posterior à data final.')
        self.assertFalse(response.context['billings'].exists())
