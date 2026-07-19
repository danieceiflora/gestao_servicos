from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from integracoes import views as integracoes_views
from django.http import HttpResponse
from pathlib import Path


def service_worker_view(request):
    sw_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'serviceworker.js'
    if not sw_path.exists():
        return HttpResponse('Service worker script not found.', status=404, content_type='text/plain')
    return HttpResponse(sw_path.read_text(encoding='utf-8'), content_type='application/javascript')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('serviceworker.js', service_worker_view),
    path('service-worker.js', service_worker_view),
    path('', include('pwa.urls')),
    path('webhooks', integracoes_views.webhooks, name='chatwoot_budget_webhook'),
    path('webhooks/', integracoes_views.webhooks, name='chatwoot_budget_webhook_slash'),
    path('api/integracoes/', include('integracoes.urls', namespace='integracoes')),
    path('integracoes/pagamentos/', include('pagamentos.urls', namespace='pagamentos')),
    path('integracoes/fiscal/', include('fiscal.urls', namespace='fiscal')),
    path('', include('services.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
