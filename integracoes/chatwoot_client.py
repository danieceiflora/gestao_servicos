import requests
import json
import logging
import sys
import re
import unicodedata
from django.conf import settings
from .models import SystemConfig

logger = logging.getLogger(__name__)

class ChatwootClient:
    def __init__(self):
        self.config = SystemConfig.load()
        self.base_url = self.config.chatwoot_base_url.rstrip('/')
        self.account_id = self.config.chatwoot_account_id
        self.inbox_id = self.config.chatwoot_inbox_id
        self.token = self.config.chatwoot_api_token
        
        self.headers = {
            "api_access_token": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_api_url(self, endpoint):
        return f"{self.base_url}/api/v1/accounts/{self.account_id}/{endpoint}"

    def normalize_label_title(self, title):
        text = unicodedata.normalize("NFKD", str(title or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower().strip()
        text = re.sub(r"\s+", "-", text)
        text = re.sub(r"[^a-z0-9_-]", "", text)
        text = re.sub(r"-{2,}", "-", text).strip("-_")
        return text

    def list_labels(self):
        url = self._get_api_url("labels")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code >= 400:
                logger.warning("Falha ao listar labels no Chatwoot. status=%s body=%s", response.status_code, response.text)
                return []

            data = response.json()
            payload = data.get("payload")
            if isinstance(payload, list):
                return payload
            return []
        except Exception:
            logger.exception("Erro ao listar labels no Chatwoot")
            return []

    def get_label_by_title(self, title):
        target = self.normalize_label_title(title)
        if not target:
            return None

        for label in self.list_labels():
            label_title = self.normalize_label_title(label.get("title"))
            if label_title == target:
                return label
        return None

    def create_label(self, title, description=None, color="#1f93ff", show_on_sidebar=True):
        label_title = self.normalize_label_title(title)
        if not label_title:
            return None

        url = self._get_api_url("labels")
        payload = {
            "title": label_title,
            "description": description or f"Etiqueta criada automaticamente para fluxo de orçamento: {label_title}",
            "color": color,
            "show_on_sidebar": bool(show_on_sidebar),
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if response.status_code >= 400:
                logger.warning("Falha ao criar label no Chatwoot. title=%s status=%s body=%s", label_title, response.status_code, response.text)
                return None

            data = response.json()
            if isinstance(data, dict):
                if isinstance(data.get("payload"), dict):
                    return data["payload"]
                if data.get("title"):
                    return data
            return None
        except Exception:
            logger.exception("Erro ao criar label no Chatwoot. title=%s", label_title)
            return None

    def list_conversation_labels(self, conversation_id):
        if conversation_id in (None, ""):
            return []

        url = self._get_api_url(f"conversations/{conversation_id}/labels")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code >= 400:
                logger.warning(
                    "Falha ao listar labels da conversa no Chatwoot. conversation_id=%s status=%s body=%s",
                    conversation_id,
                    response.status_code,
                    response.text
                )
                return []

            data = response.json()
            payload = data.get("payload")
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
            return []
        except Exception:
            logger.exception("Erro ao listar labels da conversa no Chatwoot. conversation_id=%s", conversation_id)
            return []

    def assign_labels_to_conversation(self, conversation_id, labels):
        if conversation_id in (None, ""):
            return None

        normalized_labels = []
        for label in labels or []:
            text = self.normalize_label_title(label)
            if text and text not in normalized_labels:
                normalized_labels.append(text)

        if not normalized_labels:
            return None

        url = self._get_api_url(f"conversations/{conversation_id}/labels")
        payload = {"labels": normalized_labels}

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if response.status_code >= 400:
                logger.warning(
                    "Falha ao atribuir labels à conversa no Chatwoot. conversation_id=%s status=%s body=%s",
                    conversation_id,
                    response.status_code,
                    response.text
                )
                return None

            data = response.json()
            if isinstance(data, dict):
                payload = data.get("payload")
                if isinstance(payload, list):
                    return payload
            return normalized_labels
        except Exception:
            logger.exception("Erro ao atribuir labels à conversa no Chatwoot. conversation_id=%s", conversation_id)
            return None

    def assign_label_to_conversation(self, conversation_id, label_title):
        label_title = self.normalize_label_title(label_title)
        if not label_title:
            return None

        # A API do Chatwoot sobrescreve as etiquetas da conversa.
        # Por regra de negócio, sempre mantemos apenas a etiqueta mais recente.
        return self.assign_labels_to_conversation(conversation_id, [label_title])

    def extract_message_tracking(self, response_payload):
        if not isinstance(response_payload, dict):
            return None, None

        message_id = response_payload.get("id") or response_payload.get("source_id")
        conversation_id = response_payload.get("conversation_id")

        conversation = response_payload.get("conversation")
        if not conversation_id and isinstance(conversation, dict):
            conversation_id = conversation.get("id")

        message_id = str(message_id) if message_id is not None else None
        conversation_id = str(conversation_id) if conversation_id is not None else None
        return message_id, conversation_id

    def get_meta_template(self, template_name):
        if not self.config.meta_waba_id or not self.config.meta_access_token:
            return None
        url = f"https://graph.facebook.com/v20.0/{self.config.meta_waba_id}/message_templates"
        params = {"name": template_name, "access_token": self.config.meta_access_token}
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            if data.get('data'):
                for t in data['data']:
                    if t['status'] == 'APPROVED': return t
        except: pass
        return None

    def _normalize_phone_for_search(self, phone):
        if not phone: return []
        clean_phone = phone.strip().replace(" ", "").replace("-", "")
        digits = "".join(filter(str.isdigit, clean_phone))
        variations = []
        if clean_phone.startswith("+"): variations.append(clean_phone)
        else: variations.append(f"+{digits}")
        variations.append(digits)
        if len(clean_phone) == 14 and clean_phone.startswith("+55") and clean_phone[5] == '9':
            short_phone = clean_phone[:5] + clean_phone[6:]
            variations.append(short_phone)
            variations.append(short_phone.replace("+", ""))
        return list(dict.fromkeys(variations))

    def search_contact(self, phone):
        url = self._get_api_url("contacts/search")
        variations = self._normalize_phone_for_search(phone)
        for q in variations:
            try:
                response = requests.get(url, headers=self.headers, params={"q": q}, timeout=10)
                data = response.json()
                if data['payload']: return data['payload'][0]
            except: pass
        return None

    def create_contact(self, name, phone):
        url = self._get_api_url("contacts")
        digits = "".join(filter(str.isdigit, phone))
        if not digits.startswith("55") and len(digits) <= 11: digits = "55" + digits
        formatted_phone = f"+{digits}"
        payload = {"name": name, "phone_number": formatted_phone, "inbox_id": self.inbox_id}
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if response.status_code == 422: return self.search_contact(formatted_phone)
            return response.json()['payload']['contact']
        except: return None

    def get_or_create_conversation(self, contact_id):
        url_search = self._get_api_url(f"contacts/{contact_id}/conversations")
        try:
            resp = requests.get(url_search, headers=self.headers, timeout=10)
            conversations = resp.json()['payload']
            if conversations:
                for conv in conversations:
                    if conv['status'] in ['open', 'pending']: return conv
        except: pass
        url_create = self._get_api_url("conversations")
        payload = {"contact_id": contact_id, "inbox_id": self.inbox_id, "status": "open"}
        try:
            response = requests.post(url_create, headers=self.headers, json=payload, timeout=10)
            return response.json()
        except: return None

    def get_templates(self):
        endpoints = [f"inboxes/{self.inbox_id}/templates", "templates"]
        for endpoint in endpoints:
            url = self._get_api_url(endpoint)
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data: return data
            except: pass
        return []

    def _resolve_template_parameter_format(self, template_def, variables):
        body_comp = None
        if template_def:
            body_comp = next((c for c in template_def.get("components", []) if c.get("type") == "BODY"), None)
        body_text = body_comp.get("text", "") if body_comp else ""
        explicit_format = (template_def or {}).get("parameter_format")

        if explicit_format in {"POSITIONAL", "NAMED"}:
            return explicit_format

        if isinstance(variables, dict):
            return "NAMED"

        if re.search(r"\{\{\s*[a-zA-Z_]\w*\s*\}\}", body_text):
            return "NAMED"

        if re.search(r"\{\{\s*\d+\s*\}\}", body_text):
            return "POSITIONAL"

        return "POSITIONAL"

    def _build_template_body_params(self, template_def, variables, parameter_format):
        body_comp = None
        if template_def:
            body_comp = next((c for c in template_def.get("components", []) if c.get("type") == "BODY"), None)
        body_text = body_comp.get("text", "") if body_comp else ""
        vars_input = variables or []

        if parameter_format == "NAMED":
            if isinstance(vars_input, dict):
                return {str(k): str(v) for k, v in vars_input.items()}

            names = re.findall(r"\{\{\s*([a-zA-Z_]\w*)\s*\}\}", body_text)
            if names:
                return {name: str(value) for name, value in zip(names, vars_input)}

            # Fallback: mantém estrutura nomeada com índices em string
            return {str(i + 1): str(v) for i, v in enumerate(vars_input)}

        if isinstance(vars_input, dict):
            def sort_key(item):
                key = str(item[0]).strip()
                return int(key) if key.isdigit() else key

            return {str(k): str(v) for k, v in sorted(vars_input.items(), key=sort_key)}

        numbers = re.findall(r"\{\{\s*(\d+)\s*\}\}", body_text)
        if numbers and len(numbers) == len(vars_input):
            return {str(number): str(value) for number, value in zip(numbers, vars_input)}

        return {str(i + 1): str(v) for i, v in enumerate(vars_input)}

    def _upload_attachment_and_get_url(self, conversation_id, attachment):
        if not attachment:
            return None

        url = self._get_api_url(f"conversations/{conversation_id}/messages")
        headers = {"api_access_token": self.token}
        data = {
            "content": "upload-template-header",
            "message_type": "outgoing",
            "private": "true",
        }
        files = [('attachments[]', attachment)]

        try:
            response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
            if response.status_code >= 400:
                return None
            payload = response.json()
            attachments = payload.get("attachments") or []
            if not attachments:
                return None
            return attachments[0].get("data_url")
        except:
            return None

    def send_template(self, conversation_id, template_name, variables=None, attachment=None, content=None):
        """
        Envia um template HSM (via WhatsApp) usando o formato Flat Multipart exigido pelo Rails.
        """
        debug_log = f"\n[CALL] send_template: conv={conversation_id}, template={template_name}\n"
        url = self._get_api_url(f"conversations/{conversation_id}/messages")
        
        templates = self.get_templates()
        template_def = next((t for t in templates if t['name'].lower() == template_name.strip().lower()), None)
        if not template_def: template_def = self.get_meta_template(template_name)

        language = template_def.get('language', 'pt_BR') if template_def else "pt_BR"
        category = template_def.get('category', 'UTILITY') if template_def else "UTILITY"
        parameter_format = self._resolve_template_parameter_format(template_def, variables)
        body_params = self._build_template_body_params(template_def, variables, parameter_format)

        if not content or content == ".":
            if template_def:
                body_comp = next((c for c in template_def.get('components', []) if c['type'] == 'BODY'), None)
                content = body_comp['text'] if body_comp else f"Template: {template_name}"
                for key, value in body_params.items():
                    content = content.replace(f"{{{{{key}}}}}", str(value))

                buttons_comp = next((c for c in template_def.get("components", []) if c.get("type") == "BUTTONS"), None)
                button_texts = [b.get("text") for b in (buttons_comp or {}).get("buttons", []) if b.get("text")]
                if button_texts and "[Botões]:" not in content:
                    content = f"{content}\n\n[Botões]: {', '.join(button_texts)}"
            else:
                content = f"Enviando template {template_name}..."

        try:
            headers = {"api_access_token": self.token}
            uploaded_header_media_url = None
            if attachment:
                uploaded_header_media_url = self._upload_attachment_and_get_url(conversation_id, attachment)
             
            # FORMATO FLAT: O segredo para o erro "must be of type hash" no multipart
            data = {
                "content": content,
                "message_type": "template",
                "private": "false",
                "template_params[name]": template_name.strip(),
                "template_params[language]": language,
                "template_params[category]": category,
                "template_params[parameter_format]": parameter_format,
            }

            # Variáveis do Corpo no template_params
            for key, value in body_params.items():
                data[f"template_params[processed_params][body][{key}]"] = str(value)

            # Header no template_params
            if attachment:
                data["template_params[processed_params][header][media_type]"] = "document"
                if uploaded_header_media_url:
                    data["template_params[processed_params][header][media_url]"] = uploaded_header_media_url
                    data["template_params[processed_params][header][media_name]"] = attachment[0]

            # Content Attributes (Fallback/Legacy)
            data["content_attributes[template_name]"] = template_name.strip()
            data["content_attributes[template_language]"] = language
            for i, (key, value) in enumerate(body_params.items()):
                data[f"content_attributes[parameters][{i}][type]"] = "text"
                data[f"content_attributes[parameters][{i}][text]"] = str(value)
                if parameter_format == "NAMED":
                    data[f"content_attributes[parameters][{i}][parameter_name]"] = str(key)

            files = []

            debug_log += (
                f"Template format: {parameter_format}\n"
                f"Template body params: {json.dumps(body_params, ensure_ascii=False)}\n"
                f"Header media_url: {uploaded_header_media_url}\n"
                f"URL: {url}\nDATA: {json.dumps(data, indent=2, ensure_ascii=False)}\n"
            )
            
            response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
            res_json = response.json()
            
            if response.status_code >= 400:
                debug_log += f"ERROR {response.status_code}: {response.text}\n"
            else:
                debug_log += f"SUCCESS: {json.dumps(res_json, indent=2)}\n"
            
            return res_json if response.status_code < 400 else None

        except Exception as e:
            debug_log += f"EXCEPTION: {str(e)}\n"
            return None
        finally:
            with open("chatwoot_debug.log", "a", encoding="utf-8") as f:
                f.write("="*50 + debug_log + "="*50 + "\n")
            print(f"\n>>> DEBUG: Template {template_name} processado. Veja chatwoot_debug.log <<<", flush=True)
