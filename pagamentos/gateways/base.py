from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Optional


@dataclass
class SubaccountData:
    name: str
    cpf_cnpj: str
    email: str
    phone: str
    company_type: str
    address_street: str
    address_number: str
    address_complement: str
    address_city: str
    address_state: str
    address_zip: str
    address_neighborhood: str
    income_value: float = 0.0  # faturamento mensal estimado (obrigatório no Asaas)


@dataclass
class SubaccountResult:
    wallet_id: str
    status: str
    detail: str = ''
    api_key: str = ''


@dataclass
class ChargeData:
    customer_name: str
    customer_document: str
    customer_email: str
    description: str
    amount: Decimal
    due_date: date
    method: str  # 'PIX' or 'BOLETO'
    external_reference: str
    # Desconto por antecipação
    discount_type: str = ''          # 'FIXED' | 'PERCENTAGE'
    discount_value: Decimal = field(default_factory=lambda: Decimal('0'))
    discount_due_days: int = 0
    # Juros por atraso (% ao mês)
    interest_monthly: Decimal = field(default_factory=lambda: Decimal('0'))
    # Multa por atraso
    fine_type: str = ''              # 'FIXED' | 'PERCENTAGE'
    fine_value: Decimal = field(default_factory=lambda: Decimal('0'))


@dataclass
class ChargeResult:
    external_id: str
    status: str
    method: str
    amount: Decimal
    due_date: date
    pix_qrcode: str = ''
    pix_copy_paste: str = ''
    pix_expiration_date: Optional[object] = None
    boleto_url: str = ''
    boleto_barcode: str = ''
    boleto_bank_slip_url: str = ''
    invoice_url: str = ''
    invoice_number: str = ''


class BasePaymentGateway(ABC):

    @abstractmethod
    def create_subaccount(self, data: SubaccountData) -> SubaccountResult:
        ...

    @abstractmethod
    def get_subaccount_status(self, wallet_id: str) -> SubaccountResult:
        ...

    @abstractmethod
    def create_charge(self, data: ChargeData, wallet_id: str) -> ChargeResult:
        ...

    @abstractmethod
    def get_charge(self, external_id: str) -> ChargeResult:
        ...

    @abstractmethod
    def cancel_charge(self, external_id: str) -> bool:
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> dict:
        """Normaliza um payload de webhook e retorna:
        {'event': str, 'external_id': str, 'status': str, ...}
        """
        ...
