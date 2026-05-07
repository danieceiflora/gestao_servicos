import hashlib
import hmac
from django.test import TestCase, override_settings
from django.utils import timezone


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
