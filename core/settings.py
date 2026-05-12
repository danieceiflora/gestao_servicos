from pathlib import Path
import os
##importar storages para usar o S3
from storages.backends.s3boto3 import S3Boto3Storage

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-d)7wxg0q$t5rat7#5ti5i*7g!@n)n53+tsp0$!02dnvi3w@1f@'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

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
    'services',
    'integracoes',
]

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
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_v2.sqlite3',
    }
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

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cloudflare R2 Storage Configuration
AWS_ACCESS_KEY_ID = "92a69e5e36b7b5ca24c1c67aac169427"
AWS_SECRET_ACCESS_KEY = "26c51d95cbe863791a279143bce6167c966781528592321740da6a8ec2f54a89"
AWS_STORAGE_BUCKET_NAME = "douradoscalhas"
AWS_S3_ENDPOINT_URL = "https://864993dbb991b65dd66badf35775168d.r2.cloudflarestorage.com"
AWS_S3_REGION_NAME = 'auto'
AWS_S3_CUSTOM_DOMAIN = "pub-bfbc628274d94815aeff1489b7330bf0.r2.dev"
AWS_QUERYSTRING_AUTH = False  # Set to True if you want signed URLs

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

VAPID_PUBLIC_KEY = 'BDZbfktaARHBARUImIrqiUjk8qVLP7voLcr2DppTOWYF4lMJRCsIav6EBywVgtnUMeMZ1b7NbHOc1Dni7gyOgf0'
VAPID_PRIVATE_KEY = 'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgh5fSGKWI80xtyhl9M6mjDd43eKUMpL6q2en2s0rwkUehRANCAAQ2W35LWgERwQEVCJiK6olI5PKlSz-76C3K9g6aUzlmBeJTCUQrCGr-hAcsFYLZ1DHjGdW-zWxznNQ54u4MjoH9'
VAPID_ADMIN_EMAIL = 'admin@douradoscalhas.com.br'

# Configuração de limites de upload para suportar arquivos grandes (ex: vídeos)
# 210MB em bytes (210 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = 220200960
FILE_UPLOAD_MAX_MEMORY_SIZE = 220200960

# Bling Integration
# O Client Secret pode ser encontrado nas configurações do seu aplicativo no Bling
BLING_CLIENT_SECRET = None

# Webhook Integration
# Preferencialmente definir via variável de ambiente WEBHOOK_SHARED_SECRET.
# Compatibilidade: também aceitamos CHATWOOT_WEBHOOK_SECRET.
# Fallback local: arquivo segredowebhook.md na raiz do projeto.
# Fallback temporário para teste manual (trocar depois em produção).
WEBHOOK_SHARED_SECRET = (
    os.getenv('WEBHOOK_SHARED_SECRET')
    or os.getenv('CHATWOOT_WEBHOOK_SECRET')
    or ''
).strip()
if not WEBHOOK_SHARED_SECRET:
    webhook_secret_file = BASE_DIR / 'segredowebhook.md'
    if webhook_secret_file.exists():
        WEBHOOK_SHARED_SECRET = webhook_secret_file.read_text(encoding='utf-8').strip()
if not WEBHOOK_SHARED_SECRET:
    WEBHOOK_SHARED_SECRET = 'ofMMvS4WT9qusYCsjGZD3d5D'
