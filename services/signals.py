from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder
from .workflow import trigger_payment_workflow
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ServiceOrder)
def handle_service_order_status_change(sender, instance, created, **kwargs):
    """
    Sinal que monitora mudanças na ServiceOrder.
    Se o status for WAITING_PAYMENT e a cobrança ainda não tiver sido enviada, dispara o workflow.
    """
    # Se acabou de ser criada ou o status mudou para WAITING_PAYMENT
    if instance.status == ServiceOrder.Status.WAITING_PAYMENT and not instance.pix_sent_at:
        logger.info(f"Detectada OS #{instance.number} em Aguardando Pagamento. Disparando workflow de cobrança.")
        trigger_payment_workflow(instance)
