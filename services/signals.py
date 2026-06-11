from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder, ServiceOrderTask, Sale, Occurrence
from .utils.finance import create_billing_for_task, create_billing_for_sale
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ServiceOrderTask)
def handle_task_completion(sender, instance, created, **kwargs):
    """
    Gera billing por etapa ao concluir uma task de execução.
    Bloqueia cobrança automática se houver ocorrência impeditiva não resolvida.
    """
    if instance.status != ServiceOrderTask.TaskStatus.CONCLUIDO:
        return

    if instance.task_type not in [ServiceOrderTask.TaskType.EXECUCAO, ServiceOrderTask.TaskType.GARANTIA]:
        return

    has_impeditiva = instance.occurrences.filter(
        category=Occurrence.OccurrenceCategory.IMPEDITIVA,
        status=Occurrence.OccurrenceStatus.REGISTRADA
    ).exists()

    if has_impeditiva:
        logger.info(
            f"Task {instance.id} (OS #{instance.service_order.number}) concluída com ocorrência "
            f"impeditiva não resolvida. Billing suspenso — aguardando revisão do admin."
        )
        return

    create_billing_for_task(instance)


@receiver(post_save, sender=Sale)
def handle_sale_creation(sender, instance, created, **kwargs):
    if instance.status == Sale.Status.FINALIZADA:
        create_billing_for_sale(instance)
