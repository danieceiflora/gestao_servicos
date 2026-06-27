from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

##importar storages para usar o S3
from storages.backends.s3boto3 import S3Boto3Storage

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-local-dev-only-change-in-production')

DEBUG = os.environ.get('DEBUG', 'False').lower() in ('1', 'true', 'yes', 'on')

ALLOWED_HOSTS = ['*']

SITE_URL = os.environ.get('SITE_URL', 'https://osonline.douradoscalhas.com.br')
PAYMENT_PROCESSOR_NAME = os.environ.get('PAYMENT_PROCESSOR_NAME', '')

CSRF_TRUSTED_ORIGINS = [
    'http://osonline.douradoscalhas.com.br',
    'https://osonline.douradoscalhas.com.br',
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'pwa',
    'widget_tweaks',
    'services',
    'integracoes',
    'pagamentos',
]

# --- ASAAS PAYMENT GATEWAY ---
ASAAS_API_KEY = os.environ.get('ASAAS_API_KEY', '')
ASAAS_ENVIRONMENT = os.environ.get('ASAAS_ENVIRONMENT', 'SANDBOX')  # SANDBOX ou PRODUCTION
ASAAS_MASTER_WALLET_ID = os.environ.get('ASAAS_CLIENT_WALLET_ID', '')  # Wallet da conta master (recebe split das subcontas)

# Margem da plataforma por método de pagamento (interna — não exposta na UI)
# PIX: percentual sobre o valor da transação, com valor mínimo em R$
PLATFORM_PIX_SPLIT_PERCENT = '0.008'   # 0,80%
PLATFORM_PIX_SPLIT_MINIMUM = '2.50'    # mínimo R$ 2,50 (cobre o custo Asaas de R$ 1,99)
# Boleto: taxa fixa por transação
PLATFORM_BOLETO_SPLIT_FIXED = '2.50'   # R$ 2,50 fixo

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

X_FRAME_OPTIONS = 'SAMEORIGIN'

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'services.context_processors.vapid_keys',
                'services.context_processors.system_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

if DEBUG:
    # Desenvolvimento: Usa SQLite local
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db_v2.sqlite3',
        }
    }
else:
    # Produção: Usa DATABASE_URL (PostgreSQL, etc)
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
        )
    }


AUTH_USER_MODEL = 'services.User'

LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

# Em produção (DEBUG=False), salva horário local (America/Sao_Paulo) direto no banco.
# Em desenvolvimento (DEBUG=True), mantém o padrão Django (UTC no banco).
USE_TZ = DEBUG


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudflare R2 Storage Configuration
AWS_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', '')
AWS_S3_ENDPOINT_URL = os.environ.get('R2_ENDPOINT_URL', '')
AWS_S3_REGION_NAME = os.environ.get('R2_REGION_NAME', 'auto')
AWS_S3_CUSTOM_DOMAIN = os.environ.get('R2_CUSTOM_DOMAIN', '')
AWS_QUERYSTRING_AUTH = False

if all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL]):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    # When using S3, MEDIA_URL should point to the S3 bucket/custom domain
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    else:
        # Default R2 URL pattern if no custom domain is provided
        # This might need adjustment based on how the bucket is exposed
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/'

# PWA Config
PWA_APP_NAME = "Gestão de Serviços"
PWA_APP_DESCRIPTION = "App para gestão de equipes externas"
PWA_APP_THEME_COLOR = '#000000'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {
        'src': '/static/dourados-calhas.png',
        'sizes': '160x160'
    }
]
PWA_APP_ICONS_APPLE = [
    {
        'src': '/static/dourados-calhas.png',
        'sizes': '160x160'
    }
]
PWA_APP_SPLASH_SCREEN = []
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'pt-BR'
PWA_SERVICE_WORKER_PATH = str(BASE_DIR / 'static' / 'js' / 'serviceworker.js')

# Push Notifications (VAPID Keys)
# Para gerar as chaves, execute: python -c "from pywebpush import webpush; print(webpush.generate_vapid_keys())"

VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_ADMIN_EMAIL = os.environ.get('VAPID_ADMIN_EMAIL', 'admin@douradoscalhas.com.br')

# Configuração de limites de upload para suportar arquivos grandes (ex: vídeos)
# 210MB em bytes (210 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = 220200960
FILE_UPLOAD_MAX_MEMORY_SIZE = 220200960

# Configurações de compressão de mídia (upload offline)
MEDIA_IMAGE_MAX_DIMENSION = int(os.environ.get('MEDIA_IMAGE_MAX_DIMENSION', '1920'))
MEDIA_IMAGE_QUALITY = int(os.environ.get('MEDIA_IMAGE_QUALITY', '82'))
MEDIA_VIDEO_MAX_WIDTH = int(os.environ.get('MEDIA_VIDEO_MAX_WIDTH', '1280'))
MEDIA_VIDEO_CRF = int(os.environ.get('MEDIA_VIDEO_CRF', '28'))
MEDIA_VIDEO_PRESET = os.environ.get('MEDIA_VIDEO_PRESET', 'medium')
MEDIA_VIDEO_AUDIO_BITRATE = os.environ.get('MEDIA_VIDEO_AUDIO_BITRATE', '128k')
MEDIA_FFMPEG_THREADS = int(os.environ.get('MEDIA_FFMPEG_THREADS', '1'))
MEDIA_FFMPEG_NICE = int(os.environ.get('MEDIA_FFMPEG_NICE', '10'))
MEDIA_FFMPEG_REALTIME = os.environ.get('MEDIA_FFMPEG_REALTIME', '1').lower() in ('1', 'true', 'yes', 'on')
MEDIA_PROCESSING_LOCK_TIMEOUT = int(os.environ.get('MEDIA_PROCESSING_LOCK_TIMEOUT', '0'))
MEDIA_PROCESSING_ROOT = os.environ.get('MEDIA_PROCESSING_ROOT') or str(MEDIA_ROOT / 'processing')

# Bling Integration
# O Client Secret pode ser encontrado nas configurações do seu aplicativo no Bling
BLING_CLIENT_SECRET = None

# Webhook Integration (Chatwoot)
# Segredo fixo para facilitar testes locais.
##WEBHOOK_SHARED_SECRET = "NN2L3AnkCoT9jzGeFg4XcKZK"
WEBHOOK_SHARED_SECRET = os.environ.get('WEBHOOK_SHARED_SECRET', '')

# Default primary key field type
# https://docs.djangoproject.com/en/6.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
