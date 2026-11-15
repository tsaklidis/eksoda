"""Processing one import job (requirements §6.4–§6.6, TD §12.2–§12.4).

1. Claim (short transaction): lock the row with SKIP LOCKED, continue only if the job
   is pending and due, count the attempt, and move ``next_attempt_at`` ahead as a
   lease. If the worker dies, the job is due again when the lease ends.
2. Fetch, parse and validate, outside any transaction.
3. Persist the receipt and complete the job in one transaction.
4. On failure: schedule the next attempt (retryable errors, schedule left) or fail.

Completing and failing update only rows that are still pending, and the receipt
identity constraints are the final guard, so a task that runs twice is harmless.
"""

import logging
import random
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.logging import bind_log_context
from apps.receipts.conf import default_fetcher
from apps.receipts.errors import InternalError, ReceiptError, RetryPolicy
from apps.receipts.fetching import SafeFetcher
from apps.receipts.models import Receipt, ReceiptImportJob
from apps.receipts.providers import registry
from apps.receipts.services.persistence import persist
from apps.receipts.validation import validate

logger = logging.getLogger(__name__)

Status = ReceiptImportJob.Status
RETRYABLE = frozenset({RetryPolicy.TRANSIENT, RetryPolicy.NOT_FOUND})


class JobChanged(Exception):
    """The job stopped being pending while it was processed (e.g. it was deleted)."""


def process_import(job_id: UUID, *, fetcher: SafeFetcher | None = None) -> None:
    job = claim(job_id)
    if job is None:
        return
    bind_log_context(job_id=job.pk, household_id=job.household_id, provider=job.provider_code)
    try:
        provider, identity = registry.resolve_url(job.submitted_url)
        document = provider.fetch(identity, fetcher or default_fetcher())
        canonical = provider.parse(document, identity)
        issues = validate(canonical)
        with transaction.atomic():
            receipt, outcome = persist(job, canonical, issues)
            complete(job, receipt, outcome)
    except JobChanged:
        logger.warning("receipt import discarded: the job is no longer pending")
        return
    except ReceiptError as exc:
        record_failure(job, exc)
        return
    except Exception as exc:  # includes SoftTimeLimitExceeded
        logger.exception("receipt import failed with an unexpected error")
        record_failure(job, InternalError(type(exc).__name__))
        return
    logger.info(
        "receipt imported: provider=%s outcome=%s receipt=%s lines=%d warnings=%d",
        canonical.provider_code,
        outcome,
        receipt.pk,
        len(canonical.lines),
        len(issues),
    )


def claim(job_id: UUID) -> ReceiptImportJob | None:
    """Lease a pending, due job; None when it is not (taken, done, or not due yet)."""
    now = timezone.now()
    with transaction.atomic():
        job = (
            ReceiptImportJob.objects.select_for_update(skip_locked=True)
            .filter(pk=job_id, status=Status.PENDING, next_attempt_at__lte=now)
            .first()
        )
        if job is None:
            return None
        if job.attempt_count > len(settings.IMPORT_RETRY_SCHEDULE):
            # Every attempt so far ended without recording a result (worker killed).
            _fail(job, InternalError("attempts exhausted"), now)
            return None
        job.attempt_count += 1
        job.next_attempt_at = now + timedelta(seconds=settings.IMPORT_LEASE_SECONDS)
        job.save(update_fields=["attempt_count", "next_attempt_at", "updated_at"])
    return job


def complete(job: ReceiptImportJob, receipt: Receipt, outcome: str) -> None:
    now = timezone.now()
    updated = ReceiptImportJob.objects.filter(pk=job.pk, status=Status.PENDING).update(
        status=Status.COMPLETED,
        outcome=outcome,
        receipt=receipt,
        issuer_vat=receipt.issuer_vat,  # not every link carries it; the receipt always does
        next_attempt_at=None,
        last_error_code="",
        last_error_message="",
        finished_at=now,
        updated_at=now,
    )
    if not updated:
        raise JobChanged()  # rolls back the receipt


def record_failure(job: ReceiptImportJob, exc: ReceiptError) -> None:
    """Schedule the next attempt for retryable errors while the schedule lasts; else fail."""
    schedule = settings.IMPORT_RETRY_SCHEDULE
    step = job.attempt_count - 1  # attempt n failed → wait schedule[n - 1]
    now = timezone.now()
    if exc.retry in RETRYABLE and step < len(schedule):
        delay = schedule[step] * random.uniform(0.9, 1.1)  # noqa: S311 (jitter, not security)
        next_attempt_at = now + timedelta(seconds=delay)
        ReceiptImportJob.objects.filter(pk=job.pk, status=Status.PENDING).update(
            next_attempt_at=next_attempt_at,
            last_error_code=exc.code.value,
            last_error_message=exc.public_message,
            updated_at=now,
        )
        logger.info(
            "receipt import attempt %d failed: %s (%s); next attempt at %s",
            job.attempt_count,
            exc.code,
            exc.detail,
            next_attempt_at.isoformat(),
        )
    else:
        _fail(job, exc, now)


def _fail(job: ReceiptImportJob, exc: ReceiptError, now: datetime) -> None:
    ReceiptImportJob.objects.filter(pk=job.pk, status=Status.PENDING).update(
        status=Status.FAILED,
        next_attempt_at=None,
        last_error_code=exc.code.value,
        last_error_message=exc.public_message,
        finished_at=now,
        updated_at=now,
    )
    logger.warning(
        "receipt import failed after %d attempt(s): %s (%s)",
        job.attempt_count,
        exc.code,
        exc.detail,
    )
