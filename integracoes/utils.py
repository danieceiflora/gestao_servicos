import logging
from django.db.models import Model
from .models import NotificationConfig, NotificationVariable
from .chatwoot_client import ChatwootClient

logger = logging.getLogger(__name__)

from django.apps import apps
from django.db.models import Model, ForeignKey

def get_mappable_fields(model_name, max_depth=3, only_phones=False):
    """
    Usa introspecção para retornar campos e relacionamentos úteis para mapeamento.
    Se only_phones=True, retorna uma lista curada e com labels amigáveis.
    """
    if only_phones:
        # Lista curada para facilitar a vida do usuário no seletor de destinatário
        # Note: Paramos no objeto que possui o telefone, o get_client_phone resolverá o resto.
        if model_name == 'ServiceOrder':
            return [
                ('client_property.client', 'Telefone do Cliente'),
                ('originator', 'Telefone do Vendedor/Originador'),
            ]
        elif model_name == 'ServiceOrderTask':
            return [
                ('service_order.client_property.client', 'Telefone do Cliente'),
                ('service_order.originator', 'Telefone do Vendedor/Originador'),
            ]
        elif model_name == 'Sale':
            return [
                ('client', 'Telefone do Cliente'),
                ('user', 'Telefone do Vendedor'),
            ]
        elif model_name == 'Billing':
            return [
                ('client', 'Telefone do Cliente'),
            ]
        elif model_name == 'Installment':
            return [
                ('billing.client', 'Telefone do Cliente'),
            ]
        elif model_name == 'ExpenseInstallment':
            # Despesas não têm cliente — usar Número Fixo (destinatário interno)
            return []

    try:
        model = apps.get_model('services', model_name)
    except LookupError:
        return []

    mappable = []

    def _get_fields(current_model, prefix='', depth=0):
        if depth > max_depth:
            return

        # 1. Campos Reais do Banco
        for field in current_model._meta.fields:
            path = f"{prefix}{field.name}"
            label = f"{prefix.replace('__', ' > ') if prefix else ''}{field.verbose_name or field.name}"
            
            # Pula campos internos ou IDs se não forem o primário
            if field.name in ['id', 'created_at', 'updated_at'] and depth > 0:
                continue
                
            mappable.append((path.replace('__', '.'), label))

            # Se for ForeignKey, desce um nível (se depth permitir)
            if isinstance(field, ForeignKey) and depth < max_depth:
                _get_fields(field.related_model, prefix=f"{path}__", depth=depth+1)

        # 2. Casos Especiais: Relacionamentos reversos e campos calculados
        if current_model.__name__ == 'Client':
            mappable.append((f"{prefix}phones.first.phone".replace('__', '.'), f"{prefix.replace('__', ' > ') if prefix else ''}Telefone/Whatsapp"))

        if current_model.__name__ == 'ServiceOrderTask':
            mappable.append((f"{prefix}team_display".replace('__', '.'), f"{prefix.replace('__', ' > ') if prefix else ''}Equipe Alocada"))

        # 3. Properties Úteis (manualmente selecionadas ou via convenção)
        common_props = [
            'total_value', 'display_name', 'full_address', 'balance_due', 'total_paid', 'number', 'phone',
            'amount_paid', 'amount_remaining', 'installment_label', 'get_remaining_balance', 'get_total_paid',
        ]
        for attr_name in dir(current_model):
            if attr_name in common_props or attr_name.startswith('get_') and attr_name.endswith('_display'):
                # Verifica se é property ou método sem argumentos
                try:
                    attr = getattr(current_model, attr_name)
                    if isinstance(attr, property) or callable(attr):
                        path = f"{prefix}{attr_name}"
                        label_name = attr_name.replace('get_', '').replace('_display', '').replace('_', ' ').title()
                        label = f"{prefix.replace('__', ' > ') if prefix else ''}{label_name}"
                        mappable.append((path.replace('__', '.'), label))
                except:
                    continue

    _get_fields(model)
    return sorted(list(set(mappable)), key=lambda x: x[1])

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
        if current is None:
            return None
        
        try:
            # Tenta pegar como atributo
            value = getattr(current, part)
            
            # Se for um callable (como uma property ou método simples sem args)
            # Mas não se for uma classe de Model (caso de ForeignKey sem instância?)
            if callable(value) and not isinstance(value, type) and not isinstance(value, Model):
                try:
                    current = value()
                except Exception as e:
                    logger.warning(f"Erro ao chamar '{part}' em {current}: {e}")
                    return None
            else:
                current = value
        except AttributeError:
            # Tenta ver se é um manager (reverse relationship) que não foi pego pelo getattr
            if hasattr(current, '_meta'):
                # Talvez seja um campo que não existe na instância mas existe no modelo?
                logger.warning(f"Campo '{part}' não encontrado em {current} (Tipo: {type(current)})")
            return None
        except Exception as e:
            logger.warning(f"Erro ao resolver '{part}' em {current}: {e}")
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
    from services.utils.pdf_generator import BudgetPDFGenerator, CompletionPDFGenerator, SalePDFGenerator
    
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
        if config.recipient_type == 'FIXED':
            phone = config.fixed_phone
            contact_name = "Gerente/Sistema"
        else:
            target_obj = resolve_field_path(instance, config.phone_field_path)
            phone = get_client_phone(target_obj)
            contact_name = resolve_field_path(target_obj, 'name') or resolve_field_path(target_obj, 'display_name') or "Cliente"
        
        if not phone:
            logger.warning(f"Notificação '{config.name}' ignorada: Telefone não encontrado para {instance}")
            continue
            
        # 2. Resolver Variáveis
        variables = []
        # Ordenar por índice para garantir {{1}}, {{2}}...
        mapping_vars = config.variables.all().order_by('index')
        for var in mapping_vars:
            val = resolve_field_path(instance, var.field_path)
            # Formatar data/hora se necessário
            if hasattr(val, 'strftime'):
                val = val.strftime('%d/%m/%Y %H:%M')
            variables.append(str(val) if val is not None else "")

        # 3. Resolver Mídia do Cabeçalho (Header)
        attachment = None
        if config.header_media_type != 'NONE':
            # Precisamos do ServiceOrder para gerar os PDFs
            order = instance if model_name == 'ServiceOrder' else getattr(instance, 'service_order', None)
            
            try:
                if config.header_media_type == 'BUDGET_PDF' and order:
                    pdf_gen = BudgetPDFGenerator(order)
                    pdf_content = pdf_gen.generate()
                    attachment = (f"Orcamento_{order.number}.pdf", pdf_content, "application/pdf")
                
                elif config.header_media_type == 'REPORT_PDF' and order:
                    pdf_gen = CompletionPDFGenerator(order)
                    pdf_content = pdf_gen.generate()
                    attachment = (f"Relatorio_{order.number}.pdf", pdf_content, "application/pdf")
                
                elif config.header_media_type == 'SALE_PDF':
                    sale = instance if model_name == 'Sale' else getattr(instance, 'venda', None) or getattr(instance, 'sale', None)
                    if sale:
                        pdf_gen = SalePDFGenerator(sale)
                        pdf_content = pdf_gen.generate()
                        attachment = (f"Venda_{sale.number}.pdf", pdf_content, "application/pdf")

                elif config.header_media_type == 'STATIC_PDF' and config.static_media_file:
                    file_name = config.static_media_file.name.split('/')[-1]
                    # Abrir o arquivo para leitura
                    with config.static_media_file.open('rb') as f:
                        attachment = (file_name, f.read(), "application/pdf")
            except Exception as e:
                logger.error(f"Erro ao gerar/carregar mídia para regra {config.name}: {e}")

        # 4. Enviar via Chatwoot/WhatsApp
        try:
            # Busca ou cria contato no Chatwoot
            cw_contact = client.create_contact(str(contact_name), phone)
            
            if cw_contact:
                conv = client.get_or_create_conversation(cw_contact['id'])
                if conv:
                    client.send_template(
                        conversation_id=conv['id'],
                        template_name=config.template_name,
                        variables=variables,
                        attachment=attachment
                    )
                    logger.info(f"Notificação dinâmica '{config.name}' enviada para {phone}")
        except Exception as e:
            logger.exception(f"Erro ao disparar notificação dinâmica '{config.name}': {e}")
