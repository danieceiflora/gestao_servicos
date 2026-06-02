from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder, Sale
from .workflow import trigger_payment_workflow
from .utils.finance import create_billing_for_os, create_billing_for_sale
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ServiceOrder)
def handle_service_order_status_change(sender, instance, created, **kwargs):
    """
    Sinal que monitora mudanças na ServiceOrder.
    Gera cobrança automaticamente ao atingir status de pagamento ou finalização.
    """
    if instance.status in [ServiceOrder.Status.AGUARDANDO_PAGAMENTO, ServiceOrder.Status.FINALIZADO]:
        create_billing_for_os(instance)

    # Workflow de notificação
    if instance.status == ServiceOrder.Status.AGUARDANDO_PAGAMENTO and not instance.pix_sent_at:
        logger.info(f"Detectada OS #{instance.number} em Aguardando Pagamento. Disparando workflow de cobrança.")
        trigger_payment_workflow(instance)

@receiver(post_save, sender=Sale)
def handle_sale_creation(sender, instance, created, **kwargs):
    """
    Gera cobrança básica para vendas se ainda não existir.
    """
    if instance.status == Sale.Status.FINALIZADA:
        create_billing_for_sale(instance)
