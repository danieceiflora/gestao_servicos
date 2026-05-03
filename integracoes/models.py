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
