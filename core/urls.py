from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from integracoes import views as integracoes_views
from django.contrib.staticfiles.views import serve
urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('pwa.urls')),
    path('webhooks', integracoes_views.webhooks, name='chatwoot_budget_webhook'),
    path('webhooks/', integracoes_views.webhooks, name='chatwoot_budget_webhook_slash'),
    path('api/integracoes/', include('integracoes.urls', namespace='integracoes')),
    path('', include('services.urls')),
    path('service-worker.js', serve , {'path': 'js/serviceworker.js'}),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
