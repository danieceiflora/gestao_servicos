import logging
from decimal import Decimal
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone as dj_timezone

from core.tz_utils import safe_make_aware
from .base import BasePaymentGateway, SubaccountData, SubaccountResult, ChargeData, ChargeResult

logger = logging.getLogger(__name__)

SANDBOX_URL = 'https://api-sandbox.asaas.com/v3'
PRODUCTION_URL = 'https://api.asaas.com/v3'

# Margem retida pela plataforma master, calculada sempre sobre o valor COM desconto
# (pior cenário, assumindo que o desconto de antecipação será totalmente usado).
#
# PIX: regime híbrido —
#   - valor com desconto < PIX_PERCENT_BREAKEVEN: taxa FIXA (MIN_SPLIT_MARGIN), via
#     split fixedValue, para garantir o custo operacional mínimo (cobre a tarifa real
#     do Asaas de ~R$1,99) em cobranças pequenas.
#   - valor com desconto >= PIX_PERCENT_BREAKEVEN: split PERCENTUAL (PIX_PLATFORM_PERCENT),
#     que escala automaticamente com o que o Asaas efetivamente receber.
# BOLETO: sempre taxa fixa (BOLETO_PLATFORM_FIXED), via split fixedValue.
PIX_PLATFORM_PERCENT = Decimal('0.008')   # 0,80% retido pela master (repassa 99,20% à subconta)
BOLETO_PLATFORM_FIXED = Decimal('2.50')   # R$ 2,50 fixo retido pela master

# Piso mínimo de margem, em R$, garantido via taxa fixa quando o valor com desconto
# não é suficiente para que a porcentagem cubra o custo operacional.
MIN_SPLIT_MARGIN = Decimal('2.50')

# Ponto de equilíbrio: acima deste valor (com desconto), 0,80% já supera MIN_SPLIT_MARGIN,
# então o percentual passa a ser usado no lugar da taxa fixa.
PIX_PERCENT_BREAKEVEN = MIN_SPLIT_MARGIN / PIX_PLATFORM_PERCENT  # R$ 312,50

STATUS_MAP = {
    'PENDING': 'PENDING',
    'RECEIVED': 'RECEIVED',
    'CONFIRMED': 'CONFIRMED',
    'OVERDUE': 'OVERDUE',
    'REFUNDED': 'REFUNDED',
    'DELETED': 'CANCELLED',
    'CANCELLED': 'CANCELLED',
    'AWAITING_RISK_ANALYSIS': 'PENDING',
}


