from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if SECRET_KEY == DEV_ONLY_SECRET_KEY or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to at least 50 random characters.")

# TLS terminates at the reverse proxy (Caddy), which redirects HTTP to HTTPS, so
# Django's own redirect stays off (and its deploy-check warning is silenced).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
# HSTS preload is a per-domain decision (and impossible for a dynamic-DNS subdomain).
SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W021"]
# Exactly one proxy (Caddy) sits in front of gunicorn and appends the client address to
# X-Forwarded-For; throttles use that address, not one a client sent.
REST_FRAMEWORK["NUM_PROXIES"] = 1
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# The schema and Swagger UI are for staff only in production.
SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = ["rest_framework.permissions.IsAdminUser"]
SPECTACULAR_SETTINGS["SERVE_AUTHENTICATION"] = [
    "rest_framework.authentication.SessionAuthentication",
    "apps.common.authentication.JWTAuthentication",
]

LOG_FORMAT = env.str("LOG_FORMAT", default="json")
LOGGING["handlers"]["stdout"]["formatter"] = LOG_FORMAT

if SENTRY_DSN:
    from apps.common.sentry import init_sentry

    init_sentry(SENTRY_DSN, environment=SENTRY_ENVIRONMENT, release=SENTRY_RELEASE)
