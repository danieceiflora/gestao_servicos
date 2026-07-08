from django.urls import path
from . import views

app_name = 'integracoes'

urlpatterns = [
    # Webhooks
    # Rota específica precisa vir antes de webhook/<str:provider>/, senão o
    # padrão genérico abaixo captura "asaas-assinatura" como provider e
    # nunca deixa a view específica ser alcançada.
    path('webhook/asaas-assinatura/', views.platform_subscription_webhook, name='platform_subscription_webhook'),
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
    path('notificacoes/ajax/sync-templates/', views.ajax_sync_meta_templates, name='ajax_sync_meta_templates'),
    path('notificacoes/ajax/detalhes-modelo/', views.ajax_get_template_details, name='ajax_get_template_details'),
    path('notificacoes/ajax/campos-modelo/', views.ajax_get_model_fields, name='ajax_get_model_fields'),
    path('notificacoes/ajax/status-modelo/', views.ajax_get_status_choices, name='ajax_get_status_choices'),

    # Régua de Cobrança — Sequências
    path('regua-cobranca/', views.collection_sequence_list, name='collection_sequence_list'),
    path('regua-cobranca/criar/', views.collection_sequence_create, name='collection_sequence_create'),
    path('regua-cobranca/<int:pk>/editar/', views.collection_sequence_edit, name='collection_sequence_edit'),
    path('regua-cobranca/<int:pk>/excluir/', views.collection_sequence_delete, name='collection_sequence_delete'),
    # Régua de Cobrança — Etapas
    path('regua-cobranca/<int:seq_pk>/etapas/criar/', views.collection_step_create, name='collection_step_create'),
    path('regua-cobranca/etapas/<int:pk>/editar/', views.collection_step_edit, name='collection_step_edit'),
    path('regua-cobranca/etapas/<int:pk>/excluir/', views.collection_step_delete, name='collection_step_delete'),
    # Régua de Cobrança — Simulação
    path('regua-cobranca/<int:pk>/simular/', views.collection_sequence_simulate, name='collection_sequence_simulate'),

    # Mensagens Manuais (templates configuráveis para ações do usuário)
    path('mensagens-manuais/', views.manual_message_config_list, name='manual_message_config_list'),
    path('mensagens-manuais/<str:trigger>/configurar/', views.manual_message_config_edit, name='manual_message_config_edit'),

    # Lembretes Agendados (envio único)
    path('lembretes/', views.scheduled_reminder_list, name='scheduled_reminder_list'),
    path('lembretes/criar/', views.scheduled_reminder_create, name='scheduled_reminder_create'),
    path('lembretes/<int:pk>/editar/', views.scheduled_reminder_edit, name='scheduled_reminder_edit'),
    path('lembretes/<int:pk>/excluir/', views.scheduled_reminder_delete, name='scheduled_reminder_delete'),

    # Assinatura da Plataforma (Pix Recorrente / Asaas, conta master)
    path('faturamento/', views.platform_subscription_status, name='platform_subscription_status'),
    path('faturamento/criar/', views.platform_subscription_create, name='platform_subscription_create'),
]
