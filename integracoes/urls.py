from django.urls import path
from . import views

app_name = 'integracoes'

urlpatterns = [
    # Rota genérica de recebimento que pode aceitar qualquer provedor (ex: mercado_pago, asaas, stripe, twilio, etc)
    path('webhook/<str:provider>/', views.webhook_receiver, name='webhook_receiver'),
]
