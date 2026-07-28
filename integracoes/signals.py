from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from services.models import (
    ServiceOrder, ServiceOrderTask, Sale,
    Billing, Installment, SalePayment,
    ExpenseInstallment, InstallmentPayment,
)
from .utils import dispatch_dynamic_notification
import logging

logger = logging.getLogger(__name__)

# Modelos que recebem os gatilhos padrão CRIAR e MUDANCA_STATUS
DYNAMIC_NOTIFICATION_MODELS = [
    ServiceOrder, ServiceOrderTask, Sale,
    Billing, Installment, ExpenseInstallment,
]

@receiver(pre_save)
def capture_old_status(sender, instance, **kwargs):
    """
    Captura o status anterior antes de salvar para detectar mudanças no post_save.
    """
    if sender not in DYNAMIC_NOTIFICATION_MODELS:
        return
        
    if instance.pk:
        try:
            # Busca o registro original no banco (sem usar cache do objeto atual)
            old_instance = sender.objects.get(pk=instance.pk)
            # Salva o status anterior em um atributo temporário do objeto
            instance._old_status = getattr(old_instance, 'status', None)
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save)
def handle_dynamic_notifications(sender, instance, created, **kwargs):
    """
    Dispara as notificações configuradas dinamicamente.
    """
    if sender not in DYNAMIC_NOTIFICATION_MODELS:
        return

    try:
        if created:
            # Gatilho de Criação — adiado para após o commit para garantir que objetos
            # relacionados (ex: ServiceOrderTeam) já estejam salvos quando a notificação disparar.
            pk = instance.pk
            sender_cls = sender
            # Status capturado AGORA (síncrono, no momento deste save) — não no momento em
            # que a closure roda. Views como sale_create fazem 2 saves na mesma transação
            # (1º cria com status ainda "vazio"/rascunho, 2º já grava o status final antes
            # do commit). Se comparássemos com o status "fresco" pós-commit, pareceria
            # sempre "nasceu com esse status", disparando MUDANCA_STATUS aqui de novo —
            # duplicando a notificação que o ramo `else` abaixo já disparou de forma
            # síncrona para essa mesma mudança de status.
            status_at_creation = getattr(instance, 'status', None)
            def _dispatch_criar():
                try:
                    fresh = sender_cls.objects.get(pk=pk)
                    dispatch_dynamic_notification(fresh, 'CRIAR')
                    # Só dispara MUDANCA_STATUS aqui se o status não mudou desde a criação
                    # (registro nasceu direto com o status-alvo, num único save — ex: task
                    # criada já como CONCLUIDO). Se mudou, é porque um save posterior, na
                    # mesma transação, já disparou MUDANCA_STATUS pelo ramo síncrono normal.
                    if getattr(fresh, 'status', None) and fresh.status == status_at_creation:
                        dispatch_dynamic_notification(fresh, 'MUDANCA_STATUS', old_status=None)
                except Exception as e:
                    logger.error(f"Erro ao processar notificação CRIAR para {sender_cls.__name__}: {e}")
            transaction.on_commit(_dispatch_criar)
        else:
            # Gatilho de Alteração de Status
            old_status = getattr(instance, '_old_status', None)
            new_status = getattr(instance, 'status', None)

            # Se o status mudou, ou se não tínhamos o status antigo (ex: primeiro save após migração)
            if new_status and old_status != new_status:
                dispatch_dynamic_notification(
                    instance,
                    'MUDANCA_STATUS',
                    old_status=old_status
                )
    except Exception as e:
        # Falhas no envio não devem travar o salvamento do registro principal
        logger.error(f"Erro ao processar notificações dinâmicas para {sender.__name__}: {e}")


@receiver(post_save, sender=SalePayment)
def handle_sale_payment_notifications(sender, instance, created, **kwargs):
    """
    Dispara PAGAMENTO_PARCIAL ou PAGAMENTO_INTEGRAL quando um SalePayment é registrado.
    O cálculo é feito pelo saldo real (inclui este pagamento), independente do status salvo.
    """
    if not created:
        return
    installment = instance.installment
    if not installment:
        return
    try:
        total_paid = installment.get_total_paid()
        if total_paid >= installment.amount:
            event = 'PAGAMENTO_INTEGRAL'
        elif total_paid > 0:
            event = 'PAGAMENTO_PARCIAL'
        else:
            return
        dispatch_dynamic_notification(installment, event)
    except Exception as e:
        logger.error(f"Erro ao processar notificação de pagamento de parcela #{installment.pk}: {e}")


@receiver(post_save, sender=InstallmentPayment)
def handle_expense_payment_notifications(sender, instance, created, **kwargs):
    """
    Dispara PAGAMENTO_PARCIAL ou PAGAMENTO_INTEGRAL quando um InstallmentPayment (C. a Pagar) é registrado.
    """
    if not created:
        return
    expense_installment = instance.installment
    if not expense_installment:
        return
    try:
        total_paid = expense_installment.amount_paid
        if total_paid >= expense_installment.amount:
            event = 'PAGAMENTO_INTEGRAL'
        elif total_paid > 0:
            event = 'PAGAMENTO_PARCIAL'
        else:
            return
        dispatch_dynamic_notification(expense_installment, event)
    except Exception as e:
        logger.error(f"Erro ao processar notificação de pagamento de despesa #{expense_installment.pk}: {e}")
