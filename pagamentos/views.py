import json
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from services.models import Installment, User
from .gateways.asaas import AsaasGateway
from .gateways.base import ChargeData, SubaccountData
from .models import GatewayCharge, GatewayConfig

logger = logging.getLogger(__name__)


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


def _get_gateway():
    return AsaasGateway()


# --- CONFIGURAÇÃO ---

@login_required
@user_passes_test(is_manager)
def gateway_config_view(request):
    config = GatewayConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        # Atualiza campos do formulário
        text_fields = [
            'company_name', 'company_type', 'cpf_cnpj', 'email', 'phone',
            'address_street', 'address_number', 'address_complement',
            'address_neighborhood', 'address_city', 'address_state', 'address_zip',
            'environment',
        ]
        for f in text_fields:
            val = request.POST.get(f, '').strip()
            if val:
                setattr(config, f, val)

        raw_income = request.POST.get('income_value', '').strip().replace(',', '.')
        if raw_income:
            try:
                config.income_value = Decimal(raw_income)
            except Exception:
                pass

        config.pix_enabled = 'pix_enabled' in request.POST
        config.boleto_enabled = 'boleto_enabled' in request.POST

        # webhook_token pode ser vazio intencionalmente (desabilitar validação)
        config.webhook_token = request.POST.get('webhook_token', '').strip()

        config.save()

        if action == 'create_subaccount':
            _handle_create_subaccount(request, config)
        elif action == 'refresh_status':
            _handle_refresh_status(request, config)
        else:
            messages.success(request, 'Configurações salvas.')

        return redirect('pagamentos:gateway_config')

    context = {
        'config': config,
        'title': 'Gateway de Pagamentos — Asaas',
        'active_menu': 'integracoes',
    }
    return render(request, 'pagamentos/gateway_config.html', context)


def _handle_create_subaccount(request, config: GatewayConfig):
    required = ['company_name', 'cpf_cnpj', 'email', 'phone',
                'address_street', 'address_number', 'address_city',
                'address_state', 'address_zip', 'address_neighborhood',
                'income_value']
    missing = [f for f in required if not getattr(config, f, None)]
    if missing:
        messages.error(request, f'Preencha os campos obrigatórios: {", ".join(missing)}')
        return

    try:
        gw = _get_gateway()
        data = SubaccountData(
            name=config.company_name,
            cpf_cnpj=config.cpf_cnpj,
            email=config.email,
            phone=config.phone,
            company_type=config.company_type or 'MEI',
            address_street=config.address_street,
            address_number=config.address_number,
            address_complement=config.address_complement,
            address_city=config.address_city,
            address_state=config.address_state,
            address_zip=config.address_zip,
            address_neighborhood=config.address_neighborhood,
            income_value=float(config.income_value or 0),
        )
        result = gw.create_subaccount(data)
        config.wallet_id = result.wallet_id
        config.status = result.status
        config.status_detail = result.detail
        if result.api_key:
            config.subaccount_api_key = result.api_key
        config.save()
        messages.success(request, f'Subconta criada! Status: {config.get_status_display()}')
    except Exception as e:
        logger.exception('Erro ao criar subconta Asaas')
        messages.error(request, f'Erro ao criar subconta: {e}')


def _handle_refresh_status(request, config: GatewayConfig):
    if not config.wallet_id:
        messages.warning(request, 'Nenhuma subconta configurada ainda.')
        return
    try:
        gw = _get_gateway()
        result = gw.get_subaccount_status(config.wallet_id, subaccount_api_key=config.subaccount_api_key)
        config.status = result.status
        config.status_detail = result.detail
        config.save()
        messages.success(request, f'Status atualizado: {config.get_status_display()}')
    except Exception as e:
        logger.exception('Erro ao consultar status Asaas')
        messages.error(request, f'Erro ao consultar status: {e}')


# --- COBRANÇAS ---

@login_required
@user_passes_test(is_manager)
@require_POST
def installment_create_charge(request, installment_pk):
    installment = get_object_or_404(Installment, pk=installment_pk)
    method = request.POST.get('method', 'PIX').upper()

    if method not in ['PIX', 'BOLETO']:
        messages.error(request, 'Método inválido.')
        return redirect('billing_detail', pk=installment.billing_id)

    existing = installment.gateway_charges.filter(
        status__in=[GatewayCharge.Status.PENDING, GatewayCharge.Status.RECEIVED,
                    GatewayCharge.Status.CONFIRMED]
    ).first()
    if existing:
        messages.warning(request, f'Já existe uma cobrança {existing.get_method_display()} ativa para esta parcela.')
        return redirect('billing_detail', pk=installment.billing_id)

    config = GatewayConfig.load()
    if not config.can_generate_charges:
        messages.error(request, f'Gateway não habilitado (status: {config.get_status_display()}, wallet: {"configurada" if config.wallet_id else "não configurada"}). Acesse Configurações → Gateway de Pagamentos.')
        return redirect('billing_detail', pk=installment.billing_id)

    if method == 'PIX' and not config.pix_enabled:
        messages.error(request, 'PIX não está habilitado nas configurações do gateway.')
        return redirect('billing_detail', pk=installment.billing_id)
    if method == 'BOLETO' and not config.boleto_enabled:
        messages.error(request, 'Boleto não está habilitado nas configurações do gateway.')
        return redirect('billing_detail', pk=installment.billing_id)

    client = installment.billing.client
    client_doc = client.document or ''
    client_email = client.emails.values_list('email', flat=True).first() or ''

    if not client_doc.strip():
        messages.error(
            request,
            f'O cliente <strong>{client.name}</strong> não possui CPF/CNPJ cadastrado. '
            f'Adicione o documento antes de gerar a cobrança.'
        )
        return redirect('billing_detail', pk=installment.billing_id)

    try:
        gw = _get_gateway()
        data = ChargeData(
            customer_name=client.name,
            customer_document=client_doc,
            customer_email=client_email,
            description=f'Parcela {installment.installment_number} — Cobrança #{installment.billing.number}',
            amount=installment.amount,
            due_date=installment.due_date,
            method=method,
            external_reference=str(installment.pk),
        )
        result = gw.create_charge(data, wallet_id=config.wallet_id)

        GatewayCharge.objects.create(
            installment=installment,
            config=config,
            external_id=result.external_id,
            method=method,
            status=result.status,
            amount=result.amount,
            due_date=result.due_date,
            pix_qrcode=result.pix_qrcode,
            pix_copy_paste=result.pix_copy_paste,
            pix_expiration_date=result.pix_expiration_date,
            boleto_url=result.boleto_url,
            boleto_barcode=result.boleto_barcode,
            invoice_url=result.invoice_url,
            invoice_number=result.invoice_number,
        )
        messages.success(request, f'{method} gerado com sucesso!')
    except Exception as e:
        logger.exception('Erro ao criar cobrança no gateway')
        messages.error(request, f'Erro ao gerar cobrança: {e}')

    return redirect('billing_detail', pk=installment.billing_id)


