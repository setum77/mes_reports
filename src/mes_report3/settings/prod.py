import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

_secret_key = os.environ.get("DJANGO_SECRET_KEY")
if not _secret_key:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set in production settings."
    )
SECRET_KEY = _secret_key

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

if os.environ.get("DJANGO_HTTPS", "false").lower() == "true":
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
