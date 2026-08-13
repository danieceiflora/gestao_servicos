import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from integracoes.views import (
    _build_budget_response_label,
    _is_chatwoot_client_budget_reply,
    _is_chatwoot_outgoing_message,
    _resolve_order_status_from_budget_decision,
)
from integracoes.models import PlatformSubscription, PlatformInvoice
from services.models import ServiceOrder, User


@override_settings(WEBHOOK_SHARED_SECRET='test-shared-secret')
class WebhooksAuthTests(TestCase):
    def _build_signature(self, body, timestamp):
        message = f"{timestamp}.".encode('utf-8') + body
        return "sha256=" + hmac.new(
            b'test-shared-secret',
            message,
            hashlib.sha256,
        ).hexdigest()

    def test_accepts_valid_chatwoot_signature(self):
        body = b'{"content":"teste"}'
        timestamp = str(int(timezone.now().timestamp()))
        signature = self._build_signature(body, timestamp)

        response = self.client.post(
            '/webhooks/',
            data=body,
            content_type='application/json',
            HTTP_X_CHATWOOT_TIMESTAMP=timestamp,
            HTTP_X_CHATWOOT_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)

    def test_rejects_when_signature_is_invalid(self):
        body = b'{"content":"teste"}'
        timestamp = str(int(timezone.now().timestamp()))

        response = self.client.post(
            '/webhooks/',
            data=body,
            content_type='application/json',
            HTTP_X_CHATWOOT_TIMESTAMP=timestamp,
            HTTP_X_CHATWOOT_SIGNATURE='sha256=invalid',
        )

        self.assertEqual(response.status_code, 401)

    def test_rejects_when_headers_are_missing(self):
        response = self.client.post(
            '/webhooks/',
            data=b'{"content":"teste"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 401)

    def test_rejects_when_timestamp_is_expired(self):
        body = b'{"content":"teste"}'
        timestamp = str(int(timezone.now().timestamp()) - 600)
        signature = self._build_signature(body, timestamp)

        response = self.client.post(
            '/webhooks/',
            data=body,
            content_type='application/json',
            HTTP_X_CHATWOOT_TIMESTAMP=timestamp,
            HTTP_X_CHATWOOT_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 401)


class BudgetResponseLabelTests(TestCase):
    def test_builds_rejected_label(self):
        self.assertEqual(_build_budget_response_label(False, None), "Reprovado")

    def test_builds_approved_card_label(self):
        self.assertEqual(_build_budget_response_label(True, "CREDIT_CARD"), "Aprovado - Cartão")

    def test_builds_approved_pix_label(self):
        self.assertEqual(_build_budget_response_label(True, "PIX"), "Aprovado - Pix")

    def test_sets_order_status_when_budget_approved(self):
        self.assertEqual(
            _resolve_order_status_from_budget_decision(True),
            ServiceOrder.Status.APROVADO_AGUARDANDO_AGENDAMENTO
        )

    def test_sets_order_status_when_budget_rejected(self):
        self.assertEqual(
            _resolve_order_status_from_budget_decision(False),
            ServiceOrder.Status.REPROVADO_PELO_CLIENTE
        )


class ChatwootReplyFilterTests(TestCase):
    def test_ignores_outgoing_message(self):
        payload = {
            "event": "message_created",
            "message_type": "outgoing",
            "sender": {"type": "user"},
            "content": "Orçamento enviado",
        }
        self.assertFalse(_is_chatwoot_client_budget_reply(payload))

    def test_accepts_incoming_contact_message(self):
        payload = {
            "event": "message_created",
            "message_type": "incoming",
            "sender": {"type": "contact"},
            "content": "Aprovado - Pix",
        }
        self.assertTrue(_is_chatwoot_client_budget_reply(payload))

    def test_detects_outgoing_message(self):
        payload = {
            "event": "message_created",
            "message_type": 3,
            "content_attributes": {"template_name": "enviar_orcamento_v1"},
        }
        self.assertTrue(_is_chatwoot_outgoing_message(payload))

    def test_ignores_non_outgoing_message(self):
        payload = {
            "event": "message_created",
            "message_type": "incoming",
            "content_attributes": {"template_name": "boas_vindas"},
        }
        self.assertFalse(_is_chatwoot_outgoing_message(payload))


class PlatformSubscriptionModelTests(TestCase):
    def test_load_always_returns_pk_1(self):
        obj = PlatformSubscription.load()
        self.assertEqual(obj.pk, 1)
        self.assertEqual(PlatformSubscription.objects.count(), 1)

        obj2 = PlatformSubscription.load()
        self.assertEqual(obj2.pk, 1)
        self.assertEqual(PlatformSubscription.objects.count(), 1)

    def test_default_status_is_nao_criada(self):
        obj = PlatformSubscription.load()
        self.assertEqual(obj.status, PlatformSubscription.Status.NAO_CRIADA)

    def test_estimated_next_due_dates_monthly(self):
        import datetime as dt
        obj = PlatformSubscription.load()
        obj.cycle = 'MONTHLY'
        obj.next_due_date = dt.date(2026, 8, 8)
        obj.save()

        dates = obj.estimated_next_due_dates(count=3)
        self.assertEqual(dates, [dt.date(2026, 9, 8), dt.date(2026, 10, 8), dt.date(2026, 11, 8)])

    def test_estimated_next_due_dates_empty_without_due_date(self):
        obj = PlatformSubscription.load()
        obj.cycle = 'MONTHLY'
        self.assertEqual(obj.estimated_next_due_dates(), [])


# O webhook da assinatura recorrente não tem view/rota própria — é roteado
# pela mesma pagamentos:asaas_webhook (única URL cadastrada no painel Asaas).
# Ver AsaasWebhookPlatformSubscriptionRoutingTests em pagamentos/tests.py.


class PlatformSubscriptionStatusViewTests(TestCase):
    def test_non_manager_is_redirected(self):
        user = User.objects.create_user(username='colaborador', password='x', role=User.Roles.COLLABORATOR)
        self.client.force_login(user)
        response = self.client.get(reverse('integracoes:platform_subscription_status'))
        self.assertNotEqual(response.status_code, 200)

    def test_manager_can_view(self):
        user = User.objects.create_user(username='gestor', password='x', role=User.Roles.ADMIN)
        self.client.force_login(user)
        response = self.client.get(reverse('integracoes:platform_subscription_status'))
        self.assertEqual(response.status_code, 200)


class PlatformInvoiceModelTests(TestCase):
    @override_settings(PLATFORM_SUBSCRIPTION_VALUE_CENTS=9900)
    def test_ensure_six_month_plan_creates_six_invoices_due_on_10th(self):
        PlatformInvoice.ensure_six_month_plan()
        invoices = list(PlatformInvoice.objects.order_by('due_date'))

        self.assertEqual(len(invoices), 6)
        for invoice in invoices:
            self.assertEqual(invoice.due_date.day, 10)
            self.assertEqual(invoice.value_cents, 9900)
            self.assertEqual(invoice.status, PlatformInvoice.Status.PENDENTE)

        months = [(inv.due_date.year, inv.due_date.month) for inv in invoices]
        self.assertEqual(len(set(months)), 6)
        for (y1, m1), (y2, m2) in zip(months, months[1:]):
            self.assertEqual((y2 - y1) * 12 + (m2 - m1), 1)

    def test_ensure_six_month_plan_is_idempotent(self):
        PlatformInvoice.ensure_six_month_plan()
        PlatformInvoice.ensure_six_month_plan()
        self.assertEqual(PlatformInvoice.objects.count(), 6)

    def test_is_overdue(self):
        import datetime as dt
        past = PlatformInvoice.objects.create(due_date=dt.date(2020, 1, 10), value_cents=9900)
        future = PlatformInvoice.objects.create(due_date=dt.date(2099, 1, 10), value_cents=9900)
        self.assertTrue(past.is_overdue)
        self.assertFalse(future.is_overdue)

        past.status = PlatformInvoice.Status.PAGA
        self.assertFalse(past.is_overdue)


class PlatformInvoiceListViewTests(TestCase):
    def test_non_manager_is_redirected(self):
        user = User.objects.create_user(username='colaborador2', password='x', role=User.Roles.COLLABORATOR)
        self.client.force_login(user)
        response = self.client.get(reverse('integracoes:platform_invoice_list'))
        self.assertNotEqual(response.status_code, 200)

    def test_manager_view_seeds_six_month_plan(self):
        user = User.objects.create_user(username='gestor2', password='x', role=User.Roles.ADMIN)
        self.client.force_login(user)

        self.assertEqual(PlatformInvoice.objects.count(), 0)
        response = self.client.get(reverse('integracoes:platform_invoice_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PlatformInvoice.objects.count(), 6)


class PlatformInvoiceGeneratePixViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='gestor3', password='x', role=User.Roles.ADMIN)
        self.client.force_login(self.user)
        import datetime as dt
        self.invoice = PlatformInvoice.objects.create(due_date=dt.date(2026, 8, 10), value_cents=9900)

    @patch('integracoes.views.AsaasGateway')
    def test_generate_pix_updates_invoice(self, mock_gateway_cls):
        from pagamentos.gateways.base import ChargeResult
        mock_gateway = mock_gateway_cls.return_value
        mock_gateway.create_charge.return_value = ChargeResult(
            external_id='pay_abc',
            status='PENDING',
            method='PIX',
            amount=Decimal('99.00'),
            due_date=self.invoice.due_date,
            pix_qrcode='base64img==',
            pix_copy_paste='copia-e-cola-xyz',
        )

        response = self.client.post(reverse('integracoes:platform_invoice_generate_pix', args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 302)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.asaas_charge_id, 'pay_abc')
        self.assertEqual(self.invoice.qr_code, 'copia-e-cola-xyz')
        self.assertEqual(self.invoice.qr_code_base64, 'base64img==')
        self.assertEqual(self.invoice.status, PlatformInvoice.Status.AGUARDANDO_PAGAMENTO)

    @patch('integracoes.views.AsaasGateway')
    def test_generate_pix_updates_existing_charge(self, mock_gateway_cls):
        from pagamentos.gateways.base import ChargeResult
        self.invoice.asaas_charge_id = 'pay_existing'
        self.invoice.save()

        mock_gateway = mock_gateway_cls.return_value
        mock_gateway.update_charge.return_value = ChargeResult(
            external_id='pay_existing',
            status='PENDING',
            method='PIX',
            amount=Decimal('99.00'),
            due_date=self.invoice.due_date,
            pix_qrcode='updated_base64',
            pix_copy_paste='updated_pix_code',
        )

        response = self.client.post(reverse('integracoes:platform_invoice_generate_pix', args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 302)

        mock_gateway.update_charge.assert_called_once()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.qr_code, 'updated_pix_code')

    @patch('integracoes.views.AsaasGateway')
    def test_generate_pix_uses_today_if_overdue(self, mock_gateway_cls):
        import datetime as dt
        from core.tz_utils import local_today
        from pagamentos.gateways.base import ChargeResult

        past_invoice = PlatformInvoice.objects.create(due_date=dt.date(2020, 1, 1), value_cents=9900)
        mock_gateway = mock_gateway_cls.return_value
        mock_gateway.create_charge.return_value = ChargeResult(
            external_id='pay_past',
            status='PENDING',
            method='PIX',
            amount=Decimal('99.00'),
            due_date=local_today(),
            pix_qrcode='base64',
            pix_copy_paste='copiapaste',
        )

        response = self.client.post(reverse('integracoes:platform_invoice_generate_pix', args=[past_invoice.pk]))
        self.assertEqual(response.status_code, 302)

        mock_gateway.create_charge.assert_called_once()
        charge_data = mock_gateway.create_charge.call_args[0][0]
        self.assertEqual(charge_data.due_date, local_today())


class CollectionSequenceBillingSourceTests(TestCase):
    def test_create_sequence_with_billing_source(self):
        from integracoes.models import CollectionSequence
        seq = CollectionSequence.objects.create(
            name="Régua Somente Vendas",
            billing_source=CollectionSequence.BillingSource.VENDA,
        )
        self.assertEqual(seq.billing_source, 'VENDA')

    def test_sequence_form_post_saves_billing_source(self):
        from integracoes.models import CollectionSequence
        user = User.objects.create_superuser(username='admin_seq', password='x')
        self.client.force_login(user)

        response = self.client.post(reverse('integracoes:collection_sequence_create'), {
            'name': 'Régua de Serviços',
            'billing_source': 'SERVICO',
            'start_after_days_overdue': 1,
            'stop_after_days_overdue': 30,
            'max_occurrences': 2,
            'min_interval_days': 5,
        })
        self.assertEqual(response.status_code, 302)
        seq = CollectionSequence.objects.get(name='Régua de Serviços')
        self.assertEqual(seq.billing_source, 'SERVICO')


