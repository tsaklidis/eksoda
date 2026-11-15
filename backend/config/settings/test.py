from .base import *

# Fast, deterministic tests. The database is the real PostgreSQL service.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

REGISTRATION_OPEN = False
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = False

LOGGING["root"]["level"] = "INFO"
LOGGING["handlers"]["stdout"]["formatter"] = "console"
