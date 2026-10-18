import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', '0') == '1'
SECRET_KEY = os.getenv('SECRET_KEY', '')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Set a unique SECRET_KEY of at least 50 characters.')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [v for v in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if v]
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
                  'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'portal']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
              'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
              'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
              'portal.middleware.SafetyMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
              'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
              'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                         'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
# A dedicated Neon/PostgreSQL database can be selected by the backend host.
# Never expose these credentials to GitHub Pages or the Android client.
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL:
    from urllib.parse import urlsplit, unquote
    parsed = urlsplit(DATABASE_URL)
    if parsed.scheme not in ('postgres', 'postgresql') or not all([parsed.hostname, parsed.username, parsed.path.strip('/')]):
        raise ImproperlyConfigured('DATABASE_URL must be a valid PostgreSQL connection URL.')
    if not DEBUG and parsed.hostname not in ('localhost', '127.0.0.1') and os.getenv('DB_SSLMODE', 'require') != 'require':
        raise ImproperlyConfigured('Production remote PostgreSQL connections require SSL.')
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname,
        'PORT': parsed.port or 5432,
        'CONN_MAX_AGE': 0,
        'OPTIONS': {'sslmode': os.getenv('DB_SSLMODE', 'require'), 'connect_timeout': 10},
    }}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                             'NAME': os.getenv('DATABASE_PATH', str(BASE_DIR / 'db.sqlite3')),
                             'OPTIONS': {'timeout': 20}}}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
PASSWORD_HASHERS = ['django.contrib.auth.hashers.ScryptPasswordHasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher']
LANGUAGE_CODE = 'en-nz'
TIME_ZONE = 'Pacific/Auckland'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'site' / 'dist']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
# Preload is deliberately deferred until a permanent owned domain is approved.
SILENCED_SYSTEM_CHECKS = ['security.W021']
SECURE_CONTENT_TYPE_NOSNIFF = True
# GIS uses the HTTPS origin to validate its cross-origin button frame. Send
# only the origin cross-site, never account paths or query strings.
# https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'
# Enable ONLY behind a trusted proxy that strips incoming X-Forwarded-Proto.
if os.getenv('TRUST_PROXY_HTTPS') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'portal.email_backend.BrevoEmailBackend')
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')
EMAIL_REPLY_TO = os.getenv('EMAIL_REPLY_TO', 'kiwikindbroadband@gmail.com')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 10
# Optional operator switch for a known transport outage (e.g. SMTP on Render Free).
# Runtime connection failures also return the same safe error before account lookup.
RESET_EMAIL_UNAVAILABLE = os.getenv('RESET_EMAIL_UNAVAILABLE') == '1'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'KiwiKind Broadband <kiwikindbroadband@gmail.com>')
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
LEGAL_ENTITY = os.getenv('LEGAL_ENTITY', '')
BUSINESS_CONTACT = os.getenv('BUSINESS_CONTACT', '')
PRIVACY_CONTACT = os.getenv('PRIVACY_CONTACT', '')
INTAKE_ENABLED = os.getenv('INTAKE_ENABLED') == '1'
REFERRALS_ENABLED = os.getenv('REFERRALS_ENABLED') == '1'
ADMIN_ENABLED = os.getenv('ADMIN_ENABLED') == '1'
OWNER_GOOGLE_ADMIN_ENABLED = os.getenv('OWNER_GOOGLE_ADMIN_ENABLED') == '1'
GOOGLE_WEB_CLIENT_ID = os.getenv('GOOGLE_WEB_CLIENT_ID', '').strip()
mail_configured = bool(BREVO_API_KEY) if EMAIL_BACKEND == 'portal.email_backend.BrevoEmailBackend' else bool(EMAIL_HOST)
if not DEBUG and INTAKE_ENABLED and not all([LEGAL_ENTITY, BUSINESS_CONTACT, PRIVACY_CONTACT, mail_configured, DEFAULT_FROM_EMAIL]):
    raise ImproperlyConfigured('Public intake requires legal identity, contacts and email configuration.')
if not DEBUG and ADMIN_ENABLED and OWNER_GOOGLE_ADMIN_ENABLED and not GOOGLE_WEB_CLIENT_ID:
    raise ImproperlyConfigured('Owner administration requires Google sign-in configuration.')
if not DEBUG and ADMIN_ENABLED and not OWNER_GOOGLE_ADMIN_ENABLED and os.getenv('ADMIN_MFA_PERIMETER_CONFIRMED') != '1':
    raise ImproperlyConfigured('Admin requires an independently configured MFA access perimeter.')
if not DEBUG and not PUBLIC_ORIGIN.startswith('https://'):
    raise ImproperlyConfigured('Production requires HTTPS PUBLIC_ORIGIN.')
