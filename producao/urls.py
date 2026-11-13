from django.urls import path

from . import views

app_name = 'producao'

urlpatterns = [
    path('', views.board, name='board'),
    path('painel/dados/', views.board_partial, name='board_partial'),
    path('configuracoes/', views.settings_view, name='settings'),
    path('<int:number>/', views.order_detail, name='order_detail'),
    path('<int:number>/prioridade/', views.order_priority, name='order_priority'),
    path('<int:number>/aguardando-material/', views.order_waiting_material, name='order_waiting_material'),
    path('<int:number>/saida/', views.order_deliver, name='order_deliver'),
    path('itens/<int:pk>/iniciar/', views.item_start, name='item_start'),
    path('itens/<int:pk>/concluir/', views.item_finish, name='item_finish'),
    path('itens/<int:pk>/reabrir/', views.item_reopen, name='item_reopen'),
]
