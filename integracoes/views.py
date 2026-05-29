import json
import hmac
import hashlib
import logging
import re
import unicodedata
import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import WebhookEvent, SystemConfig
from .chatwoot_client import ChatwootClient
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
        return ServiceOrderTask.WhatsAppConfirmationStatus.RESCHEDULE

    if any(keyword in text for keyword in confirm_keywords) or any(keyword in words for keyword in confirm_keywords):
        return ServiceOrderTask.WhatsAppConfirmationStatus.CONFIRMED

    return None


def _build_confirmation_response_label(status):
    if status == ServiceOrderTask.WhatsAppConfirmationStatus.CONFIRMED:
        return "confirmado"
    if status == ServiceOrderTask.WhatsAppConfirmationStatus.RESCHEDULE:
        return "reagendar"
    return None


def _is_chatwoot_client_confirmation_reply(payload):
    return _is_chatwoot_client_budget_reply(payload)


def _resolve_order_status_from_budget_decision(is_approved):
    if is_approved:
        return ServiceOrder.Status.APPROVED_WAITING_SCHEDULE
    return ServiceOrder.Status.REJECTED_BY_CLIENT


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
                ServiceOrder.Status.BUDGET_DONE_WAITING_SEND,
                ServiceOrder.Status.WAITING_APPROVAL,
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
                ServiceOrder.Status.BUDGET_DONE_WAITING_SEND,
                ServiceOrder.Status.WAITING_APPROVAL,
            ]
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
                ServiceOrderTask.WhatsAppConfirmationStatus.SENT,
                ServiceOrderTask.WhatsAppConfirmationStatus.WAITING,
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
        try:
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
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
    else:
        # Opcional: Logar sucesso de sincronização silenciosamente ou com mensagem
        pass

    return render(request, 'integracoes/whatsapp_template_list.html', {
        'templates': templates,
        'config': config
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
                    btn['url'] = button_urls[i]
                elif b_type == 'PHONE_NUMBER':
                    btn['phone_number'] = button_phones[i]
                
                buttons.append(btn)
            
            if buttons:
                components.append({"type": "BUTTONS", "buttons": buttons})
        
        result = api.create_template(name, language, category, components)
        
        if 'error' in result:
            messages.error(request, f"Erro ao criar template: {result['error'].get('message', 'Erro desconhecido')}")
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
