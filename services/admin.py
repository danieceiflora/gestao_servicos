from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Client, ClientPhone, ClientEmail, Property,
    ProfessionalRole, Professional, WorkSchedule, WorkScheduleDay,
    ServiceOrder, ServiceItem, ServiceMedia, ServiceOrderTeam,
    ServiceOrderTask, Product, ProductCategory, ServiceCategory, Service,
    ServiceChecklistItem, TaskChecklistResponse, ChecklistTemplate,
    ChecklistResponseMedia, Sale, SaleItem, Supplier, PaymentMethod, SalePayment,
    FinancialCategory, BankAccount, Expense, ExpenseInstallment, ExpenseAttachment,
    RecurrenceRule, FinanceSettings
)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['descricao', 'tipo_provedor', 'tarifa_porcentagem', 'tarifa_fixa', 'ativo']
    list_filter = ['tipo_provedor', 'ativo']
    search_fields = ['descricao']


@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'metodo_pagamento', 'valor_bruto', 'data_pagamento', 'venda', 'os']
    list_filter = ['metodo_pagamento', 'data_pagamento']
    readonly_fields = ['data_pagamento']


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


class ServiceChecklistItemInline(admin.TabularInline):
    model = ServiceChecklistItem
    extra = 1
    fields = ['name', 'description', 'evidence_type', 'is_required', 'is_active', 'order']


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    inlines = [ServiceChecklistItemInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'checklist_template', 'base_price', 'is_active']
    list_filter = ['is_active', 'category', 'checklist_template']
    search_fields = ['name', 'description']
    inlines = [ServiceChecklistItemInline]


class ChecklistResponseMediaInline(admin.TabularInline):
    model = ChecklistResponseMedia
    extra = 0


@admin.register(TaskChecklistResponse)
class TaskChecklistResponseAdmin(admin.ModelAdmin):
    list_display = ['item', 'task', 'completed', 'updated_at']
    list_filter = ['completed', 'item__service', 'item__template']
    search_fields = ['task__service_order__number', 'item__name']
    inlines = [ChecklistResponseMediaInline]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'document', 'is_active', 'created_at']
    list_filter = ['client_type', 'is_active']
    search_fields = ['name', 'trade_name', 'cpf', 'cnpj']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'supplier', 'unit_type', 'default_unit_price', 'is_active']
    list_filter = ['is_active', 'unit_type', 'supplier']
    search_fields = ['name', 'code']

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Informações Adicionais', {'fields': ('role', 'cpf', 'phone')}),
    )
    list_display = ['username', 'email', 'role', 'is_staff']

class ClientPhoneInline(admin.TabularInline):
    model = ClientPhone
    extra = 1

class ClientEmailInline(admin.TabularInline):
    model = ClientEmail
    extra = 1

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'cpf', 'created_at']
    search_fields = ['name', 'cpf']
    inlines = [ClientPhoneInline, ClientEmailInline]

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['address', 'number', 'neighborhood', 'city', 'client']
    list_filter = ['classification', 'city']
    search_fields = ['address', 'client__name']

@admin.register(ProfessionalRole)
class ProfessionalRoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'commission_rate_display']

    def commission_rate_display(self, obj):
        return f"{obj.commission_rate}%"
    commission_rate_display.short_description = "Comissão"

class WorkScheduleDayInline(admin.TabularInline):
    model = WorkScheduleDay
    extra = 7

@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    inlines = [WorkScheduleDayInline]

@admin.register(Professional)
class ProfessionalAdmin(admin.ModelAdmin):
    list_display = ['name', 'cpf', 'phone', 'base_salary_display', 'work_schedule', 'is_active']
    list_filter = ['is_active', 'roles', 'work_schedule']
    search_fields = ['name', 'cpf', 'city']
    filter_horizontal = ['roles']
    fieldsets = (
        ('Dados Básicos', {
            'fields': ('user', 'name', 'cpf', 'phone', 'email', 'is_active')
        }),
        ('Endereço', {
            'fields': (('cep', 'state'), 'address', ('number', 'complement'), 'neighborhood', 'city')
        }),
        ('Financeiro e Escala', {
            'fields': ('base_salary', 'roles', 'work_schedule')
        }),
    )

    def base_salary_display(self, obj):
        return f"R$ {obj.base_salary:,.2f}"
    base_salary_display.short_description = "Salário Base"

class ServiceItemInline(admin.TabularInline):
    model = ServiceItem
    extra = 1

class ServiceMediaInline(admin.TabularInline):
    model = ServiceMedia
    extra = 0

class ServiceOrderTeamInline(admin.TabularInline):
    model = ServiceOrderTeam
    extra = 1
    autocomplete_fields = ['professional']

class ServiceOrderTaskInline(admin.TabularInline):
    model = ServiceOrderTask
    extra = 1
    show_change_link = True
    fields = ['task_type', 'status', 'scheduled_at']

@admin.register(ServiceOrderTask)
class ServiceOrderTaskAdmin(admin.ModelAdmin):
    list_display = ['task_type', 'service_order', 'status', 'scheduled_at']
    list_filter = ['task_type', 'status']
    inlines = [ServiceOrderTeamInline, ServiceMediaInline]

@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = ['id_short', 'client_name', 'status', 'is_recurrent', 'total_value_display', 'created_at']
    list_filter = ['status', 'is_recurrent', 'created_at']
    inlines = [ServiceOrderTaskInline, ServiceItemInline]

    def id_short(self, obj):
        return f"#{obj.number}"
    id_short.short_description = "ID"

    def client_name(self, obj):
        return obj.client_property.client.name
    client_name.short_description = "Cliente"

    def total_value_display(self, obj):
        return f"R$ {obj.total_value:,.2f}"
    total_value_display.short_description = "Valor Total"


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['uuid_short', 'client', 'user', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['uuid', 'client__name', 'user__username']
    inlines = [SaleItemInline]

    def uuid_short(self, obj):
        return str(obj.uuid.hex)[:8]
    uuid_short.short_description = "ID"

@admin.register(FinancialCategory)
class FinancialCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category_type']
    list_filter = ['category_type']
    search_fields = ['name']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'initial_balance']
    search_fields = ['name']


class ExpenseInstallmentInline(admin.TabularInline):
    model = ExpenseInstallment
    extra = 1

class ExpenseAttachmentInline(admin.TabularInline):
    model = ExpenseAttachment
    extra = 1

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['description', 'supplier', 'category', 'total_amount', 'issue_date', 'is_recurrent']
    list_filter = ['is_recurrent', 'category', 'issue_date']
    search_fields = ['description', 'supplier__name']
    inlines = [ExpenseInstallmentInline, ExpenseAttachmentInline]

@admin.register(ExpenseInstallment)
class ExpenseInstallmentAdmin(admin.ModelAdmin):
    list_display = ['expense', 'installment_number', 'amount', 'due_date', 'status', 'payment_date']
    list_filter = ['status', 'due_date', 'payment_method']
    search_fields = ['expense__description']


@admin.register(RecurrenceRule)
class RecurrenceRuleAdmin(admin.ModelAdmin):
    list_display = ['description', 'supplier', 'amount', 'frequency', 'start_date', 'end_date', 'is_active']
    list_filter = ['frequency', 'is_active']
    search_fields = ['description', 'supplier__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(FinanceSettings)
class FinanceSettingsAdmin(admin.ModelAdmin):
    list_display = ['days_before_generation', 'updated_at']
