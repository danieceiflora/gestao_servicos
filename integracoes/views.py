import json
import hmac
import hashlib
import logging
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import WebhookEvent, SystemConfig, PlatformSubscription, PlatformSubscriptionEvent, PlatformInvoice
from .chatwoot_client import ChatwootClient
from pagamentos.gateways.asaas import AsaasGateway
from pagamentos.gateways.base import ChargeData
from services.models import ServiceOrder, ServiceOrderTask, Sale, Billing, Installment, ExpenseInstallment

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

    has_approved = 'aprova' in text
    has_rejected = 'reprova' in text

    is_approved = None
    if has_approved and has_rejected:
        return None, None
    if has_rejected:
        is_approved = False
    elif has_approved:
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


def _build_budget_response_label(is_approved, payment_method):
    if not is_approved:
        return "Reprovado"

    payment_labels = {
        'PIX': 'Aprovado - Pix',
        'DEBIT_CARD': 'Aprovado - Cartão',
        'CREDIT_CARD': 'Aprovado - Cartão',
        'CASH': 'Aprovado - Dinheiro',
        'TRANSFER': 'Aprovado - Transferência',
        'BOLETO': 'Aprovado - Boleto',
    }
    return payment_labels.get(payment_method, 'Aprovado')

def _parse_confirmation_decision(reply_text):
    text = _normalize_text(reply_text)

    reschedule_keywords = ['reagend', 'remarc', 'reagenda', 'remarca', 'alterar', 'mudar', 'adiar']
    confirm_keywords = ['confirm', 'ok', 'certo', 'sim']
    words = re.findall(r"[a-z0-9]+", text)

    if any(keyword in text for keyword in reschedule_keywords):
        return ServiceOrderTask.WhatsAppConfirmationStatus.REAGENDAR

    if any(keyword in text for keyword in confirm_keywords) or any(keyword in words for keyword in confirm_keywords):
        return ServiceOrderTask.WhatsAppConfirmationStatus.CONFIRMADO

    return None


def _build_confirmation_response_label(status):
    if status == ServiceOrderTask.WhatsAppConfirmationStatus.CONFIRMADO:
        return "confirmado"
    if status == ServiceOrderTask.WhatsAppConfirmationStatus.REAGENDAR:
        return "reagendar"
    return None


def _is_chatwoot_client_confirmation_reply(payload):
    return _is_chatwoot_client_budget_reply(payload)


def _resolve_order_status_from_budget_decision(is_approved):
    if is_approved:
        return ServiceOrder.Status.APROVADO_AGUARDANDO_AGENDAMENTO
    return ServiceOrder.Status.REPROVADO_PELO_CLIENTE


def _is_chatwoot_client_budget_reply(payload):
    if not isinstance(payload, dict):
        return False

    event_name = str(payload.get('event') or '').strip().lower()
    if event_name and event_name != 'message_created':
        return False

    message_type = payload.get('message_type')
    if isinstance(message_type, str):
        normalized_type = message_type.strip().lower()
        if normalized_type in {'outgoing', 'template', 'activity'}:
            return False
    elif isinstance(message_type, int) and message_type != 0:
        return False

    sender_type = _dig(payload, 'sender', 'type')
    if sender_type and str(sender_type).strip().lower() != 'contact':
        return False

    if payload.get('private') is True:
        return False

    return True


def _is_chatwoot_outgoing_message(payload):
    if not isinstance(payload, dict):
        return False

    event_name = str(payload.get('event') or '').strip().lower()
    if event_name != 'message_created':
        return False

    message_type = payload.get('message_type')
    is_outgoing = False
    if isinstance(message_type, str):
        is_outgoing = message_type.strip().lower() in {'outgoing', 'template'}
    elif isinstance(message_type, int):
        is_outgoing = message_type == 3

    if not is_outgoing:
        return False

    return True


def _process_chatwoot_budget_sent(payload):
    if not _is_chatwoot_outgoing_message(payload):
        return 'processed', 'Evento Chatwoot ignorado (não é envio de orçamento).'

    message_id = _extract_first(payload, [('id',), ('source_id',)])
    conversation_id = _extract_first(payload, [('conversation_id',), ('conversation', 'id')])
    if conversation_id in (None, ''):
        return 'failed', 'Envio de orçamento detectado sem conversation_id.'

    order = None
    if message_id not in (None, ''):
        order = ServiceOrder.objects.filter(chatwoot_budget_message_id=str(message_id)).order_by('-updated_at').first()

    if not order:
        order = ServiceOrder.objects.filter(
            chatwoot_budget_conversation_id=str(conversation_id),
            status__in=[
                ServiceOrder.Status.ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO,
                ServiceOrder.Status.AGUARDANDO_APROVACAO,
            ]
        ).order_by('-updated_at').first()

    if not order:
        return 'processed', 'Evento de envio ignorado (sem OS de orçamento vinculada).'

    try:
        cw = ChatwootClient()
        label = cw.get_label_by_title("Orçamento-Enviado") or cw.create_label("Orçamento-Enviado")
        if not label:
            return 'failed', 'Não foi possível criar/localizar etiqueta Orçamento-Enviado.'

        assigned = cw.assign_label_to_conversation(conversation_id, label.get("title", "Orçamento-Enviado"))
        if not assigned:
            return 'failed', 'Não foi possível atribuir etiqueta Orçamento-Enviado na conversa.'
    except Exception:
        logger.exception("Erro ao etiquetar envio de orçamento no Chatwoot. conversation_id=%s", conversation_id)
        return 'failed', 'Erro ao etiquetar envio de orçamento.'

    return 'processed', 'Etiqueta Orçamento-Enviado atribuída após envio do template.'


def _process_chatwoot_budget_reply(payload):
    if not _is_chatwoot_client_budget_reply(payload):
        return 'processed', 'Evento Chatwoot ignorado (não é resposta de cliente).'

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
            status__in=[
                ServiceOrder.Status.ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO,
                ServiceOrder.Status.AGUARDANDO_APROVACAO,
            ]
        ).order_by('-updated_at').first()

    if not order:
        logger.warning("Webhook Chatwoot sem OS correspondente. refs=%s convs=%s", list(reply_refs), list(conversation_refs))
        return 'failed', 'Não foi possível localizar a OS pelo ID da mensagem/conversa.'

    budget_task = order.tasks.filter(task_type=ServiceOrderTask.TaskType.ORCAMENTO).order_by('-scheduled_at').first()
    if not budget_task:
        return 'failed', f'OS #{order.number} sem etapa de orçamento para atualizar.'

    budget_task.is_approved = is_approved
    budget_task.payment_method = payment_method if is_approved else None
    budget_task.save(update_fields=['is_approved', 'payment_method'])

    order.status = _resolve_order_status_from_budget_decision(is_approved)
    order.client_budget_response = reply_text
    order.client_budget_responded_at = timezone.now()
    order.client_budget_approved_at = timezone.now() if is_approved else None
    order.save(update_fields=['status', 'client_budget_response', 'client_budget_responded_at', 'client_budget_approved_at', 'updated_at'])

    label_title = _build_budget_response_label(is_approved, payment_method)
    conversation_id = next(iter(conversation_refs), None) or order.chatwoot_budget_conversation_id
    if conversation_id:
        try:
            cw = ChatwootClient()
            label = cw.get_label_by_title(label_title) or cw.create_label(label_title)
            if not label:
                logger.warning(
                    "Não foi possível criar/localizar etiqueta de resposta no Chatwoot. label=%s conversation_id=%s",
                    label_title,
                    conversation_id
                )
            else:
                assigned = cw.assign_label_to_conversation(conversation_id, label.get("title", label_title))
                if not assigned:
                    logger.warning(
                        "Não foi possível atribuir etiqueta de resposta no Chatwoot. label=%s conversation_id=%s",
                        label_title,
                        conversation_id
                    )
        except Exception:
            logger.exception(
                "Erro ao etiquetar conversa de orçamento no Chatwoot. label=%s conversation_id=%s",
                label_title,
                conversation_id
            )

    return 'processed', f'OS #{order.number} atualizada via Chatwoot ({ "aprovado" if is_approved else "reprovado" }).'


