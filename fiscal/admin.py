from django.contrib import admin
from .models import NFeConfig, NFeDocument


@admin.register(NFeConfig)
class NFeConfigAdmin(admin.ModelAdmin):
    list_display = ['razao_social', 'cnpj', 'environment', 'status', 'updated_at']
    readonly_fields = ['created_at', 'updated_at', 'focus_empresa_id', 'certificado_valido_ate']
    fieldsets = (
        ('Regime Fiscal (CST vs CSOSN para produtos)', {
            'fields': ('regime_tributario',),
            'description': 'Controla como o sistema importa XMLs de NF-e de fornecedores: '
                           'Simples Nacional (1/2) usa CSOSN; Regime Normal (3/4) usa CST ICMS.',
        }),
        ('Emitente', {
            'fields': ('razao_social', 'nome_fantasia', 'cnpj', 'inscricao_estadual', 'inscricao_municipal'),
        }),
        ('Endereço', {
            'fields': ('logradouro', 'numero', 'complemento', 'bairro', 'municipio', 'codigo_municipio_ibge', 'uf', 'cep'),
        }),
        ('Documentos habilitados', {
            'fields': ('habilita_nfe', 'habilita_nfce', 'habilita_nfse'),
        }),
        ('Tokens Focus', {
            'fields': ('token_producao', 'token_homologacao', 'account_token'),
        }),
        ('Certificado', {
            'fields': ('certificado_valido_ate', 'certificado_enviado_em'),
        }),
        ('Outros', {
            'fields': (
                'environment', 'status', 'status_detail', 'webhook_token',
                'base_erp_webhook_token', 'nfse_provider',
                'default_codigo_tributacao_iss', 'default_codigo_tributacao_municipal_iss',
                'default_codigo_indicador_operacao', 'default_codigo_nbs',
                'default_ibs_cbs_situacao_tributaria', 'default_ibs_cbs_classificacao_tributaria',
                'asaas_municipal_service_id', 'asaas_municipal_service_label',
                'asaas_municipal_service_name', 'asaas_municipal_service_code',
                'asaas_retain_iss', 'asaas_iss_aliquota', 'asaas_pis_aliquota',
                'asaas_cofins_aliquota', 'asaas_csll_aliquota', 'asaas_inss_aliquota',
                'asaas_ir_aliquota', 'asaas_fiscal_email', 'asaas_cultural_projects_promoter',
                'asaas_cnae', 'asaas_simples_nacional', 'asaas_special_tax_regime',
                'asaas_service_list_item', 'asaas_national_portal_tax_calc_regime',
                'asaas_rps_serie', 'asaas_rps_number', 'asaas_lote_number',
                'focus_empresa_id', 'created_at', 'updated_at',
            ),
        }),
    )


@admin.register(NFeDocument)
class NFeDocumentAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'ref', 'gateway_id', 'status', 'numero', 'owner', 'created_at']
    list_filter = ['document_type', 'status']
    search_fields = ['ref', 'gateway_id', 'numero', 'chave_acesso']
    readonly_fields = ['created_at', 'updated_at', 'raw_response']
