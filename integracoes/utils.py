import logging
from django.db.models import Model
from .models import NotificationConfig, NotificationVariable
from .chatwoot_client import ChatwootClient

logger = logging.getLogger(__name__)

# Campos globais do SystemConfig disponíveis em todos os modelos.
# Prefixo __config__ é interceptado em resolve_field_path.
CONFIG_FIELDS = [
    ('__config__.company_name',    'Configurações Globais > Nome da Empresa'),
    ('__config__.company_cnpj',    'Configurações Globais > CNPJ'),
    ('__config__.company_phone',   'Configurações Globais > Telefone da Empresa'),
    ('__config__.company_address', 'Configurações Globais > Endereço da Empresa'),
    ('__config__.pix_key',         'Configurações Globais > Chave PIX'),
    ('__config__.pix_bank',        'Configurações Globais > Banco PIX'),
    ('__config__.pix_recipient',   'Configurações Globais > Destinatário PIX'),
]

# Campos mapeáveis por modelo — lista curada com labels amigáveis no formato "Grupo > Campo".
# A ordem dentro de cada grupo define a ordem de exibição no dropdown.
CURATED_FIELDS = {
    'ServiceOrder': [
        ('number',                                              'OS > Número'),
        ('get_status_display',                                  'OS > Status'),
        ('description',                                         'OS > Descrição'),
        ('total_value',                                         'OS > Valor Total'),
        ('created_at',                                          'OS > Data de Criação'),
        ('finished_at',                                         'OS > Data de Conclusão'),
        ('public_token',                                        'OS > Token da Página Pública (UUID puro)'),
        ('public_page_path',                                    'OS > Caminho da Página Pública (os/token/)'),
        ('public_page_url',                                     'OS > Link da Página Pública (URL completa)'),
        ('client_property.client.display_name',                 'Cliente > Nome Completo'),
        ('client_property.client.phones.first.phone',           'Cliente > Telefone / WhatsApp'),
        ('client_property.full_address',                        'Imóvel > Endereço Completo'),
        ('client_property.address',                             'Imóvel > Logradouro'),
        ('client_property.neighborhood',                        'Imóvel > Bairro'),
        ('client_property.city',                                'Imóvel > Cidade'),
        ('originator.name',                                     'Vendedor > Nome'),
    ],
    'ServiceOrderTask': [
        ('get_task_type_display',                               'Etapa > Tipo'),
        ('get_status_display',                                  'Etapa > Status'),
        ('scheduled_at',                                        'Etapa > Data Agendada'),
        ('started_at',                                          'Etapa > Início da Execução'),
        ('finished_at',                                         'Etapa > Conclusão'),
        ('notes',                                               'Etapa > Observações Técnicas'),
        ('team_display',                                        'Etapa > Equipe Alocada'),
        ('billing_value',                                       'Etapa > Valor da Etapa'),
        ('customer_name',                                       'Etapa > Nome do Signatário'),
        ('confirmation_token',                                  'Etapa > Token de Confirmação (sufixo URL)'),
        ('confirmation_url',                                    'Etapa > Link de Confirmação (URL completa)'),
        ('service_order.number',                                'OS > Número'),
        ('service_order.get_status_display',                    'OS > Status'),
        ('service_order.total_value',                           'OS > Valor Total'),
        ('service_order.description',                           'OS > Descrição'),
        ('service_order.public_token',                          'OS > Token da Página Pública (UUID puro)'),
        ('service_order.public_page_path',                      'OS > Caminho da Página Pública (os/token/)'),
        ('service_order.public_page_url',                       'OS > Link da Página Pública (URL completa)'),
        ('service_order.client_property.client.display_name',   'Cliente > Nome Completo'),
        ('service_order.client_property.client.phones.first.phone', 'Cliente > Telefone / WhatsApp'),
        ('service_order.client_property.full_address',          'Imóvel > Endereço Completo'),
        ('service_order.client_property.neighborhood',          'Imóvel > Bairro'),
        ('service_order.client_property.city',                  'Imóvel > Cidade'),
    ],
    'Sale': [
        ('number',                  'Venda > Número'),
        ('get_status_display',      'Venda > Status'),
        ('total_amount',            'Venda > Valor Total'),
        ('created_at',              'Venda > Data'),
        ('client.display_name',     'Cliente > Nome Completo'),
        ('client.phones.first.phone', 'Cliente > Telefone / WhatsApp'),
        ('user.get_full_name',      'Vendedor > Nome'),
        ('user.username',           'Vendedor > Usuário'),
    ],
    'Billing': [
        ('number',                  'Cobrança > Número'),
        ('get_status_display',      'Cobrança > Status'),
        ('total_amount',            'Cobrança > Valor Bruto'),
        ('get_remaining_balance',   'Cobrança > Saldo Devedor'),
        ('get_total_paid',          'Cobrança > Total Pago'),
        ('service_order.number',         'OS > Número'),
        ('service_order.public_token',    'OS > Token da Página Pública (UUID puro)'),
        ('service_order.public_page_path','OS > Caminho da Página Pública (os/token/)'),
        ('service_order.public_page_url', 'OS > Link da Página Pública (URL completa)'),
        ('client.display_name',          'Cliente > Nome Completo'),
        ('client.phones.first.phone',    'Cliente > Telefone / WhatsApp'),
    ],
    'Installment': [
        ('installment_number',          'Parcela > Número'),
        ('amount',                      'Parcela > Valor'),
        ('due_date',                    'Parcela > Vencimento'),
        ('get_status_display',          'Parcela > Status'),
        ('get_total_paid',              'Parcela > Total Pago'),
        ('get_remaining_balance',       'Parcela > Saldo Restante'),
        ('billing.number',              'Cobrança > Número'),
        ('billing.service_order.number','OS > Número'),
        ('billing.client.display_name', 'Cliente > Nome Completo'),
        ('billing.client.phones.first.phone', 'Cliente > Telefone / WhatsApp'),
        ('gateway_pix_code',            'PIX > Código Copia e Cola'),
        ('gateway_payment_link',        'PIX/Boleto > Link de Pagamento'),
        ('gateway_boleto_barcode',      'Boleto > Linha Digitável'),
    ],
    'ExpenseInstallment': [
        ('expense.description',         'Despesa > Descrição'),
        ('expense.supplier.display_name', 'Despesa > Fornecedor'),
        ('installment_number',          'Parcela > Número'),
        ('amount',                      'Parcela > Valor'),
        ('due_date',                    'Parcela > Vencimento'),
        ('get_status_display',          'Parcela > Status'),
        ('amount_paid',                 'Parcela > Valor Pago'),
        ('amount_remaining',            'Parcela > Saldo Restante'),
    ],
}

