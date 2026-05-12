import logging
import threading
from django.utils import timezone
from .utils.pdf_generator import CompletionPDFGenerator
from integracoes.chatwoot_client import ChatwootClient
from integracoes.models import SystemConfig

logger = logging.getLogger(__name__)

def run_payment_request_workflow(service_order_id):
    """
    Função principal do workflow de cobrança. 
    Deve ser chamada preferencialmente em uma thread separada.
    """
    from .models import ServiceOrder # Import local para evitar circular import
    
    try:
        service_order = ServiceOrder.objects.get(id=service_order_id)
        
        # 1. Verificação de Segurança: Evitar reenvio
        if service_order.pix_sent_at:
            logger.info(f"Workflow abortado para OS #{service_order.number}: Cobrança já enviada em {service_order.pix_sent_at}")
            return

        config = SystemConfig.load()
        
        # 2. Verificar se as configurações necessárias existem
        if not all([config.chatwoot_pix_template, config.chatwoot_api_token]):
            logger.warning(f"Workflow abortado para OS #{service_order.number}: Configurações de PIX/Chatwoot incompletas.")
            return

        # 3. Gerar PDF de Execução
        logger.info(f"Gerando PDF de execução para OS #{service_order.number}")
        pdf_gen = CompletionPDFGenerator(service_order)
        pdf_content = pdf_gen.generate()
        
        # 4. Preparar Cliente Chatwoot
        client = ChatwootClient()
        customer = service_order.client_property.client
        primary_phone = customer.phones.filter(is_primary=True).first() or customer.phones.first()
        
        if not primary_phone:
            logger.error(f"Workflow abortado para OS #{service_order.number}: Cliente sem telefone cadastrado.")
            return

        # 5. Buscar ou Criar Contato e Conversa no Chatwoot
        contact = client.search_contact(primary_phone.phone)
        if not contact:
            contact = client.create_contact(customer.name, primary_phone.phone)
        
        if not contact:
            logger.error(f"Não foi possível localizar ou criar contato no Chatwoot para OS #{service_order.number}")
            return

        conversation = client.get_or_create_conversation(contact['id'])
        if not conversation:
            logger.error(f"Não foi possível abrir conversa no Chatwoot para OS #{service_order.number}")
            return

        conversation_id = conversation.get('id')

        # 6. Enviar Template de PIX com PDF Anexo (Header)
        # O attachment deve ser uma tupla (nome_arquivo, conteudo, tipo_mime)
        filename = f"Execucao_OS_{service_order.number}.pdf"
        attachment = (filename, pdf_content, 'application/pdf')
        
        logger.info(f"Enviando template {config.chatwoot_pix_template} para OS #{service_order.number}")
        
        # Formatação de valores
        total_value_float = float(service_order.balance_due)
        total_value_str = f"{total_value_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        # Variáveis do Corpo (4 variáveis conforme solicitado)
        # 1. numero os, 2. valor do serviço, 3. chave pix, 4. Banco + Destinatario
        body_variables = [
            str(service_order.number),
            total_value_str,            # Valor formatado
            config.pix_key,             # Chave Pix (Global)
            f"{config.pix_bank} - {config.pix_recipient}" # Banco e Destinatário combinados
        ]

        # Enviar Template com Header tipo PDF e sem botões
        response = client.send_template(
            conversation_id=conversation_id,
            template_name=config.chatwoot_pix_template,
            variables=body_variables,
            attachment=attachment,
            button_data=None
        )

        if response:
            # 7. Atribuir Etiqueta
            label = config.chatwoot_pix_label or "pix-enviado"
            client.assign_label_to_conversation(conversation_id, label)
            
            # 8. Marcar como enviado no banco
            service_order.pix_sent_at = timezone.now()
            service_order.save(update_fields=['pix_sent_at'])
            logger.info(f"Workflow concluído com sucesso para OS #{service_order.number}")
        else:
            logger.error(f"Falha ao enviar template de PIX para OS #{service_order.number}")

    except Exception as e:
        logger.exception(f"Erro crítico no workflow de pagamento da OS {service_order_id}: {str(e)}")

def trigger_payment_workflow(service_order):
    """
    Dispara o workflow em uma thread separada para não bloquear o processo principal.
    """
    thread = threading.Thread(
        target=run_payment_request_workflow,
        args=(service_order.id,),
        daemon=True
    )
    thread.start()
