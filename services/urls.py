from django.urls import path
from . import views
from . import notifications
from . import views_equipe

urlpatterns = [
    path('', views.home, name='home'),
    
    # --- VISÃO EQUIPE / COLABORADORES ---
    path('equipe/tarefas/', views_equipe.equipe_task_list, name='equipe_task_list'),
    path('equipe/etapa/<uuid:task_id>/', views_equipe.equipe_task_detail, name='equipe_task_detail'),
    path('equipe/etapa/<uuid:task_id>/iniciar/', views_equipe.equipe_task_start, name='equipe_task_start'),
    path('equipe/etapa/<uuid:task_id>/finalizar/', views_equipe.equipe_task_finish, name='equipe_task_finish'),
    path('equipe/etapa/<uuid:task_id>/midia/', views_equipe.equipe_task_add_media, name='equipe_task_add_media'),
    path('equipe/etapa/<uuid:task_id>/ocorrencia/', views_equipe.equipe_task_add_occurrence, name='equipe_task_add_occurrence'),
    path('equipe/propriedade/<uuid:property_id>/atualizar-gps/', views_equipe.equipe_update_gps, name='equipe_update_gps'),

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
    path('orders/new/', views.service_order_scheduling, name='service_order_scheduling'),
    path('orders/calendar/', views.service_order_calendar, name='service_order_calendar'),
    path('orders/<uuid:order_id>/', views.service_order_detail, name='service_order_detail'),
    path('orders/<uuid:order_id>/edit/', views.service_order_edit, name='service_order_edit'),
    path('orders/<uuid:order_id>/budget/', views.service_order_budget, name='service_order_budget'),
    path('orders/<uuid:order_id>/execute/', views.service_order_execution, name='service_order_execution'),  # Legacy redirect
    # Tasks (Etapas de Serviço)
    path('tasks/<uuid:task_id>/execute/', views.task_execution, name='task_execution'),
    path('tasks/<uuid:task_id>/edit/', views.task_edit, name='task_edit'),
    path('tasks/<uuid:task_id>/cancel/', views.task_cancel, name='task_cancel'),
    path('orders/<uuid:order_id>/tasks/add/', views.task_add, name='task_add'),
    path('tasks/media/<int:media_id>/delete/', views.task_media_delete, name='task_media_delete'),
    
    # Itens da OS e Pagamentos
    path('orders/<uuid:order_id>/items/add/', views.order_item_add, name='order_item_add'),
    path('items/<int:item_id>/delete/', views.order_item_delete, name='order_item_delete'),
    path('orders/<uuid:order_id>/payments/add/', views.order_payment_add, name='order_payment_add'),
    path('orders/<uuid:order_id>/discount/', views.order_discount_update, name='order_discount_update'),
    
    # Push Notifications
    path('notifications/panel/', notifications.notifications_test_view, name='notifications_test'),
    path('notifications/subscribe/', notifications.subscribe_push, name='subscribe_push'),
    path('notifications/unsubscribe/', notifications.unsubscribe_push, name='unsubscribe_push'),
    path('notifications/send-test/', notifications.test_notification, name='test_notification'),
    path('notifications/send/', notifications.send_notification, name='send_notification'),
    
    # API
    path('api/check-availability/', views.api_check_availability, name='api_check_availability'),
    path('api/calendar-events/', views.api_calendar_events, name='api_calendar_events'),
    path('api/clients/list/', views.api_get_clients, name='api_get_clients'),
    ##path('api/clients/quick-create/', views.api_quick_create_client, name='api_quick_create_client'),
    ##path('api/properties/quick-create/', views.api_quick_create_property, name='api_quick_create_property'),
    path('api/properties/list/', views.api_get_properties, name='api_get_properties'),
    path('api/orders/quick-create/', views.api_quick_create_order, name='api_quick_create_order'),
    # Ocorrências
    path('occurrences/', views.occurrence_list, name='occurrence_list'),
    path('occurrences/<int:occurrence_id>/resolve/', views.occurrence_resolve, name='occurrence_resolve'),
]

