from django.urls import path
from . import views

app_name = 'pagamentos'

urlpatterns = [
    path('gateway/', views.gateway_config_view, name='gateway_config'),
    path('parcelas/<int:installment_pk>/cobrar/', views.installment_create_charge, name='installment_create_charge'),
    path('parcelas/<int:installment_pk>/editar/', views.installment_update, name='installment_update'),
    path('cobranças/<int:charge_pk>/cancelar/', views.installment_cancel_charge, name='installment_cancel_charge'),
    path('cobranças/<int:charge_pk>/', views.charge_detail, name='charge_detail'),
    path('webhook/asaas/', views.asaas_webhook, name='asaas_webhook'),
    # Regras de cobrança
    path('regras/', views.charge_config_list, name='charge_config_list'),
    path('regras/nova/', views.charge_config_create, name='charge_config_create'),
    path('regras/<int:pk>/editar/', views.charge_config_edit, name='charge_config_edit'),
    path('regras/<int:pk>/toggle/', views.charge_config_toggle, name='charge_config_toggle'),
]
