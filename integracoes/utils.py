import logging
from django.db.models import Model
from .models import NotificationConfig, NotificationVariable
from .chatwoot_client import ChatwootClient

logger = logging.getLogger(__name__)

def resolve_field_path(instance, path):
    """
    Resolve um caminho de campo separado por pontos (ex: 'client_property.client.name').
    Suporta atributos e propriedades.
    """
    if not path or path == 'self':
        return instance
    
    parts = path.split('.')
    current = instance
    for part in parts:
        try:
            if current is None:
                return None
            
            # Tenta pegar como atributo
            value = getattr(current, part)
            
            # Se for um callable (como uma property ou método simples sem args)
            if callable(value) and not isinstance(value, Model):
                current = value()
            else:
                current = value
        except (AttributeError, TypeError, ValueError):
            logger.warning(f"Não foi possível resolver '{part}' em {current} para o caminho '{path}'")
            return None
    return current

def get_client_phone(client_obj):
    """
    Tenta encontrar o telefone principal do objeto Cliente.
    """
    if not client_obj:
        return None
    
    # Se o objeto já for uma string (talvez o caminho resolveu direto para o telefone)
    if isinstance(client_obj, str):
        return client_obj
        
    # Tenta buscar pelo related name 'phones' (conforme models.py)
    try:
        if hasattr(client_obj, 'phones'):
            primary_phone = client_obj.phones.filter(is_primary=True).first()
            if primary_phone:
                return primary_phone.phone
            
            # Se não tem principal, pega o primeiro
            any_phone = client_obj.phones.first()
            if any_phone:
                return any_phone.phone
                
        # Se não tem o set 'phones', tenta o atributo 'phone' direto (ex: no Professional)
        if hasattr(client_obj, 'phone'):
            return client_obj.phone
    except Exception as e:
        logger.error(f"Erro ao buscar telefone do cliente: {e}")
        
    return None

def dispatch_dynamic_notification(instance, event_type, old_status=None):
    """
    Encontra e dispara notificações baseadas na configuração.
    """
    model_name = instance.__class__.__name__
    new_status = getattr(instance, 'status', None)
    
    # Busca configurações ativas para este modelo e evento
    configs = NotificationConfig.objects.filter(
        model_name=model_name,
        event_type=event_type,
        is_active=True
    )
    
    if not configs.exists():
        return
        
    client = ChatwootClient()
    
    for config in configs:
        # Validação adicional para alteração de status
        if event_type == 'MUDANCA_STATUS':
            # Se o status de destino da config for definido, deve bater com o novo status
            if config.to_status and str(new_status) != str(config.to_status):
                continue
            
            # Se o status de origem da config for definido, deve bater com o status anterior
            if config.from_status and str(old_status) != str(config.from_status):
                continue

        # 1. Resolver Destinatário
        target_obj = resolve_field_path(instance, config.phone_field_path)
        phone = get_client_phone(target_obj)
        
        if not phone:
            logger.warning(f"Notificação '{config.name}' ignorada: Telefone não encontrado para {instance}")
            continue
            
        # 2. Resolver Variáveis
        variables = []
        # Ordenar por índice para garantir {{1}}, {{2}}...
        mapping_vars = config.variables.all().order_by('index')
        for var in mapping_vars:
            val = resolve_field_path(instance, var.field_path)
            variables.append(str(val) if val is not None else "")

        # 3. Enviar via Chatwoot/WhatsApp
        try:
            # Busca ou cria contato no Chatwoot
            contact_name = resolve_field_path(target_obj, 'name') or resolve_field_path(target_obj, 'display_name') or "Cliente"
            cw_contact = client.create_contact(str(contact_name), phone)
            
            if cw_contact:
                conv = client.get_or_create_conversation(cw_contact['id'])
                if conv:
                    client.send_template(
                        conversation_id=conv['id'],
                        template_name=config.template_name,
                        variables=variables
                    )
                    logger.info(f"Notificação dinâmica '{config.name}' enviada para {phone}")
        except Exception as e:
            logger.exception(f"Erro ao disparar notificação dinâmica '{config.name}': {e}")
