from django.contrib import admin
from .models import GatewayConfig, GatewayCharge


@admin.register(GatewayConfig)
class GatewayConfigAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'environment', 'status', 'wallet_id', 'updated_at']
    readonly_fields = ['created_at', 'updated_at', 'status_detail']


@admin.register(GatewayCharge)
class GatewayChargeAdmin(admin.ModelAdmin):
    list_display = ['external_id', 'method', 'status', 'amount', 'due_date', 'installment', 'created_at']
    list_filter = ['method', 'status', 'gateway']
    search_fields = ['external_id', 'installment__billing__number']
    readonly_fields = ['created_at', 'updated_at', 'pix_qrcode', 'pix_copy_paste', 'boleto_barcode']
