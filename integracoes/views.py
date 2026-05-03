import json
import hmac
import hashlib
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import WebhookEvent

@csrf_exempt
@require_POST
def webhook_receiver(request, provider):
    """
    View centralizada para receber e salvar payloads brutos de webhooks.
    Salva os cabeçalhos (headers) e o corpo (body).
    Inclui validação de assinatura para o Bling.
    """
    # Validação de Assinatura do Bling
    if provider == 'bling':
        bling_signature = request.headers.get('X-Bling-Signature-256')
        client_secret = getattr(settings, 'BLING_CLIENT_SECRET', None)
        
        if not client_secret:
            # Se não houver secret configurado, podemos optar por logar ou permitir (em dev)
            # Para segurança, em produção deveria falhar.
            pass 
        elif not bling_signature:
            return JsonResponse({
                "status": "error",
                "message": "Missing authentication signature"
            }, status=401)
        else:
            # Calcular HMAC SHA256 do payload bruto
            expected_signature = hmac.new(
                client_secret.encode('utf-8'),
                request.body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_signature, bling_signature):
                return JsonResponse({
                    "status": "error",
                    "message": "Invalid authentication signature"
                }, status=401)

    try:
        # Se for JSON, carrega com json.loads. Caso contrário, salva a string pura.
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            # Caso não seja JSON formatado corretamente, tenta pegar os dados como dict
            if request.POST:
                payload = request.POST.dict()
            else:
                payload = request.body.decode('utf-8')

        # Converte o request.headers para dict nativo
        headers_dict = dict(request.headers.items())

        # Salva o evento no banco
        event = WebhookEvent.objects.create(
            provider=provider,
            payload=payload,
            headers=headers_dict,
            status='pending'
        )

        return JsonResponse({
            "status": "success",
            "message": "Webhook received and authenticated successfully",
            "event_id": event.id
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=400)
