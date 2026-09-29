import json
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from services.models import Sale
from services.pos_payments import (
    cancel_checkout, checkout_data, ensure_pix, replace_part, start_checkout,
)
from services.views_pos import _can_operate

logger = logging.getLogger(__name__)


def checkout_access(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _can_operate(request.user):
            return JsonResponse({'error': 'Sem permissão.'}, status=403)
        sale_id = kwargs.get('pk')
        if sale_id and not Sale.objects.filter(
            pk=sale_id, origin=Sale.Origin.POS, user=request.user,
            cash_session__operator=request.user, cash_session__status='OPEN',
            pos_checkout_key__isnull=False,
        ).exists():
            return JsonResponse({'error': 'Recebimento não encontrado nesta sessão.'}, status=404)
        try:
            return view(request, *args, **kwargs)
        except (ValueError, TypeError, KeyError) as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        except Exception:
            logger.exception('Falha no recebimento do PDV')
            return JsonResponse({'error': 'Não foi possível concluir a operação. Verifique o pagamento antes de tentar novamente.'}, status=503)
    return wrapped


@login_required
@require_POST
@checkout_access
def start(request):
    sale = start_checkout(json.loads(request.body), request.user)
    ensure_pix(sale.pk)
    return JsonResponse(checkout_data(sale))


@login_required
@require_GET
@never_cache
@checkout_access
def status(request, pk):
    return JsonResponse(checkout_data(Sale.objects.get(pk=pk)))


@login_required
@require_GET
@never_cache
@checkout_access
def recover(request, key):
    sale = Sale.objects.filter(
        pos_checkout_key=key, user=request.user, origin=Sale.Origin.POS,
        cash_session__operator=request.user, cash_session__status='OPEN',
    ).first()
    return JsonResponse(checkout_data(sale) if sale else {'found': False})


@login_required
@require_POST
@checkout_access
def verify(request, pk):
    ensure_pix(pk, reconcile=True)
    return JsonResponse(checkout_data(Sale.objects.get(pk=pk)))


@login_required
@require_POST
@checkout_access
def replace(request, pk):
    payload = json.loads(request.body)
    sale = replace_part(pk, payload.get('installment_id'), payload.get('payments', []))
    ensure_pix(pk)
    return JsonResponse(checkout_data(sale))


@login_required
@require_POST
@checkout_access
def cancel(request, pk):
    sale = cancel_checkout(pk)
    return JsonResponse(checkout_data(sale))
