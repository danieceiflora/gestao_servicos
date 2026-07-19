import json
import logging
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from services.models import Sale, ServiceOrderTask, User

from .builders import (
    FiscalValidationError, build_nfe_or_nfce_payload, build_nfe_or_nfce_payload_from_task,
    build_nfse_nacional_payload,
)
from .gateways.base import EmpresaData
from .gateways.focusnfe import FocusNFeError, FocusNFeGateway
from .models import NFeConfig, NFeDocument
from .utils import resolve_ibge_code_from_cep

logger = logging.getLogger(__name__)


def is_manager(user):
    return user.is_superuser or user.role in [User.Roles.ADMIN, User.Roles.MANAGER]


def _get_gateway(config: NFeConfig) -> FocusNFeGateway:
    return FocusNFeGateway(token=config.active_token, environment=config.environment)


# --- CONFIGURAÇÃO ---

@login_required
@user_passes_test(is_manager)
def nfe_config_view(request):
    config = NFeConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        text_fields = [
            'environment', 'razao_social', 'nome_fantasia', 'cnpj',
            'inscricao_estadual', 'inscricao_municipal',
            'logradouro', 'numero', 'complemento', 'bairro', 'municipio',
            'codigo_municipio_ibge', 'uf', 'cep',
            'token_producao', 'token_homologacao', 'account_token',
            'webhook_token', 'default_codigo_tributacao_iss', 'default_codigo_tributacao_municipal_iss',
            'default_codigo_indicador_operacao',
            'default_ibs_cbs_situacao_tributaria', 'default_ibs_cbs_classificacao_tributaria',
        ]
        for f in text_fields:
            if f in request.POST:
                setattr(config, f, request.POST.get(f, '').strip())

        if request.POST.get('regime_tributario'):
            config.regime_tributario = int(request.POST['regime_tributario'])

        config.habilita_nfe = 'habilita_nfe' in request.POST
        config.habilita_nfce = 'habilita_nfce' in request.POST
        config.habilita_nfse = 'habilita_nfse' in request.POST

        if config.status == NFeConfig.Status.NAO_CONFIGURADO and config.active_token:
            config.status = NFeConfig.Status.ATIVO

        config.save()

        if action == 'create_empresa':
            _handle_create_empresa(request, config)
        elif action == 'register_webhook':
            _handle_register_webhook(request, config)
        else:
            messages.success(request, 'Configurações salvas.')

        return redirect('fiscal:nfe_config')

    context = {
        'config': config,
        'title': 'Integração Fiscal — FocusNFe',
        'active_menu': 'integracoes',
    }
    return render(request, 'fiscal/config.html', context)


def _handle_create_empresa(request, config: NFeConfig):
    if not config.account_token:
        messages.error(request, 'Informe o Token de Conta/Revenda da Focus para cadastrar a empresa por aqui '
                                 '(ou cole os tokens de produção/homologação manualmente se já cadastrou a '
                                 'empresa pelo painel da Focus).')
        return

    data = EmpresaData(
        razao_social=config.razao_social,
        cnpj=config.cnpj,
        inscricao_estadual=config.inscricao_estadual,
        inscricao_municipal=config.inscricao_municipal,
        regime_tributario=config.regime_tributario,
        logradouro=config.logradouro,
        numero=config.numero,
        complemento=config.complemento,
        bairro=config.bairro,
        municipio=config.municipio,
        codigo_municipio_ibge=config.codigo_municipio_ibge,
        uf=config.uf,
        cep=config.cep,
        habilita_nfe=config.habilita_nfe,
        habilita_nfce=config.habilita_nfce,
        habilita_nfse=config.habilita_nfse,
    )
    gw = FocusNFeGateway(token=config.account_token, environment=config.environment)
    try:
        result = gw.create_empresa(data) if not config.focus_empresa_id else gw.update_empresa(config.focus_empresa_id, data)
        config.focus_empresa_id = result.focus_id
        config.token_producao = result.token_producao or config.token_producao
        config.token_homologacao = result.token_homologacao or config.token_homologacao
        config.status = NFeConfig.Status.PENDENTE_CERTIFICADO
        config.status_detail = ''
        config.save()
        messages.success(request, 'Empresa cadastrada/atualizada na Focus! Agora anexe o certificado digital A1 '
                                   'pelo painel da Focus ("Serviços > Minhas Empresas > Anexar Certificado") — '
                                   'a Focus custodia o certificado, não fazemos upload por aqui.')
    except FocusNFeError as e:
        config.status = NFeConfig.Status.ERRO
        config.status_detail = f'{e.codigo}: {e.mensagem}'
        config.save()
        messages.error(request, f'Erro ao cadastrar empresa na Focus: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao cadastrar empresa na Focus')
        messages.error(request, f'Erro inesperado: {e}')


