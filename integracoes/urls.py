from django.urls import path
from . import views

app_name = 'integracoes'

urlpatterns = [
    # Webhooks
    path('webhook/<str:provider>/', views.webhook_receiver, name='webhook_receiver'),
    
    # WhatsApp Templates (Meta)
    path('whatsapp/templates/', views.whatsapp_template_list, name='whatsapp_template_list'),
    path('whatsapp/templates/create/', views.whatsapp_template_create, name='whatsapp_template_create'),
    path('whatsapp/templates/<str:template_id>/edit/', views.whatsapp_template_edit, name='whatsapp_template_edit'),
    path('whatsapp/templates/<str:name>/delete/', views.whatsapp_template_delete, name='whatsapp_template_delete'),

    # Gerenciador de Notificações Dinâmicas (Personalizado)
    path('notifications/', views.notification_config_list, name='notification_config_list'),
    path('notifications/create/', views.notification_config_create, name='notification_config_create'),
    path('notifications/<int:pk>/edit/', views.notification_config_edit, name='notification_config_edit'),
    path('notifications/<int:pk>/delete/', views.notification_config_delete, name='notification_config_delete'),
    
    # HTMX Endpoints para Dinamismo
    path('notifications/ajax/template-details/', views.ajax_get_template_details, name='ajax_get_template_details'),
]
