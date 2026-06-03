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
    ]
    
    EVENT_CHOICES = [
        ('CRIAR', 'Criação do Registro'),
        ('MUDANCA_STATUS', 'Alteração de Status'),
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
    Mapeamento de variáveis {{1}}, {{2}}, etc do template para campos do modelo.
    """
    config = models.ForeignKey(NotificationConfig, on_delete=models.CASCADE, related_name='variables', verbose_name="Configuração")
    index = models.PositiveIntegerField('Índice da Variável (Ex: 1 para {{1}})')
    field_path = models.CharField(
        'Caminho do Campo no Modelo', 
        max_length=255, 
        help_text='Ex: number, client_property.client.name, total_value'
    )

    class Meta:
        verbose_name = 'Variável de Notificação'
        verbose_name_plural = 'Variáveis de Notificação'
        ordering = ['index']
        unique_together = ('config', 'index')
