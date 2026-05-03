import json
from django.contrib import admin
from django.utils.html import format_html
from .models import WebhookEvent

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
