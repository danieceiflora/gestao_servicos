import hashlib
import hmac
import json
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from integracoes.views import (
    _build_budget_response_label,
    _is_chatwoot_client_budget_reply,
    _is_chatwoot_outgoing_message,
    _resolve_order_status_from_budget_decision,
)
from integracoes.models import PlatformSubscription, PlatformSubscriptionEvent
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
            status=ServiceOrder.Status.APROVADO_AGUARDANDO_AGENDAMENTO
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


@override_settings(ASAAS_MASTER_WEBHOOK_TOKEN='test-token-123')
class PlatformSubscriptionWebhookViewTests(TestCase):
    def setUp(self):
        self.subscription = PlatformSubscription.load()
        self.subscription.status = PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO
        self.subscription.save()

    def _post(self, token, event, payment_extra=None):
        payload = {'event': event, 'payment': {'id': 'pay_1', **(payment_extra or {})}}
        kwargs = {'HTTP_ASAAS_ACCESS_TOKEN': token} if token is not None else {}
        return self.client.post(
            reverse('integracoes:platform_subscription_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
            **kwargs,
        )

    def test_rejects_wrong_token(self):
        response = self._post('wrong-token', 'PAYMENT_RECEIVED')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(PlatformSubscriptionEvent.objects.count(), 0)

    def test_paid_event_activates_subscription(self):
        response = self._post('test-token-123', 'PAYMENT_RECEIVED')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.ATIVA)

        event = PlatformSubscriptionEvent.objects.get()
        self.assertEqual(event.mapped_status, PlatformSubscription.Status.ATIVA)
        self.assertEqual(event.charge_id, 'pay_1')

    def test_overdue_event_marks_subscription_atrasada(self):
        response = self._post('test-token-123', 'PAYMENT_OVERDUE')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.ATRASADA)

    def test_unrecognized_event_persists_history_without_changing_status(self):
        response = self._post('test-token-123', 'PAYMENT_SOMETHING_NEW')
        self.assertEqual(response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO)

        event = PlatformSubscriptionEvent.objects.get()
        self.assertEqual(event.mapped_status, '')
        self.assertIn('não reconhecido', event.notes)

    def test_malformed_body_still_persists_an_event(self):
        response = self.client.post(
            reverse('integracoes:platform_subscription_webhook'),
            data=b'not-json',
            content_type='application/json',
            HTTP_ASAAS_ACCESS_TOKEN='test-token-123',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PlatformSubscriptionEvent.objects.count(), 1)


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
