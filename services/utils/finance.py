from datetime import date as date_type, timedelta
from decimal import Decimal
from django.utils import timezone
from ..models import Billing, Installment, SystemConfig


def _get_due_date(charge_config=None):
    """Data de vencimento da 1ª parcela: usa charge_config.due_days se informado,
    caso contrário cai para SystemConfig.billing_default_due_days."""
    if charge_config is not None:
        due_days = charge_config.due_days
    else:
        config = SystemConfig.load()
        due_days = config.billing_default_due_days or 1
    return timezone.now().date() + timezone.timedelta(days=due_days)


def resolve_charge_config_for_payment_method(payment_method):
    """Resolve a BillingChargeConfig ativa cujo default_payment_method seja exatamente
    o método informado. Retorna None se não houver método ou nenhuma regra ativa o mira."""
    from pagamentos.models import BillingChargeConfig

    if not payment_method:
        return None
    return (
        BillingChargeConfig.objects
        .filter(default_payment_method=payment_method, is_active=True)
        .order_by('-updated_at')
        .first()
    )


def resolve_charge_config_from_post(request):
    """Resolve a BillingChargeConfig ativa a partir de request.POST['charge_config_id']."""
    from pagamentos.models import BillingChargeConfig
    config_id = request.POST.get('charge_config_id', '').strip()
    if not config_id:
        return None
    try:
        return BillingChargeConfig.objects.get(pk=int(config_id), is_active=True)
    except (BillingChargeConfig.DoesNotExist, ValueError):
        return None


def resolve_installment_payment_method_id(explicit_payment_method_id, charge_config=None):
    """Mantém a escolha explícita da parcela e usa o método da regra como padrão."""
    if explicit_payment_method_id:
        return explicit_payment_method_id
    return getattr(charge_config, 'default_payment_method_id', None)


def compute_discount_deadline(discount_type, discount_value, discount_due_days, due_date):
    """due_date - discount_due_days, ou None se não há desconto (tipo NONE/vazio ou
    valor <= 0). Usado tanto no snapshot inicial da parcela quanto na edição manual
    (installment_update em pagamentos/views.py), para devolver sempre o mesmo cálculo."""
    if discount_type and discount_type != Installment.DiscountType.NONE and discount_value and discount_value > 0:
        return due_date - timedelta(days=discount_due_days)
    return None


def installment_charge_snapshot(charge_config, due_date, apply_discount):
    """Snapshot dos termos de desconto/juros/multa de uma BillingChargeConfig, no
    formato dos campos de Installment. Calculado uma vez na criação da parcela para
    não depender da regra ainda existir/estar inalterada depois (mesmo raciocínio já
    usado em GatewayCharge, aqui estendido para toda parcela — inclusive as pagas em
    dinheiro, que nunca chegam a ter um GatewayCharge).

    apply_discount controla se o desconto por antecipação é aplicado — regras com
    discount_applies_to_installments=False só concedem desconto quando a cobrança
    for à vista (billing com 1 única parcela).
    """
    if not charge_config:
        return {}

    discount_type = charge_config.discount_type if (apply_discount and charge_config.discount_type != 'NONE') else Installment.DiscountType.NONE
    discount_value = charge_config.discount_value if apply_discount else Decimal('0')
    discount_due_days = charge_config.discount_due_days
    discount_deadline = compute_discount_deadline(discount_type, discount_value, discount_due_days, due_date)

    return {
        'discount_type': discount_type,
        'discount_value': discount_value,
        'discount_due_days': discount_due_days,
        'discount_deadline': discount_deadline,
        'interest_monthly': charge_config.interest_monthly,
        'fine_type': charge_config.fine_type,
        'fine_value': charge_config.fine_value,
    }


def resolve_apply_discount(charge_config, installment_count):
    """Regra de is_cash: desconto por antecipação só vale para parcelamento se a
    regra permitir explicitamente (discount_applies_to_installments), ou se a
    cobrança for à vista (1 única parcela)."""
    if not charge_config:
        return False
    is_cash = installment_count == 1
    return bool(charge_config.discount_applies_to_installments or is_cash)


