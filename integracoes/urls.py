from django.urls import path
from . import views

app_name = 'integracoes'

urlpatterns = [
    # Webhooks
    path('webhook/<str:provider>/', views.webhook_receiver, name='webhook_receiver'),
    
    # WhatsApp Templates (Meta)
    path('whatsapp/modelos/', views.whatsapp_template_list, name='whatsapp_template_list'),
    path('whatsapp/modelos/criar/', views.whatsapp_template_create, name='whatsapp_template_create'),
    path('whatsapp/modelos/<str:template_id>/editar/', views.whatsapp_template_edit, name='whatsapp_template_edit'),
    path('whatsapp/modelos/<str:name>/excluir/', views.whatsapp_template_delete, name='whatsapp_template_delete'),

    # Gerenciador de Notificações Dinâmicas (Personalizado)
    path('notificacoes/', views.notification_config_list, name='notification_config_list'),
    path('notificacoes/criar/', views.notification_config_create, name='notification_config_create'),
    path('notificacoes/<int:pk>/editar/', views.notification_config_edit, name='notification_config_edit'),
    path('notificacoes/<int:pk>/excluir/', views.notification_config_delete, name='notification_config_delete'),
    
    # HTMX Endpoints para Dinamismo
    path('notificacoes/ajax/detalhes-modelo/', views.ajax_get_template_details, name='ajax_get_template_details'),
    path('notificacoes/ajax/campos-modelo/', views.ajax_get_model_fields, name='ajax_get_model_fields'),
    path('notificacoes/ajax/status-modelo/', views.ajax_get_status_choices, name='ajax_get_status_choices'),
]
