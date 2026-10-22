"""
Django settings — Proyecto "Lista de Precios" (chapa y tubo).

Reemplaza la lógica del Excel LISTA_UNIFICADA:
- Config global (precios base DD / Negra)
- Cotización del dólar en tiempo real
- Clientes con % de incremento propio
- Reglas de markup por espesor de chapa
- Catálogo de tubos
"""

import socket
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# Algunos servidores (p. ej. el droplet de producción) resuelven hosts como
# smtp.gmail.com a una dirección IPv6 sin tener ruta IPv6 real — la conexión
# se cuelga hasta el timeout y después falla con "Network is unreachable".
# Forzamos IPv4 en todas las resoluciones DNS del proceso para evitarlo.
_getaddrinfo_original = socket.getaddrinfo


def _getaddrinfo_solo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_solo_ipv4

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-CAMBIAR-EN-PRODUCCION')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    'precios',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'

# Base de datos: sqlite por defecto, pero se puede apuntar a Postgres via .env
DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DB_NAME', default=BASE_DIR / 'db.sqlite3'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = config('TIME_ZONE', default='America/Argentina/Buenos_Aires')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Django REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'precios.auth.CookieJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': ('rest_framework.filters.SearchFilter',),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/min',
        'user': '120/min',
        'login': '10/min',
        'contacto': '5/min',
        'password_reset': '5/min',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
}

# --- CORS (útil si consumís la API desde un frontend separado) ---
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000', cast=Csv())
# Necesario para que el navegador mande/reciba las cookies httpOnly del JWT
# en requests cross-origin (frontend en :5173, backend en :8000).
CORS_ALLOW_CREDENTIALS = True

# --- Cookies de autenticación (JWT guardado en cookie httpOnly, no en localStorage) ---
# Evita que un XSS pueda robar el token leyéndolo desde JS. SameSite=Lax alcanza
# como protección CSRF acá porque son requests JSON vía fetch/axios (SameSite=Lax
# ya bloquea que esas cookies viajen en un request cross-site que no sea una
# navegación GET de nivel superior).
AUTH_COOKIE_ACCESS = 'access_token'
AUTH_COOKIE_REFRESH = 'refresh_token'
AUTH_COOKIE_SECURE = config('AUTH_COOKIE_SECURE', default=not DEBUG, cast=bool)
AUTH_COOKIE_SAMESITE = config('AUTH_COOKIE_SAMESITE', default='Lax')

# --- Cotización del dólar ---
# Fuente pública usada para traer el dólar oficial en tiempo real.
DOLAR_API_URL = config('DOLAR_API_URL', default='https://dolarapi.com/v1/dolares/oficial')
# Minutos que se considera "fresca" una cotización cacheada antes de volver a pedirla.
DOLAR_CACHE_MINUTOS = config('DOLAR_CACHE_MINUTOS', default=10, cast=int)

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Email (para el envío de presupuestos) ---
# Por defecto queda en "console": los emails se imprimen en la terminal en
# vez de enviarse de verdad — útil para probar sin configurar un SMTP real.
# Para producción, poné EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# y completá el resto de las variables EMAIL_* en el .env.
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Lausane S.A.C. <presupuestos@lausane.com.ar>')

# Si EMAIL_BACKEND = precios.services.sendgrid_backend.SendGridBackend (ver
# ese archivo para el porqué), esta es la API key de SendGrid.
SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')

# URL pública del frontend, usada para armar el link que se manda por
# WhatsApp/email cuando no se adjunta el PDF directamente.
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# Casilla que recibe los mensajes del formulario de contacto del sitio público.
CONTACTO_EMAIL_DESTINO = config('CONTACTO_EMAIL_DESTINO', default='lausaneventas@lausane.com.ar')