def _process_chatwoot_confirmation_reply(payload):
    if not _is_chatwoot_client_confirmation_reply(payload):
        return 'processed', 'Evento Chatwoot ignorado (não é resposta de confirmação).'

    reply_text = _extract_chatwoot_reply_text(payload)
    if not reply_text:
        return 'processed', 'Payload Chatwoot sem conteúdo de confirmação.'

    decision = _parse_confirmation_decision(reply_text)
    if decision is None:
        return 'processed', f'Resposta recebida sem decisão de confirmação: "{reply_text}"'

    reply_refs, conversation_refs = _extract_chatwoot_references(payload)

    task = None
    if reply_refs:
        task = ServiceOrderTask.objects.filter(
            chatwoot_confirmation_message_id__in=reply_refs
        ).order_by('-created_at').first()

    if not task and conversation_refs:
        task = ServiceOrderTask.objects.filter(
            chatwoot_confirmation_conversation_id__in=conversation_refs,
            whatsapp_confirmation_status__in=[
                ServiceOrderTask.WhatsAppConfirmationStatus.ENVIADO,
                ServiceOrderTask.WhatsAppConfirmationStatus.AGUARDANDO,
            ]
        ).order_by('-created_at').first()

    if not task:
        logger.warning(
            "Webhook Chatwoot sem etapa correspondente. refs=%s convs=%s",
            list(reply_refs),
            list(conversation_refs)
        )
        return 'failed', 'Não foi possível localizar a etapa para confirmação.'

    task.whatsapp_confirmation_status = decision
    task.whatsapp_confirmation_received_at = timezone.now()
    task.whatsapp_response_content = reply_text
    task.save(update_fields=[
        'whatsapp_confirmation_status',
        'whatsapp_confirmation_received_at',
        'whatsapp_response_content'
    ])

    label_title = _build_confirmation_response_label(decision)
    conversation_id = next(iter(conversation_refs), None) or task.chatwoot_confirmation_conversation_id
    if label_title and conversation_id:
        try:
            cw = ChatwootClient()
            label = cw.get_label_by_title(label_title) or cw.create_label(label_title)
            if not label:
                logger.warning(
                    "Não foi possível criar/localizar etiqueta de confirmação no Chatwoot. label=%s conversation_id=%s",
                    label_title,
                    conversation_id
                )
            else:
                assigned = cw.assign_label_to_conversation(conversation_id, label.get("title", label_title))
                if not assigned:
                    logger.warning(
                        "Não foi possível atribuir etiqueta de confirmação no Chatwoot. label=%s conversation_id=%s",
                        label_title,
                        conversation_id
                    )
        except Exception:
            logger.exception(
                "Erro ao etiquetar conversa de confirmação no Chatwoot. label=%s conversation_id=%s",
                label_title,
                conversation_id
            )

    return 'processed', f'Etapa #{task.id} atualizada via Chatwoot ({decision}).'


def _validate_webhook_secret(request):
    expected_secret = (getattr(settings, 'WEBHOOK_SHARED_SECRET', '') or '').strip()
    if not expected_secret:
        logger.error("WEBHOOK_SHARED_SECRET não configurado no Django settings.")
        return False

    received_signature = (request.headers.get('X-Chatwoot-Signature') or '').strip()
    timestamp = (request.headers.get('X-Chatwoot-Timestamp') or '').strip()

    if not received_signature or not timestamp:
        logger.warning("Webhook Chatwoot rejeitado: headers de assinatura ausentes.")
        return False

    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        logger.warning("Webhook Chatwoot rejeitado: timestamp inválido. ts=%s", timestamp)
        return False

    # Janela de 5 minutos para mitigar replay attack.
    current_timestamp = int(timezone.now().timestamp())
    if abs(current_timestamp - timestamp_value) > 300:
        logger.warning("Webhook Chatwoot rejeitado: timestamp fora da janela (skew). recebido=%s, atual=%s", timestamp_value, current_timestamp)
        return False

    # O formato correto do payload assinado pelo Chatwoot é "{timestamp}.{raw_body}"
    # O raw_body deve ser bytes puros vindos do request.body
    message = f"{timestamp}.".encode('utf-8') + request.body
    
    computed_hash = hmac.new(
        expected_secret.encode('utf-8'),
        message,
        hashlib.sha256,
    ).hexdigest()

    # Chatwoot costuma enviar com prefixo 'sha256=', mas aceitamos ambos para robustez
    expected_with_prefix = f"sha256={computed_hash}"
    
    # Verificação constante de tempo
    if hmac.compare_digest(expected_with_prefix, received_signature):
        return True
    
    if hmac.compare_digest(computed_hash, received_signature):
        return True

    logger.error("Falha na verificação de assinatura do Webhook Chatwoot. Hash calculado não confere.")
    return False


class MetaCloudAPI:
    def __init__(self, waba_id, token):
        self.waba_id = waba_id
        self.token = token
        self.base_url = "https://graph.facebook.com/v20.0"

    def get_templates(self):
        if not self.waba_id or not self.token:
            return {"data": []}
        url = f"{self.base_url}/{self.waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {
            "fields": "name,components,language,status,category,last_updated_time,modified_time",
            "limit": 200,
        }
        try:
            all_templates = []
            next_url = url
            next_params = params
            while next_url:
                response = requests.get(next_url, headers=headers, params=next_params, timeout=10)
                data = response.json()
                all_templates.extend(data.get("data", []))
                next_url = data.get("paging", {}).get("next")
                next_params = None  # URL "next" já inclui os params
            return {"data": all_templates}
        except Exception as e:
            logger.error(f"Error fetching templates: {e}")
            return {"error": str(e), "data": []}

    def get_template(self, template_id):
        url = f"{self.base_url}/{template_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching template {template_id}: {e}")
            return {"error": str(e)}

    def update_template(self, template_id, category, components):
        url = f"{self.base_url}/{template_id}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        data = {
            "category": category,
            "components": components
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"Error updating template {template_id}: {e}")
            return {"error": str(e)}

    def get_app_id(self):
        url = "https://graph.facebook.com/debug_token"
        params = {
            "input_token": self.token,
            "access_token": self.token
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            return data.get('data', {}).get('app_id')
        except Exception as e:
            logger.error(f"Error getting app_id: {e}")
            return None

    def upload_header_media(self, file_obj):
        """
        Meta Resumable Upload API for template header handles.
        Returns the handle (e.g., '4::...') or None.
        """
        app_id = self.get_app_id()
        if not app_id:
            return None

        file_name = file_obj.name
        file_length = file_obj.size
        file_type = file_obj.content_type

        # 1. Create upload session
        url_session = f"{self.base_url}/{app_id}/uploads"
        params = {
            "file_name": file_name,
            "file_length": file_length,
            "file_type": file_type,
            "access_token": self.token
        }
        try:
            res_session = requests.post(url_session, params=params, timeout=10)
            session_data = res_session.json()
            upload_id = session_data.get('id')
            if not upload_id:
                logger.error(f"Failed to create upload session: {session_data}")
                return None

            # 2. Upload file content
            url_upload = f"{self.base_url}/{upload_id}"
            headers = {
                "Authorization": f"OAuth {self.token}",
                "file_offset": "0"
            }
            res_upload = requests.post(url_upload, headers=headers, data=file_obj.read(), timeout=30)
            upload_data = res_upload.json()
            handle = upload_data.get('h')
            if not handle:
                logger.error(f"Failed to get media handle: {upload_data}")
                return None
            
            return handle
        except Exception as e:
            logger.error(f"Error in resumable upload: {e}")
            return None

    def create_template(self, name, language, category, components):
        url = f"{self.base_url}/{self.waba_id}/message_templates"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        data = {
            "name": name,
            "language": language,
            "category": category,
            "components": components
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"Error creating template: {e}")
            return {"error": str(e)}

    def delete_template(self, template_name):
        url = f"{self.base_url}/{self.waba_id}/message_templates"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"name": template_name}
        try:
            response = requests.delete(url, headers=headers, params=params, timeout=10)
            return response.json()
        except Exception as e:
            logger.error(f"Error deleting template: {e}")
            return {"error": str(e)}