def parse_installments_from_post(request):
    """Lê amount[]/due_date[]/payment_method_id[] do POST e retorna lista de dicts
    [{'amount': Decimal, 'due_date': date, 'payment_method_id': int|None}]."""
    amounts = request.POST.getlist('amount[]')
    due_dates = request.POST.getlist('due_date[]')
    methods = request.POST.getlist('payment_method_id[]')

    installments_data = []
    for amt, dt, mid in zip(amounts, due_dates, methods):
        amt = amt.strip().replace(',', '.')
        dt = dt.strip()
        if not amt or not dt:
            continue
        try:
            amount = Decimal(amt)
            due_date = date_type.fromisoformat(dt)
        except (Exception,):
            continue
        pm_id = None
        if mid and mid.strip():
            try:
                pm_id = int(mid.strip())
            except ValueError:
                pass
        installments_data.append({'amount': amount, 'due_date': due_date, 'payment_method_id': pm_id})

    return installments_data


def create_billing_for_task(task, charge_config=None):
    """
    Gera um Billing vinculado a uma etapa concluída (EXECUCAO, GARANTIA ou RETORNO).
    Aplica task.discount como desconto da cobrança.
    Impede duplicata por etapa. Retorna None se o valor bruto for zero.

    Se charge_config não for informado, resolve pela forma de pagamento preferida da etapa
    (task.preferred_payment_method).
    """
    if task.billings.exists():
        return task.billings.first()

    value = task.billing_value
    if not value:
        return None

    discount = task.discount or Decimal('0')
    net_value = max(value - discount, Decimal('0'))

    if charge_config is None:
        charge_config = resolve_charge_config_for_payment_method(task.preferred_payment_method)

    billing = Billing.objects.create(
        client=task.service_order.client_property.client,
        service_order=task.service_order,
        task=task,
        charge_config=charge_config,
        total_amount=value,
        discount=discount,
        status=Billing.Status.PENDENTE
    )

    due_date = _get_due_date(charge_config)
    apply_discount = resolve_apply_discount(charge_config, installment_count=1)
    snapshot = installment_charge_snapshot(charge_config, due_date, apply_discount)

    Installment.objects.create(
        billing=billing,
        installment_number=1,
        due_date=due_date,
        amount=net_value,
        payment_method_id=resolve_installment_payment_method_id(
            task.preferred_payment_method_id, charge_config
        ),
        status=Installment.Status.PENDENTE,
        **snapshot,
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


def create_billing_for_sale(sale, installments_data=None, charge_config=None):
    """
    Gera um Billing e parcelas para uma venda.
    installments_data: lista de dicts [{'due_date': date, 'amount': decimal, 'payment_method_id': id}]
    """
    if hasattr(sale, 'billing'):
        sale.billing.installments.all().delete()
        billing = sale.billing
        billing.total_amount = sale.total_amount
        billing.discount = sale.discount
        billing.charge_config = charge_config
        billing.save()
    else:
        billing = Billing.objects.create(
            client=sale.client,
            sale=sale,
            charge_config=charge_config,
            total_amount=sale.total_amount,
            discount=sale.discount,
            status=Billing.Status.PENDENTE
        )

    if installments_data:
        apply_discount = resolve_apply_discount(charge_config, installment_count=len(installments_data))
        for i, data in enumerate(installments_data, 1):
            snapshot = installment_charge_snapshot(charge_config, data['due_date'], apply_discount)
            Installment.objects.create(
                billing=billing,
                installment_number=i,
                due_date=data['due_date'],
                amount=data['amount'],
                payment_method_id=resolve_installment_payment_method_id(
                    data.get('payment_method_id'), charge_config
                ),
                status=Installment.Status.PENDENTE,
                **snapshot,
            )
    else:
        due_date = _get_due_date(charge_config)
        apply_discount = resolve_apply_discount(charge_config, installment_count=1)
        snapshot = installment_charge_snapshot(charge_config, due_date, apply_discount)
        Installment.objects.create(
            billing=billing,
            installment_number=1,
            due_date=due_date,
            amount=sale.total_amount - sale.discount,
            payment_method_id=resolve_installment_payment_method_id(None, charge_config),
            status=Installment.Status.PENDENTE,
            **snapshot,
        )

    return billing
