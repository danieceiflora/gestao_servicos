from django.urls import path
from . import views
from . import notifications
from . import views_equipe
from . import views_finance
from . import views_offline
from . import views_stock
from . import views_maintenance
from . import views_bi

urlpatterns = [
    path('confirmar/<uuid:token>/', views.task_public_confirmation, name='task_public_confirmation'),
    path('os/<uuid:token>/', views.public_os_page, name='public_os_page'),
    path('os/<uuid:token>/aprovar-orcamento/', views.public_os_approve_budget, name='public_os_approve_budget'),
    path('os/<uuid:token>/gerar-cobranca/', views.public_os_generate_charge, name='public_os_generate_charge'),
    path('os/<uuid:token>/pdf/orcamento/', views.public_os_pdf_budget, name='public_os_pdf_budget'),
    path('os/<uuid:token>/pdf/relatorio/', views.public_os_pdf_report, name='public_os_pdf_report'),
    path('', views.home, name='home'),
    path('financeiro/', views_finance.finance_dashboard, name='finance_dashboard'),
    path('financeiro/comissoes/', views_finance.finance_commissions, name='finance_commissions'),
    path('financeiro/pagamentos-profissionais/', views_finance.finance_professional_payments, name='finance_professional_payments'),
    path('financeiro/pagamentos-profissionais/<int:payment_id>/confirmar/', views_finance.finance_confirm_payment, name='finance_confirm_payment'),
    path('financeiro/pagamentos-profissionais/confirmacao-em-massa/', views_finance.finance_bulk_confirm_payments, name='finance_bulk_confirm_payments'),
    
    # --- CONTAS A RECEBER (FINANCEIRO CENTRALIZADO) ---
    path('financeiro/contas-a-receber/', views_finance.billing_list, name='billing_list'),
    path('financeiro/contas-a-receber/<uuid:pk>/', views_finance.billing_detail, name='billing_detail'),
    path('financeiro/parcelas/<int:pk>/pagar/', views_finance.installment_pay, name='installment_pay'),
    path('ordens/<uuid:order_id>/gerar-cobranca/', views_finance.billing_generate_for_os, name='billing_generate_for_os'),
    path('etapas/<uuid:task_id>/gerar-cobranca/', views_finance.billing_generate_for_task, name='billing_generate_for_task'),
    path('ordens/<uuid:order_id>/cobranca/nova/', views_finance.billing_create_for_os, name='billing_create_for_os'),
    path('etapas/<uuid:task_id>/cobranca/nova/', views_finance.billing_create_for_task, name='billing_create_for_task'),
    
    # --- MÉTODOS DE PAGAMENTO ---
    path('financeiro/metodos-pagamento/', views_finance.payment_method_list, name='payment_method_list'),
    path('financeiro/metodos-pagamento/novo/', views_finance.payment_method_create, name='payment_method_create'),
    path('financeiro/metodos-pagamento/<int:pk>/editar/', views_finance.payment_method_edit, name='payment_method_edit'),
    path('financeiro/metodos-pagamento/<int:pk>/alternar/', views_finance.payment_method_toggle, name='payment_method_toggle'),
    
    # --- CONTAS A PAGAR (DESPESAS) ---
    path('financeiro/contas-a-pagar/', views_finance.expense_list, name='expense_list'),
    path('financeiro/contas-a-pagar/novo/', views_finance.expense_create, name='expense_create'),
    path('financeiro/contas-a-pagar/<uuid:pk>/editar/', views_finance.expense_edit, name='expense_edit'),
    path('financeiro/contas-a-pagar/<uuid:pk>/excluir/', views_finance.expense_delete, name='expense_delete'),
    path('financeiro/contas-a-pagar/previsualizar-parcelas/', views_finance.render_expense_installments_preview, name='render_expense_installments_preview'),
    path('financeiro/contas-a-pagar/parcelas/<int:pk>/status/', views_finance.expense_installment_status_update, name='expense_installment_status_update'),
    path('financeiro/contas-a-pagar/parcelas/<int:pk>/baixa/', views_finance.installment_payment_modal, name='installment_payment_modal'),
    path('financeiro/contas-a-pagar/parcelas/<int:pk>/baixa/adicionar/', views_finance.installment_payment_add, name='installment_payment_add'),
    path('financeiro/contas-a-pagar/baixas/<int:payment_pk>/excluir/', views_finance.installment_payment_delete, name='installment_payment_delete'),
    path('financeiro/contas-a-pagar/parcelas/<int:pk>/desconto/', views_finance.installment_apply_discount, name='installment_apply_discount'),
    path('financeiro/recorrencias/<uuid:rule_pk>/materializar/', views_finance.recurrence_materialize, name='recurrence_materialize'),
    path('financeiro/contas-a-pagar/exportar/', views_finance.expense_installments_export, name='expense_installments_export'),
    path('financeiro/fluxo-de-caixa/', views_finance.expense_cashflow, name='expense_cashflow'),
    path('financeiro/contas-bancarias/', views_finance.bank_account_list, name='bank_account_list'),
    path('financeiro/contas-bancarias/nova/', views_finance.bank_account_create, name='bank_account_create'),
    path('financeiro/contas-bancarias/<int:pk>/editar/', views_finance.bank_account_edit, name='bank_account_edit'),
    path('financeiro/contas-bancarias/<int:pk>/alternar/', views_finance.bank_account_toggle, name='bank_account_toggle'),
    path('financeiro/comprovantes/<int:pk>/excluir/', views_finance.payment_attachment_delete, name='payment_attachment_delete'),
    path('api/financeiro/previsao/', views_finance.expense_forecast_api, name='expense_forecast_api'),
    path('financeiro/configuracoes/', views_finance.finance_settings_view, name='finance_settings'),
    path('financeiro/recorrencias/<uuid:pk>/alternar/', views_finance.recurrence_rule_toggle, name='recurrence_rule_toggle'),

    # --- VENDAS (PDV) ---
    path('vendas/', views_finance.sale_list, name='sale_list'),
    path('vendas/criar/', views_finance.sale_create, name='sale_create'),
    path('vendas/configuracoes/', views_finance.sale_settings_view, name='sale_settings'),
    path('vendas/exportar/', views_finance.sale_export_csv, name='sale_export_csv'),
    path('vendas/devolucoes/<int:return_id>/aprovar/', views_finance.sale_return_approve, name='sale_return_approve'),
    path('vendas/devolucoes/<int:return_id>/cancelar/', views_finance.sale_return_cancel, name='sale_return_cancel'),
    path('vendas/<int:number>/', views_finance.sale_detail, name='sale_detail'),
    path('vendas/<int:number>/cancelar/', views_finance.sale_cancel, name='sale_cancel'),
    path('vendas/<int:number>/duplicar/', views_finance.sale_duplicate, name='sale_duplicate'),
    path('vendas/<int:number>/devolucao/', views_finance.sale_return_create, name='sale_return_create'),
    path('api/produtos/<int:product_id>/estoque/', views_finance.api_product_stock, name='api_product_stock'),
    
    # --- ESTOQUE ---
    path('produtos/', views_stock.ProductListView.as_view(), name='product_list'),
    path('produtos/novo/', views_stock.ProductCreateView.as_view(), name='product_create'),
    path('produtos/importar/', views_stock.product_import, name='product_import'),
    path('produtos/importar/modelo/', views_stock.product_import_template, name='product_import_template'),
    path('produtos/importar/historico/', views_stock.ImportHistoryListView.as_view(), name='product_import_history'),
    path('produtos/importar/historico/<int:pk>/', views_stock.ImportHistoryDetailView.as_view(), name='product_import_history_detail'),
    path('produtos/<int:pk>/editar/', views_stock.ProductUpdateView.as_view(), name='product_edit'),
    path('produtos/<int:pk>/historico/', views_stock.product_stock_history, name='product_stock_history'),
    path('produtos/buscar-materia-prima/', views_stock.search_materia_prima, name='search_materia_prima'),
    path('produtos/<int:pk>/precos/', views_stock.get_product_prices, name='product_prices'),
    path('estoque/movimentacao/novo/', views_stock.StockMovementCreateView.as_view(), name='stock_movement_create'),
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
    path('api/tecnico/sincronizar/pull/', views_offline.api_tecnico_sync_pull, name='api_tecnico_sync_pull'),
    path('api/tecnico/sincronizar/push/', views_offline.api_tecnico_sync_push, name='api_tecnico_sync_push'),
    path('api/tecnico/etapa/<uuid:task_id>/upload-midia/', views_offline.api_tecnico_upload_media, name='api_tecnico_upload_media'),
    path('api/tecnico/visita-manutencao/<int:visit_id>/upload-midia/', views_offline.api_tecnico_upload_maintenance_media, name='api_tecnico_upload_maintenance_media'),

    # --- RELATÓRIOS / BI ---
    path('relatorios/operacional/', views_bi.bi_operacional, name='bi_operacional'),
    path('relatorios/produtividade/', views_bi.bi_produtividade, name='bi_produtividade'),
    path('relatorios/manutencao/', views_bi.bi_manutencao, name='bi_manutencao'),

    # Clientes
    path('clientes/', views.client_list, name='client_list'),
    path('clientes/novo/', views.client_create, name='client_create'),
    path('clientes/<uuid:client_id>/editar/', views.client_edit, name='client_edit'),
    path('clientes/<uuid:client_id>/propriedade/nova/', views.property_create, name='property_create'),
    
    # Profissionais
    path('profissionais/', views.ProfessionalListView.as_view(), name='professional_list'),
    path('profissionais/novo/', views.ProfessionalCreateView.as_view(), name='professional_create'),
    path('profissionais/<uuid:pk>/editar/', views.ProfessionalUpdateView.as_view(), name='professional_edit'),
    
    # Bloqueios de Agenda (Folgas/Férias)
    path('profissionais/bloqueios/', views.ProfessionalScheduleBlockListView.as_view(), name='schedule_block_list'),
    path('profissionais/bloqueios/novo/', views.ProfessionalScheduleBlockCreateView.as_view(), name='schedule_block_create'),
    path('profissionais/bloqueios/<int:pk>/editar/', views.ProfessionalScheduleBlockUpdateView.as_view(), name='schedule_block_edit'),
    path('profissionais/bloqueios/<int:pk>/excluir/', views.ProfessionalScheduleBlockDeleteView.as_view(), name='schedule_block_delete'),
    
    # Ordens de Serviço
    path('ordens/', views.service_order_list, name='service_order_list'),
    path('ordens/nova/', views.service_order_scheduling, name='service_order_scheduling'),
    path('ordens/calendario/', views.service_order_calendar, name='service_order_calendar'),
    path('ordens/<uuid:order_id>/', views.service_order_detail, name='service_order_detail'),
    path('ordens/<uuid:order_id>/pdf/', views.service_order_pdf, name='service_order_pdf'),
    path('ordens/<uuid:order_id>/relatorio/pdf/', views.service_order_report_pdf, name='service_order_report_pdf'),
    path('ordens/<uuid:order_id>/enviar-orcamento/', views.service_order_send_budget, name='service_order_send_budget'),
    path('ordens/<uuid:order_id>/editar/', views.service_order_edit, name='service_order_edit'),
    path('ordens/<uuid:order_id>/orcamento/', views.service_order_budget, name='service_order_budget'),
    path('ordens/<uuid:order_id>/executar/', views.service_order_execution, name='service_order_execution'),  # Legacy redirect
    # Tasks (Etapas de Serviço)
    path('etapas/<uuid:task_id>/executar/', views.task_execution, name='task_execution'),
    path('etapas/<uuid:task_id>/editar/', views.task_edit, name='task_edit'),
    path('etapas/<uuid:task_id>/cancelar/', views.task_cancel, name='task_cancel'),
    path('ordens/<uuid:order_id>/etapas/adicionar/', views.task_add, name='task_add'),
    path('etapas/midia/<int:media_id>/excluir/', views.task_media_delete, name='task_media_delete'),
    
    # Itens da OS e Pagamentos
    path('api/resolve-maps-url/', views.resolve_maps_url, name='resolve_maps_url'),
    path('ordens/<uuid:order_id>/itens/adicionar/', views.order_item_add, name='order_item_add'),
    path('itens/<int:item_id>/excluir/', views.order_item_delete, name='order_item_delete'),
    path('itens/<int:item_id>/atualizar/', views.order_item_update, name='order_item_update'),
    path('ordens/<uuid:order_id>/pagamentos/adicionar/', views.order_payment_add, name='order_payment_add'),
    path('ordens/<uuid:order_id>/desconto/', views.order_discount_update, name='order_discount_update'),
    path('etapas/<uuid:task_id>/desconto/', views.task_discount_update, name='task_discount_update'),
    path('ordens/<uuid:order_id>/observacao/', views.order_observation_update, name='order_observation_update'),
    
    # Push Notifications
    path('notificacoes/painel/', notifications.notifications_test_view, name='notifications_test'),
    path('notificacoes/inscrever/', notifications.subscribe_push, name='subscribe_push'),
    path('notificacoes/desinscrever/', notifications.unsubscribe_push, name='unsubscribe_push'),
    path('notificacoes/enviar-teste/', notifications.test_notification, name='test_notification'),
    path('notificacoes/enviar/', notifications.send_notification, name='send_notification'),
    
    # API
    path('api/verificar-disponibilidade/', views.api_check_availability, name='api_check_availability'),
    path('api/eventos-calendario/', views.api_calendar_events, name='api_calendar_events'),
    path('api/clientes/lista/', views.api_get_clients, name='api_get_clients'),
    ##path('api/clientes/criacao-rapida/', views.api_quick_create_client, name='api_quick_create_client'),
    ##path('api/propriedades/criacao-rapida/', views.api_quick_create_property, name='api_quick_create_property'),
    path('api/propriedades/lista/', views.api_get_properties, name='api_get_properties'),
    path('api/ordens/criacao-rapida/', views.api_quick_create_order, name='api_quick_create_order'),
    # Ocorrências
    path('ocorrencias/', views.occurrence_list, name='occurrence_list'),
    path('ocorrencias/<int:occurrence_id>/resolver/', views.occurrence_resolve, name='occurrence_resolve'),
    
    # Uppy Test
    path('uppy-teste/', views.uppy_test_page, name='uppy_test_page'),
    path('api/uppy-upload/', views.uppy_upload, name='uppy_upload'),

    # --- MÓDULO DE MANUTENÇÃO ---
    # Categorias de Equipamentos
    path('manutencao/categorias/', views_maintenance.asset_category_list, name='asset_category_list'),
    path('manutencao/categorias/nova/', views_maintenance.asset_category_create, name='asset_category_create'),
    path('manutencao/categorias/<int:pk>/editar/', views_maintenance.asset_category_edit, name='asset_category_edit'),
    # Equipamentos / Bens
    path('manutencao/equipamentos/', views_maintenance.asset_list, name='asset_list'),
    path('manutencao/equipamentos/novo/', views_maintenance.asset_create, name='asset_create'),
    path('manutencao/equipamentos/<uuid:pk>/editar/', views_maintenance.asset_edit, name='asset_edit'),
    path('api/manutencao/imoveis/', views_maintenance.api_get_properties_for_asset, name='api_get_properties_for_asset'),
    # Contratos de Manutenção
    path('manutencao/contratos/', views_maintenance.contract_list, name='contract_list'),
    path('manutencao/contratos/novo/', views_maintenance.contract_create, name='contract_create'),
    path('manutencao/contratos/<uuid:pk>/', views_maintenance.contract_detail, name='contract_detail'),
    path('manutencao/contratos/<uuid:pk>/editar/', views_maintenance.contract_edit, name='contract_edit'),
    path('manutencao/contratos/<uuid:pk>/status/', views_maintenance.contract_toggle_status, name='contract_toggle_status'),
    # Visitas
    path('manutencao/contratos/<uuid:contract_id>/visitas/nova/', views_maintenance.visit_create, name='visit_create'),
    path('manutencao/visitas/<int:pk>/editar/', views_maintenance.visit_edit, name='visit_edit'),
    path('manutencao/visitas/<int:pk>/status/', views_maintenance.visit_quick_status, name='visit_quick_status'),
    # Fechamentos Mensais
    path('manutencao/fechamentos/', views_maintenance.closing_list, name='closing_list'),
    path('manutencao/fechamentos/gerar/', views_maintenance.closing_generate, name='closing_generate'),
    path('manutencao/fechamentos/<int:pk>/', views_maintenance.closing_detail, name='closing_detail'),
    path('manutencao/fechamentos/<int:pk>/aprovar/', views_maintenance.closing_approve, name='closing_approve'),
]
