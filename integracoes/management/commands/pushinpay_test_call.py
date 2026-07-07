import json

from django.conf import settings
from django.core.management.base import BaseCommand

from integracoes.pushinpay_client import criar_pix_recorrente, PushinPayError


class Command(BaseCommand):
    help = (
        'Chamada única de verificação contra a API real da PushinPay (Pix Recorrente). '
        'NÃO grava nada no banco — só imprime a resposta bruta, para confirmar os nomes '
        'reais de campo (id, qr_code, subscription_id, etc.) e o comportamento de '
        '"frequency" antes de ligar a UI de assinatura. Depois de rodar isso e confirmar '
        'que a assinatura foi criada de fato na PushinPay, capture um webhook real '
        '(painel da PushinPay ou primeiro pagamento) para validar parse_webhook_event.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--webhook-url', default='',
            help='URL de webhook a informar na chamada de teste (default: settings.SITE_URL + rota do webhook).',
        )

    def handle(self, *args, **options):
        webhook_url = options['webhook_url']
        if not webhook_url:
            from django.urls import reverse
            token = getattr(settings, 'PUSHINPAY_WEBHOOK_TOKEN', '') or 'TOKEN-NAO-CONFIGURADO'
            webhook_url = settings.SITE_URL.rstrip('/') + reverse('integracoes:pushinpay_webhook', args=[token])

        self.stdout.write(f'Chamando criar_pix_recorrente() com webhook_url={webhook_url!r} ...')
        try:
            result = criar_pix_recorrente(webhook_url)
        except PushinPayError as e:
            self.stderr.write(self.style.ERROR(f'Falhou: {e}'))
            return

        self.stdout.write(self.style.SUCCESS('Resposta bruta da PushinPay:'))
        self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False))
        self.stdout.write(self.style.WARNING(
            'Nada foi gravado no banco. Confira se os campos id/qr_code/qr_code_base64/'
            'status/subscription_id batem com o que pushinpay_client.py espera.'
        ))