# Adiciona campos globais a todos os modelos
for _model_key in list(CURATED_FIELDS.keys()):
    CURATED_FIELDS[_model_key] = CURATED_FIELDS[_model_key] + CONFIG_FIELDS


def get_mappable_fields(model_name, max_depth=3, only_phones=False):
    """
    Retorna campos mapeáveis para o modelo informado.
    Se only_phones=True, retorna lista curada de caminhos que levam ao telefone do destinatário.
    """
    if only_phones:
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
            return [('client', 'Telefone do Cliente')]
        elif model_name == 'Installment':
            return [('billing.client', 'Telefone do Cliente')]
        elif model_name == 'ExpenseInstallment':
            return []

    return CURATED_FIELDS.get(model_name, [])

def resolve_field_path(instance, path):
    """
    Resolve um caminho de campo separado por pontos (ex: 'client_property.client.name').
    Suporta atributos e propriedades.
    Caminhos iniciados com '__config__.' resolvem a partir do SystemConfig singleton.
    """
    if not path or path == 'self':
        return instance

    if path.startswith('static:'):
        return path[len('static:'):]

    if path.startswith('__config__.'):
        from integracoes.models import SystemConfig
        config_instance = SystemConfig.load()
        remainder = path[len('__config__.'):]
        return resolve_field_path(config_instance, remainder)

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
        for var in config.variables.filter(component='BODY').order_by('index'):
            val = resolve_field_path(instance, var.field_path)
            if hasattr(val, 'strftime'):
                val = val.strftime('%d/%m/%Y %H:%M')
            variables.append(str(val) if val is not None else "")

        # Variáveis de botão (sufixo de URL dinâmica)
        btn_url_params = {}
        for var in config.variables.filter(component='BUTTON').order_by('index'):
            val = resolve_field_path(instance, var.field_path)
            btn_url_params[var.index] = str(val) if val is not None else ""

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
                    btn_data = None
                    if btn_url_params:
                        btn_data = {'type': 'url_suffix', 'params': btn_url_params}
                    client.send_template(
                        conversation_id=conv['id'],
                        template_name=config.template_name,
                        variables=variables,
                        attachment=attachment,
                        button_data=btn_data,
                    )
                    logger.info(f"Notificação dinâmica '{config.name}' enviada para {phone}")

                    # Persiste o conversation_id na task para permitir atualização
                    # de etiqueta Chatwoot quando o cliente responder via página pública.
                    if model_name == 'ServiceOrderTask':
                        from django.utils import timezone
                        instance.chatwoot_confirmation_conversation_id = str(conv['id'])
                        instance.whatsapp_notification_sent_at = timezone.now()
                        instance.whatsapp_confirmation_status = 'AGUARDANDO'
                        instance.save(update_fields=[
                            'chatwoot_confirmation_conversation_id',
                            'whatsapp_notification_sent_at',
                            'whatsapp_confirmation_status',
                        ])
        except Exception as e:
            logger.exception(f"Erro ao disparar notificação dinâmica '{config.name}': {e}")
