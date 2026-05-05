import requests
import json
import logging
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

    def _normalize_phone_for_search(self, phone):
        """
        Retorna uma lista de variações de telefone para busca.
        """
        if not phone:
            return []
            
        # Remove espaços e hifens, mantém + se existir
        clean_phone = phone.strip().replace(" ", "").replace("-", "")
        
        # Garante que temos apenas dígitos para as variações
        digits = "".join(filter(str.isdigit, clean_phone))
        
        variations = []
        
        # 1. Formato E.164 completo (+55...)
        if clean_phone.startswith("+"):
            variations.append(clean_phone)
        else:
            variations.append(f"+{digits}")
            
        # 2. Formato sem +
        variations.append(digits)
        
        # 3. Fallback para 9º dígito (Brasil)
        # Se for +55... com 14 caracteres (incluindo +) e o 6º dígito for 9
        if len(clean_phone) == 14 and clean_phone.startswith("+55") and clean_phone[5] == '9':
            # Tenta sem o 9
            short_phone = clean_phone[:5] + clean_phone[6:]
            variations.append(short_phone)
            variations.append(short_phone.replace("+", ""))
            
        # 4. Caso inverso: se for 8 dígitos, tenta com 9 (se for celular)
        if len(clean_phone) == 13 and clean_phone.startswith("+55"):
            ddd = clean_phone[3:5]
            prefix = clean_phone[5]
            if prefix in "6789":
                long_phone = clean_phone[:5] + "9" + clean_phone[5:]
                variations.append(long_phone)
                variations.append(long_phone.replace("+", ""))

        # Remove duplicatas mantendo a ordem
        return list(dict.fromkeys(variations))

    def search_contact(self, phone):
        """
        Busca contato pelo telefone tentando diversas variações.
        """
        url = self._get_api_url("contacts/search")
        variations = self._normalize_phone_for_search(phone)
        
        for q in variations:
            try:
                response = requests.get(url, headers=self.headers, params={"q": q}, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data['payload']:
                    # Retorna o primeiro contato que tenha o telefone na busca
                    return data['payload'][0]
            except Exception as e:
                logger.warning(f"Erro na busca do contato com termo '{q}': {e}")
                
        return None

    def create_contact(self, name, phone):
        """Cria um novo contato no formato E.164"""
        url = self._get_api_url("contacts")
        
        # Garante formato +55...
        digits = "".join(filter(str.isdigit, phone))
        if not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits
        
        formatted_phone = f"+{digits}"
        
        payload = {
            "name": name,
            "phone_number": formatted_phone,
            "inbox_id": self.inbox_id
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if response.status_code == 422:
                # Provavelmente contato já existe. Tenta buscar uma última vez com o formato exato enviado.
                logger.info(f"Contato com telefone {formatted_phone} já parece existir (422). Buscando...")
                return self.search_contact(formatted_phone)
                
            response.raise_for_status()
            return response.json()['payload']['contact']
        except Exception as e:
            logger.error(f"Erro ao criar contato no Chatwoot: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Detalhes do erro: {e.response.text}")
            return None

    def get_or_create_conversation(self, contact_id):
        """Busca conversa ativa ou cria uma nova"""
        # Tenta buscar conversas existentes do contato
        url_search = self._get_api_url(f"contacts/{contact_id}/conversations")
        try:
            resp = requests.get(url_search, headers=self.headers, timeout=10)
            resp.raise_for_status()
            conversations = resp.json()['payload']
            if conversations:
                # Retorna a mais recente que esteja aberta ou pendente
                for conv in conversations:
                    if conv['status'] in ['open', 'pending']:
                        return conv
        except Exception as e:
            logger.error(f"Erro ao buscar conversas do contato {contact_id}: {e}")

        # Se não encontrou, cria uma nova
        url_create = self._get_api_url("conversations")
        payload = {
            "contact_id": contact_id,
            "inbox_id": self.inbox_id,
            "status": "open"
        }
        try:
            response = requests.post(url_create, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Erro ao criar conversa no Chatwoot: {e}")
            return None

    def send_message(self, conversation_id, content, message_type="outgoing", attachments=None):
        """
        Envia mensagem. 
        Para anexos, 'attachments' deve ser uma lista de arquivos (file-like objects ou caminhos).
        """
        url = self._get_api_url(f"conversations/{conversation_id}/messages")
        
        if attachments:
            # Chatwoot API usa multipart/form-data para anexos
            headers = {"api_access_token": self.token}
            data = {
                "content": content,
                "message_type": message_type,
                "private": "false"
            }
            files = []
            for i, attr in enumerate(attachments):
                # attr pode ser (filename, content, content_type)
                files.append(('attachments[]', attr))
            
            try:
                response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
                response.raise_for_status()
                resp_json = response.json()
                print(f"DEBUG Chatwoot send_message (with attachment) response: {json.dumps(resp_json, indent=2)}")
                return resp_json
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem com anexo no Chatwoot: {e}")
                return None
        else:
            payload = {
                "content": content,
                "message_type": message_type,
                "private": False
            }
            try:
                response = requests.post(url, headers=self.headers, json=payload, timeout=10)
                response.raise_for_status()
                resp_json = response.json()
                print(f"DEBUG Chatwoot send_message response: {json.dumps(resp_json, indent=2)}")
                return resp_json
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem no Chatwoot: {e}")
                return None

    def send_template(self, conversation_id, template_name, variables=None, attachment=None):
        """
        Envia um template HSM (via WhatsApp) com parâmetros e opcionalmente um anexo de cabeçalho.
        variables: lista de strings para os parâmetros do corpo do template.
        attachment: tupla (filename, content, content_type) para o documento do cabeçalho.
        """
        url = self._get_api_url(f"conversations/{conversation_id}/messages")
        
        # Prepara os parâmetros do template no formato esperado pelo Chatwoot (integração WhatsApp)
        params = [{"type": "text", "text": str(v)} for v in (variables or [])]
        
        content_attributes = {
            "template_name": template_name,
            "template_language": "pt_BR",
            "parameters": params
        }

        if attachment:
            # Para envios com anexo, usamos multipart/form-data
            headers = {"api_access_token": self.token}
            data = {
                "content": "", # Templates geralmente não precisam de content textual extra
                "message_type": "outgoing",
                "content_type": "template",
                "content_attributes": json.dumps(content_attributes),
                "private": "false"
            }
            files = [('attachments[]', attachment)]
            
            try:
                response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
                response.raise_for_status()
                resp_json = response.json()
                print(f"DEBUG Chatwoot send_template (with attachment) response: {json.dumps(resp_json, indent=2)}")
                return resp_json
            except Exception as e:
                logger.error(f"Erro ao enviar template com anexo no Chatwoot: {e}")
                if hasattr(e, 'response') and e.response:
                    logger.error(f"Detalhes do erro: {e.response.text}")
                return None
        else:
            # Envio simples via JSON
            payload = {
                "content": "",
                "message_type": "outgoing",
                "content_type": "template",
                "content_attributes": content_attributes,
                "private": False
            }
            try:
                response = requests.post(url, headers=self.headers, json=payload, timeout=10)
                response.raise_for_status()
                resp_json = response.json()
                print(f"DEBUG Chatwoot send_template response: {json.dumps(resp_json, indent=2)}")
                return resp_json
            except Exception as e:
                logger.error(f"Erro ao enviar template no Chatwoot: {e}")
                return None
