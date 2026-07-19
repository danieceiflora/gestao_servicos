from django.db import models


class NFeConfig(models.Model):
    """Configuração da integração com a FocusNFe (singleton, pk=1).

    Diferente do gateway de pagamento (Asaas), a Focus não usa uma chave de API
    estática de conta — o token é por empresa e só existe depois que a empresa é
    cadastrada na Focus (`token_producao`/`token_homologacao`, devolvidos por
    `POST /empresas`). O certificado digital (A1) é enviado uma única vez em
    base64 para esse mesmo endpoint e fica custodiado pela Focus — não guardamos
    o arquivo aqui, só a validade retornada."""

    class Environment(models.TextChoices):
        SANDBOX = 'SANDBOX', 'Sandbox (Homologação)'
        PRODUCTION = 'PRODUCTION', 'Produção'

    class Status(models.TextChoices):
        NAO_CONFIGURADO = 'NAO_CONFIGURADO', 'Não configurado'
        PENDENTE_CERTIFICADO = 'PENDENTE_CERTIFICADO', 'Empresa criada — certificado pendente'
        ATIVO = 'ATIVO', 'Ativo'
        ERRO = 'ERRO', 'Erro'

    class RegimeTributario(models.IntegerChoices):
        SIMPLES_NACIONAL = 1, '1 - Simples Nacional'
        SIMPLES_EXCESSO = 2, '2 - Simples Nacional - excesso de sublimite de receita bruta'
        NORMAL = 3, '3 - Regime Normal'
        MEI = 4, '4 - MEI'

    environment = models.CharField('Ambiente', max_length=15, choices=Environment.choices, default=Environment.SANDBOX)
    status = models.CharField('Status', max_length=25, choices=Status.choices, default=Status.NAO_CONFIGURADO)
    status_detail = models.TextField('Detalhe do Status', blank=True)

    # Identificação na Focus
    focus_empresa_id = models.PositiveIntegerField('ID da Empresa na Focus', null=True, blank=True)
    token_producao = models.CharField(
        'Token de Produção', max_length=255, blank=True,
        help_text='Token da empresa na Focus (ambiente de produção). Copie do painel da Focus '
                  '("Serviços > Minhas Empresas") ou gere automaticamente usando o botão de '
                  'cadastro de empresa abaixo.'
    )
    token_homologacao = models.CharField('Token de Homologação', max_length=255, blank=True)
    account_token = models.CharField(
        'Token de Conta/Revenda da Focus', max_length=255, blank=True,
        help_text='Necessário apenas para cadastrar a empresa por aqui via API (botão "Cadastrar '
                  'empresa na Focus"). Não é o mesmo token da empresa — é o token de conta, '
                  'disponível no painel da Focus. Se preferir, cadastre a empresa direto no painel '
                  'da Focus e cole os tokens de produção/homologação acima manualmente.'
    )

    # Dados cadastrais do emitente
    razao_social = models.CharField('Razão Social', max_length=255, blank=True)
    nome_fantasia = models.CharField('Nome Fantasia', max_length=255, blank=True)
    cnpj = models.CharField('CNPJ', max_length=18, blank=True)
    inscricao_estadual = models.CharField('Inscrição Estadual', max_length=20, blank=True)
    inscricao_municipal = models.CharField('Inscrição Municipal', max_length=20, blank=True)
    regime_tributario = models.IntegerField('Regime Tributário (CRT)', choices=RegimeTributario.choices, default=RegimeTributario.SIMPLES_NACIONAL)

    # Endereço estruturado do emitente — necessário porque SystemConfig.company_address
    # é um único TextField livre, insuficiente para o JSON da Focus.
    logradouro = models.CharField('Logradouro', max_length=255, blank=True)
    numero = models.CharField('Número', max_length=20, blank=True)
    complemento = models.CharField('Complemento', max_length=255, blank=True)
    bairro = models.CharField('Bairro', max_length=100, blank=True)
    municipio = models.CharField('Município', max_length=100, blank=True, default='Goiânia')
    codigo_municipio_ibge = models.CharField(
        'Código IBGE do Município', max_length=7, blank=True, default='5208707',
        help_text='Código IBGE de 7 dígitos do município do prestador/emitente. Padrão: Goiânia/GO.'
    )
    uf = models.CharField('UF', max_length=2, blank=True, default='GO')
    cep = models.CharField('CEP', max_length=9, blank=True)

    # Documentos habilitados — controla quais botões de emissão aparecem na UI
    habilita_nfe = models.BooleanField('Habilita NFe', default=False)
    habilita_nfce = models.BooleanField('Habilita NFCe', default=False)
    habilita_nfse = models.BooleanField('Habilita NFSe Nacional', default=True)

    # Certificado — só metadados; o arquivo é custodiado pela Focus
    certificado_valido_ate = models.DateTimeField('Certificado Válido Até', null=True, blank=True)
    certificado_enviado_em = models.DateTimeField('Certificado Enviado em', null=True, blank=True)

    # Webhook — segredo próprio, registrado na Focus via authorization_header
    webhook_token = models.CharField('Token do Webhook', max_length=100, blank=True)

    # Fallback de tributação de serviço quando o Service faturado não tiver código próprio
    default_codigo_tributacao_iss = models.CharField(
        'Código de Tributação Nacional do ISS (padrão)', max_length=6, blank=True,
        help_text='Usado quando o serviço faturado não tiver um código de tributação nacional do ISS próprio.'
    )
    default_codigo_tributacao_municipal_iss = models.CharField(
        'Código de Tributação Municipal do ISS (padrão)', max_length=3, blank=True,
        help_text='Tabela própria da prefeitura (distinto do código nacional acima). Usado quando o '
                  'serviço faturado não tiver um código municipal próprio.'
    )
    default_codigo_indicador_operacao = models.CharField(
        'Código Indicador de Operação — cIndOp (padrão)', max_length=6, blank=True,
        help_text='Indicador de operação da Reforma Tributária (Anexo VIII — correlação item LC 116 x '
                  'NBS x cIndOp x cClassTrib). Usado quando o serviço faturado não tiver um código próprio.'
    )
    default_codigo_nbs = models.CharField(
        'Código NBS (padrão)', max_length=9, blank=True,
        help_text='Nomenclatura Brasileira de Serviços, 9 dígitos sem pontos (Anexo VIII). Diferente do '
                  'cIndOp, o NBS não é único por item LC 116 — varia por tipo específico de serviço, então '
                  'esse default só é confiável se todos os serviços faturados forem do mesmo tipo. Usado '
                  'quando o serviço faturado não tiver um código NBS próprio.'
    )

    # Reforma Tributária (IBS/CBS) — grupo obrigatório na NFSe Nacional a partir de 2026.
    # Não temos como adivinhar esse código automaticamente: depende do serviço prestado e
    # das regras de transição. Confirme com seu contador ou a documentação da Focus
    # (campos.focusnfe.com.br) antes de preencher.
    default_ibs_cbs_situacao_tributaria = models.CharField(
        'CST IBS/CBS (padrão)', max_length=3, blank=True,
        help_text='Código de Situação Tributária do IBS/CBS (Reforma Tributária). Consulte seu contador.'
    )
    default_ibs_cbs_classificacao_tributaria = models.CharField(
        'Classificação Tributária IBS/CBS (padrão)', max_length=6, blank=True,
        help_text='Código de Classificação Tributária do IBS/CBS (Reforma Tributária). Consulte seu contador.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de Nota Fiscal'
        verbose_name_plural = 'Configuração de Nota Fiscal'

    def __str__(self):
        return f'NFe Config ({self.get_environment_display()} — {self.get_status_display()})'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_sandbox(self):
        return self.environment == self.Environment.SANDBOX

    @property
    def active_token(self):
        return self.token_producao if self.environment == self.Environment.PRODUCTION else self.token_homologacao

    @property
    def can_emit(self):
        return self.status == self.Status.ATIVO and bool(self.active_token)

    @property
    def can_emit_nfe(self):
        return self.can_emit and self.habilita_nfe

    @property
    def can_emit_nfce(self):
        return self.can_emit and self.habilita_nfce

    @property
    def can_emit_nfse(self):
        return self.can_emit and self.habilita_nfse


class NFeDocument(models.Model):
    """Uma linha por tentativa de emissão de documento fiscal — trilha de
    auditoria de todas as chamadas feitas à Focus para uma Venda/Etapa de OS.

    Emissão de OS é por ETAPA (ServiceOrderTask), não pela OS inteira: cada
    etapa pode ter produto e serviço misturados, e cada tipo de item precisa
    de um documento fiscal diferente (NFe/NFCe pro produto, NFSe pro serviço),
    com tributação separada — nunca somando os dois no mesmo documento."""

    class DocumentType(models.TextChoices):
        NFE = 'NFE', 'NFe'
        NFCE = 'NFCE', 'NFCe'
        NFSE = 'NFSE', 'NFSe Nacional'

    class Status(models.TextChoices):
        PROCESSANDO = 'PROCESSANDO', 'Processando Autorização'
        AUTORIZADO = 'AUTORIZADO', 'Autorizado'
        ERRO = 'ERRO', 'Erro na Autorização'
        CANCELADO = 'CANCELADO', 'Cancelado'

    document_type = models.CharField('Tipo de Documento', max_length=10, choices=DocumentType.choices)

    sale = models.ForeignKey(
        'services.Sale', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_documents', verbose_name='Venda',
    )
    task = models.ForeignKey(
        'services.ServiceOrderTask', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_documents', verbose_name='Etapa da OS',
    )

    ref = models.CharField('Referência (nosso ID enviado à Focus)', max_length=80, unique=True)
    status = models.CharField('Status', max_length=15, choices=Status.choices, default=Status.PROCESSANDO)

    numero = models.CharField('Número', max_length=20, blank=True)
    serie = models.CharField('Série', max_length=10, blank=True)
    chave_acesso = models.CharField('Chave de Acesso', max_length=60, blank=True)
    codigo_verificacao = models.CharField('Código de Verificação (NFSe)', max_length=60, blank=True)

    status_sefaz = models.CharField('Status SEFAZ/Prefeitura', max_length=10, blank=True)
    mensagem_sefaz = models.TextField('Mensagem SEFAZ/Prefeitura', blank=True)

    xml_url = models.URLField('URL do XML', blank=True, max_length=500)
    pdf_url = models.URLField('URL do PDF (DANFE/DANFCe/DANFSe)', blank=True, max_length=500)
    qrcode_url = models.URLField('URL do QR Code (NFCe)', blank=True, max_length=500)

    error_details = models.JSONField('Detalhes do Erro', null=True, blank=True)
    raw_response = models.JSONField('Última Resposta Bruta da Focus', null=True, blank=True)

    cancelled_at = models.DateTimeField('Cancelado em', null=True, blank=True)
    cancel_justificativa = models.TextField('Justificativa do Cancelamento', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Documento Fiscal'
        verbose_name_plural = 'Documentos Fiscais'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(sale__isnull=False, task__isnull=True) |
                    models.Q(sale__isnull=True, task__isnull=False)
                ),
                name='fiscal_nfedocument_exactly_one_owner',
            ),
        ]

    def __str__(self):
        return f'{self.get_document_type_display()} #{self.numero or self.ref} ({self.get_status_display()})'

    @property
    def owner(self):
        return self.sale or self.task

    @property
    def service_order(self):
        return self.task.service_order if self.task_id else None
