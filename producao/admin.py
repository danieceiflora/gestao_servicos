from django.contrib import admin

from .models import (
    ProductionEvent, ProductionItem, ProductionOrder, ProductionSettings,
)


class ProductionItemInline(admin.TabularInline):
    model = ProductionItem
    extra = 0
    fields = ('description', 'product', 'variant', 'quantity', 'quantity_done',
              'status', 'needs_review', 'source_key')
    readonly_fields = ('source_key',)
    autocomplete_fields = ('product',)


class ProductionEventInline(admin.TabularInline):
    """Append-only: o histórico é auditoria, não campo editável."""
    model = ProductionEvent
    extra = 0
    can_delete = False
    fields = ('created_at', 'user', 'from_status', 'to_status', 'message')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'status', 'priority', 'delivery_mode', 'due_date',
                    'origin_label', 'updated_at')
    list_filter = ('status', 'priority', 'delivery_mode', 'waiting_material')
    search_fields = ('number', 'sale__number', 'service_order__number',
                     'delivered_to', 'tracking_code')
    readonly_fields = ('number', 'source_status', 'created_at', 'updated_at')
    inlines = [ProductionItemInline, ProductionEventInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'sale', 'service_order', 'service_order_task',
        )


@admin.register(ProductionSettings)
class ProductionSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ProductionSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
