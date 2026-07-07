from django.db import models

class WebhookEvent(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processado', 'Processado'),
        ('falha', 'Falha'),
    ]

    provider = models.CharField(max_length=50, verbose_name='Provedor')
    payload = models.JSONField(verbose_name='Payload Bruto')
    headers = models.JSONField(verbose_name='Cabeçalhos', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente', verbose_name='Status')
    notes = models.TextField(blank=True, null=True, verbose_name='Notas/Erros')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Recebido em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        verbose_name = 'Evento de Webhook'
        verbose_name_plural = 'Eventos de Webhook'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider} - {self.get_status_display()} ({self.created_at.strftime('%d/%m/%Y %H:%M')})"

class SystemConfig(models.Model):
    """
    Configurações globais do sistema: Dados da empresa para PDF e chaves de API.
    Apenas um registro deve existir (Singleton).
    """
    # Dados da Empresa (para o PDF)
    company_name = models.CharField('Razão Social / Nome Fantasia', max_length=255, default='Minha Empresa')
    company_cnpj = models.CharField('CNPJ', max_length=20, blank=True, null=True)
    tax_regime = models.CharField('Regime Tributário', max_length=20, choices=[('SIMPLES', 'Simples Nacional'), ('NORMAL', 'Regime Normal')], default='SIMPLES')
    company_address = models.TextField('Endereço Completo', blank=True, null=True, help_text='Endereço que sairá no cabeçalho do PDF do Orçamento')
    state = models.CharField('UF', max_length=2, default='MS', help_text='UF da empresa para cálculo de CFOP')
    company_website = models.URLField('Site', blank=True, null=True)
    company_phone = models.CharField('Telefone de Contato', max_length=20, blank=True, null=True)
    company_logo = models.ImageField('Logo da Empresa', upload_to='company/', blank=True, null=True)

    # Configurações do Chatwoot
    chatwoot_base_url = models.URLField('Chatwoot API URL', default='https://app.chatwoot.com', help_text='URL base da sua instância do Chatwoot (se self-hosted, altere)')
    chatwoot_account_id = models.CharField('Account ID', max_length=50, blank=True, null=True, help_text='ID da conta no Chatwoot')
    chatwoot_inbox_id = models.CharField('Inbox ID (WhatsApp)', max_length=50, blank=True, null=True, help_text='ID da caixa de entrada do WhatsApp')
    chatwoot_api_token = models.CharField('User API Access Token', max_length=255, blank=True, null=True, help_text='Token de acesso à API (do usuário/bot)')
    chatwoot_budget_template = models.CharField('Nome do Template de Orçamento', max_length=100, blank=True, null=True, help_text='Ex: enviar_orcamento_v1')
    chatwoot_pix_template = models.CharField('Nome do Template de Cobrança/PIX', max_length=100, blank=True, null=True, help_text='Ex: enviar_pix_v1')
    chatwoot_pix_label = models.CharField('Etiqueta para PIX Enviado', max_length=50, default='pix-enviado', help_text='Etiqueta que será aplicada na conversa ao enviar o PIX')
    chatwoot_receipt_template = models.CharField('Nome do Template de Recibo/Avaliação', max_length=100, default='baixa_pagamento_avaliacao', help_text='Template enviado ao finalizar a OS')
    chatwoot_evaluation_label = models.CharField('Etiqueta de Avaliação', max_length=50, default='avaliacao-google', help_text='Etiqueta aplicada após o envio do recibo. Substitui as anteriores.')

    # Dados Financeiros para PIX
    pix_key = models.CharField('Chave PIX', max_length=100, default='41426314000138')
    pix_bank = models.CharField('Banco', max_length=100, default='Bradesco')
    pix_recipient = models.CharField('Destinatário (Nome/Razão Social)', max_length=255, default='Dourados Calhas')

    # Configurações Financeiras
    billing_default_due_days = models.PositiveIntegerField('Dias Padrão para Vencimento', default=1, help_text='Prazo padrão em dias para o primeiro vencimento após a conclusão do serviço/venda.')

    # Configurações Diretas da Meta (WhatsApp Cloud API)
    meta_waba_id = models.CharField('WhatsApp Business Account ID', max_length=100, blank=True, null=True, help_text='Necessário para buscar definições de templates diretamente na Meta')
    meta_phone_number_id = models.CharField('WhatsApp Phone Number ID', max_length=100, blank=True, null=True, help_text='ID do número de telefone na API da Meta')
    meta_access_token = models.CharField('Meta System User Access Token', max_length=512, blank=True, null=True, help_text='Token de acesso permanente do Gerenciador de Negócios da Meta')

    class Meta:
        verbose_name = 'Configuração do Sistema'
        verbose_name_plural = 'Configurações do Sistema'

    def __str__(self):
        return "Configurações Globais"

    def save(self, *args, **kwargs):
        # Garante que só existe 1 registro no banco
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class NotificationConfig(models.Model):
    """
    Configuração dinâmica de notificações automáticas baseadas em eventos de modelos.
    """
    MODEL_CHOICES = [
        ('ServiceOrder', 'Ordem de Serviço'),
        ('ServiceOrderTask', 'Etapa de Serviço'),
        ('Sale', 'Venda'),
        ('Billing', 'Cobrança (Fatura)'),
        ('Installment', 'Parcela de Cobrança'),
        ('ExpenseInstallment', 'Parcela de Despesa (C. a Pagar)'),
    ]

    EVENT_CHOICES = [
        ('CRIAR', 'Criação do Registro'),
        ('MUDANCA_STATUS', 'Alteração de Status'),
        ('PAGAMENTO_PARCIAL', 'Pagamento Parcial Registrado'),
        ('PAGAMENTO_INTEGRAL', 'Pagamento Integral Registrado'),
    ]

    name = models.CharField('Nome da Regra/Descrição', max_length=100)
    model_name = models.CharField('Modelo', max_length=50, choices=MODEL_CHOICES)
    event_type = models.CharField('Evento Gatilho', max_length=20, choices=EVENT_CHOICES)
    
    # Filtros de Status (apenas para EVENT_TYPE == 'MUDANCA_STATUS')
    from_status = models.CharField(
        'Status de Origem (Filtro)', 
        max_length=50, 
        blank=True, 
        null=True, 
        help_text='Opcional: Disparar apenas se vier deste status. Deixe vazio para qualquer origem.'
    )
    to_status = models.CharField(
        'Status de Destino (Gatilho)', 
        max_length=50, 
        blank=True, 
        null=True,
        help_text='Obrigatório: O status que o registro deve assumir para disparar a regra.'
    )
    
    # Template e Destinatário
    RECIPIENT_CHOICES = [
        ('DYNAMIC', 'Campo Dinâmico (Variável do Modelo)'),
        ('FIXED', 'Número Fixo (Sempre o mesmo)'),
    ]
    
    recipient_type = models.CharField(
        'Tipo de Destinatário', 
        max_length=20, 
        choices=RECIPIENT_CHOICES, 
        default='DYNAMIC'
    )
    
    fixed_phone = models.CharField(
        'Telefone Fixo', 
        max_length=20, 
        blank=True, 
        null=True, 
        help_text='Somente se o tipo for Número Fixo. Ex: 5567999999999'
    )

    template_name = models.CharField('Nome do Template na Meta', max_length=100, help_text='Ex: boas_vindas_cliente')
    
    # Suporte a Mídia no Cabeçalho (Header)
    HEADER_MEDIA_CHOICES = [
        ('NONE', 'Nenhum'),
        ('BUDGET_PDF', 'Orçamento (PDF Gerado)'),
        ('REPORT_PDF', 'Relatório de Execução (PDF Gerado)'),
        ('SALE_PDF', 'Relatório de Venda (PDF Gerado)'),
        ('STATIC_PDF', 'PDF Estático (Upload)'),
    ]
    header_media_type = models.CharField(
        'Tipo de Mídia no Cabeçalho', 
        max_length=20, 
        choices=HEADER_MEDIA_CHOICES, 
        default='NONE'
    )
    static_media_file = models.FileField(
        'Arquivo Estático', 
        upload_to='notifications/static/', 
        blank=True, 
        null=True,
        help_text='Somente se o tipo for PDF Estático'
    )

    phone_field_path = models.CharField(
        'Caminho para o Cliente/Telefone', 
        max_length=255, 
        default='client_property.client',
        blank=True, 
        null=True,
        help_text='Caminho para chegar no objeto Cliente ou campo de Telefone. Ex: client_property.client para OS.'
    )
    
    is_active = models.BooleanField('Ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de Notificação'
        verbose_name_plural = 'Configurações de Notificações'
        ordering = ['model_name', 'name']

    def __str__(self):
        return f"{self.get_model_name_display()} - {self.name} ({self.template_name})"

class NotificationVariable(models.Model):
    """
    Mapeamento de variáveis do template para campos do modelo.
    component=BODY → {{index}} no corpo; component=BUTTON → sufixo dinâmico do botão na posição index.
    """
    class Component(models.TextChoices):
        BODY = 'BODY', 'Corpo'
        BUTTON = 'BUTTON', 'Botão'

    config = models.ForeignKey(NotificationConfig, on_delete=models.CASCADE, related_name='variables', verbose_name="Configuração")
    index = models.PositiveIntegerField('Índice (corpo: 1-based; botão: 0-based)')
    field_path = models.CharField(
        'Caminho do Campo no Modelo',
        max_length=255,
        help_text='Ex: number, client_property.client.name, total_value'
    )
    component = models.CharField(
        'Componente', max_length=10,
        choices=Component.choices, default=Component.BODY,
    )

    class Meta:
        verbose_name = 'Variável de Notificação'
        verbose_name_plural = 'Variáveis de Notificação'
        ordering = ['component', 'index']
        unique_together = ('config', 'component', 'index')


# --- RÉGUA DE COBRANÇA ---

class CollectionSequence(models.Model):
    name = models.CharField('Nome da Régua', max_length=200)
    start_after_days_overdue = models.PositiveIntegerField(
        'Iniciar após (dias em atraso)', default=1,
        help_text='Só começa a cobrar após a parcela estar em atraso por este número de dias'
    )
    stop_after_days_overdue = models.PositiveIntegerField(
        'Parar após (dias em atraso)', default=60,
        help_text='Para de cobrar se a parcela estiver em atraso há mais dias que este valor'
    )
    max_occurrences = models.PositiveIntegerField(
        'Máximo de cobranças', default=3,
        help_text='Número máximo de mensagens enviadas por parcela'
    )
    min_interval_days = models.PositiveIntegerField(
        'Intervalo mínimo (dias)', default=5,
        help_text='Intervalo mínimo entre cobranças para saúde da conta Meta'
    )
    is_active = models.BooleanField('Ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Régua de Cobrança'
        verbose_name_plural = 'Réguas de Cobrança'
        ordering = ['name']

    def __str__(self):
        return self.name


class CollectionStep(models.Model):
    sequence = models.ForeignKey(CollectionSequence, on_delete=models.CASCADE, related_name='steps')
    occurrence = models.PositiveIntegerField('Nº da Ocorrência', help_text='1 = primeira cobrança, 2 = segunda, etc.')
    label = models.CharField('Tom / Descrição', max_length=200, blank=True, help_text='Ex: Tom amigável, Tom firme')
    template_name = models.CharField('Template WhatsApp (Meta)', max_length=200)
    wait_days_before_next = models.PositiveIntegerField(
        'Aguardar antes da próxima (dias)', default=7,
        help_text='Dias a aguardar após este envio antes de enviar a próxima etapa'
    )

    class Meta:
        verbose_name = 'Etapa da Régua'
        verbose_name_plural = 'Etapas da Régua'
        unique_together = ('sequence', 'occurrence')
        ordering = ['occurrence']

    def __str__(self):
        return f"{self.sequence.name} — #{self.occurrence} {self.label or self.template_name}"

    @property
    def effective_interval(self):
        return max(self.sequence.min_interval_days, self.wait_days_before_next)


class CollectionStepVariable(models.Model):
    class Component(models.TextChoices):
        BODY   = 'BODY',   'Corpo'
        BUTTON = 'BUTTON', 'Botão'

    step = models.ForeignKey(CollectionStep, on_delete=models.CASCADE, related_name='variables')
    index = models.PositiveIntegerField('Índice')
    field_path = models.CharField('Caminho do Campo', max_length=255)
    component = models.CharField('Componente', max_length=10, choices=Component.choices, default=Component.BODY)

    class Meta:
        verbose_name = 'Variável da Etapa'
        verbose_name_plural = 'Variáveis da Etapa'
        ordering = ['component', 'index']
        unique_together = ('step', 'component', 'index')


class CollectionInstallmentState(models.Model):
    installment = models.OneToOneField(
        'services.Installment', on_delete=models.CASCADE,
        related_name='collection_state'
    )
    sequence = models.ForeignKey(CollectionSequence, on_delete=models.CASCADE, related_name='states')
    current_occurrence = models.PositiveIntegerField('Ocorrência Atual', default=0)
    last_sent_at = models.DateField('Último Envio', null=True, blank=True)
    next_eligible_date = models.DateField('Próximo Envio Elegível', null=True, blank=True)
    is_paused = models.BooleanField('Pausado', default=False)

    class Meta:
        verbose_name = 'Estado de Cobrança da Parcela'
        verbose_name_plural = 'Estados de Cobrança das Parcelas'

    def __str__(self):
        return f"Parcela #{self.installment_id} — ocorrência {self.current_occurrence}"


class CollectionLog(models.Model):
    class Status(models.TextChoices):
        SENT   = 'SENT',   'Enviado'
        FAILED = 'FAILED', 'Falhou'

    installment = models.ForeignKey(
        'services.Installment', on_delete=models.CASCADE,
        related_name='collection_logs'
    )
    step = models.ForeignKey(CollectionStep, on_delete=models.CASCADE, related_name='logs')
    occurrence_number = models.PositiveIntegerField('Nº da Ocorrência')
    sent_at = models.DateTimeField('Enviado em', auto_now_add=True)
    phone = models.CharField('Telefone', max_length=30, blank=True)
    status = models.CharField('Status', max_length=10, choices=Status.choices, default=Status.SENT)
    notes = models.TextField('Observações', blank=True)

    class Meta:
        verbose_name = 'Log de Cobrança'
        verbose_name_plural = 'Logs de Cobrança'
        ordering = ['-sent_at']

    def __str__(self):
        return f"Parcela #{self.installment_id} — etapa #{self.occurrence_number} ({self.status})"


# --- LEMBRETES AGENDADOS (ENVIO ÚNICO) ---

class ScheduledReminder(models.Model):
    name = models.CharField('Nome', max_length=200)
    offset_days = models.IntegerField(
        'Offset em Dias', default=-1,
        help_text='Negativo = antes do vencimento (ex: -1 = 1 dia antes), 0 = no vencimento, positivo = após (ex: 3 = 3 dias após vencido)'
    )
    template_name = models.CharField('Template WhatsApp (Meta)', max_length=200)
    is_active = models.BooleanField('Ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lembrete Agendado'
        verbose_name_plural = 'Lembretes Agendados'
        ordering = ['offset_days', 'name']

    def __str__(self):
        return self.name

    @property
    def offset_label(self):
        if self.offset_days < 0:
            return f'{abs(self.offset_days)} dia(s) antes do vencimento'
        elif self.offset_days == 0:
            return 'No dia do vencimento'
        return f'{self.offset_days} dia(s) após o vencimento'


class ScheduledReminderVariable(models.Model):
    class Component(models.TextChoices):
        BODY   = 'BODY',   'Corpo'
        BUTTON = 'BUTTON', 'Botão'

    reminder = models.ForeignKey(ScheduledReminder, on_delete=models.CASCADE, related_name='variables')
    index = models.PositiveIntegerField('Índice')
    field_path = models.CharField('Caminho do Campo', max_length=255)
    component = models.CharField('Componente', max_length=10, choices=Component.choices, default=Component.BODY)

    class Meta:
        verbose_name = 'Variável do Lembrete'
        verbose_name_plural = 'Variáveis do Lembrete'
        unique_together = ('reminder', 'component', 'index')
        ordering = ['component', 'index']


class ScheduledReminderLog(models.Model):
    class Status(models.TextChoices):
        SENT   = 'SENT',   'Enviado'
        FAILED = 'FAILED', 'Falhou'

    reminder = models.ForeignKey(ScheduledReminder, on_delete=models.CASCADE, related_name='logs')
    installment = models.ForeignKey(
        'services.Installment', on_delete=models.CASCADE,
        related_name='scheduled_reminder_logs'
    )
    sent_at = models.DateTimeField('Enviado em', auto_now_add=True)
    phone = models.CharField('Telefone', max_length=30, blank=True)
    status = models.CharField('Status', max_length=10, choices=Status.choices, default=Status.SENT)
    notes = models.TextField('Observações', blank=True)

    class Meta:
        verbose_name = 'Log de Lembrete'
        verbose_name_plural = 'Logs de Lembretes'
        ordering = ['-sent_at']

    def __str__(self):
        return f'Lembrete #{self.reminder_id} → Parcela #{self.installment_id} ({self.status})'


# ── MENSAGENS MANUAIS ────────────────────────────────────────────────────────

class ManualMessageConfig(models.Model):
    """Configura o template WhatsApp disparado por ações manuais (ex: Enviar Orçamento)."""

    TRIGGER_CHOICES = [
        ('ENVIO_ORCAMENTO',  'Envio de Orçamento'),
        ('CONVITE_CADASTRO', 'Convite para Cadastro'),
    ]

    HEADER_MEDIA_CHOICES = [
        ('NONE',       'Sem mídia'),
        ('BUDGET_PDF', 'PDF do Orçamento (gerado dinamicamente)'),
        ('STATIC_PDF', 'PDF Estático (upload)'),
    ]

    trigger = models.CharField('Gatilho', max_length=50, choices=TRIGGER_CHOICES, unique=True)
    template_name = models.CharField('Template WhatsApp (Meta)', max_length=100)
    header_media_type = models.CharField(
        'Mídia do Cabeçalho', max_length=20,
        choices=HEADER_MEDIA_CHOICES, default='NONE',
    )
    static_media_file = models.FileField(
        'Arquivo Estático', upload_to='manual_messages/static/',
        blank=True, null=True,
    )
    is_active = models.BooleanField('Ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mensagem Manual'
        verbose_name_plural = 'Mensagens Manuais'

    def __str__(self):
        return f'{self.get_trigger_display()} → {self.template_name}'


class ManualMessageVariable(models.Model):
    class Component(models.TextChoices):
        BODY   = 'BODY',   'Corpo'
        BUTTON = 'BUTTON', 'Botão'

    config     = models.ForeignKey(ManualMessageConfig, on_delete=models.CASCADE, related_name='variables')
    index      = models.PositiveIntegerField('Índice')
    field_path = models.CharField('Caminho do Campo', max_length=255)
    component  = models.CharField('Componente', max_length=10, choices=Component.choices, default=Component.BODY)

    class Meta:
        verbose_name = 'Variável de Mensagem Manual'
        verbose_name_plural = 'Variáveis de Mensagens Manuais'
        unique_together = ('config', 'component', 'index')
        ordering = ['component', 'index']


# --- ASSINATURA DA PLATAFORMA (PIX RECORRENTE / PUSHINPAY) ---

class PushinPaySubscription(models.Model):
    """
    Estado atual da assinatura da plataforma (mensalidade devida ao fornecedor
    do software), cobrada via Pix recorrente da PushinPay. Singleton (pk=1).
    Valor e periodicidade não são configuráveis aqui — vêm de settings/.env.
    """
    class Status(models.TextChoices):
        NAO_CRIADA = 'NAO_CRIADA', 'Não criada'
        AGUARDANDO_PRIMEIRO_PAGAMENTO = 'AGUARDANDO_PRIMEIRO_PAGAMENTO', 'Aguardando primeiro pagamento'
        ATIVA = 'ATIVA', 'Ativa'
        ATRASADA = 'ATRASADA', 'Atrasada'
        CANCELADA = 'CANCELADA', 'Cancelada'

    subscription_id = models.CharField('ID da Assinatura (PushinPay)', max_length=100, blank=True)
    first_charge_id = models.CharField('ID da Primeira Cobrança', max_length=100, blank=True)
    status = models.CharField('Status', max_length=40, choices=Status.choices, default=Status.NAO_CRIADA)

    qr_code = models.TextField('Pix Copia e Cola', blank=True)
    qr_code_base64 = models.TextField('QR Code (base64)', blank=True)

    # Snapshot dos parâmetros usados na criação (histórico continua correto
    # mesmo que o .env mude depois).
    value_cents = models.PositiveIntegerField('Valor (centavos)', default=0)
    frequency = models.CharField('Periodicidade', max_length=50, blank=True)
    retry_policy = models.PositiveIntegerField('Política de Retentativas', default=0)

    last_event_at = models.DateTimeField('Último Evento em', null=True, blank=True)
    status_detail = models.TextField('Observações', blank=True, help_text='Avisos, ex: evento de webhook não reconhecido — revisar manualmente')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Assinatura da Plataforma'
        verbose_name_plural = 'Assinatura da Plataforma'

    def __str__(self):
        return f"Assinatura da Plataforma — {self.get_status_display()}"

    @property
    def value_reais(self):
        return f'{self.value_cents / 100:.2f}'.replace('.', ',')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class PushinPaySubscriptionEvent(models.Model):
    """
    Histórico append-only de eventos da assinatura (criação + cada webhook
    recebido da PushinPay). Nunca editável pela UI/admin — ver admin.py.
    """
    subscription = models.ForeignKey(PushinPaySubscription, on_delete=models.CASCADE, related_name='events')
    charge_id = models.CharField('ID da Cobrança', max_length=100, blank=True)
    raw_event = models.CharField('Evento (bruto)', max_length=100, blank=True)
    mapped_status = models.CharField('Status Mapeado', max_length=40, choices=PushinPaySubscription.Status.choices, blank=True)
    payload = models.JSONField('Payload Bruto', default=dict, blank=True)
    headers = models.JSONField('Cabeçalhos', blank=True, null=True)
    notes = models.TextField('Observações', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Evento da Assinatura'
        verbose_name_plural = 'Eventos da Assinatura'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.raw_event or 'evento'} — {self.created_at.strftime('%d/%m/%Y %H:%M')}"
