from django.apps import AppConfig


class ProducaoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'producao'
    verbose_name = 'Expedição / Produção'

    def ready(self):
        import producao.signals  # noqa: F401
