from django.db import models
from decimal import Decimal


class BillingChargeConfig(models.Model):
    """Regra de cobrança via gateway: desconto antecipado, juros e multa por atraso."""

    class DiscountType(models.TextChoices):
        NONE = 'NONE', 'Sem desconto'
        FIXED = 'FIXED', 'Valor fixo (R$)'
        PERCENTAGE = 'PERCENTAGE', 'Percentual (%)'

    class FineType(models.TextChoices):
        NONE = 'NONE', 'Sem multa'
        FIXED = 'FIXED', 'Valor fixo (R$)'
        PERCENTAGE = 'PERCENTAGE', 'Percentual (%)'

    class DefaultMethod(models.TextChoices):
        PIX = 'PIX', 'PIX'
        BOLETO = 'BOLETO', 'Boleto Bancário'

    name = models.CharField('Nome da Regra', max_length=100)
    default_method = models.CharField('Método Padrão', max_length=10,
                                      choices=DefaultMethod.choices, default=DefaultMethod.PIX)

    # Desconto por antecipação
    discount_type = models.CharField('Tipo de Desconto', max_length=15,
                                     choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField('Valor do Desconto', max_digits=10, decimal_places=2,
                                         default=Decimal('0'))
    discount_due_days = models.IntegerField(
        'Prazo do Desconto (dias antes do vencimento)', default=0,
        help_text='0 = desconto válido até o próprio vencimento'
    )

    # Juros por atraso
    interest_monthly = models.DecimalField(
        'Juros por Atraso (% a.m.)', max_digits=6, decimal_places=2, default=Decimal('0'),
        help_text='Percentual ao mês cobrado em caso de atraso. Ex: 1.00 = 1%/mês'
    )

    # Multa por atraso
    fine_type = models.CharField('Tipo de Multa', max_length=15,
                                 choices=FineType.choices, default=FineType.NONE)
    fine_value = models.DecimalField('Valor da Multa', max_digits=10, decimal_places=2,
                                     default=Decimal('0'))

    # Disparo automático
    auto_send_to_gateway = models.BooleanField(
        'Gerar cobrança automaticamente', default=False,
        help_text='Se ativo, dispara a cobrança no gateway assim que o billing for criado'
    )

    is_default = models.BooleanField('Regra padrão', default=False,
                                     help_text='Aplicada automaticamente ao criar novos billings')
    is_active = models.BooleanField('Ativa', default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Regra de Cobrança'
        verbose_name_plural = 'Regras de Cobrança'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            BillingChargeConfig.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class GatewayConfig(models.Model):
    """Singleton — configuração do gateway de pagamento para esta instância."""

    class Environment(models.TextChoices):
        SANDBOX = 'SANDBOX', 'Sandbox (Testes)'
        PRODUCTION = 'PRODUCTION', 'Produção'

    class Status(models.TextChoices):
        NOT_CONFIGURED = 'NOT_CONFIGURED', 'Não Configurado'
        PENDING_DOCS = 'PENDING_DOCS', 'Documentação Pendente'
        UNDER_ANALYSIS = 'UNDER_ANALYSIS', 'Em Análise'
        APPROVED = 'APPROVED', 'Aprovado'
        REJECTED = 'REJECTED', 'Rejeitado'

    class CompanyType(models.TextChoices):
        MEI = 'MEI', 'MEI'
        LIMITED = 'LIMITED', 'LTDA'
        INDIVIDUAL = 'INDIVIDUAL', 'Empresário Individual'
        ASSOCIATION = 'ASSOCIATION', 'Associação'
        AUTONOMO = 'AUTONOMO', 'Autônomo'

    class SplitType(models.TextChoices):
        PERCENT = 'PERCENT', 'Percentual (%)'
        FIXED = 'FIXED', 'Valor Fixo (R$)'

    # Dados da empresa (subconta)
    company_name = models.CharField('Razão Social', max_length=255, blank=True)
    company_type = models.CharField('Tipo de Empresa', max_length=15, choices=CompanyType.choices, blank=True)
    cpf_cnpj = models.CharField('CPF / CNPJ', max_length=20, blank=True)
    email = models.EmailField('E-mail', blank=True)
    phone = models.CharField('Telefone / Celular', max_length=20, blank=True)

    # Endereço
    address_street = models.CharField('Logradouro', max_length=255, blank=True)
    address_number = models.CharField('Número', max_length=20, blank=True)
    address_complement = models.CharField('Complemento', max_length=100, blank=True)
    address_neighborhood = models.CharField('Bairro', max_length=100, blank=True)
    address_city = models.CharField('Cidade', max_length=100, blank=True)
    address_state = models.CharField('Estado (UF)', max_length=2, blank=True)
    address_zip = models.CharField('CEP', max_length=10, blank=True)

    income_value = models.DecimalField('Faturamento Mensal Estimado (R$)', max_digits=12,
                                       decimal_places=2, default=Decimal('0'),
                                       help_text='Exigido pelo Asaas para abertura de subconta')

    # Credenciais da subconta Asaas (preenchidos após criação)
    wallet_id = models.CharField('Wallet ID', max_length=100, blank=True,
                                 help_text='ID da carteira no Asaas após criação da subconta')
    subaccount_api_key = models.CharField('API Key da Subconta', max_length=255, blank=True,
                                          help_text='Chave da subconta — usada para emitir cobranças no nome do cliente')

    # Ambiente e status
    environment = models.CharField('Ambiente', max_length=15,
                                   choices=Environment.choices, default=Environment.SANDBOX)
    status = models.CharField('Status', max_length=20,
                              choices=Status.choices, default=Status.NOT_CONFIGURED)
    status_detail = models.TextField('Detalhes do Status', blank=True)

    # Métodos de pagamento habilitados
    pix_enabled = models.BooleanField('PIX habilitado', default=True)
    boleto_enabled = models.BooleanField('Boleto habilitado', default=False)

    webhook_token = models.CharField(
        'Token de Autenticação do Webhook',
        max_length=100,
        blank=True,
        help_text='Token cadastrado no painel Asaas ao registrar o webhook. '
                  'O Asaas envia este valor no header asaas-access-token.',
    )

    # Split — margem retida pela plataforma
    platform_split_type = models.CharField('Tipo de Split', max_length=10,
                                           choices=SplitType.choices, default=SplitType.PERCENT)
    platform_split_value = models.DecimalField('Valor do Split', max_digits=6,
                                               decimal_places=2, default=Decimal('0'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de Gateway'
        verbose_name_plural = 'Configurações de Gateway'

    def __str__(self):
        return f'Gateway ({self.get_environment_display()} — {self.get_status_display()})'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_active(self):
        return self.status == self.Status.APPROVED

    @property
    def is_sandbox(self):
        from django.conf import settings
        return getattr(settings, 'ASAAS_ENVIRONMENT', 'SANDBOX').upper() == 'SANDBOX'

    @property
    def can_generate_charges(self):
        """Em produção exige APPROVED. Em sandbox libera se a subconta já foi criada."""
        if self.status == self.Status.APPROVED:
            return True
        if self.is_sandbox and self.wallet_id and self.status in [
            self.Status.PENDING_DOCS, self.Status.UNDER_ANALYSIS,
        ]:
            return True
        return False


class GatewayCharge(models.Model):
    """Cobrança criada no gateway vinculada a uma Installment do sistema."""

    class Method(models.TextChoices):
        PIX = 'PIX', 'PIX'
        BOLETO = 'BOLETO', 'Boleto Bancário'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Aguardando Pagamento'
        RECEIVED = 'RECEIVED', 'Recebido'
        CONFIRMED = 'CONFIRMED', 'Confirmado'
        OVERDUE = 'OVERDUE', 'Vencido'
        REFUNDED = 'REFUNDED', 'Estornado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    installment = models.ForeignKey(
        'services.Installment',
        on_delete=models.PROTECT,
        related_name='gateway_charges',
        verbose_name='Parcela',
    )
    config = models.ForeignKey(
        GatewayConfig,
        on_delete=models.PROTECT,
        related_name='charges',
        verbose_name='Configuração',
    )
    gateway = models.CharField('Gateway', max_length=20, default='ASAAS')
    external_id = models.CharField('ID Externo', max_length=100, unique=True,
                                   help_text='ID da cobrança no gateway')
    method = models.CharField('Método', max_length=10, choices=Method.choices)
    status = models.CharField('Status', max_length=20, choices=Status.choices,
                              default=Status.PENDING)
    amount = models.DecimalField('Valor (R$)', max_digits=10, decimal_places=2)
    due_date = models.DateField('Vencimento')

    # PIX
    pix_qrcode = models.TextField('QR Code PIX (Base64)', blank=True)
    pix_copy_paste = models.TextField('PIX Copia e Cola', blank=True)
    pix_expiration_date = models.DateTimeField('Expiração PIX', null=True, blank=True)

    # Boleto
    boleto_url = models.URLField('URL do Boleto', blank=True)
    boleto_barcode = models.CharField('Linha Digitável', max_length=200, blank=True)
    boleto_bank_slip_url = models.URLField('URL PDF Boleto', blank=True)

    # Página de fatura hospedada pelo Asaas (PIX e Boleto) — permite ao cliente
    # copiar o código/linha digitável e baixar o PDF sem precisarmos hospedar nada
    invoice_url = models.URLField('URL da Fatura (Asaas)', blank=True)
    invoice_number = models.CharField('Número da Fatura (Asaas)', max_length=50, blank=True,
                                      help_text='Número visível no extrato do recebedor ao receber split')

    # Confirmação de pagamento
    paid_at = models.DateTimeField('Pago em', null=True, blank=True)
    net_value = models.DecimalField('Valor Líquido', max_digits=10, decimal_places=2,
                                    null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cobrança no Gateway'
        verbose_name_plural = 'Cobranças no Gateway'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_method_display()} — {self.external_id} ({self.get_status_display()})'

    @property
    def is_paid(self):
        return self.status in [self.Status.RECEIVED, self.Status.CONFIRMED]

    @property
    def is_active(self):
        return self.status in [self.Status.PENDING, self.Status.OVERDUE]
