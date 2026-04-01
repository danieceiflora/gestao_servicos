"""
Views para gerenciamento de Push Notifications
"""
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from pywebpush import webpush, WebPushException
from .models import PushSubscription, User


@login_required
def notifications_test_view(request):
    """Página de teste de notificações"""
    users = User.objects.filter(is_active=True).order_by('first_name', 'username')
    
    context = {
        'users': users,
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
    }
    return render(request, 'services/notifications_test.html', context)


@login_required
@require_http_methods(["POST"])
def subscribe_push(request):
    """Salvar subscription do usuário"""
    try:
        data = json.loads(request.body)
        
        endpoint = data.get('endpoint')
        keys = data.get('keys', {})
        
        if not endpoint or not keys:
            return JsonResponse({'error': 'Dados inválidos'}, status=400)
        
        # Criar ou atualizar subscription
        subscription, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                'p256dh': keys.get('p256dh', ''),
                'auth': keys.get('auth', ''),
                'is_active': True
            }
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Subscription salva com sucesso!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def unsubscribe_push(request):
    """Remover subscription do usuário"""
    try:
        PushSubscription.objects.filter(user=request.user).update(is_active=False)
        
        return JsonResponse({
            'success': True,
            'message': 'Unsubscribed com sucesso!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def test_notification(request):
    """Enviar notificação de teste para o usuário logado"""
    try:
        subscriptions = PushSubscription.objects.filter(
            user=request.user,
            is_active=True
        )
        
        if not subscriptions.exists():
            return JsonResponse({
                'error': 'Você não tem subscriptions ativas'
            }, status=400)
        
        # Dados da notificação
        notification_data = {
            'title': '🎉 Notificação de Teste',
            'body': f'Olá {request.user.get_full_name() or request.user.username}! As notificações estão funcionando!',
            'icon': '/static/dourados-calhas.png',
            'url': '/',
        }
        
        # Enviar para todas as subscriptions do usuário
        sent_count = 0
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh,
                            'auth': sub.auth
                        }
                    },
                    data=json.dumps(notification_data),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={
                        'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'
                    }
                )
                sent_count += 1
            except WebPushException as e:
                print(f'Erro ao enviar push: {e}')
                # Se subscription inválida, desativar
                if e.response and e.response.status_code in [404, 410]:
                    sub.is_active = False
                    sub.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Notificação enviada para {sent_count} dispositivo(s)!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def send_notification(request):
    """Enviar notificação para usuários selecionados"""
    try:
        data = json.loads(request.body)
        
        title = data.get('title', 'Nova Notificação')
        body = data.get('body', '')
        target_users = data.get('target_users', [])
        
        if not body:
            return JsonResponse({'error': 'Mensagem não pode estar vazia'}, status=400)
        
        # Determinar usuários alvo
        if 'all' in target_users:
            subscriptions = PushSubscription.objects.filter(is_active=True)
        else:
            subscriptions = PushSubscription.objects.filter(
                user_id__in=target_users,
                is_active=True
            )
        
        if not subscriptions.exists():
            return JsonResponse({
                'error': 'Nenhum usuário com notificações ativas'
            }, status=400)
        
        # Dados da notificação
        notification_data = {
            'title': title,
            'body': body,
            'icon': '/static/dourados-calhas.png',
            'url': '/',
        }
        
        # Enviar para todos
        sent_count = 0
        failed_count = 0
        
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh,
                            'auth': sub.auth
                        }
                    },
                    data=json.dumps(notification_data),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={
                        'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'
                    }
                )
                sent_count += 1
            except WebPushException as e:
                print(f'Erro ao enviar push para {sub.user.username}: {e}')
                failed_count += 1
                # Se subscription inválida, desativar
                if e.response and e.response.status_code in [404, 410]:
                    sub.is_active = False
                    sub.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Notificações enviadas! {sent_count} sucesso, {failed_count} falhas.',
            'sent': sent_count,
            'failed': failed_count
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
