"""Liveness and readiness endpoints (outside /api/v1, no authentication)."""

import logging

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def healthz(request):
    """Liveness: the process is up and serving requests."""
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request):
    """Readiness: PostgreSQL and Redis are reachable. Never exposes failure details."""
    ready = _database_ready() and _redis_ready()
    return JsonResponse(
        {"status": "ok" if ready else "unavailable"},
        status=200 if ready else 503,
    )


def _database_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.warning("Readiness check failed: database unreachable", exc_info=True)
        return False


def _redis_ready() -> bool:
    try:
        with redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        ) as client:  # closes the connection after the probe
            return bool(client.ping())
    except Exception:
        logger.warning("Readiness check failed: redis unreachable", exc_info=True)
        return False
