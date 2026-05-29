from django.urls import path
from . import views

app_name = 'integracoes'

urlpatterns = [
    # Rota genérica de recebimento que pode aceitar qualquer provedor (ex: mercado_pago, asaas, stripe, twilio, etc)
    path('webhook/<str:provider>/', views.webhook_receiver, name='webhook_receiver'),
    
    # WhatsApp API Cloud
    path('whatsapp/templates/', views.whatsapp_template_list, name='whatsapp_template_list'),
    path('whatsapp/templates/create/', views.whatsapp_template_create, name='whatsapp_template_create'),
    path('whatsapp/templates/<str:template_id>/edit/', views.whatsapp_template_edit, name='whatsapp_template_edit'),
    path('whatsapp/templates/<str:name>/delete/', views.whatsapp_template_delete, name='whatsapp_template_delete'),
]