def _handle_register_webhook(request, config: NFeConfig):
    if not config.active_token:
        messages.error(request, 'Configure o token da empresa antes de registrar o webhook.')
        return
    if not config.webhook_token:
        config.webhook_token = uuid.uuid4().hex
        config.save(update_fields=['webhook_token'])

    from django.urls import reverse
    from django.conf import settings as dj_settings
    webhook_url = f"{dj_settings.SITE_URL.rstrip('/')}{reverse('fiscal:focusnfe_webhook')}"

    gw = _get_gateway(config)
    events = []
    if config.habilita_nfe:
        events.append('nfe')
    if config.habilita_nfce:
        events.append('nfce')
    if config.habilita_nfse:
        events.append('nfsen')

    errors = []
    for event in events:
        try:
            gw.create_webhook(event, webhook_url, config.webhook_token, 'X-Fiscal-Webhook-Token')
        except FocusNFeError as e:
            errors.append(f'{event}: {e.mensagem}')

    if errors:
        messages.warning(request, 'Webhook registrado com ressalvas: ' + '; '.join(errors))
    else:
        messages.success(request, f'Webhook registrado para: {", ".join(events) or "nenhum tipo habilitado"}.')


# --- PAINEL (incluído em sale_form.html) ---

@login_required
def sale_nfe_panel(request, number):
    sale = get_object_or_404(Sale, number=number)
    config = NFeConfig.load()
    documents = NFeDocument.objects.filter(sale=sale).order_by('-created_at')
    return render(request, 'fiscal/_nfe_panel.html', {
        'nfe_config': config, 'sale': sale, 'documents': documents,
    })


# --- EMISSÃO ---

def _new_ref(prefix: str, number) -> str:
    return f'{prefix}-{number}-{uuid.uuid4().hex[:8]}'


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfe(request, number):
    return _emit_sale_document(request, number, 'NFE')


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfce(request, number):
    return _emit_sale_document(request, number, 'NFCE')


def _emit_sale_document(request, number, document_type):
    sale = get_object_or_404(Sale, number=number)
    config = NFeConfig.load()

    can_emit = config.can_emit_nfe if document_type == 'NFE' else config.can_emit_nfce
    if not can_emit:
        messages.error(request, 'Emissão de nota fiscal não está habilitada. Configure a integração primeiro.')
        return redirect('sale_detail', number=number)

    ref = _new_ref('venda', sale.number)
    doc = NFeDocument.objects.create(document_type=document_type, sale=sale, ref=ref)

    try:
        payload = build_nfe_or_nfce_payload(sale, document_type)
        gw = _get_gateway(config)
        result = gw.emit_nfe(ref, payload) if document_type == 'NFE' else gw.emit_nfce(ref, payload)
        _apply_result(doc, result)
        messages.success(request, f'{doc.get_document_type_display()} enviada para autorização (ref {ref}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save()
        for problem in e.problems:
            messages.error(request, problem)
    except FocusNFeError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = e.mensagem
        doc.error_details = [{'codigo': e.codigo, 'mensagem': e.mensagem, 'correcao': e.correcao}]
        doc.save()
        messages.error(request, f'Erro ao emitir: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao emitir documento fiscal para Sale #%s', number)
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save()
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('sale_detail', args=[number])}#fiscal")


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_nfse(request, task_id):
    """NFSe cobre só os itens de SERVIÇO da etapa — ver build_nfse_nacional_payload."""
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order_id = task.service_order_id
    config = NFeConfig.load()

    if not config.can_emit_nfse:
        messages.error(request, 'Emissão de NFSe não está habilitada. Configure a integração primeiro.')
        return redirect('service_order_detail', order_id=order_id)

    # Cadastros antigos podem não ter o Código IBGE do imóvel preenchido (não é um
    # dado que as pessoas digitam manualmente) — tenta resolver pelo CEP via ViaCEP
    # antes de falhar a validação. Builders.py continua livre de chamada de rede.
    prop = task.service_order.client_property
    if not prop.ibge_code and prop.cep:
        resolved = resolve_ibge_code_from_cep(prop.cep)
        if resolved:
            prop.ibge_code = resolved
            prop.save(update_fields=['ibge_code'])

    ref = _new_ref('etapa', str(task.id)[:8])
    doc = NFeDocument.objects.create(document_type=NFeDocument.DocumentType.NFSE, task=task, ref=ref)

    try:
        payload = build_nfse_nacional_payload(task)
        gw = _get_gateway(config)
        result = gw.emit_nfse(ref, payload)
        _apply_result(doc, result)
        messages.success(request, f'NFSe enviada para autorização (ref {ref}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save()
        for problem in e.problems:
            messages.error(request, problem)
    except FocusNFeError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = e.mensagem
        doc.error_details = [{'codigo': e.codigo, 'mensagem': e.mensagem, 'correcao': e.correcao}]
        doc.save()
        messages.error(request, f'Erro ao emitir NFSe: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao emitir NFSe para etapa #%s', task_id)
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save()
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('service_order_detail', args=[order_id])}#nota-fiscal")


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_task_nfe(request, task_id):
    return _emit_task_document(request, task_id, 'NFE')


