import json
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    WebhookEvent, SystemConfig, NotificationConfig, NotificationVariable,
    ScheduledReminder, ScheduledReminderVariable, ScheduledReminderLog,
    PlatformSubscription, PlatformSubscriptionEvent,
)

class NotificationVariableInline(admin.TabularInline):
    model = NotificationVariable
    extra = 1

@admin.register(NotificationConfig)
class NotificationConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_name', 'event_type', 'template_name', 'is_active')
    list_filter = ('model_name', 'event_type', 'is_active')
    search_fields = ('name', 'template_name')
    inlines = [NotificationVariableInline]
    
    fieldsets = (
        ('Identificação', {
            'fields': ('name', 'is_active')
        }),
        ('Gatilho', {
            'fields': ('model_name', 'event_type', 'from_status', 'to_status'),
            'description': 'Configure quando esta notificação deve ser enviada.'
        }),
        ('WhatsApp Template', {
            'fields': ('template_name', 'phone_field_path'),
            'description': 'Configure qual template usar e como encontrar o telefone do cliente.'
        }),
    )

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


# --- Lembretes Agendados ---

class ScheduledReminderVariableInline(admin.TabularInline):
    model = ScheduledReminderVariable
    extra = 1
    fields = ['index', 'field_path']


@admin.register(ScheduledReminder)
class ScheduledReminderAdmin(admin.ModelAdmin):
    list_display = ['name', 'offset_days', 'template_name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'template_name']
    inlines = [ScheduledReminderVariableInline]
    fieldsets = (
        ('Identificação', {
            'fields': ('name', 'is_active'),
        }),
        ('Gatilho', {
            'fields': ('offset_days',),
            'description': 'Negativo = antes do vencimento. Zero = no vencimento. Positivo = após o vencimento.',
        }),
        ('Mensagem', {
            'fields': ('template_name',),
        }),
    )


@admin.register(ScheduledReminderLog)
class ScheduledReminderLogAdmin(admin.ModelAdmin):
    list_display = ['reminder', 'installment', 'phone', 'status', 'sent_at']
    list_filter = ['status', 'sent_at', 'reminder']
    search_fields = ['reminder__name', 'phone', 'installment__billing__number']
    readonly_fields = ['reminder', 'installment', 'phone', 'status', 'notes', 'sent_at']

    def has_add_permission(self, request):
        return False


# --- Assinatura da Plataforma (Pix Recorrente / Asaas) ---

@admin.register(PlatformSubscription)
class PlatformSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['status', 'subscription_id', 'value_cents', 'last_event_at', 'updated_at']
    readonly_fields = [
        'subscription_id', 'first_charge_id', 'qr_code', 'qr_code_base64',
        'value_cents', 'cycle', 'last_event_at',
        'created_at', 'updated_at',
    ]

    def has_add_permission(self, request):
        # Singleton — nunca criar um segundo registro pelo admin
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformSubscriptionEvent)
class PlatformSubscriptionEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'subscription', 'raw_event', 'mapped_status', 'charge_id', 'created_at']
    list_filter = ['mapped_status', 'created_at']
    search_fields = ['charge_id', 'raw_event']
    readonly_fields = ['subscription', 'charge_id', 'raw_event', 'mapped_status', 'formatted_payload', 'formatted_headers', 'notes', 'created_at']
    fields = ['subscription', 'charge_id', 'raw_event', 'mapped_status', 'formatted_payload', 'formatted_headers', 'notes', 'created_at']

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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
