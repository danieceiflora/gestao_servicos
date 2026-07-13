from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ServiceOrder, ServiceOrderTask, Sale, Occurrence, FinanceSettings
from .utils.finance import create_billing_for_task, create_billing_for_sale, resolve_charge_config_for_payment_method
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

    if instance.skip_auto_billing:
        logger.info(
            f"Task {instance.id} (OS #{instance.service_order.number}) concluída com faturamento "
            f"automático desativado para esta etapa (skip_auto_billing=True). Gere a cobrança "
            f"manualmente, se necessário."
        )
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

    if not instance.preferred_payment_method_id:
        logger.warning(
            f"Task {instance.id} (OS #{instance.service_order.number}) concluída, mas nenhuma "
            f"forma de pagamento foi definida para esta etapa. Billing automático não foi gerado "
            f"— defina a forma de pagamento na etapa ou gere a cobrança manualmente."
        )
        return

    charge_config = resolve_charge_config_for_payment_method(instance.preferred_payment_method)
    if not charge_config:
        logger.warning(
            f"Task {instance.id} (OS #{instance.service_order.number}) concluída, mas não há "
            f"regra de cobrança ativa para o método '{instance.preferred_payment_method}'. "
            f"Billing automático não foi gerado — configure uma regra para esse método ou gere "
            f"a cobrança manualmente."
        )
        return

    billing = create_billing_for_task(instance, charge_config=charge_config)
    if billing and billing.charge_config and billing.charge_config.auto_send_to_gateway:
        from pagamentos.views import auto_create_charges_for_billing
        try:
            auto_create_charges_for_billing(billing)
        except Exception:
            logger.exception(
                'Erro ao disparar cobranças automáticas para billing %s (etapa %s)',
                billing.number, instance.id
            )


@receiver(post_save, sender=Sale)
def handle_sale_creation(sender, instance, created, **kwargs):
    """
    Gera (ou atualiza) o billing/parcelas de uma venda finalizada.
    Views que já coletaram parcelas customizadas do POST devem anexá-las à
    instância antes do save final, via _pending_installments_data /
    _pending_charge_config — evita criar o billing padrão aqui e recriá-lo
    de novo na view logo em seguida (dupla-criação que gerava Installment
    fantasma e erro de notificação CRIAR ao comitar a transação).
    """
    if instance.status != Sale.Status.FINALIZADA:
        return

    installments_data = getattr(instance, '_pending_installments_data', None)
    charge_config = getattr(instance, '_pending_charge_config', None)
    billing = create_billing_for_sale(instance, installments_data, charge_config=charge_config)

    if billing and billing.charge_config and billing.charge_config.auto_send_to_gateway:
        from pagamentos.views import auto_create_charges_for_billing
        try:
            auto_create_charges_for_billing(billing)
        except Exception:
            logger.exception('Erro ao disparar cobranças automáticas para billing %s', billing.number)
