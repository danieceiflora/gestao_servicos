from django.db import models

class WebhookEvent(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('processed', 'Processado'),
        ('failed', 'Falha'),
    ]

    provider = models.CharField(max_length=50, verbose_name='Provedor')
    payload = models.JSONField(verbose_name='Payload Bruto')
    headers = models.JSONField(verbose_name='Cabeçalhos', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
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
    company_address = models.TextField('Endereço Completo', blank=True, null=True, help_text='Endereço que sairá no cabeçalho do PDF do Orçamento')
    company_website = models.URLField('Site', blank=True, null=True)
    company_phone = models.CharField('Telefone de Contato', max_length=20, blank=True, null=True)
    company_logo = models.ImageField('Logo da Empresa', upload_to='company/', blank=True, null=True)

    # Configurações do Chatwoot
    chatwoot_base_url = models.URLField('Chatwoot API URL', default='https://app.chatwoot.com', help_text='URL base da sua instância do Chatwoot (se self-hosted, altere)')
    chatwoot_account_id = models.CharField('Account ID', max_length=50, blank=True, null=True, help_text='ID da conta no Chatwoot')
    chatwoot_inbox_id = models.CharField('Inbox ID (WhatsApp)', max_length=50, blank=True, null=True, help_text='ID da caixa de entrada do WhatsApp')
    chatwoot_api_token = models.CharField('User API Access Token', max_length=255, blank=True, null=True, help_text='Token de acesso à API (do usuário/bot)')
    chatwoot_budget_template = models.CharField('Nome do Template de Orçamento', max_length=100, blank=True, null=True, help_text='Ex: enviar_orcamento_v1')

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