@login_required
@user_passes_test(is_manager)
@require_POST
def installment_cancel_charge(request, charge_pk):
    charge = get_object_or_404(GatewayCharge, pk=charge_pk)
    billing_pk = charge.installment.billing_id

    try:
        gw = _get_gateway()
        gw.cancel_charge(charge.external_id)
        charge.status = GatewayCharge.Status.CANCELLED
        charge.save()
        messages.success(request, 'Cobrança cancelada no gateway.')
    except Exception as e:
        logger.exception('Erro ao cancelar cobrança no gateway')
        messages.error(request, f'Erro ao cancelar cobrança: {e}')

    return redirect('billing_detail', pk=billing_pk)


@login_required
@user_passes_test(is_manager)
def charge_detail(request, charge_pk):
    charge = get_object_or_404(
        GatewayCharge.objects.select_related('installment__billing', 'config'),
        pk=charge_pk
    )
    # Atualiza status do Asaas antes de exibir
    if charge.status not in [GatewayCharge.Status.RECEIVED, GatewayCharge.Status.CONFIRMED,
                              GatewayCharge.Status.CANCELLED, GatewayCharge.Status.REFUNDED]:
        try:
            gw = _get_gateway()
            result = gw.get_charge(charge.external_id)
            if result.status != charge.status:
                charge.status = result.status
                charge.save(update_fields=['status', 'updated_at'])
        except Exception:
            pass

    context = {
        'charge': charge,
        'title': f'Cobrança {charge.get_method_display()} — {charge.external_id}',
    }
    return render(request, 'pagamentos/charge_detail.html', context)


# --- WEBHOOK ---

@csrf_exempt
def asaas_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    config = GatewayConfig.load()
    
    if config.webhook_token:
        token_recebido = request.headers.get('asaas-access-token', '')
        if token_recebido != config.webhook_token:
            logger.warning(f'Webhook Asaas: token inválido recebido: {token_recebido!r}')
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
        gw = AsaasGateway()
        normalized = gw.parse_webhook(payload)

        external_id = normalized.get('external_id')
        if not external_id:
            return JsonResponse({'ok': True})

        charge = GatewayCharge.objects.filter(external_id=external_id).first()
        if not charge:
            logger.warning(f'Webhook Asaas: cobrança não encontrada para ID {external_id}')
            return JsonResponse({'ok': True})

        charge.status = normalized['status']
        if normalized.get('payment_date'):
            charge.paid_at = timezone.now()
        if normalized.get('net_value'):
            charge.net_value = Decimal(str(normalized['net_value']))
        charge.save()

        if normalized['status'] in ['RECEIVED', 'CONFIRMED']:
            _auto_baixa_installment(charge)

        logger.info(f'Webhook Asaas processado: {external_id} → {normalized["status"]}')
    except Exception as e:
        logger.exception(f'Erro ao processar webhook Asaas: {e}')

    return JsonResponse({'ok': True})


def _auto_baixa_installment(charge: GatewayCharge):
    from services.models import Installment as Inst, Billing, SalePayment, PaymentMethod
    from decimal import Decimal as D

    installment = charge.installment
    installment.status = Inst.Status.PAGO
    installment.paid_at = timezone.now()
    installment.save(update_fields=['status', 'paid_at'])

    # Cria SalePayment para que get_total_paid() / saldo devedor reflitam o recebimento
    method_label = 'PIX' if charge.method == 'PIX' else 'Boleto'
    payment_method = (
        PaymentMethod.objects.filter(descricao__icontains=method_label, ativo=True).first()
        or PaymentMethod.objects.filter(ativo=True).first()
    )
    if payment_method:
        valor_liquido = charge.net_value if charge.net_value else charge.amount
        valor_tarifa = max(charge.amount - valor_liquido, D('0.00'))
        SalePayment.objects.create(
            installment=installment,
            metodo_pagamento=payment_method,
            valor_bruto=charge.amount,
            valor_tarifa=valor_tarifa,
            valor_liquido=valor_liquido,
            data_pagamento=timezone.now(),
            data_previsao=timezone.now().date(),
        )
    else:
        logger.warning('_auto_baixa_installment: nenhum PaymentMethod ativo encontrado; '
                       'SalePayment não criado para charge %s', charge.external_id)

    billing = installment.billing
    if not billing.installments.exclude(status=Inst.Status.PAGO).exists():
        billing.status = Billing.Status.PAGO
        billing.save(update_fields=['status'])
