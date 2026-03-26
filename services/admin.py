from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Client, ClientPhone, ClientEmail, Property, 
    ProfessionalRole, Professional, ProfessionalAvailability,
    ServiceOrder, ServiceItem, ServiceMedia, ServiceOrderTeam,
    ServiceOrderTask
)

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

class ProfessionalAvailabilityInline(admin.TabularInline):
    model = ProfessionalAvailability
    extra = 7

@admin.register(Professional)
class ProfessionalAdmin(admin.ModelAdmin):
    list_display = ['name', 'cpf', 'phone', 'base_salary_display', 'is_active']
    list_filter = ['is_active', 'roles']
    search_fields = ['name', 'cpf', 'city']
    filter_horizontal = ['roles']
    inlines = [ProfessionalAvailabilityInline]
    fieldsets = (
        ('Dados Básicos', {
            'fields': ('user', 'name', 'cpf', 'phone', 'email', 'is_active')
        }),
        ('Endereço', {
            'fields': (('cep', 'state'), 'address', ('number', 'complement'), 'neighborhood', 'city')
        }),
        ('Financeiro', {
            'fields': ('base_salary', 'roles')
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
        return f"#{obj.id.hex[:8]}"
    id_short.short_description = "ID"

    def client_name(self, obj):
        return obj.client_property.client.name
    client_name.short_description = "Cliente"

    def total_value_display(self, obj):
        return f"R$ {obj.total_value:,.2f}"
    total_value_display.short_description = "Valor Total"