@login_required
@user_passes_test(is_manager)
@require_POST
def emit_task_nfce(request, task_id):
    return _emit_task_document(request, task_id, 'NFCE')


def _emit_task_document(request, task_id, document_type):
    """NFe/NFCe da etapa cobre só os itens de PRODUTO — ver
    build_nfe_or_nfce_payload_from_task."""
    task = get_object_or_404(ServiceOrderTask, id=task_id)
    order_id = task.service_order_id
    config = NFeConfig.load()

    can_emit = config.can_emit_nfe if document_type == 'NFE' else config.can_emit_nfce
    if not can_emit:
        messages.error(request, 'Emissão de nota fiscal não está habilitada. Configure a integração primeiro.')
        return redirect('service_order_detail', order_id=order_id)

    ref = _new_ref('etapa', str(task.id)[:8])
    doc = NFeDocument.objects.create(document_type=document_type, task=task, ref=ref)

    try:
        payload = build_nfe_or_nfce_payload_from_task(task, document_type)
        gw = _get_gateway(config)
        result = gw.emit_nfe(ref, payload) if document_type == 'NFE' else gw.emit_nfce(ref, payload)
        _apply_result(doc, result)
        messages.success(request, f'{doc.get_document_type_display()} enviada para autorização (ref {ref}).')
    except FiscalValidationError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = '; '.join(e.problems)
        doc.error_details = [{'mensagem': p} for p in e.problems]
        doc.save()
        for problem in e.problems:
            messages.error(request, problem)
    except FocusNFeError as e:
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = e.mensagem
        doc.error_details = [{'codigo': e.codigo, 'mensagem': e.mensagem, 'correcao': e.correcao}]
        doc.save()
        messages.error(request, f'Erro ao emitir: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao emitir documento fiscal para etapa #%s', task_id)
        doc.status = NFeDocument.Status.ERRO
        doc.mensagem_sefaz = str(e)
        doc.save()
        messages.error(request, f'Erro inesperado ao emitir: {e}')

    return redirect(f"{reverse('service_order_detail', args=[order_id])}#nota-fiscal")


def _apply_result(doc: NFeDocument, result):
    status_map = {
        'processando_autorizacao': NFeDocument.Status.PROCESSANDO,
        'autorizado': NFeDocument.Status.AUTORIZADO,
        'erro_autorizacao': NFeDocument.Status.ERRO,
        'cancelado': NFeDocument.Status.CANCELADO,
    }
    doc.status = status_map.get(result.status, NFeDocument.Status.PROCESSANDO)
    doc.numero = result.numero
    doc.serie = result.serie
    doc.chave_acesso = result.chave_acesso
    doc.codigo_verificacao = result.codigo_verificacao
    doc.status_sefaz = result.status_sefaz
    doc.mensagem_sefaz = result.mensagem_sefaz
    doc.xml_url = result.xml_url or ''
    doc.pdf_url = result.pdf_url or ''
    doc.qrcode_url = result.qrcode_url or ''
    doc.error_details = result.error_details
    doc.raw_response = result.raw
    doc.save()


