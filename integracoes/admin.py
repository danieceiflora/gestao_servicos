import json
from django.contrib import admin
from django.utils.html import format_html
from .models import WebhookEvent, SystemConfig

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Dados da Empresa (PDF de Orçamento)', {
            'fields': ('company_name', 'company_cnpj', 'company_address', 'company_phone', 'company_website', 'company_logo')
        }),
        ('Integração Meta API Cloud (Principal)', {
            'fields': ('meta_access_token', 'meta_waba_id', 'meta_phone_number_id'),
            'description': 'Configure aqui as credenciais principais para sincronização de templates e envios diretos via WhatsApp Cloud API.'
        }),
        ('Integração Chatwoot (Atendimento)', {
            'fields': (
                'chatwoot_base_url', 'chatwoot_account_id', 'chatwoot_inbox_id', 
                'chatwoot_api_token', 'chatwoot_budget_template', 
                'chatwoot_pix_template', 'chatwoot_pix_label'
            )
        }),
        ('Dados Financeiros para PIX', {
            'fields': ('pix_key', 'pix_bank', 'pix_recipient'),
            'description': 'Estes dados serão enviados aos clientes nos templates de cobrança.'
        }),
    )

    def has_add_permission(self, request):
        # Evita criar mais de um registro
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Evita deletar o registro de configuração global
        return False

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'status', 'created_at')
    list_filter = ('status', 'provider', 'created_at')
    search_fields = ('provider', 'payload')
    readonly_fields = ('created_at', 'updated_at', 'formatted_payload', 'formatted_headers')
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('provider', 'status', 'notes', 'created_at', 'updated_at')
        }),
        ('Dados Recebidos', {
            'fields': ('formatted_payload', 'formatted_headers')
        }),
    )

    def formatted_payload(self, obj):
        if obj.payload:
            try:
                formatted = json.dumps(obj.payload, indent=2, sort_keys=True, ensure_ascii=False)
                return format_html('<pre>{}</pre>', formatted)
            except Exception:
                return str(obj.payload)
        return "-"
    formatted_payload.short_description = 'Payload Formatado'

    def formatted_headers(self, obj):
        if obj.headers:
            try:
                formatted = json.dumps(obj.headers, indent=2, sort_keys=True, ensure_ascii=False)
                return format_html('<pre>{}</pre>', formatted)
            except Exception:
                return str(obj.headers)
        return "-"
    formatted_headers.short_description = 'Cabeçalhos Formatados'
