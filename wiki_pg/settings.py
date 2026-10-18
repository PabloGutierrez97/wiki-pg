"""Configuración de Wiki PG.

Los secretos y lo que cambia entre entornos van en el .env (nunca en el repo).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = False

ALLOWED_HOSTS = ['192.168.0.63', 'localhost', '127.0.0.1', 'wiki.pablogg.dev']

# Ruta del admin real. Va en el .env para que no quede en el repositorio público:
# si está aquí, cualquiera que lea GitHub se salta el honeypot de /admin/.
ADMIN_URL = os.getenv('ADMIN_URL', 'termistawk').strip('/') + '/'

# URL pública de la wiki y del código (enlaces de LinkedIn, terminal, IA...).
SITE_URL = os.getenv('SITE_URL', 'https://wiki.pablogg.dev').rstrip('/')
GITHUB_URL = 'https://github.com/PabloGutierrez97'
CSRF_TRUSTED_ORIGINS = [SITE_URL]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'django_otp.plugins.otp_email',
    'two_factor',
    'two_factor.plugins.email',
    'mdeditor',
    'wiki',
    'django_celery_beat',
    'axes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'wiki.middleware.TwoFactorRequiredMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'wiki_pg.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'wiki' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wiki_pg.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'wiki_pg'),
        'USER': os.getenv('DB_USER', 'termista'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Europe/Madrid'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = '/opt/wiki_pg/staticfiles'

# ===== SEGURIDAD =====
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = '/opt/wiki_pg/media'

# LinkedIn API
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
LINKEDIN_REDIRECT_URI = SITE_URL + '/linkedin/callback/'

# Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Two Factor Auth
LOGIN_URL = 'two_factor:login'
LOGIN_REDIRECT_URL = '/account/two_factor/setup/'
TWO_FACTOR_CALL_GATEWAY = None
TWO_FACTOR_SMS_GATEWAY = None
TWO_FACTOR_FORCE_OTP_ADMIN = True
TWO_FACTOR_PATCH_ADMIN = True

# Celery
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Madrid'

# Cabeceras de seguridad
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Caché compartida entre todos los workers (Redis, base 1; Celery usa la 0).
# Los límites de ritmo y las plazas de la IA dependen de que sea compartida:
# con la caché por defecto (memoria de cada proceso) cada worker contaba aparte.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('CACHE_URL', 'redis://127.0.0.1:6379/1'),
        'KEY_PREFIX': 'wiki',
        'TIMEOUT': 300,
    }
}

# IA local (Ollama en otro contenedor)
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://192.168.0.183:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
OLLAMA_EMBED_MODEL = os.getenv('OLLAMA_EMBED_MODEL', 'bge-m3')

# Respuestas de la IA generándose a la vez como máximo (Ollama las atiende de una en una;
# el resto esperaría en cola reteniendo workers). Si están todas ocupadas se avisa al momento.
AI_MAX_CONCURRENT = int(os.getenv('AI_MAX_CONCURRENT', '2'))

# El editor Markdown solo admite subidas de usuarios autenticados (además la URL
# de subida está restringida a staff con 2FA en wiki_pg/urls.py).
MDEDITOR_CONFIGS = {
    'default': {
        'upload_require_auth': True,
    }
}

# Django-axes (protección fuerza bruta)
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ['ip_address']
# Detrás de nginx, REMOTE_ADDR es siempre 127.0.0.1: sin esto, 5 fallos de
# cualquiera bloqueaban el login para todo el mundo. Usa la IP real del visitante.
AXES_CLIENT_IP_CALLABLE = 'wiki.security.client_ip'
