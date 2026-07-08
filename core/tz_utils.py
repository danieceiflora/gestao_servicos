from django.conf import settings
from django.utils import timezone as dj_timezone


def local_today():
    """Substitui timezone.localdate(), que quebra com USE_TZ=False (naive
    datetime). Este projeto usa USE_TZ = DEBUG (core/settings.py), então isso
    acontece sempre que DEBUG=False (produção)."""
    now = dj_timezone.now()
    return dj_timezone.localtime(now).date() if dj_timezone.is_aware(now) else now.date()


def safe_localtime(value):
    """Substitui timezone.localtime(value) para valores que podem vir naive
    (USE_TZ=False, produção) ou aware (USE_TZ=True, desenvolvimento)."""
    if value is None:
        return None
    return dj_timezone.localtime(value) if dj_timezone.is_aware(value) else value


def safe_make_aware(value, tz=None):
    """Substitui timezone.make_aware(value, tz). Só converte para aware
    quando USE_TZ está ligado: com USE_TZ=False (produção deste projeto), o
    Postgres rejeita datetimes aware (ValueError) e valores vindos do banco
    já são naive, então forçar aware aqui quebraria as comparações."""
    if value is None:
        return None
    if not settings.USE_TZ:
        return value
    if dj_timezone.is_aware(value):
        return value
    return dj_timezone.make_aware(value, tz)
