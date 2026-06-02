import hashlib
import hmac
from django.test import TestCase, override_settings
from django.utils import timezone
from integracoes.views import (
    _build_budget_response_label,
    _is_chatwoot_client_budget_reply,
    _is_chatwoot_outgoing_message,
    _resolve_order_status_from_budget_decision,
)
from services.models import ServiceOrder


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
