from django.conf import settings

def vapid_keys(request):
    return {
        'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', None)
    }

def system_config(request):
    try:
        from integracoes.models import SystemConfig
        config = SystemConfig.objects.first()
    except Exception:
        config = None
    return {'SYSTEM_CONFIG': config}
