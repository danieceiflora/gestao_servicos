from django.apps import AppConfig
import mimetypes


class AjudaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ajuda'
    verbose_name = 'Central de Ajuda'

    def ready(self):
        # No Windows, a tabela MIME pode não reconhecer WebP. Sem esse tipo o
        # link sem JS vira download em vez de abrir o print no navegador.
        mimetypes.add_type('image/webp', '.webp')
