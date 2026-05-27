import logging
import threading
import time
from django.db import transaction
from django.utils import timezone
from .utils.pdf_generator import CompletionPDFGenerator
from integracoes.chatwoot_client import ChatwootClient
from integracoes.models import SystemConfig

logger = logging.getLogger(__name__)

def _clean_phone_number(phone):
    """Limpa o número de telefone para garantir formato E.164 básico."""
    if not phone:
        return ""
    digits = "".join(filter(str.isdigit, str(phone)))
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    return f"+{digits}"

def _get_order_payment_method(service_order):
    from .models import ServiceOrderTask
    exec_task = service_order.tasks.filter(
        task_type=ServiceOrderTask.TaskType.EXECUTION,
        payment_method__isnull=False
    ).order_by('scheduled_at').first()
    if exec_task and exec_task.payment_method:
        return exec_task.payment_method

    budget_task = service_order.tasks.filter(
        task_type=ServiceOrderTask.TaskType.BUDGET,
        payment_method__isnull=False
    ).order_by('scheduled_at').first()
    if budget_task and budget_task.payment_method:
        return budget_task.payment_method

    any_task = service_order.tasks.filter(
        payment_method__isnull=False
    ).order_by('scheduled_at').first()
    return any_task.payment_method if any_task else None

def _has_technician_payment(service_order):
    from .models import ServicePayment
    return service_order.payments.filter(
        status=ServicePayment.PaymentStatus.PENDING,
        amount__gt=0
    ).exists()

def run_payment_request_workflow(service_order_id):
    """
    Função principal do workflow de cobrança. 
    Deve ser chamada preferencialmente em uma thread separada.
    """
    from .models import ServiceOrder # Import local para evitar circular import
    
    lock_time = None
    sent_success = False
    try:
        service_order = ServiceOrder.objects.get(id=service_order_id)
        
        # 1. Verificação de Segurança: Evitar reenvio
        if service_order.pix_sent_at:
            logger.info(f"Workflow abortado para OS #{service_order.number}: Cobrança já enviada em {service_order.pix_sent_at}")
            return

        config = SystemConfig.load()

        if not config.chatwoot_api_token:
            logger.warning(f"Workflow abortado para OS #{service_order.number}: Token do Chatwoot não configurado.")
            return

        payment_method = _get_order_payment_method(service_order)
        has_technician_payment = _has_technician_payment(service_order)
        use_pix_flow = payment_method == 'PIX' and not has_technician_payment

        if use_pix_flow and not config.chatwoot_pix_template:
            logger.warning(f"Workflow abortado para OS #{service_order.number}: Template de PIX não configurado.")
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

        phone_number = _clean_phone_number(primary_phone.phone)

        # 5. Buscar ou Criar Contato e Conversa no Chatwoot
        contact = client.search_contact(phone_number)
        if not contact:
            contact = client.create_contact(customer.name, phone_number)
        
        if not contact:
            logger.error(f"Não foi possível localizar ou criar contato no Chatwoot para OS #{service_order.number}")
            return

        conversation = client.get_or_create_conversation(contact['id'])
        if not conversation:
            logger.error(f"Não foi possível abrir conversa no Chatwoot para OS #{service_order.number}")
            return

        conversation_id = conversation.get('id')

        # 6. Travar envio para evitar duplicidade (idempotência)
        lock_time = timezone.now()
        with transaction.atomic():
            claimed = ServiceOrder.objects.filter(
                id=service_order_id,
                pix_sent_at__isnull=True
            ).update(pix_sent_at=lock_time)
        if claimed == 0:
            logger.info(f"Workflow abortado para OS #{service_order.number}: Cobrança já enviada ou em andamento.")
            return

        # Pequeno delay para garantir que o Chatwoot/Meta sincronizou o contato/conversa
        # Isso reduz erros de 'Undeliverable' em envios imediatos
        time.sleep(2)

        # 7. Enviar Template com PDF Anexo (Header)
        # O attachment deve ser uma tupla (nome_arquivo, conteudo, tipo_mime)
        filename = f"Execucao_OS_{service_order.number}.pdf"
        attachment = (filename, pdf_content, 'application/pdf')
        
        if use_pix_flow:
            template_name = config.chatwoot_pix_template
            logger.info(f"Enviando template {template_name} para OS #{service_order.number}")
            
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
        else:
            template_name = "servico_finalizado_recebido_tecnico"
            logger.info(f"Enviando template {template_name} para OS #{service_order.number}")
            # O template espera apenas o número da OS como variável {{1}}
            body_variables = [str(service_order.number)]

        # Enviar Template com Header tipo PDF e sem botões
        response = client.send_template(
            conversation_id=conversation_id,
            template_name=template_name,
            variables=body_variables,
            attachment=attachment,
            button_data=None
        )

        if response:
            if use_pix_flow:
                # 7. Atribuir Etiqueta
                label = config.chatwoot_pix_label or "pix-enviado"
                client.assign_label_to_conversation(conversation_id, label)
            
            # 8. Marcar como enviado no banco
            ServiceOrder.objects.filter(id=service_order_id).update(pix_sent_at=timezone.now())
            sent_success = True
            logger.info(f"Workflow concluído com sucesso para OS #{service_order.number}")
        else:
            logger.error(f"Falha ao enviar template de finalização/cobrança para OS #{service_order.number}")

    except Exception as e:
        logger.exception(f"Erro crítico no workflow de pagamento da OS {service_order_id}: {str(e)}")
    finally:
        if lock_time and not sent_success:
            # Libera a trava se o envio falhar para permitir nova tentativa
            ServiceOrder.objects.filter(id=service_order_id, pix_sent_at=lock_time).update(pix_sent_at=None)


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

