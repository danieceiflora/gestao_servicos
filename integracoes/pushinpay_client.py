"""
Cliente para a API de Pix Recorrente da PushinPay (assinatura da plataforma).

⚠ ATENÇÃO: a doc pública da PushinPay não confirma o host exato da API nem o
path do endpoint de "Criar Pix Recorrente" (a doc completa exige login). Os
valores abaixo (BASE_URL default, RECURRING_PATH) são a melhor suposição e
DEVEM ser validados com `python manage.py pushinpay_test_call` antes de uso
em produção — ver plano de implementação.
"""
import re
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# TODO: confirmar path real do endpoint "Criar Pix Recorrente" com o suporte/
# doc autenticada da PushinPay antes de ir para produção.
RECURRING_PATH = '/pix/CashIn/subscription'  # suposição baseada em doc pública e teste manual
##RECURRING_PATH = '/pix/cashIn/subscription'

_TIMEOUT = (10, 30)


class PushinPayError(Exception):
    pass


def _base_url() -> str:
    return getattr(settings, 'PUSHINPAY_BASE_URL', 'https://api.pushinpay.com.br').rstrip('/')


def _headers() -> dict:
    token = getattr(settings, 'PUSHINPAY_API_TOKEN', '')
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }


def _clean_document(doc: str) -> str:
    return re.sub(r'\D', '', doc or '')


def _raise_for_status(resp):
    if not resp.ok:
        body = resp.text[:1000]
        logger.error('PushinPay API error %s on %s %s: %s', resp.status_code, resp.request.method, resp.url, body)
        raise PushinPayError(f'PushinPay {resp.status_code}: {body}')


def criar_pix_recorrente(webhook_url: str) -> dict:
    """
    Cria a assinatura recorrente (Pix Automático) com valor/periodicidade
    fixos vindos de settings/.env — nunca configuráveis pela UI.
    Retorna o JSON bruto da resposta da PushinPay.
    """
    from integracoes.models import SystemConfig

    config = SystemConfig.load()

    payload = {
        'value': getattr(settings, 'PUSHINPAY_SUBSCRIPTION_VALUE_CENTS', 0),
        'frequency': getattr(settings, 'PUSHINPAY_SUBSCRIPTION_FREQUENCY', ''),
        'name': getattr(settings, 'PUSHINPAY_SUBSCRIPTION_NAME', 'Assinatura da Plataforma'),
        'comment': getattr(settings, 'PUSHINPAY_SUBSCRIPTION_COMMENT', ''),
        'pix_recurring_retry_policy': getattr(settings, 'PUSHINPAY_SUBSCRIPTION_RETRY_POLICY', 3),
        'customer': {
            'name': config.company_name,
            'document': _clean_document(config.company_cnpj),
        },
        'webhook_url': webhook_url,
    }

    url = f'{_base_url()}{RECURRING_PATH}'
    resp = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
    _raise_for_status(resp)
    return resp.json()


# Vocabulário best-effort para o status recebido no webhook. Não confirmado
# contra um payload real da PushinPay — qualquer valor fora deste dicionário
# fica sem `mapped_status` e é sinalizado para revisão manual, nunca é
# adivinhado silenciosamente.
_STATUS_MAP = {
    'paid': 'ATIVA',
    'confirmed': 'ATIVA',
    'active': 'ATIVA',
    'failed': 'ATRASADA',
    'retry': 'ATRASADA',
    'overdue': 'ATRASADA',
    'expired': 'CANCELADA',
    'cancelled': 'CANCELADA',
    'canceled': 'CANCELADA',
}


def parse_webhook_event(payload: dict) -> dict:
    """
    Normalizador best-effort do payload de webhook da PushinPay.
    v1 — precisa ser revalidado contra um payload real antes de confiar no
    mapeamento de status em produção (ver plano de implementação).
    """
    raw_event = str(payload.get('status') or payload.get('event') or '').strip()
    charge_id = str(
        payload.get('id')
        or payload.get('charge_id')
        or payload.get('transaction_id')
        or ''
    )
    mapped_status = _STATUS_MAP.get(raw_event.lower(), '')
    return {
        'raw_event': raw_event,
        'charge_id': charge_id,
        'mapped_status': mapped_status,
    }
