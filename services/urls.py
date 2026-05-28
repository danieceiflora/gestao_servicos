from django.urls import path
from . import views
from . import notifications
from . import views_equipe
from . import views_finance
from . import views_offline
from . import views_stock

urlpatterns = [
    path('', views.home, name='home'),
    path('finance/', views_finance.finance_dashboard, name='finance_dashboard'),
    path('finance/professional-payments/', views_finance.finance_professional_payments, name='finance_professional_payments'),
    path('finance/professional-payments/<int:payment_id>/confirm/', views_finance.finance_confirm_payment, name='finance_confirm_payment'),
    path('finance/professional-payments/bulk-confirm/', views_finance.finance_bulk_confirm_payments, name='finance_bulk_confirm_payments'),
    
    # --- ESTOQUE ---
    path('products/', views_stock.ProductListView.as_view(), name='product_list'),
    path('products/new/', views_stock.ProductCreateView.as_view(), name='product_create'),
    path('products/import/', views_stock.product_import, name='product_import'),
    path('products/import/template/', views_stock.product_import_template, name='product_import_template'),
    path('products/import/history/', views_stock.ImportHistoryListView.as_view(), name='product_import_history'),
    path('products/import/history/<int:pk>/', views_stock.ImportHistoryDetailView.as_view(), name='product_import_history_detail'),
    path('products/<int:pk>/edit/', views_stock.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/history/', views_stock.product_stock_history, name='product_stock_history'),
    path('stock/movement/new/', views_stock.StockMovementCreateView.as_view(), name='stock_movement_create'),
    path('politica-de-privacidade/', views.privacy_policy, name='privacy_policy'),
    path('exclusao-de-dados/', views.data_deletion_policy, name='data_deletion_policy'),
    path('termos-de-servico/', views.terms_of_service, name='terms_of_service'),
    
    # --- VISÃO EQUIPE / COLABORADORES ---
    path('equipe/inicio/', views_equipe.equipe_dashboard, name='equipe_dashboard'),
    path('equipe/tarefas/', views_equipe.equipe_task_list, name='equipe_task_list'),
    path('equipe/etapa/<uuid:task_id>/', views_equipe.equipe_task_detail, name='equipe_task_detail'),
    path('equipe/etapa/<uuid:task_id>/iniciar/', views_equipe.equipe_task_start, name='equipe_task_start'),
    path('equipe/etapa/<uuid:task_id>/finalizar/', views_equipe.equipe_task_finish, name='equipe_task_finish'),
    path('equipe/etapa/<uuid:task_id>/checklist/atualizar/', views_equipe.equipe_task_checklist_update, name='equipe_task_checklist_update'),
    path('equipe/checklist/midia/<int:media_id>/excluir/', views_equipe.equipe_checklist_media_delete, name='equipe_checklist_media_delete'),
    path('equipe/etapa/<uuid:task_id>/midia/', views_equipe.equipe_task_add_media, name='equipe_task_add_media'),
    path('equipe/midia/<int:media_id>/excluir/', views_equipe.equipe_media_delete, name='equipe_media_delete'),
    path('equipe/etapa/<uuid:task_id>/ocorrencia/', views_equipe.equipe_task_add_occurrence, name='equipe_task_add_occurrence'),
    path('equipe/etapa/<uuid:task_id>/pagamento/', views_equipe.equipe_task_add_payment, name='equipe_task_add_payment'),
    path('equipe/pagamento/<int:payment_id>/editar/', views_equipe.equipe_payment_edit, name='equipe_payment_edit'),
    path('equipe/pagamento/<int:payment_id>/excluir/', views_equipe.equipe_payment_delete, name='equipe_payment_delete'),
    path('equipe/propriedade/<uuid:property_id>/atualizar-gps/', views_equipe.equipe_update_gps, name='equipe_update_gps'),
    path('api/equipe/agenda-do-dia/', views_equipe.api_equipe_agenda_do_dia, name='api_equipe_agenda_do_dia'),
    
    # --- API OFFLINE-FIRST ---
    path('app/', views_offline.equipe_offline_app, name='equipe_offline_app'),
    path('api/tecnico/bootstrap/', views_offline.api_tecnico_bootstrap, name='api_tecnico_bootstrap'),
    path('api/tecnico/sync/pull/', views_offline.api_tecnico_sync_pull, name='api_tecnico_sync_pull'),
    path('api/tecnico/sync/push/', views_offline.api_tecnico_sync_push, name='api_tecnico_sync_push'),
    path('api/tecnico/etapa/<uuid:task_id>/upload-media/', views_offline.api_tecnico_upload_media, name='api_tecnico_upload_media'),

    # Clientes
    path('clients/', views.client_list, name='client_list'),
    path('clients/new/', views.client_create, name='client_create'),
    path('clients/<uuid:client_id>/edit/', views.client_edit, name='client_edit'),
    path('clients/<uuid:client_id>/property/new/', views.property_create, name='property_create'),
    
    # Profissionais
    path('professionals/', views.ProfessionalListView.as_view(), name='professional_list'),
    path('professionals/new/', views.ProfessionalCreateView.as_view(), name='professional_create'),
    path('professionals/<uuid:pk>/edit/', views.ProfessionalUpdateView.as_view(), name='professional_edit'),
    
    # Bloqueios de Agenda (Folgas/Férias)
    path('professionals/blocks/', views.ProfessionalScheduleBlockListView.as_view(), name='schedule_block_list'),
    path('professionals/blocks/new/', views.ProfessionalScheduleBlockCreateView.as_view(), name='schedule_block_create'),
    path('professionals/blocks/<int:pk>/edit/', views.ProfessionalScheduleBlockUpdateView.as_view(), name='schedule_block_edit'),
    path('professionals/blocks/<int:pk>/delete/', views.ProfessionalScheduleBlockDeleteView.as_view(), name='schedule_block_delete'),
    
    # Ordens de Serviço
    path('orders/', views.service_order_list, name='service_order_list'),
    path('orders/new/', views.service_order_scheduling, name='service_order_scheduling'),
    path('orders/calendar/', views.service_order_calendar, name='service_order_calendar'),
    path('orders/<uuid:order_id>/', views.service_order_detail, name='service_order_detail'),
    path('orders/<uuid:order_id>/pdf/', views.service_order_pdf, name='service_order_pdf'),
    path('orders/<uuid:order_id>/report/pdf/', views.service_order_report_pdf, name='service_order_report_pdf'),
    path('orders/<uuid:order_id>/send-budget/', views.service_order_send_budget, name='service_order_send_budget'),
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
    path('api/resolve-maps-url/', views.resolve_maps_url, name='resolve_maps_url'),
    path('orders/<uuid:order_id>/items/add/', views.order_item_add, name='order_item_add'),
    path('items/<int:item_id>/delete/', views.order_item_delete, name='order_item_delete'),
    path('orders/<uuid:order_id>/payments/add/', views.order_payment_add, name='order_payment_add'),
    path('orders/<uuid:order_id>/discount/', views.order_discount_update, name='order_discount_update'),
    path('orders/<uuid:order_id>/observation/', views.order_observation_update, name='order_observation_update'),
    
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
    
    # Uppy Test
    path('uppy-test/', views.uppy_test_page, name='uppy_test_page'),
    path('api/uppy-upload/', views.uppy_upload, name='uppy_upload'),
    path('os/<uuid:pk>/resend-billing/', views.resend_billing, name='service_order_resend_billing'),
]
