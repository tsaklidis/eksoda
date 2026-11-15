"""Celery application. Job state lives in PostgreSQL; Redis is only the broker (TD §12.7)."""

import os

from celery import Celery
from celery.signals import setup_logging, task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("eksoda")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def _use_django_logging(**_kwargs):
    """Workers log through settings.LOGGING (JSON, context, URL redaction), not Celery's."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@task_prerun.connect
def _bind_task_log_context(task_id=None, **_kwargs):
    from apps.common.logging import bind_log_context

    bind_log_context(task_id=task_id)


@task_postrun.connect
def _clear_task_log_context(**_kwargs):
    from apps.common.logging import clear_log_context

    clear_log_context()
