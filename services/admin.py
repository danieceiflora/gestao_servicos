from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Client, ClientPhone, ClientEmail, Property,
    ProfessionalRole, Professional, WorkSchedule, WorkScheduleDay,
    ServiceOrder, ServiceItem, ServiceMedia, ServiceOrderTeam,
    ServiceOrderTask, Product, ServiceCategory, Service,
    ServiceChecklistItem, TaskChecklistResponse
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


class ServiceChecklistItemInline(admin.TabularInline):
    model = ServiceChecklistItem
    extra = 1


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'base_price', 'unit_of_measure', 'is_active']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'description']
    inlines = [ServiceChecklistItemInline]


@admin.register(TaskChecklistResponse)
class TaskChecklistResponseAdmin(admin.ModelAdmin):
    list_display = ['item', 'task', 'completed', 'updated_at']
    list_filter = ['completed', 'item__service']
    search_fields = ['task__service_order__number', 'item__name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'unit_type', 'default_unit_price', 'is_active']
    list_filter = ['is_active', 'unit_type']
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
