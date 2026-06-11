from decimal import Decimal
from django.utils import timezone
from ..models import Billing, Installment, SystemConfig


def _get_due_date():
    config = SystemConfig.load()
    due_days = config.billing_default_due_days or 1
    return timezone.now().date() + timezone.timedelta(days=due_days)


def create_billing_for_task(task):
    """
    Gera um Billing vinculado a uma etapa (task) concluída.
    Usa task.value se definido; senão usa a soma dos itens da etapa.
    Impede duplicata por etapa.
    """
    if task.billings.exists():
        return task.billings.first()

    value = task.billing_value

    billing = Billing.objects.create(
        client=task.service_order.client_property.client,
        service_order=task.service_order,
        task=task,
        total_amount=value,
        discount=Decimal('0'),
        status=Billing.Status.PENDENTE
    )

    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=_get_due_date(),
        amount=value,
        status=Installment.Status.PENDENTE
    )

    return billing


def create_billing_for_os(service_order):
    """
    Gera um Billing no nível da OS (sem etapa vinculada).
    Mantido para compatibilidade com OSs antigas e fluxos legados.
    Impede duplicata por OS (considera apenas billings sem task).
    """
    if service_order.billings.filter(task__isnull=True).exists():
        return service_order.billings.filter(task__isnull=True).first()

    billing = Billing.objects.create(
        client=service_order.client_property.client,
        service_order=service_order,
        task=None,
        total_amount=service_order.total_value,
        discount=service_order.discount,
        status=Billing.Status.PENDENTE
    )

    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=_get_due_date(),
        amount=service_order.balance_due,
        status=Installment.Status.PENDENTE
    )

    return billing


def create_billing_for_sale(sale, installments_data=None):
    """
    Gera um Billing e parcelas para uma venda.
    installments_data: lista de dicts [{'due_date': date, 'amount': decimal, 'payment_method_id': id}]
    """
    if hasattr(sale, 'billing'):
        sale.billing.installments.all().delete()
        billing = sale.billing
        billing.total_amount = sale.total_amount
        billing.discount = sale.discount
        billing.save()
    else:
        billing = Billing.objects.create(
            client=sale.client,
            sale=sale,
            total_amount=sale.total_amount,
            discount=sale.discount,
            status=Billing.Status.PENDENTE
        )

    if installments_data:
        for i, data in enumerate(installments_data, 1):
            Installment.objects.create(
                billing=billing,
                installment_number=i,
                due_date=data['due_date'],
                amount=data['amount'],
                payment_method_id=data.get('payment_method_id'),
                status=Installment.Status.PENDENTE
            )
    else:
        Installment.objects.create(
            billing=billing,
            installment_number=1,
            due_date=_get_due_date(),
            amount=sale.total_amount - sale.discount,
            status=Installment.Status.PENDENTE
        )

    return billing
