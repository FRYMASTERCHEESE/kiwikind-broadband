from .settings import *
DEBUG = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
INTAKE_ENABLED = True
REGISTRATION_ENABLED = True
ADMIN_ENABLED = True
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'test@example.invalid'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.PBKDF2PasswordHasher']
