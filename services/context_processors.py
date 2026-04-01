from django.conf import settings

def vapid_keys(request):
    return {
        'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', None)
    }
