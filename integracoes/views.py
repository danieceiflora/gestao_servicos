import json
import hmac
import hashlib
import logging
import unicodedata
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import WebhookEvent
from services.models import ServiceOrder, ServiceOrderTask

logger = logging.getLogger(__name__)


def _dig(container, *path):
    current = container
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_first(payload, paths):
    for path in paths:
        value = _dig(payload, *path)
        if value not in (None, ""):
            return value
    return None


def _normalize_text(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def _extract_chatwoot_reply_text(payload):
    payloads = [payload]
    nested_message = payload.get('message') if isinstance(payload, dict) else None
    if isinstance(nested_message, dict):
        payloads.append(nested_message)

    paths = [
        ('content_attributes', 'submitted_values', 'title'),
        ('content_attributes', 'submitted_values', 'value'),
        ('content_attributes', 'button_text'),
        ('content_attributes', 'button_payload'),
        ('content',),
    ]

    for item in payloads:
        text = _extract_first(item, paths)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _extract_chatwoot_references(payload):
    payloads = [payload]
    nested_message = payload.get('message') if isinstance(payload, dict) else None
    if isinstance(nested_message, dict):
        payloads.append(nested_message)

    reply_ref_paths = [
        ('content_attributes', 'in_reply_to'),
        ('content_attributes', 'in_reply_to_id'),
        ('content_attributes', 'in_reply_to_message_id'),
        ('content_attributes', 'in_reply_to_external_id'),
        ('in_reply_to',),
        ('in_reply_to_id',),
    ]
    conversation_paths = [
        ('conversation_id',),
        ('conversation', 'id'),
    ]

    reply_refs = set()
    conversation_refs = set()

    for item in payloads:
        for path in reply_ref_paths:
            value = _dig(item, *path)
            if value not in (None, ''):
                reply_refs.add(str(value))

        for path in conversation_paths:
            value = _dig(item, *path)
            if value not in (None, ''):
                conversation_refs.add(str(value))

    return reply_refs, conversation_refs


def _parse_approval_decision(reply_text):
    text = _normalize_text(reply_text)

    is_approved = None
    if 'reprova' in text:
        is_approved = False
    elif 'aprova' in text:
        is_approved = True

    if is_approved is None:
        return None, None

    payment_method = None
    if is_approved:
        if 'pix' in text:
            payment_method = 'PIX'
        elif 'debito' in text:
            payment_method = 'DEBIT_CARD'
        elif 'cart' in text or 'credito' in text:
            payment_method = 'CREDIT_CARD'
        elif 'dinheiro' in text or 'cash' in text:
            payment_method = 'CASH'
        elif 'transfer' in text:
            payment_method = 'TRANSFER'
        elif 'boleto' in text:
            payment_method = 'BOLETO'

    return is_approved, payment_method


def _process_chatwoot_budget_reply(payload):
    reply_text = _extract_chatwoot_reply_text(payload)
    if not reply_text:
        return 'processed', 'Payload Chatwoot sem conteúdo de resposta.'

    is_approved, payment_method = _parse_approval_decision(reply_text)
    if is_approved is None:
        return 'processed', f'Resposta recebida sem decisão de aprovação: "{reply_text}"'

    reply_refs, conversation_refs = _extract_chatwoot_references(payload)

    order = None
    if reply_refs:
        order = ServiceOrder.objects.filter(chatwoot_budget_message_id__in=reply_refs).order_by('-updated_at').first()

    if not order and conversation_refs:
        order = ServiceOrder.objects.filter(
            chatwoot_budget_conversation_id__in=conversation_refs,
            status=ServiceOrder.Status.WAITING_APPROVAL
        ).order_by('-updated_at').first()

    if not order:
        logger.warning("Webhook Chatwoot sem OS correspondente. refs=%s convs=%s", list(reply_refs), list(conversation_refs))
        return 'failed', 'Não foi possível localizar a OS pelo ID da mensagem/conversa.'

    budget_task = order.tasks.filter(task_type=ServiceOrderTask.TaskType.BUDGET).order_by('-scheduled_at').first()
    if not budget_task:
        return 'failed', f'OS #{order.number} sem etapa de orçamento para atualizar.'

    budget_task.is_approved = is_approved
    budget_task.payment_method = payment_method if is_approved else None
    budget_task.save(update_fields=['is_approved', 'payment_method'])

    order.client_budget_response = reply_text
    order.client_budget_approved_at = timezone.now() if is_approved else None
    order.save(update_fields=['client_budget_response', 'client_budget_approved_at', 'updated_at'])

    return 'processed', f'OS #{order.number} atualizada via Chatwoot ({ "aprovado" if is_approved else "reprovado" }).'


def _validate_webhook_secret(request):
    expected_secret = (getattr(settings, 'WEBHOOK_SHARED_SECRET', '') or '').strip()
    if not expected_secret:
        logger.error("WEBHOOK_SHARED_SECRET não configurado para /webhooks")
        return False

    received_signature = (request.headers.get('X-Chatwoot-Signature') or '').strip()
    timestamp = (request.headers.get('X-Chatwoot-Timestamp') or '').strip()

    if not received_signature or not timestamp:
        return False

    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False

    # Janela de 5 minutos para mitigar replay attack.
    current_timestamp = int(timezone.now().timestamp())
    if abs(current_timestamp - timestamp_value) > 300:
        logger.warning("Webhook Chatwoot rejeitado por timestamp fora da janela. ts=%s", timestamp)
        return False

    message = f"{timestamp}.".encode('utf-8') + request.body
    expected_signature = "sha256=" + hmac.new(
        expected_secret.encode('utf-8'),
        message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, received_signature)


def _handle_webhook_request(request, provider):
    # Validação de Assinatura do Bling
    if provider == 'bling':
        bling_signature = request.headers.get('X-Bling-Signature-256')
        client_secret = getattr(settings, 'BLING_CLIENT_SECRET', None)
        
        if not client_secret:
            # Se não houver secret configurado, podemos optar por logar ou permitir (em dev)
            # Para segurança, em produção deveria falhar.
            pass 
        elif not bling_signature:
            return JsonResponse({
                "status": "error",
                "message": "Missing authentication signature"
            }, status=401)
        else:
            # Calcular HMAC SHA256 do payload bruto
            expected_signature = hmac.new(
                client_secret.encode('utf-8'),
                request.body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_signature, bling_signature):
                return JsonResponse({
                    "status": "error",
                    "message": "Invalid authentication signature"
                }, status=401)

    # Se for JSON, carrega com json.loads. Caso contrário, salva a string pura.
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        # Caso não seja JSON formatado corretamente, tenta pegar os dados como dict
        if request.POST:
            payload = request.POST.dict()
        else:
            payload = request.body.decode('utf-8')

    # Converte o request.headers para dict nativo
    headers_dict = dict(request.headers.items())

    event_status = 'pending'
    event_notes = None

    if provider == 'chatwoot':
        event_status, event_notes = _process_chatwoot_budget_reply(payload)

    # Salva o evento no banco
    event = WebhookEvent.objects.create(
        provider=provider,
        payload=payload,
        headers=headers_dict,
        status=event_status,
        notes=event_notes
    )

    return JsonResponse({
        "status": "success",
        "message": "Webhook recebido com sucesso",
        "event_id": event.id,
        "event_status": event.status
    }, status=200)


@csrf_exempt
@require_POST
def webhooks(request):
    if not _validate_webhook_secret(request):
        return JsonResponse({
            "status": "error",
            "message": "Invalid webhook signature"
        }, status=401)

    try:
        return _handle_webhook_request(request, provider='chatwoot')
    except Exception as e:
        logger.exception("Erro ao processar webhook /webhooks")
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)

@csrf_exempt
@require_POST
def webhook_receiver(request, provider):
    """
    View centralizada para receber e salvar payloads brutos de webhooks.
    Salva os cabeçalhos (headers) e o corpo (body).
    Inclui validação de assinatura para o Bling.
    """
    try:
        return _handle_webhook_request(request, provider=provider)
    except Exception as e:
        logger.exception("Erro ao processar webhook provider=%s", provider)
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)
