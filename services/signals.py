from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder, ServiceOrderTask, Sale, Occurrence, FinanceSettings
from .utils.finance import create_billing_for_task, create_billing_for_sale
import logging

logger = logging.getLogger(__name__)

_BILLABLE_TASK_TYPES = [
    ServiceOrderTask.TaskType.EXECUCAO,
    ServiceOrderTask.TaskType.GARANTIA,
    ServiceOrderTask.TaskType.RETORNO,
]


@receiver(post_save, sender=ServiceOrderTask)
def handle_task_completion(sender, instance, created, **kwargs):
    """
    Gera billing por etapa ao concluir uma task faturável (EXECUCAO, GARANTIA, RETORNO).
    Respeita a configuração auto_billing_on_task_completion de FinanceSettings.
    Bloqueia se valor = 0 ou se houver ocorrência impeditiva não resolvida.
    """
    if instance.status != ServiceOrderTask.TaskStatus.CONCLUIDO:
        return

    if instance.task_type not in _BILLABLE_TASK_TYPES:
        return

    if instance.billing_value == 0:
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

    config, _ = FinanceSettings.objects.get_or_create(pk=1)
    if not config.auto_billing_on_task_completion:
        return

    create_billing_for_task(instance)


@receiver(post_save, sender=Sale)
def handle_sale_creation(sender, instance, created, **kwargs):
    if instance.status == Sale.Status.FINALIZADA:
        create_billing_for_sale(instance)