from .models import (
    WebhookEvent, SystemConfig,
    NotificationConfig, NotificationVariable,
    CollectionSequence, CollectionStep, CollectionStepVariable,
    CollectionInstallmentState, CollectionLog,
    ScheduledReminder, ScheduledReminderVariable, ScheduledReminderLog,
)

from .utils import get_mappable_fields

@login_required
@user_passes_test(lambda u: u.is_staff)
def notification_config_list(request):
    configs = NotificationConfig.objects.all().order_by('-updated_at')
    status_labels = {
        # ServiceOrder
        'ORCAMENTO_AGENDADO': 'Orçamento Agendado',
        'ORCAMENTO_REALIZADO_AGUARDANDO_ENVIO': 'Orçamento Realizado',
        'APROVADO_AGUARDANDO_AGENDAMENTO': 'Aprovado / Ag. Agendamento',
        'AGUARDANDO_EXECUCAO': 'Aguardando Execução',
        'CONCLUIDA': 'Concluída',
        'GARANTIA': 'Garantia',
        'CANCELADO': 'Cancelado',
        # ServiceOrderTask
        'AGENDADO': 'Agendado',
        'EM_ANDAMENTO': 'Em Andamento',
        'CONCLUIDO': 'Concluído',
        'NAO_EXECUTADO': 'Não Executado',
        # Billing / Installment / Sale
        'PENDENTE': 'Pendente',
        'PARCIAL': 'Parcialmente Pago',
        'PAGO': 'Pago',
        'ATRASADO': 'Atrasado',
        'ATIVO': 'Ativo',
        'INATIVO': 'Inativo',
    }
    return render(request, 'integracoes/notifications/config_list.html', {
        'configs': configs,
        'status_labels': status_labels,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def notification_config_create(request):
    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    templates = api.get_templates().get('data', [])
    
    if request.method == 'POST':
        name = request.POST.get('name')
        model_name = request.POST.get('model_name')
        event_type = request.POST.get('event_type')
        from_status = request.POST.get('from_status')
        to_status = request.POST.get('to_status')
        template_name = request.POST.get('template_name')
        recipient_type = request.POST.get('recipient_type')
        fixed_phone = request.POST.get('fixed_phone')
        phone_path = request.POST.get('phone_field_path')
        header_media_type = request.POST.get('header_media_type', 'NONE')
        static_media_file = request.FILES.get('static_media_file')
        
        config = NotificationConfig.objects.create(
            name=name, model_name=model_name, event_type=event_type,
            from_status=from_status, to_status=to_status,
            template_name=template_name, recipient_type=recipient_type,
            fixed_phone=fixed_phone, phone_field_path=phone_path,
            header_media_type=header_media_type,
            static_media_file=static_media_file
        )
        
        # Salvar variáveis do corpo
        indices = request.POST.getlist('var_index[]')
        paths = request.POST.getlist('var_path[]')
        for i, path in zip(indices, paths):
            if path:
                NotificationVariable.objects.create(config=config, index=i, field_path=path, component='BODY')

        # Salvar variáveis de botão (URL dinâmica)
        btn_indices = request.POST.getlist('btn_var_index[]')
        btn_paths = request.POST.getlist('btn_var_path[]')
        for i, path in zip(btn_indices, btn_paths):
            if path:
                NotificationVariable.objects.create(config=config, index=int(i), field_path=path, component='BUTTON')

        messages.success(request, "Configuração de notificação criada com sucesso!")
        return redirect('integracoes:notification_config_list')

    return render(request, 'integracoes/notifications/config_form.html', {
        'templates': templates,
        'model_choices': NotificationConfig.MODEL_CHOICES,
        'event_choices': NotificationConfig.EVENT_CHOICES,
        'recipient_choices': NotificationConfig.RECIPIENT_CHOICES,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def notification_config_edit(request, pk):
    config = get_object_or_404(NotificationConfig, pk=pk)
    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    templates = api.get_templates().get('data', [])
    
    if request.method == 'POST':
        config.name = request.POST.get('name')
        config.model_name = request.POST.get('model_name')
        config.event_type = request.POST.get('event_type')
        config.from_status = request.POST.get('from_status')
        config.to_status = request.POST.get('to_status')
        config.template_name = request.POST.get('template_name')
        config.recipient_type = request.POST.get('recipient_type')
        config.fixed_phone = request.POST.get('fixed_phone')
        config.phone_field_path = request.POST.get('phone_field_path')
        config.is_active = request.POST.get('is_active') == 'on'
        
        header_media_type = request.POST.get('header_media_type')
        if header_media_type:
            config.header_media_type = header_media_type
        
        static_media_file = request.FILES.get('static_media_file')
        if static_media_file:
            config.static_media_file = static_media_file
            
        config.save()
        
        # Atualizar variáveis do corpo
        config.variables.all().delete()
        indices = request.POST.getlist('var_index[]')
        paths = request.POST.getlist('var_path[]')
        for i, path in zip(indices, paths):
            if path:
                NotificationVariable.objects.create(config=config, index=i, field_path=path, component='BODY')

        # Atualizar variáveis de botão (URL dinâmica)
        btn_indices = request.POST.getlist('btn_var_index[]')
        btn_paths = request.POST.getlist('btn_var_path[]')
        for i, path in zip(btn_indices, btn_paths):
            if path:
                NotificationVariable.objects.create(config=config, index=int(i), field_path=path, component='BUTTON')

        messages.success(request, "Configuração atualizada!")
        return redirect('integracoes:notification_config_list')

    return render(request, 'integracoes/notifications/config_form.html', {
        'config': config,
        'templates': templates,
        'model_choices': NotificationConfig.MODEL_CHOICES,
        'event_choices': NotificationConfig.EVENT_CHOICES,
        'recipient_choices': NotificationConfig.RECIPIENT_CHOICES,
        'variables': config.variables.all().order_by('index')
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def notification_config_delete(request, pk):
    config = get_object_or_404(NotificationConfig, pk=pk)
    if request.method == 'POST':
        config.delete()
        messages.success(request, "Configuração removida.")
    return redirect('integracoes:notification_config_list')

@login_required
@user_passes_test(lambda u: u.is_staff)
def manual_message_config_list(request):
    from .models import ManualMessageConfig
    TRIGGER_META = {
        'ENVIO_ORCAMENTO': {
            'label': 'Envio de Orçamento',
            'description': 'Disparada ao clicar em "Enviar Orçamento" na OS.',
        },
        'CONVITE_CADASTRO': {
            'label': 'Convite para Cadastro',
            'description': 'Disparada ao clicar em "Convidar para Cadastro" na lista de clientes.',
            'model_name': 'ServiceOrder',
        },
    }
    items = []
    for trigger, meta in TRIGGER_META.items():
        config = ManualMessageConfig.objects.filter(trigger=trigger).first()
        items.append({'trigger': trigger, 'meta': meta, 'config': config})
    return render(request, 'integracoes/manual_message/config_list.html', {'items': items})


@login_required
@user_passes_test(lambda u: u.is_staff)
def manual_message_config_edit(request, trigger):
    from .models import ManualMessageConfig, ManualMessageVariable

    TRIGGER_MODEL = {
        'ENVIO_ORCAMENTO':  'ServiceOrder',
        'CONVITE_CADASTRO': 'Convite',
    }
    TRIGGER_LABELS = dict(ManualMessageConfig.TRIGGER_CHOICES)
    if trigger not in TRIGGER_LABELS:
        raise Http404

    model_name = TRIGGER_MODEL[trigger]
    config, _ = ManualMessageConfig.objects.get_or_create(trigger=trigger)

    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    templates = api.get_templates().get('data', [])

    if request.method == 'POST':
        config.template_name = request.POST.get('template_name', '').strip()
        config.header_media_type = request.POST.get('header_media_type', 'NONE')
        config.is_active = 'is_active' in request.POST
        if request.FILES.get('static_media_file'):
            config.static_media_file = request.FILES['static_media_file']
        config.save()

        config.variables.all().delete()
        indices = request.POST.getlist('var_index[]')
        paths = request.POST.getlist('var_path[]')
        for i, path in zip(indices, paths):
            if path:
                ManualMessageVariable.objects.create(config=config, index=int(i), field_path=path, component='BODY')
        btn_indices = request.POST.getlist('btn_var_index[]')
        btn_paths = request.POST.getlist('btn_var_path[]')
        for i, path in zip(btn_indices, btn_paths):
            if path:
                ManualMessageVariable.objects.create(config=config, index=int(i), field_path=path, component='BUTTON')

        messages.success(request, f'Mensagem "{TRIGGER_LABELS[trigger]}" configurada.')
        return redirect('integracoes:manual_message_config_list')

    return render(request, 'integracoes/manual_message/config_form.html', {
        'config': config,
        'trigger': trigger,
        'trigger_label': TRIGGER_LABELS[trigger],
        'model_name': model_name,
        'templates': templates,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def ajax_sync_meta_templates(request):
    """Pinga a Meta API para verificar conexão e retorna timestamp da sincronização."""
    from django.utils import timezone
    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    result = api.get_templates()
    if 'error' in result:
        return JsonResponse({'ok': False, 'error': result['error']})
    count = len(result.get('data', []))
    ts = timezone.now().isoformat()
    return JsonResponse({'ok': True, 'count': count, 'ts': ts})

@login_required
def ajax_get_template_details(request):
    """Retorna o corpo do template e campos de variáveis via AJAX/HTMX."""
    template_name = request.GET.get('template_name')
    model_name = request.GET.get('model_name')
    
    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    templates = api.get_templates().get('data', [])
    
    # Coleta todas as entradas com esse nome (pode haver versões antigas com status diferente)
    matching = [t for t in templates if t['name'] == template_name]
    # Prefere APPROVED; se não houver, pega qualquer outra (PENDING_DELETION, PAUSED, etc.)
    template = next((t for t in matching if t.get('status') == 'APPROVED'), None)
    if not template:
        template = matching[0] if matching else None
    if not template:
        # Fallback: tenta buscar por ID
        template = next((t for t in templates if t.get('id') == template_name), None)
        
    if not template:
        return render(request, 'integracoes/notifications/partials/template_variables.html', {
            'error': 'Template não encontrado ou não selecionado.'
        })
        
    body_comp = next((c for c in template.get('components', []) if c['type'] == 'BODY'), None)
    body_text = body_comp.get('text', '') if body_comp else ''
    
    # Encontrar variáveis {{n}}
    vars_count = len(re.findall(r"\{\{\d+\}\}", body_text))
    
    # Detectar Mídia no Cabeçalho
    header_comp = next((c for c in template.get('components', []) if c['type'] == 'HEADER'), None)
    header_format = header_comp.get('format') if header_comp else None
    has_media_header = header_format in ['IMAGE', 'VIDEO', 'DOCUMENT']
    
    # Campos curados do modelo, agrupados por categoria para a UI
    suggested_fields = get_mappable_fields(model_name)
    from collections import OrderedDict
    groups_dict = OrderedDict()
    for path, label in suggested_fields:
        group, field_label = label.split(' > ', 1) if ' > ' in label else ('Outros', label)
        groups_dict.setdefault(group, []).append((path, label, field_label))
    suggested_fields_grouped = list(groups_dict.items())

    # Detectar botões com URL dinâmica.
    # A Meta API pode retornar o {{1}} no campo 'url' OU apenas como 'example';
    # ambas as formas indicam um parâmetro dinâmico no sufixo da URL.
    buttons_comp = next((c for c in template.get('components', []) if c['type'] == 'BUTTONS'), None)
    button_vars = []
    if buttons_comp:
        logger.debug('Botões do template %s: %s', template_name, buttons_comp.get('buttons', []))
        for btn_idx, btn in enumerate(buttons_comp.get('buttons', [])):
            if btn.get('type') == 'URL':
                url = btn.get('url', '')
                has_dynamic = '{{1}}' in url or bool(btn.get('example'))
                if has_dynamic:
                    button_vars.append({
                        'btn_index': btn_idx,
                        'btn_text': btn.get('text', f'Botão {btn_idx + 1}'),
                        'url_template': url,
                    })

    # Carrega mapeamentos existentes
    config_id = request.GET.get('config_id')
    step_id = request.GET.get('step_id')
    reminder_id = request.GET.get('reminder_id')
    manual_config_id = request.GET.get('manual_config_id')
    existing_vars = {}
    existing_btn_vars = {}
    config = None
    header_media_choices = NotificationConfig.HEADER_MEDIA_CHOICES
    if config_id and config_id.isdigit():
        config = NotificationConfig.objects.filter(id=config_id).first()
        existing_vars = {v.index: v.field_path for v in NotificationVariable.objects.filter(config_id=config_id, component='BODY')}
        existing_btn_vars = {v.index: v.field_path for v in NotificationVariable.objects.filter(config_id=config_id, component='BUTTON')}
    elif step_id and step_id.isdigit():
        existing_vars = {v.index: v.field_path for v in CollectionStepVariable.objects.filter(step_id=step_id, component='BODY')}
        existing_btn_vars = {v.index: v.field_path for v in CollectionStepVariable.objects.filter(step_id=step_id, component='BUTTON')}
    elif reminder_id and reminder_id.isdigit():
        existing_vars = {v.index: v.field_path for v in ScheduledReminderVariable.objects.filter(reminder_id=reminder_id, component='BODY')}
        existing_btn_vars = {v.index: v.field_path for v in ScheduledReminderVariable.objects.filter(reminder_id=reminder_id, component='BUTTON')}
    elif manual_config_id and manual_config_id.isdigit():
        from .models import ManualMessageConfig, ManualMessageVariable
        config = ManualMessageConfig.objects.filter(id=manual_config_id).first()
        existing_vars = {v.index: v.field_path for v in ManualMessageVariable.objects.filter(config_id=manual_config_id, component='BODY')}
        existing_btn_vars = {v.index: v.field_path for v in ManualMessageVariable.objects.filter(config_id=manual_config_id, component='BUTTON')}
        if config:
            header_media_choices = config.HEADER_MEDIA_CHOICES

    return render(request, 'integracoes/notifications/partials/template_variables.html', {
        'body_text': body_text,
        'vars_count': range(1, vars_count + 1),
        'has_media_header': has_media_header,
        'header_format': header_format,
        'suggested_fields': suggested_fields,
        'suggested_fields_grouped': suggested_fields_grouped,
        'existing_vars': existing_vars,
        'existing_btn_vars': existing_btn_vars,
        'button_vars': button_vars,
        'config': config,
        'header_media_choices': header_media_choices,
    })

@login_required
def ajax_get_model_fields(request):
    """Retorna apenas os campos do modelo para o seletor de telefone."""
    model_name = request.GET.get('model_name')
    suggested_fields = get_mappable_fields(model_name, only_phones=True)
    
    # Tenta pegar o valor atual se estiver editando
    current_val = request.GET.get('current_val', 'client_property.client.phones.first.phone')
    
    return render(request, 'integracoes/notifications/partials/model_fields_select.html', {
        'suggested_fields': suggested_fields,
        'current_val': current_val
    })

@login_required
def ajax_get_status_choices(request):
    """Retorna as opções de status para um determinado modelo."""
    model_name = request.GET.get('model_name')
    from_val = request.GET.get('from_val')
    to_val = request.GET.get('to_val')
    
    choices = []
    if model_name == 'ServiceOrder':
        choices = ServiceOrder.Status.choices
    elif model_name == 'ServiceOrderTask':
        choices = ServiceOrderTask.TaskStatus.choices
    elif model_name == 'Sale':
        choices = Sale.Status.choices
    elif model_name == 'Billing':
        choices = Billing.Status.choices
    elif model_name == 'Installment':
        choices = Installment.Status.choices
    elif model_name == 'ExpenseInstallment':
        choices = ExpenseInstallment.Status.choices
        
    return render(request, 'integracoes/notifications/partials/status_choices_select.html', {
        'choices': choices,
        'from_val': from_val,
        'to_val': to_val
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def whatsapp_template_list(request):
    config = SystemConfig.load()
    
    # Verificar se as credenciais estão configuradas (agora via Django Admin)
    if not all([config.meta_access_token, config.meta_waba_id, config.meta_phone_number_id]):
        messages.warning(
            request, 
            "As credenciais da API Meta (Token, WABA ID ou Phone ID) não estão configuradas. "
            "Por favor, configure-as no painel administrativo."
        )
        return render(request, 'integracoes/whatsapp_template_list.html', {
            'templates': [],
            'config': config,
            'missing_credentials': True
        })

    api = MetaCloudAPI(config.meta_waba_id, config.meta_access_token)

    # Sincronização automática ao carregar a página
    result = api.get_templates()
    templates = result.get('data', [])
    error = result.get('error')

    if error:
        messages.error(request, f"Erro ao sincronizar templates com a Meta: {error}")

    # Converte string ISO 8601 de última edição para datetime
    from django.utils.dateparse import parse_datetime
    for t in templates:
        ts = t.get('last_updated_time') or t.get('modified_time')
        dt_val = None
        if ts:
            try:
                # Meta retorna formato "2026-06-24T15:09:41+0000" — normaliza para "+00:00"
                ts_norm = str(ts)
                if len(ts_norm) > 5 and ts_norm[-5] in ('+', '-') and ':' not in ts_norm[-5:]:
                    ts_norm = ts_norm[:-2] + ':' + ts_norm[-2:]
                dt_val = parse_datetime(ts_norm)
            except Exception:
                pass
        t['last_updated_dt'] = dt_val

    from django.utils import timezone as dj_timezone
    last_sync = dj_timezone.now()

    return render(request, 'integracoes/whatsapp_template_list.html', {
        'templates': templates,
        'config': config,
        'last_sync': last_sync,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def whatsapp_template_create(request):
    config = SystemConfig.load()
    api = MetaCloudAPI(config.meta_waba_id, config.meta_access_token)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        category = request.POST.get('category')
        language = request.POST.get('language', 'pt_BR')
        
        # Components data
        header_type = request.POST.get('header_type', 'NONE')
        header_text = request.POST.get('header_text')
        header_example = request.POST.get('header_example')
        header_file = request.FILES.get('header_file')
        
        body_text = request.POST.get('body_text')
        body_examples = request.POST.getlist('body_examples[]')
        
        footer_text = request.POST.get('footer_text')
        
        # Buttons
        button_types = request.POST.getlist('button_type[]')
        button_texts = request.POST.getlist('button_text[]')
        button_urls = request.POST.getlist('button_url[]')
        button_url_examples = request.POST.getlist('button_url_example[]')
        button_phones = request.POST.getlist('button_phone[]')
        
        components = []
        
        # 1. Header
        if header_type != 'NONE':
            header_comp = {"type": "HEADER", "format": header_type}
            if header_type == 'TEXT':
                header_comp['text'] = header_text
                if header_example:
                    header_comp['example'] = {"header_text": [header_example]}
            else:
                # Media headers (IMAGE, VIDEO, DOCUMENT) require an example handle
                handle = None
                if header_file:
                    handle = api.upload_header_media(header_file)
                
                if not handle:
                    handle = request.POST.get('header_handle')
                
                if handle:
                    header_comp['example'] = {"header_handle": [handle]}
                else:
                    messages.error(request, "Cabeçalhos de mídia exigem um arquivo ou handle de exemplo para aprovação.")
                    return redirect('integracoes:whatsapp_template_create')

            components.append(header_comp)
            
        # 2. Body
        body_comp = {"type": "BODY", "text": body_text}
        if body_examples:
            # Filter empty strings and ensure it matches variable count if possible
            clean_examples = [ex for ex in body_examples if ex]
            if clean_examples:
                body_comp['example'] = {"body_text": [clean_examples]}
        components.append(body_comp)
        
        # 3. Footer
        if footer_text:
            components.append({"type": "FOOTER", "text": footer_text})
            
        # 4. Buttons
        if button_types:
            buttons = []
            for i in range(len(button_types)):
                b_type = button_types[i]
                b_text = button_texts[i]
                
                btn = {"type": b_type, "text": b_text}
                if b_type == 'URL':
                    url = button_urls[i] if i < len(button_urls) else ''
                    if not url:
                        continue  # URL vazia — pula botão inválido
                    btn['url'] = url
                    example = button_url_examples[i] if i < len(button_url_examples) else ''
                    # example só é válido quando a URL tem variável dinâmica {{1}}
                    if '{{1}}' in url and example:
                        btn['example'] = [example]
                elif b_type == 'PHONE_NUMBER':
                    btn['phone_number'] = button_phones[i] if i < len(button_phones) else ''

                buttons.append(btn)
            
            if buttons:
                components.append({"type": "BUTTONS", "buttons": buttons})
        
        result = api.create_template(name, language, category, components)
        
        if 'error' in result:
            err = result['error']
            user_title = err.get('error_user_title', '')
            user_msg = err.get('error_user_msg', '')
            generic_msg = err.get('message', 'Erro desconhecido')
            detail = f"{user_title}: {user_msg}" if user_title or user_msg else generic_msg
            logger.error(f"Meta API template creation error: {result}")
            messages.error(request, f"Erro ao criar template: {detail}")
        else:
            messages.success(request, f"Template '{name}' criado com sucesso e enviado para revisão.")
            return redirect('integracoes:whatsapp_template_list')

    return render(request, 'integracoes/whatsapp_template_create.html', {
        'config': config
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def whatsapp_template_edit(request, template_id):
    config = SystemConfig.load()
    api = MetaCloudAPI(config.meta_waba_id, config.meta_access_token)
    
    # 1. Buscar estado atual do template
    template = api.get_template(template_id)
    if 'error' in template:
        messages.error(request, f"Erro ao buscar template: {template['error'].get('message', 'Erro desconhecido')}")
        return redirect('integracoes:whatsapp_template_list')

    if request.method == 'POST':
        category = request.POST.get('category')
        body_text = request.POST.get('body_text')
        
        # Extrair exemplos do POST
        body_examples = request.POST.getlist('body_examples[]')
        header_example = request.POST.get('header_example')
        
        # Reconstruir componentes
        new_components = []
        for comp in template.get('components', []):
            new_comp = comp.copy()
            
            if comp['type'] == 'BODY':
                new_comp['text'] = body_text
                if body_examples:
                    # A Meta espera um array de arrays para o body_text
                    new_comp['example'] = {"body_text": [body_examples]}
                elif 'example' in new_comp:
                    del new_comp['example']
            
            elif comp['type'] == 'HEADER' and comp.get('format') == 'TEXT':
                # Preservar texto do header ou permitir edição simples se implementado futuramente
                if header_example:
                    new_comp['example'] = {"header_text": [header_example]}
            
            # Botões e outros componentes são mantidos como estão (ou editados via POST se adicionarmos campos)
            new_components.append(new_comp)
        
        result = api.update_template(template_id, category, new_components)
        
        if 'error' in result:
            messages.error(request, f"Erro ao atualizar: {result['error'].get('message', 'Erro desconhecido')}")
        else:
            messages.success(request, f"Template '{template.get('name')}' enviado para revisão.")
            return redirect('integracoes:whatsapp_template_list')

    # Extrair dados para o template
    body_text = ""
    body_examples = []
    header_text = ""
    header_example = ""
    header_format = ""
    buttons = []

    for comp in template.get('components', []):
        if comp['type'] == 'BODY':
            body_text = comp.get('text', "")
            # Extrair exemplos existentes
            example_data = comp.get('example', {}).get('body_text', [])
            if example_data and isinstance(example_data[0], list):
                body_examples = example_data[0]
        
        elif comp['type'] == 'HEADER':
            header_format = comp.get('format', "")
            header_text = comp.get('text', "")
            
            # Tenta extrair exemplo baseado no formato
            example_obj = comp.get('example', {})
            if header_format == 'TEXT':
                example_data = example_obj.get('header_text', [])
                if example_data:
                    header_example = example_data[0]
            elif header_format in ['IMAGE', 'VIDEO', 'DOCUMENT']:
                example_data = example_obj.get('header_handle', [])
                if example_data:
                    header_example = example_data[0]
                
        elif comp['type'] == 'BUTTONS':
            buttons = comp.get('buttons', [])

    # Identificar quantas variáveis existem no body para gerar campos de exemplo
    body_vars_count = len(re.findall(r"\{\{\d+\}\}", body_text))
    # Garantir que a lista de exemplos tenha o tamanho correto
    while len(body_examples) < body_vars_count:
        body_examples.append("")

    return render(request, 'integracoes/whatsapp_template_edit.html', {
        'template': template,
        'body_text': body_text,
        'body_examples': body_examples[:body_vars_count],
        'header_text': header_text,
        'header_example': header_example,
        'header_format': header_format,
        'buttons': buttons,
        'config': config
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def whatsapp_template_delete(request, name):
    if request.method == 'POST':
        config = SystemConfig.load()
        if not config.meta_access_token or not config.meta_waba_id:
             messages.error(request, "Credenciais ausentes para realizar a exclusão.")
             return redirect('integracoes:whatsapp_template_list')

        api = MetaCloudAPI(config.meta_waba_id, config.meta_access_token)
        result = api.delete_template(name)
        
        if 'error' in result:
            messages.error(request, f"Erro ao excluir template: {result['error'].get('message', 'Erro desconhecido')}")
        else:
            messages.success(request, f"Template '{name}' excluído com sucesso.")
            
    return redirect('integracoes:whatsapp_template_list')

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
        sent_status, sent_notes = _process_chatwoot_budget_sent(payload)
        reply_status, reply_notes = _process_chatwoot_budget_reply(payload)
        confirmation_status, confirmation_notes = _process_chatwoot_confirmation_reply(payload)

        status_candidates = [sent_status, reply_status, confirmation_status]
        event_status = 'failed' if 'failed' in status_candidates else 'processed'
        event_notes = ' | '.join(note for note in [sent_notes, reply_notes, confirmation_notes] if note)

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


# --- RÉGUA DE COBRANÇA ---

def _get_meta_templates():
    config_obj = SystemConfig.load()
    api = MetaCloudAPI(config_obj.meta_waba_id, config_obj.meta_access_token)
    return api.get_templates().get('data', [])


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_sequence_list(request):
    sequences = CollectionSequence.objects.prefetch_related('steps__logs').all()
    recent_logs = (
        CollectionLog.objects
        .select_related('installment__billing__client', 'step__sequence')
        .order_by('-sent_at')[:50]
    )
    return render(request, 'integracoes/collection/sequence_list.html', {
        'sequences': sequences,
        'recent_logs': recent_logs,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_sequence_create(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        start_after = int(request.POST.get('start_after_days_overdue', 1))
        stop_after = int(request.POST.get('stop_after_days_overdue', 60))
        max_occ = int(request.POST.get('max_occurrences', 3))
        min_interval = int(request.POST.get('min_interval_days', 5))

        seq = CollectionSequence.objects.create(
            name=name,
            start_after_days_overdue=start_after,
            stop_after_days_overdue=stop_after,
            max_occurrences=max_occ,
            min_interval_days=min_interval,
        )
        messages.success(request, f'Régua "{name}" criada! Adicione as etapas abaixo.')
        return redirect('integracoes:collection_sequence_edit', pk=seq.pk)

    return render(request, 'integracoes/collection/sequence_form.html', {})


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_sequence_edit(request, pk):
    sequence = get_object_or_404(CollectionSequence, pk=pk)

    if request.method == 'POST':
        sequence.name = request.POST.get('name')
        sequence.start_after_days_overdue = int(request.POST.get('start_after_days_overdue', 1))
        sequence.stop_after_days_overdue = int(request.POST.get('stop_after_days_overdue', 60))
        sequence.max_occurrences = int(request.POST.get('max_occurrences', 3))
        sequence.min_interval_days = int(request.POST.get('min_interval_days', 5))
        sequence.is_active = request.POST.get('is_active') == 'on'
        sequence.save()
        messages.success(request, 'Régua atualizada!')
        return redirect('integracoes:collection_sequence_list')

    steps = sequence.steps.prefetch_related('variables').all()
    recent_logs = (
        CollectionLog.objects
        .filter(step__sequence=sequence)
        .select_related('installment__billing__client', 'step')
        .order_by('-sent_at')[:15]
    )
    return render(request, 'integracoes/collection/sequence_form.html', {
        'sequence': sequence,
        'steps': steps,
        'recent_logs': recent_logs,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_sequence_simulate(request, pk):
    """Simula o disparo da régua para hoje e retorna tabela de resultados via HTMX."""
    from datetime import timedelta
    from integracoes.models import CollectionInstallmentState
    from integracoes.utils import get_client_phone
    from services.models import Installment

    sequence = get_object_or_404(CollectionSequence, pk=pk)
    today = timezone.localdate()

    max_due_date = today - timedelta(days=sequence.start_after_days_overdue)
    min_due_date = today - timedelta(days=sequence.stop_after_days_overdue)

    installments = (
        Installment.objects
        .filter(
            due_date__lte=max_due_date,
            due_date__gte=min_due_date,
            status__in=['PENDENTE', 'PARCIAL', 'ATRASADO'],
        )
        .select_related('billing__client')
        .prefetch_related('billing__client__phones', 'gateway_charges')
    )

    results = []
    for installment in installments:
        state = CollectionInstallmentState.objects.filter(installment=installment).first()

        skip_reason = None
        if state and state.sequence_id != sequence.id:
            skip_reason = 'Em outra régua'
        elif state and state.is_paused:
            skip_reason = 'Pausado'
        elif state and state.current_occurrence >= sequence.max_occurrences:
            skip_reason = 'Máximo de cobranças atingido'
        elif state and state.next_eligible_date and today < state.next_eligible_date:
            skip_reason = f'Aguardando até {state.next_eligible_date.strftime("%d/%m")}'

        current_occ = state.current_occurrence if state else 0
        step = sequence.steps.filter(occurrence__gt=current_occ).order_by('occurrence').first()
        if not step and not skip_reason:
            skip_reason = 'Sem próxima etapa'

        client = getattr(getattr(installment, 'billing', None), 'client', None)
        phone = get_client_phone(client)

        results.append({
            'installment': installment,
            'client': client,
            'phone': phone,
            'step': step,
            'state': state,
            'skip_reason': skip_reason,
            'would_send': not skip_reason and bool(phone) and bool(step),
        })

    results.sort(key=lambda r: (not r['would_send'], r['installment'].due_date))

    return render(request, 'integracoes/collection/partials/simulate_result.html', {
        'sequence': sequence,
        'results': results,
        'today': today,
        'send_count': sum(1 for r in results if r['would_send']),
        'skip_count': sum(1 for r in results if not r['would_send']),
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_sequence_delete(request, pk):
    sequence = get_object_or_404(CollectionSequence, pk=pk)
    if request.method == 'POST':
        sequence.delete()
        messages.success(request, 'Régua removida.')
    return redirect('integracoes:collection_sequence_list')


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_step_create(request, seq_pk):
    sequence = get_object_or_404(CollectionSequence, pk=seq_pk)
    templates = _get_meta_templates()
    next_occurrence = sequence.steps.count() + 1

    if request.method == 'POST':
        occurrence = int(request.POST.get('occurrence', next_occurrence))
        label = request.POST.get('label', '')
        template_name = request.POST.get('template_name')
        wait_days = int(request.POST.get('wait_days_before_next', 7))

        step = CollectionStep.objects.create(
            sequence=sequence,
            occurrence=occurrence,
            label=label,
            template_name=template_name,
            wait_days_before_next=wait_days,
        )

        for i, path in zip(request.POST.getlist('var_index[]'), request.POST.getlist('var_path[]')):
            if path:
                CollectionStepVariable.objects.create(step=step, index=i, field_path=path, component='BODY')
        for i, path in zip(request.POST.getlist('btn_var_index[]'), request.POST.getlist('btn_var_path[]')):
            if path:
                CollectionStepVariable.objects.create(step=step, index=i, field_path=path, component='BUTTON')

        messages.success(request, f'Etapa #{occurrence} adicionada!')
        return redirect('integracoes:collection_sequence_edit', pk=seq_pk)

    return render(request, 'integracoes/collection/step_form.html', {
        'sequence': sequence,
        'templates': templates,
        'next_occurrence': next_occurrence,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_step_edit(request, pk):
    step = get_object_or_404(CollectionStep, pk=pk)
    templates = _get_meta_templates()

    if request.method == 'POST':
        step.occurrence = int(request.POST.get('occurrence', step.occurrence))
        step.label = request.POST.get('label', '')
        step.template_name = request.POST.get('template_name')
        step.wait_days_before_next = int(request.POST.get('wait_days_before_next', 7))
        step.save()

        step.variables.all().delete()
        for i, path in zip(request.POST.getlist('var_index[]'), request.POST.getlist('var_path[]')):
            if path:
                CollectionStepVariable.objects.create(step=step, index=i, field_path=path, component='BODY')
        for i, path in zip(request.POST.getlist('btn_var_index[]'), request.POST.getlist('btn_var_path[]')):
            if path:
                CollectionStepVariable.objects.create(step=step, index=i, field_path=path, component='BUTTON')

        messages.success(request, f'Etapa #{step.occurrence} atualizada!')
        return redirect('integracoes:collection_sequence_edit', pk=step.sequence_id)

    return render(request, 'integracoes/collection/step_form.html', {
        'step': step,
        'sequence': step.sequence,
        'templates': templates,
        'next_occurrence': step.occurrence,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def collection_step_delete(request, pk):
    step = get_object_or_404(CollectionStep, pk=pk)
    seq_pk = step.sequence_id
    if request.method == 'POST':
        step.delete()
        messages.success(request, 'Etapa removida.')
    return redirect('integracoes:collection_sequence_edit', pk=seq_pk)


# --- LEMBRETES AGENDADOS ---

@login_required
@user_passes_test(lambda u: u.is_staff)
def scheduled_reminder_list(request):
    reminders = ScheduledReminder.objects.prefetch_related('variables').all()
    recent_logs = (
        ScheduledReminderLog.objects
        .select_related('installment__billing__client', 'reminder')
        .order_by('-sent_at')[:50]
    )
    return render(request, 'integracoes/collection/scheduled_reminder_list.html', {
        'reminders': reminders,
        'recent_logs': recent_logs,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def scheduled_reminder_create(request):
    templates = _get_meta_templates()

    if request.method == 'POST':
        name = request.POST.get('name')
        offset_days = int(request.POST.get('offset_days', -1))
        template_name = request.POST.get('template_name')

        reminder = ScheduledReminder.objects.create(
            name=name,
            offset_days=offset_days,
            template_name=template_name,
        )

        for i, path in zip(request.POST.getlist('var_index[]'), request.POST.getlist('var_path[]')):
            if path:
                ScheduledReminderVariable.objects.create(reminder=reminder, index=i, field_path=path, component='BODY')
        for i, path in zip(request.POST.getlist('btn_var_index[]'), request.POST.getlist('btn_var_path[]')):
            if path:
                ScheduledReminderVariable.objects.create(reminder=reminder, index=i, field_path=path, component='BUTTON')

        messages.success(request, f'Lembrete "{name}" criado!')
        return redirect('integracoes:scheduled_reminder_list')

    return render(request, 'integracoes/collection/scheduled_reminder_form.html', {
        'templates': templates,
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def scheduled_reminder_edit(request, pk):
    reminder = get_object_or_404(ScheduledReminder, pk=pk)
    templates = _get_meta_templates()

    if request.method == 'POST':
        reminder.name = request.POST.get('name')
        reminder.offset_days = int(request.POST.get('offset_days', -1))
        reminder.template_name = request.POST.get('template_name')
        reminder.is_active = request.POST.get('is_active') == 'on'
        reminder.save()

        reminder.variables.all().delete()
        for i, path in zip(request.POST.getlist('var_index[]'), request.POST.getlist('var_path[]')):
            if path:
                ScheduledReminderVariable.objects.create(reminder=reminder, index=i, field_path=path, component='BODY')
        for i, path in zip(request.POST.getlist('btn_var_index[]'), request.POST.getlist('btn_var_path[]')):
            if path:
                ScheduledReminderVariable.objects.create(reminder=reminder, index=i, field_path=path, component='BUTTON')

        messages.success(request, 'Lembrete atualizado!')
        return redirect('integracoes:scheduled_reminder_list')

    return render(request, 'integracoes/collection/scheduled_reminder_form.html', {
        'reminder': reminder,
        'templates': templates,
        'variables': reminder.variables.all(),
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def scheduled_reminder_delete(request, pk):
    reminder = get_object_or_404(ScheduledReminder, pk=pk)
    if request.method == 'POST':
        reminder.delete()
        messages.success(request, 'Lembrete removido.')
    return redirect('integracoes:scheduled_reminder_list')


# --- FATURAS MANUAIS DA PLATAFORMA (fluxo ativo até completar 6 meses de conta) ---

@login_required
@user_passes_test(lambda u: u.is_manager)
def platform_invoice_list(request):
    PlatformInvoice.ensure_six_month_plan()
    invoices = PlatformInvoice.objects.all()
    return render(request, 'integracoes/platform_invoice_list.html', {
        'invoices': invoices,
    })


@login_required
@user_passes_test(lambda u: u.is_manager)
def platform_invoice_generate_pix(request, pk):
    if request.method != 'POST':
        return redirect('integracoes:platform_invoice_list')

    invoice = get_object_or_404(PlatformInvoice, pk=pk)
    if invoice.asaas_charge_id:
        messages.warning(request, 'O Pix desta fatura já foi gerado.')
        return redirect('integracoes:platform_invoice_list')

    config = SystemConfig.load()

    try:
        gw = AsaasGateway()
        charge = gw.create_charge(ChargeData(
            customer_name=config.company_name,
            customer_document=config.company_cnpj,
            customer_email='',
            description=getattr(settings, 'PLATFORM_SUBSCRIPTION_DESCRIPTION', 'Assinatura da Plataforma'),
            amount=Decimal(invoice.value_cents) / 100,
            due_date=invoice.due_date,
            method='PIX',
            external_reference=f'platform-invoice-{invoice.pk}',
        ))
    except Exception as e:
        logger.exception('Falha ao gerar Pix da fatura da plataforma')
        messages.error(request, f'Não foi possível gerar o Pix: {e}')
        return redirect('integracoes:platform_invoice_list')

    invoice.asaas_charge_id = charge.external_id
    invoice.qr_code = charge.pix_copy_paste
    invoice.qr_code_base64 = charge.pix_qrcode
    invoice.status = PlatformInvoice.Status.AGUARDANDO_PAGAMENTO
    invoice.save()

    messages.success(request, 'Pix gerado! Escaneie o QR Code para pagar esta fatura.')
    return redirect('integracoes:platform_invoice_list')


# --- ASSINATURA DA PLATAFORMA (PIX RECORRENTE / ASAAS) ---
# Fica pausado até a conta Asaas completar 6 meses (exigência do Pix
# Automático) — não está ligado no menu, mas o fluxo continua funcional.
# O webhook de confirmação dos ciclos passa pela MESMA rota já configurada
# no painel Asaas (pagamentos:asaas_webhook) — ver
# pagamentos/views.py:_handle_platform_subscription_webhook. Não existe (e
# não pode existir) uma rota de webhook dedicada aqui, porque o Asaas só
# aceita uma URL de webhook cadastrada.


def _parse_asaas_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@login_required
@user_passes_test(lambda u: u.is_manager)
def platform_subscription_status(request):
    subscription = PlatformSubscription.load()
    events = subscription.events.all()[:50]
    return render(request, 'integracoes/platform_subscription_status.html', {
        'subscription': subscription,
        'events': events,
    })


@login_required
@user_passes_test(lambda u: u.is_manager)
def platform_subscription_create(request):
    if request.method != 'POST':
        return redirect('integracoes:platform_subscription_status')

    subscription = PlatformSubscription.load()
    if subscription.status in [
        PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO,
        PlatformSubscription.Status.ATIVA,
        PlatformSubscription.Status.ATRASADA,
    ]:
        messages.warning(request, 'Já existe uma assinatura em andamento.')
        return redirect('integracoes:platform_subscription_status')

    config = SystemConfig.load()
    value_cents = getattr(settings, 'PLATFORM_SUBSCRIPTION_VALUE_CENTS', 0)
    cycle = getattr(settings, 'PLATFORM_SUBSCRIPTION_CYCLE', 'MONTHLY')

    # Não passamos webhook_url aqui: no Asaas o webhook é configurado uma
    # única vez no painel da conta (é o mesmo já usado por
    # pagamentos:asaas_webhook), não por chamada de API — diferente da
    # PushinPay, que exigia informar a URL a cada cobrança/assinatura.
    try:
        gw = AsaasGateway()
        result = gw.create_subscription(
            customer_name=config.company_name,
            customer_document=config.company_cnpj,
            value=Decimal(value_cents) / 100,
            cycle=cycle,
            description=getattr(settings, 'PLATFORM_SUBSCRIPTION_DESCRIPTION', 'Assinatura da Plataforma'),
        )
    except Exception as e:
        logger.exception('Falha ao criar assinatura Asaas')
        messages.error(request, f'Não foi possível criar a assinatura: {e}')
        return redirect('integracoes:platform_subscription_status')

    subscription.subscription_id = result['subscription_id']
    subscription.first_charge_id = result['first_charge_id']
    subscription.qr_code = result['qr_code']
    subscription.qr_code_base64 = result['qr_code_base64']
    subscription.value_cents = value_cents
    subscription.cycle = cycle
    subscription.next_due_date = _parse_asaas_date(result.get('next_due_date'))
    subscription.status = PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO
    subscription.last_event_at = timezone.now()
    subscription.save()

    PlatformSubscriptionEvent.objects.create(
        subscription=subscription,
        charge_id=subscription.first_charge_id,
        raw_event='created',
        mapped_status=PlatformSubscription.Status.AGUARDANDO_PRIMEIRO_PAGAMENTO,
        payload=result,
        notes='Assinatura criada — aguardando primeiro pagamento.',
    )

    messages.success(request, 'Assinatura criada! Escaneie o QR Code para pagar o primeiro ciclo.')
    return redirect('integracoes:platform_subscription_status')
