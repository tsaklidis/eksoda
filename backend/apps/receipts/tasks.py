"""Import tasks (requirements §14, TD §12.6, §12.7).

The database is the scheduler: retries are stored as ``next_attempt_at`` and
``run_due_imports`` (beat, every minute) enqueues the jobs that are due. Broker
countdowns are not used, because long ETAs are unreliable with a Redis broker.
"""

from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.common.logging import bind_log_context
from apps.receipts.models import ReceiptImportJob
from apps.receipts.services import pipeline

DUE_BATCH_SIZE = 100


@shared_task(
    name="receipts.process_import",
    soft_time_limit=60,
    time_limit=90,
    rate_limit=settings.IMPORT_TASK_RATE_LIMIT,
)
def process_import(job_id: str) -> None:
    bind_log_context(job_id=job_id)
    pipeline.process_import(UUID(job_id))


@shared_task(name="receipts.run_due_imports")
def run_due_imports() -> int:
    """Enqueue pending jobs whose time has come: scheduled retries, lost messages, and
    jobs of crashed workers (their lease ended). An extra message is harmless."""
    due = (
        ReceiptImportJob.objects.filter(
            status=ReceiptImportJob.Status.PENDING, next_attempt_at__lte=timezone.now()
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:DUE_BATCH_SIZE]
    )
    job_ids = list(due)
    for job_id in job_ids:
        process_import.delay(str(job_id))
    return len(job_ids)
