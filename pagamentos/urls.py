from django.urls import path
from . import views

app_name = 'pagamentos'

urlpatterns = [
    path('gateway/', views.gateway_config_view, name='gateway_config'),
    path('parcelas/<int:installment_pk>/cobrar/', views.installment_create_charge, name='installment_create_charge'),
    path('cobranças/<int:charge_pk>/cancelar/', views.installment_cancel_charge, name='installment_cancel_charge'),
    path('cobranças/<int:charge_pk>/', views.charge_detail, name='charge_detail'),
    path('webhook/asaas/', views.asaas_webhook, name='asaas_webhook'),
]