class AsaasGateway(BasePaymentGateway):

    def __init__(self):
        env = getattr(settings, 'ASAAS_ENVIRONMENT', 'SANDBOX')
        self.api_key = getattr(settings, 'ASAAS_API_KEY', '')
        self.base_url = SANDBOX_URL if env == 'SANDBOX' else PRODUCTION_URL
        self.split_wallet_id = getattr(settings, 'ASAAS_SPLIT_WALLET_ID', '')

    def _headers(self, api_key: str = None):
        return {
            'Content-Type': 'application/json',
            'access_token': api_key or self.api_key,
        }

    def _raise_for_status(self, resp):
        if not resp.ok:
            body = resp.text[:1000]
            logger.error('Asaas API error %s on %s %s: %s', resp.status_code, resp.request.method, resp.url, body)
            detail = body
            try:
                parsed = resp.json()
                errors = parsed.get('errors', [])
                msgs = [e.get('description', '') for e in errors if e.get('description')]
                if msgs:
                    detail = '; '.join(msgs)
            except Exception:
                pass
            raise Exception(f'Asaas {resp.status_code}: {detail}')

    # (connect_timeout, read_timeout) — Asaas sandbox pode ser lento para responder
    _TIMEOUT = (10, 60)

    def _get(self, path, params=None, api_key: str = None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.get(url, headers=self._headers(api_key), params=params, timeout=self._TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path, data, api_key: str = None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.post(url, headers=self._headers(api_key), json=data, timeout=self._TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _put(self, path, data, api_key: str = None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.put(url, headers=self._headers(api_key), json=data, timeout=self._TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _delete(self, path):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.delete(url, headers=self._headers(), timeout=self._TIMEOUT)
        self._raise_for_status(resp)
        return resp.json()

    def _clean_document(self, doc: str) -> str:
        import re
        return re.sub(r'\D', '', doc or '')

    def _discount_amount(self, amount: Decimal, discount_type: str, discount_value: Decimal) -> Decimal:
        """Maior desconto possível (pior cenário) para uma regra de desconto por antecipação."""
        if not discount_type or discount_type == 'NONE' or discount_value <= 0:
            return Decimal('0')
        if discount_type == 'PERCENTAGE':
            return (amount * discount_value / Decimal('100')).quantize(Decimal('0.01'))
        return min(discount_value, amount)

    def _get_or_create_customer(self, name: str, document: str, email: str, api_key: str = None) -> str:
        doc_clean = self._clean_document(document)
        if doc_clean:
            result = self._get('customers', params={'cpfCnpj': doc_clean, 'limit': 1}, api_key=api_key)
            if result.get('data'):
                return result['data'][0]['id']

        payload = {'name': name}
        if email:
            payload['email'] = email
        if doc_clean:
            payload['cpfCnpj'] = doc_clean
        logger.info('Asaas _get_or_create_customer payload: %s', payload)
        created = self._post('customers', payload, api_key=api_key)
        return created['id']

    def create_subaccount(self, data: SubaccountData) -> SubaccountResult:
        doc_clean = self._clean_document(data.cpf_cnpj)
        payload = {
            'name': data.name,
            'email': data.email,
            'cpfCnpj': doc_clean,
            'mobilePhone': self._clean_document(data.phone),
            'companyType': data.company_type,
            'incomeValue': float(data.income_value),
            'address': data.address_street,
            'addressNumber': data.address_number,
            'complement': data.address_complement or '',
            'province': data.address_neighborhood,
            'city': data.address_city,
            'state': data.address_state,
            'postalCode': self._clean_document(data.address_zip),
        }
        result = self._post('accounts', payload)
        return SubaccountResult(
            wallet_id=result.get('walletId', ''),
            status=result.get('status', 'PENDING_DOCS'),
            detail=str(result),
            api_key=result.get('apiKey', ''),
        )

    def get_subaccount_status(self, wallet_id: str, subaccount_api_key: str = '') -> SubaccountResult:
        if subaccount_api_key:
            # Autentica como a própria subconta — retorna status real e não depende do account id
            result = self._get('myAccount', api_key=subaccount_api_key)
        else:
            # Fallback: lista subcontas da master e filtra pelo walletId
            data = self._get('accounts', params={'limit': 100})
            result = next(
                (a for a in data.get('data', []) if a.get('walletId') == wallet_id),
                {}
            )
        return SubaccountResult(
            wallet_id=result.get('walletId', wallet_id),
            status=result.get('status', 'UNKNOWN'),
            detail=str(result),
        )

    def create_charge(self, data: ChargeData, wallet_id: str = '') -> ChargeResult:
        """Gera cobrança pela conta master.

        Se wallet_id for fornecido, configura split com base no valor COM desconto
        (pior cenário, assumindo que o desconto de antecipação será totalmente usado):

        - PIX com valor-com-desconto >= PIX_PERCENT_BREAKEVEN: split percentual
          (PIX_PLATFORM_PERCENT), que escala automaticamente com o que o Asaas
          efetivamente receber — nunca excede o valor recebido.
        - Caso contrário (PIX abaixo do breakeven, ou Boleto): split fixedValue,
          calculado sobre o valor-com-desconto, garantindo MIN_SPLIT_MARGIN /
          BOLETO_PLATFORM_FIXED de margem mesmo se o desconto for usado.
        """
        split_kwargs = None
        if wallet_id:
            discount_amount = self._discount_amount(data.amount, data.discount_type, data.discount_value)
            worst_case_value = data.amount - discount_amount

            if data.method == 'PIX' and worst_case_value >= PIX_PERCENT_BREAKEVEN:
                client_percent = (Decimal('1') - PIX_PLATFORM_PERCENT) * Decimal('100')
                split_kwargs = {'percentualValue': float(round(client_percent, 2))}
            else:
                fixed_margin = MIN_SPLIT_MARGIN if data.method == 'PIX' else BOLETO_PLATFORM_FIXED
                client_amount = max(worst_case_value - fixed_margin, Decimal('0'))
                split_kwargs = {'fixedValue': float(round(client_amount, 2))}

        customer_id = self._get_or_create_customer(
            data.customer_name, data.customer_document, data.customer_email
        )

        billing_type = 'PIX' if data.method == 'PIX' else 'BOLETO'
        payload = {
            'customer': customer_id,
            'billingType': billing_type,
            'value': float(data.amount),
            'dueDate': data.due_date.strftime('%Y-%m-%d'),
            'description': data.description,
            'externalReference': data.external_reference,
        }

        if data.discount_type and data.discount_type != 'NONE' and data.discount_value > 0:
            payload['discount'] = {
                'value': float(round(data.discount_value, 2)),
                'dueDateLimitDays': data.discount_due_days,
                'type': data.discount_type,
            }
        if data.interest_monthly > 0:
            payload['interest'] = {'value': float(round(data.interest_monthly, 2))}
        if data.fine_type and data.fine_type != 'NONE' and data.fine_value > 0:
            payload['fine'] = {
                'value': float(round(data.fine_value, 2)),
                'type': data.fine_type,
            }

        if wallet_id:
            payload['split'] = [{'walletId': wallet_id, **split_kwargs}]

        result = self._post('payments', payload)
        charge_id = result['id']

        charge = ChargeResult(
            external_id=charge_id,
            status=STATUS_MAP.get(result.get('status', ''), 'PENDING'),
            method=data.method,
            amount=Decimal(str(result['value'])),
            due_date=data.due_date,
            invoice_url=result.get('invoiceUrl', ''),
            invoice_number=str(result.get('invoiceNumber', '') or ''),
        )

        self._populate_charge_artifacts(charge, charge_id, billing_type, result)

        return charge

    def _populate_charge_artifacts(self, charge: ChargeResult, charge_id: str, billing_type: str, result: dict):
        """Preenche QR Code PIX ou linha digitável do boleto a partir da resposta do
        Asaas — usado após criar ou atualizar uma cobrança (o Asaas regenera esses
        artefatos quando a data/valor mudam)."""
        if billing_type == 'PIX':
            try:
                pix = self._get(f'payments/{charge_id}/pixQrCode')
                charge.pix_qrcode = pix.get('encodedImage', '')
                charge.pix_copy_paste = pix.get('payload', '')
                if pix.get('expirationDate'):
                    charge.pix_expiration_date = safe_make_aware(datetime.fromisoformat(pix['expirationDate']))
            except Exception:
                logger.warning(f'Não foi possível obter QR Code PIX para {charge_id}')
        else:
            charge.boleto_url = result.get('bankSlipUrl', '')
            try:
                ident = self._get(f'payments/{charge_id}/identificationField')
                charge.boleto_barcode = ident.get('identificationField', '')
            except Exception:
                logger.warning(f'Não foi possível obter código de barras para {charge_id}')

    def update_charge(self, external_id: str, data: ChargeData) -> ChargeResult:
        """Atualiza valor/vencimento (e desconto/juros/multa) de uma cobrança já
        existente — PUT /payments/{id} do Asaas. Mantém a mesma cobrança (mesmo
        boleto/PIX, mesmo external_id); não recria nem envia customer/billingType/split,
        que não mudam numa atualização."""
        billing_type = 'PIX' if data.method == 'PIX' else 'BOLETO'
        payload = {
            'value': float(data.amount),
            'dueDate': data.due_date.strftime('%Y-%m-%d'),
            'description': data.description,
        }

        if data.discount_type and data.discount_type != 'NONE' and data.discount_value > 0:
            payload['discount'] = {
                'value': float(round(data.discount_value, 2)),
                'dueDateLimitDays': data.discount_due_days,
                'type': data.discount_type,
            }
        if data.interest_monthly > 0:
            payload['interest'] = {'value': float(round(data.interest_monthly, 2))}
        if data.fine_type and data.fine_type != 'NONE' and data.fine_value > 0:
            payload['fine'] = {
                'value': float(round(data.fine_value, 2)),
                'type': data.fine_type,
            }

        result = self._put(f'payments/{external_id}', payload)

        charge = ChargeResult(
            external_id=external_id,
            status=STATUS_MAP.get(result.get('status', ''), 'PENDING'),
            method=data.method,
            amount=Decimal(str(result['value'])),
            due_date=data.due_date,
            invoice_url=result.get('invoiceUrl', ''),
            invoice_number=str(result.get('invoiceNumber', '') or ''),
        )
        self._populate_charge_artifacts(charge, external_id, billing_type, result)

        return charge

    def get_charge(self, external_id: str) -> ChargeResult:
        result = self._get(f'payments/{external_id}')
        due = None
        if result.get('dueDate'):
            due = datetime.strptime(result['dueDate'], '%Y-%m-%d').date()
        billing_type = result.get('billingType', '')
        return ChargeResult(
            external_id=external_id,
            status=STATUS_MAP.get(result.get('status', ''), 'PENDING'),
            method='PIX' if billing_type == 'PIX' else 'BOLETO',
            amount=Decimal(str(result.get('value', 0))),
            due_date=due,
            boleto_url=result.get('bankSlipUrl', ''),
        )

    def cancel_charge(self, external_id: str) -> bool:
        result = self._delete(f'payments/{external_id}')
        return result.get('deleted', False)

    def create_subscription(self, customer_name: str, customer_document: str, value: Decimal,
                             cycle: str, description: str, external_reference: str = '') -> dict:
        """
        Cria uma assinatura Pix recorrente na conta master (sem split — quem
        recebe é a própria plataforma, não uma subconta). Usada para a
        mensalidade da plataforma, não para cobrança de clientes.

        `cycle` segue o vocabulário do Asaas: WEEKLY, BIWEEKLY, MONTHLY,
        QUARTERLY, SEMIANNUALLY, YEARLY.
        """
        customer_id = self._get_or_create_customer(customer_name, customer_document, '')

        # dj_timezone.localdate() explode com USE_TZ=False (naive datetime) —
        # este projeto usa USE_TZ = DEBUG, então isso acontece sempre que
        # DEBUG=False (produção). Calcular assim funciona nos dois modos.
        _now = dj_timezone.now()
        today = dj_timezone.localtime(_now).date() if dj_timezone.is_aware(_now) else _now.date()

        payload = {
            'customer': customer_id,
            'billingType': 'PIX',
            'value': float(value),
            'nextDueDate': today.strftime('%Y-%m-%d'),
            'cycle': cycle,
            'description': description,
            'externalReference': external_reference,
        }
        subscription = self._post('subscriptions', payload)
        subscription_id = subscription['id']

        result = {
            'subscription_id': subscription_id,
            'status': subscription.get('status', ''),
            'first_charge_id': '',
            'qr_code': '',
            'qr_code_base64': '',
            'next_due_date': subscription.get('nextDueDate', ''),
        }

        payments = self._get(f'subscriptions/{subscription_id}/payments')
        first_payment = next(iter(payments.get('data', [])), None)
        if first_payment:
            charge_id = first_payment['id']
            result['first_charge_id'] = charge_id
            if first_payment.get('dueDate'):
                result['next_due_date'] = first_payment['dueDate']
            try:
                pix = self._get(f'payments/{charge_id}/pixQrCode')
                result['qr_code'] = pix.get('payload', '')
                result['qr_code_base64'] = pix.get('encodedImage', '')
            except Exception:
                logger.warning(f'Não foi possível obter QR Code Pix para assinatura {subscription_id}')

        return result

    def cancel_subscription(self, subscription_id: str) -> bool:
        result = self._delete(f'subscriptions/{subscription_id}')
        return result.get('deleted', False)

    def parse_webhook(self, payload: dict) -> dict:
        event = payload.get('event', '')
        payment = payload.get('payment', {})
        status_map = {
            'PAYMENT_RECEIVED': 'RECEIVED',
            'PAYMENT_CONFIRMED': 'CONFIRMED',
            'PAYMENT_OVERDUE': 'OVERDUE',
            'PAYMENT_DELETED': 'CANCELLED',
            'PAYMENT_REFUNDED': 'REFUNDED',
        }
        return {
            'event': event,
            'external_id': payment.get('id', ''),
            # None = evento que não altera o status da cobrança (ex: PAYMENT_CREATED,
            # PAYMENT_UPDATED, PAYMENT_CHECKOUT_VIEWED...). O Asaas envia dezenas de eventos
            # além dos 5 mapeados aqui — nunca sobrescrever o status da cobrança com um
            # valor arbitrário para eventos que não reconhecemos.
            'status': status_map.get(event),
            'paid_value': payment.get('value'),
            'net_value': payment.get('netValue'),
            'payment_date': payment.get('paymentDate'),
            'subscription_id': payment.get('subscription', ''),
            'due_date': payment.get('dueDate', ''),
        }