@login_required
@user_passes_test(is_manager)
@require_POST
def refresh_nfe_status(request, pk):
    doc = get_object_or_404(NFeDocument, pk=pk)
    config = NFeConfig.load()
    gw = _get_gateway(config)

    try:
        if doc.document_type == NFeDocument.DocumentType.NFE:
            result = gw.consultar_nfe(doc.ref)
        elif doc.document_type == NFeDocument.DocumentType.NFCE:
            result = gw.consultar_nfce(doc.ref)
        else:
            result = gw.consultar_nfse(doc.ref)
        _apply_result(doc, result)
        messages.success(request, f'Status atualizado: {doc.get_status_display()}.')
    except FocusNFeError as e:
        messages.error(request, f'Erro ao consultar status: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao consultar status do documento fiscal #%s', pk)
        messages.error(request, f'Erro inesperado: {e}')

    return _redirect_to_owner(doc)


@login_required
@user_passes_test(is_manager)
@require_POST
def cancel_nfe(request, pk):
    doc = get_object_or_404(NFeDocument, pk=pk)
    justificativa = request.POST.get('justificativa', '').strip()

    if len(justificativa) < 15:
        messages.error(request, 'A justificativa de cancelamento precisa ter pelo menos 15 caracteres.')
        return _redirect_to_owner(doc)

    config = NFeConfig.load()
    gw = _get_gateway(config)

    try:
        if doc.document_type == NFeDocument.DocumentType.NFE:
            result = gw.cancelar_nfe(doc.ref, justificativa)
        elif doc.document_type == NFeDocument.DocumentType.NFCE:
            result = gw.cancelar_nfce(doc.ref, justificativa)
        else:
            result = gw.cancelar_nfse(doc.ref, justificativa)
        _apply_result(doc, result)
        doc.cancelled_at = timezone.now()
        doc.cancel_justificativa = justificativa
        doc.save(update_fields=['cancelled_at', 'cancel_justificativa'])
        messages.success(request, 'Documento fiscal cancelado.')
    except FocusNFeError as e:
        messages.error(request, f'Erro ao cancelar: {e.mensagem}')
    except Exception as e:
        logger.exception('Erro inesperado ao cancelar documento fiscal #%s', pk)
        messages.error(request, f'Erro inesperado: {e}')

    return _redirect_to_owner(doc)


def _redirect_to_owner(doc: NFeDocument):
    if doc.sale_id:
        return redirect(f"{reverse('sale_detail', args=[doc.sale.number])}#fiscal")
    return redirect(f"{reverse('service_order_detail', args=[doc.task.service_order_id])}#nota-fiscal")


# --- WEBHOOK ---

@csrf_exempt
def focusnfe_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    config = NFeConfig.load()
    if config.webhook_token:
        received = request.headers.get('X-Fiscal-Webhook-Token', '')
        if received != config.webhook_token:
            logger.warning('Webhook FocusNFe: token inválido recebido: %r', received)
            return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
        ref = payload.get('ref')
        if not ref:
            return JsonResponse({'ok': True})

        doc = NFeDocument.objects.filter(ref=ref).first()
        if not doc:
            logger.warning('Webhook FocusNFe: documento não encontrado para ref %r', ref)
            return JsonResponse({'ok': True})

        status_map = {
            'processando_autorizacao': NFeDocument.Status.PROCESSANDO,
            'autorizado': NFeDocument.Status.AUTORIZADO,
            'erro_autorizacao': NFeDocument.Status.ERRO,
            'cancelado': NFeDocument.Status.CANCELADO,
        }
        new_status = status_map.get(payload.get('status'))
        if new_status:
            doc.status = new_status
        doc.numero = str(payload.get('numero', '') or doc.numero)
        doc.chave_acesso = payload.get('chave_nfe', '') or doc.chave_acesso
        doc.codigo_verificacao = payload.get('codigo_verificacao', '') or doc.codigo_verificacao
        doc.status_sefaz = str(payload.get('status_sefaz', '') or doc.status_sefaz)
        doc.mensagem_sefaz = payload.get('mensagem_sefaz', '') or doc.mensagem_sefaz
        doc.xml_url = payload.get('caminho_xml_nota_fiscal', '') or doc.xml_url
        doc.pdf_url = payload.get('caminho_danfe', '') or doc.pdf_url
        doc.error_details = payload.get('erros') or doc.error_details
        doc.raw_response = payload
        doc.save()
        logger.info('Webhook FocusNFe processado: %s → %s', ref, doc.status)
    except Exception:
        logger.exception('Erro ao processar webhook FocusNFe')

    return JsonResponse({'ok': True})
