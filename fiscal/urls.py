from django.urls import path
from . import views

app_name = 'fiscal'

urlpatterns = [
    path('config/', views.nfe_config_view, name='nfe_config'),
    path('config/asaas/servicos-municipais/', views.asaas_search_municipal_services, name='asaas_search_municipal_services'),

    path('vendas/<int:number>/painel/', views.sale_nfe_panel, name='sale_nfe_panel'),

    path('vendas/<int:number>/emitir-nfe/', views.emit_nfe, name='emit_nfe'),
    path('vendas/<int:number>/emitir-nfce/', views.emit_nfce, name='emit_nfce'),

    path('etapas/<uuid:task_id>/emitir-nfse/', views.emit_nfse, name='emit_nfse'),
    path('etapas/<uuid:task_id>/emitir-nfe/', views.emit_task_nfe, name='emit_task_nfe'),
    path('etapas/<uuid:task_id>/emitir-nfce/', views.emit_task_nfce, name='emit_task_nfce'),

    path('documentos/<int:pk>/consultar/', views.refresh_nfe_status, name='refresh_nfe_status'),
    path('documentos/<int:pk>/cancelar/', views.cancel_nfe, name='cancel_nfe'),

    path('webhook/focusnfe/', views.focusnfe_webhook, name='focusnfe_webhook'),
    path('webhook/base_erp/', views.base_erp_webhook, name='base_erp_webhook'),
]
