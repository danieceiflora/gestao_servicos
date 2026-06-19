import logging
from decimal import Decimal
from datetime import datetime

import requests
from django.conf import settings

from .base import BasePaymentGateway, SubaccountData, SubaccountResult, ChargeData, ChargeResult

logger = logging.getLogger(__name__)

SANDBOX_URL = 'https://api-sandbox.asaas.com/v3'
PRODUCTION_URL = 'https://api.asaas.com/v3'

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

    def _get(self, path, params=None, api_key: str = None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.get(url, headers=self._headers(api_key), params=params, timeout=30)
        self._raise_for_status(resp)
        return resp.json()

    def _post(self, path, data, api_key: str = None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.post(url, headers=self._headers(api_key), json=data, timeout=30)
        self._raise_for_status(resp)
        return resp.json()

    def _delete(self, path):
        url = f'{self.base_url}/{path.lstrip("/")}'
        resp = requests.delete(url, headers=self._headers(), timeout=30)
        self._raise_for_status(resp)
        return resp.json()

    def _clean_document(self, doc: str) -> str:
        import re
        return re.sub(r'\D', '', doc or '')

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

    def get_subaccount_status(self, wallet_id: str) -> SubaccountResult:
        result = self._get(f'accounts/{wallet_id}')
        return SubaccountResult(
            wallet_id=wallet_id,
            status=result.get('status', 'UNKNOWN'),
            detail=str(result),
        )

    def create_charge(
        self,
        data: ChargeData,
        wallet_id: str = '',
        subaccount_api_key: str = '',
        master_wallet_id: str = '',
        split_type: str = 'PERCENT',
        split_value: float = 0,
    ) -> ChargeResult:
        # Se temos a API key da subconta, emitimos a cobrança através dela
        # (remetente = empresa do cliente). Caso contrário, usa a master key.
        use_key = subaccount_api_key or None

        customer_id = self._get_or_create_customer(
            data.customer_name, data.customer_document, data.customer_email, api_key=use_key
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

        if subaccount_api_key:
            # Cobrança via subconta → repasse da margem para a carteira master (nunca para a própria carteira do emissor)
            if master_wallet_id:
                platform_pct = float(split_value) if split_value else 0
                if split_type == 'FIXED' and platform_pct > 0:
                    payload['split'] = [{'walletId': master_wallet_id, 'fixedValue': round(platform_pct, 2)}]
                elif platform_pct > 0:
                    payload['split'] = [{'walletId': master_wallet_id, 'percentualValue': platform_pct}]
            else:
                logger.warning('ASAAS_MASTER_WALLET_ID não configurado — cobrança será emitida sem split de margem')
        elif wallet_id:
            # Cobrança via master → repasse da parte do cliente para subconta
            if split_type == 'FIXED' and split_value > 0:
                client_fixed = float(data.amount) - split_value
                payload['split'] = [{'walletId': wallet_id, 'fixedValue': round(max(client_fixed, 0), 2)}]
            else:
                platform_pct = float(split_value) if split_value else 0
                client_pct = round(100 - platform_pct, 4)
                payload['split'] = [{'walletId': wallet_id, 'percentualValue': client_pct}]

        result = self._post('payments', payload, api_key=use_key)
        charge_id = result['id']

        charge = ChargeResult(
            external_id=charge_id,
            status=STATUS_MAP.get(result.get('status', ''), 'PENDING'),
            method=data.method,
            amount=Decimal(str(result['value'])),
            due_date=data.due_date,
            invoice_url=result.get('invoiceUrl', ''),
        )

        if billing_type == 'PIX':
            try:
                pix = self._get(f'payments/{charge_id}/pixQrCode', api_key=use_key)
                charge.pix_qrcode = pix.get('encodedImage', '')
                charge.pix_copy_paste = pix.get('payload', '')
                if pix.get('expirationDate'):
                    charge.pix_expiration_date = datetime.fromisoformat(pix['expirationDate'])
            except Exception:
                logger.warning(f'Não foi possível obter QR Code PIX para {charge_id}')
        else:
            charge.boleto_url = result.get('bankSlipUrl', '')
            try:
                ident = self._get(f'payments/{charge_id}/identificationField', api_key=use_key)
                charge.boleto_barcode = ident.get('identificationField', '')
            except Exception:
                logger.warning(f'Não foi possível obter código de barras para {charge_id}')

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
            'status': status_map.get(event, 'UNKNOWN'),
            'paid_value': payment.get('value'),
            'net_value': payment.get('netValue'),
            'payment_date': payment.get('paymentDate'),
        }
