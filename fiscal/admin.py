from django.contrib import admin
from .models import NFeConfig, NFeDocument


@admin.register(NFeConfig)
class NFeConfigAdmin(admin.ModelAdmin):
    list_display = ['razao_social', 'cnpj', 'environment', 'status', 'updated_at']
    readonly_fields = ['created_at', 'updated_at', 'focus_empresa_id', 'certificado_valido_ate']


@admin.register(NFeDocument)
class NFeDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'ref', 'status', 'numero', 'owner', 'created_at']
    list_filter = ['document_type', 'status']
    search_fields = ['ref', 'numero', 'chave_acesso']
    readonly_fields = ['created_at', 'updated_at', 'raw_response']
