"""Settings shared by every environment. See docs/technical-design.md §4."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
env = environ.Env()

DEV_ONLY_SECRET_KEY = "django-insecure-dev-only-key-never-use-in-production"  # noqa: S105


def env_list(name: str, default: list[str]) -> list[str]:
    """Comma-separated list from the environment; blank values are ignored."""
    return [item for item in env.list(name, default=default) if item]


# --- Core ---------------------------------------------------------------------
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="") or DEV_ONLY_SECRET_KEY
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])
ADMIN_PATH = env.str("DJANGO_ADMIN_PATH", default="admin/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.common",
    "apps.accounts",
    "apps.households",
    "apps.merchants",
    "apps.products",
    "apps.receipts",
    "apps.analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.common.logging.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Data stores ----------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://eksoda:eksoda@db:5432/eksoda"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env.str("REDIS_URL", default="redis://redis:6379").rstrip("/")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
    },
}

# --- Authentication -------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization ---------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Athens"  # display default; storage is UTC
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024  # API bodies are small JSON; larger ones get a 400

# --- Django REST Framework --------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.common.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["apps.common.parsers.LimitedJSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.PageNumberPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "apps.common.schema.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_THROTTLE_RATES": {
        "login": env.str("THROTTLE_LOGIN", default="5/min"),
        "login_ip": env.str("THROTTLE_LOGIN_IP", default="30/min"),
        "register": env.str("THROTTLE_REGISTER", default="10/hour"),
        "join": env.str("THROTTLE_JOIN", default="20/hour"),
        "import_minute": env.str("THROTTLE_IMPORT_MINUTE", default="30/min"),
        "import_day": env.str("THROTTLE_IMPORT_DAY", default="500/day"),
        "admin_login": env.str("THROTTLE_ADMIN_LOGIN", default="5/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env.str("JWT_SIGNING_KEY", default="") or SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Eksoda API",
    "DESCRIPTION": (
        "Household expense and receipt intelligence API. Errors use the envelope "
        '`{"error": {"code", "message", "details"}}`. Household-scoped endpoints accept '
        "an optional `X-Household-ID` header."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "ENUM_NAME_OVERRIDES": {
        "InvitationStatusEnum": "apps.households.models.HouseholdInvitation.Status",
        "ImportStatusEnum": "apps.receipts.models.ReceiptImportJob.Status",
        "ReceiptStatusEnum": "apps.receipts.models.Receipt.Status",
        "NormalizedUnitEnum": "apps.receipts.models.ReceiptItem.NormalizedUnit",
    },
}

# --- Application settings ------------------------------------------------------------
REGISTRATION_OPEN = env.bool("REGISTRATION_OPEN", default=False)
INVITATION_TTL_DAYS = env.int("INVITATION_TTL_DAYS", default=7)
# Receipt fetching limits (requirements §15.1).
FETCH_CONNECT_TIMEOUT = env.float("FETCH_CONNECT_TIMEOUT", default=5.0)
FETCH_READ_TIMEOUT = env.float("FETCH_READ_TIMEOUT", default=15.0)
FETCH_TOTAL_TIMEOUT = env.float("FETCH_TOTAL_TIMEOUT", default=30.0)
FETCH_MAX_BYTES = env.int("FETCH_MAX_BYTES", default=2 * 1024 * 1024)
# Import jobs (requirements §6.5, TD §12.2): the claim lease and the retry schedule, in
# seconds after a failed attempt (7 attempts in all). Constants until a need arises.
IMPORT_LEASE_SECONDS = 300
IMPORT_RETRY_SCHEDULE = (60, 300, 1800, 7200, 21600, 86400)
IMPORT_TASK_RATE_LIMIT = env.str("IMPORT_TASK_RATE_LIMIT", default="30/m")  # per worker
# Code-reuse guard (requirements §9.2): a mapped item code whose description is less
# similar than this to the last one seen goes to review instead of being matched.
MATCH_GUARD_SIMILARITY = 0.4

# --- Celery (TD §12.7) ------------------------------------------------------------
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_TASK_IGNORE_RESULT = True
# A task whose worker dies is redelivered (tasks are idempotent, TD §12.2). Redis
# redelivers an unacknowledged task after the visibility timeout, which matches the
# import lease (IMPORT_LEASE_SECONDS).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 300}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_WORKER_REDIRECT_STDOUTS = False
CELERY_TASK_DEFAULT_QUEUE = "maintenance"
CELERY_TASK_ROUTES = {"receipts.*": {"queue": "imports"}}
CELERY_TIMEZONE = "Europe/Athens"
CELERY_BEAT_SCHEDULE = {
    "run-due-imports": {
        "task": "receipts.run_due_imports",
        "schedule": 60.0,
    },
    "flush-expired-tokens": {
        "task": "accounts.flush_expired_tokens",
        "schedule": crontab(hour=3, minute=20),
    },
}

# --- Logging (TD §16) ---------------------------------------------------------------
LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")
LOG_FORMAT = env.str("LOG_FORMAT", default="console")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "context": {"()": "apps.common.logging.ContextFilter"},
        "redact": {"()": "apps.common.logging.RedactFilter"},
    },
    "formatters": {
        "json": {
            "()": "apps.common.logging.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "rename_fields": {"levelname": "level", "name": "logger"},
        },
        "console": {
            "format": "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": LOG_FORMAT,
            "filters": ["context", "redact"],
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "django.db.backends": {"level": "WARNING"},
        "celery": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
    },
}

# --- Error tracking --------------------------------------------------------------
SENTRY_DSN = env.str("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env.str("SENTRY_ENVIRONMENT", default="production")
SENTRY_RELEASE = env.str("SENTRY_RELEASE", default="")