def run_payment_receipt_workflow(service_order_id):
    """
    Workflow para enviar mensagem de baixa de pagamento e avaliação,
    após a OS ser finalizada, sem pendências e com pagamento registrado.
    """
    from .models import ServiceOrder
    try:
        service_order = ServiceOrder.objects.get(id=service_order_id)

        # 1. Verificações de Elegibilidade
        if service_order.chatwoot_payment_receipt_sent_at:
            logger.info(f"Workflow de recibo abortado para OS #{service_order.number}: Já enviado.")
            return
            
        if service_order.status != ServiceOrder.Status.FINISHED:
            return

        has_pending_payment = service_order.payments.filter(status='PENDING').exists() or service_order.balance_due > 0
        has_any_payment = service_order.payments.filter(amount__gt=0).exists()

        if has_pending_payment or not has_any_payment:
            logger.info(f"OS #{service_order.number} não elegível para recibo. Pendente: {has_pending_payment}, Tem pgto: {has_any_payment}")
            return

        # 2. Configurações
        config = SystemConfig.load()
        if not config.chatwoot_api_token:
            logger.warning(f"Workflow de recibo abortado para OS #{service_order.number}: Token do Chatwoot não configurado.")
            return

        template_name = config.chatwoot_receipt_template or "baixa_pagamento_avaliacao"

        # 3. Preparar Cliente Chatwoot
        client = ChatwootClient()
        customer = service_order.client_property.client
        primary_phone = customer.phones.filter(is_primary=True).first() or customer.phones.first()
        
        if not primary_phone:
            logger.error(f"Workflow de recibo abortado para OS #{service_order.number}: Cliente sem telefone cadastrado.")
            return

        # Buscar ou Criar Contato e Conversa no Chatwoot
        contact = client.search_contact(primary_phone.phone)
        if not contact:
            contact = client.create_contact(customer.name, primary_phone.phone)
        if not contact:
            return

        conversation = client.get_or_create_conversation(contact['id'])
        if not conversation:
            return

        conversation_id = conversation.get('id')

        # 4. Enviar Template
        # O template espera apenas o número da OS como variável {{1}}
        body_variables = [str(service_order.number)]
        google_link = "https://maps.app.goo.gl/WrnYYVZ4FjpqphyT6"

        logger.info(f"Enviando template {template_name} para OS #{service_order.number}")
        
        # O link é enviado no 'content' com prefixo '.' apenas para o histórico do Chatwoot.
        # O cliente NÃO recebe o link no WhatsApp (pois o template só tem 1 variável),
        # mas o atendente consegue ver para onde o botão do template aponta.
        response = client.send_template(
            conversation_id=conversation_id,
            template_name=template_name,
            variables=body_variables,
            content=f".\n\nLink de Avaliação: {google_link}",
            attachment=None,
            button_data=None
        )

        if response:
            # 6. Atribuir Etiqueta de Avaliação (Substituindo as anteriores)
            evaluation_label = config.chatwoot_evaluation_label or "avaliacao-google"
            client.assign_label_to_conversation(conversation_id, evaluation_label)

            service_order.chatwoot_payment_receipt_sent_at = timezone.now()
            service_order.save(update_fields=['chatwoot_payment_receipt_sent_at'])
            logger.info(f"Workflow de recibo concluído com sucesso para OS #{service_order.number}")
        else:
            logger.error(f"Falha ao enviar template de recibo para OS #{service_order.number}")

    except Exception as e:
        logger.exception(f"Erro crítico no workflow de recibo da OS {service_order_id}: {str(e)}")

def trigger_payment_receipt_workflow(service_order):
    """
    Dispara o workflow de recibo de pagamento em uma thread separada.
    """
    thread = threading.Thread(
        target=run_payment_receipt_workflow,
        args=(service_order.id,),
        daemon=True
    )
    thread.start()
