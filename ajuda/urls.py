from django.urls import path
from . import views

app_name = 'ajuda'

urlpatterns = [
    path('', views.index, name='index'),
    path('contexto/', views.contextual, name='contextual'),
    path('categoria/<slug:slug>/', views.category, name='category'),
    path('artigo/<slug:slug>/', views.article, name='article'),
]
