from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    
    # Clientes
    path('clients/', views.client_list, name='client_list'),
    path('clients/new/', views.client_create, name='client_create'),
    path('clients/<uuid:client_id>/edit/', views.client_edit, name='client_edit'),
    path('clients/<uuid:client_id>/property/new/', views.property_create, name='property_create'),
    
    # Profissionais
    path('professionals/', views.ProfessionalListView.as_view(), name='professional_list'),
    path('professionals/new/', views.ProfessionalCreateView.as_view(), name='professional_create'),
    path('professionals/<uuid:pk>/edit/', views.ProfessionalUpdateView.as_view(), name='professional_edit'),
    
    # Ordens de Serviço
    path('orders/', views.service_order_list, name='service_order_list'),
    path('orders/<uuid:order_id>/', views.service_order_detail, name='service_order_detail'),
    path('orders/<uuid:order_id>/team/', views.service_order_team, name='service_order_team'),
    path('orders/<uuid:order_id>/budget/', views.service_order_budget, name='service_order_budget'),
    path('orders/<uuid:order_id>/execute/', views.service_order_execution, name='service_order_execution'),
    path('property/<uuid:property_id>/service/new/', views.service_order_create, name='service_order_create'),
]
