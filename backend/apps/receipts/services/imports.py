"""Submitting receipt URLs and retrying imports (requirements §6.2–§6.5, TD §12.1).

Submitting is idempotent by itself: the provider derives a stable identity from the
URL, and ``UNIQUE(household, provider_code, url_identity)`` turns repeat and
concurrent submissions into one job. Nothing is fetched during the request: the job
is enqueued after the transaction commits.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.receipts.api_errors import NotRetryable
from apps.receipts.errors import UnsupportedProvider, UnsupportedUrlFormat
from apps.receipts.links import parse_submitted_url
from apps.receipts.models import ReceiptImportJob
from apps.receipts.providers import registry
from apps.receipts.providers.base import UrlIdentity

logger = logging.getLogger(__name__)

Status = ReceiptImportJob.Status
Outcome = ReceiptImportJob.Outcome

# Jobs a resubmission starts again: failed ones, and ones whose receipt was deleted.
RESUBMITTABLE = Q(status=Status.FAILED) | Q(
    status=Status.COMPLETED, outcome=Outcome.RECEIPT_DELETED
)


@dataclass(frozen=True)
class SubmitResult:
    job: ReceiptImportJob
    created: bool  # False: the household submitted this receipt link before
    requeued: bool  # an earlier failed or deleted import was started again


def submit_import(*, user, household, raw_url: object) -> SubmitResult:
    """Create or reuse the household's job for this URL identity.

    Raises InvalidUrl, UnsupportedProvider or UnsupportedUrlFormat (ReceiptError).
    """
    url = parse_submitted_url(raw_url)  # raises InvalidUrl; the host is logged below
    try:
        _provider, identity = registry.resolve_url(raw_url)
    except (UnsupportedProvider, UnsupportedUrlFormat) as exc:
        logger.info("receipt link rejected: %s host=%s", exc.code, url.host)
        raise

    # The outer transaction makes the enqueue wait for the commit; the inner savepoint
    # keeps it usable after an IntegrityError.
    with transaction.atomic():
        try:
            with transaction.atomic():
                job = ReceiptImportJob.objects.create(
                    household=household,
                    requested_by=user,
                    provider_code=identity.provider_code,
                    url_identity=identity.identity,
                    submitted_url=identity.canonical_url,
                    url_fingerprint=identity.url_fingerprint,
                    issuer_vat=identity.issuer_vat or "",
                    next_attempt_at=timezone.now(),
                )
            created, requeued = True, False
        except IntegrityError:  # submitted before, possibly by a concurrent request
            job = ReceiptImportJob.objects.get(
                household=household,
                provider_code=identity.provider_code,
                url_identity=identity.identity,
            )
            created = False
            requeued = _requeue(job.pk, RESUBMITTABLE, identity=identity)
            if requeued:
                job.refresh_from_db()
        if created or requeued:
            _enqueue_on_commit(job.pk)

    logger.info(
        "receipt import submitted: provider=%s host=%s url_fp=%s job=%s created=%s requeued=%s",
        identity.provider_code,
        url.host,
        identity.url_fingerprint[:12],
        job.pk,
        created,
        requeued,
    )
    return SubmitResult(job=job, created=created, requeued=requeued)


def retry_import(job: ReceiptImportJob) -> ReceiptImportJob:
    """Start a failed job again with the full retry schedule (requirements §6.5)."""
    with transaction.atomic():
        if not _requeue(job.pk, Q(status=Status.FAILED)):
            raise NotRetryable()
        _enqueue_on_commit(job.pk)
    logger.info("receipt import retried: job=%s", job.pk)
    job.refresh_from_db()
    return job


def _requeue(job_id: UUID, condition: Q, *, identity: UrlIdentity | None = None) -> bool:
    """Set the job back to pending if it matches ``condition``.

    A conditional UPDATE: it never waits on a worker, because a job a worker holds is
    pending and so never matches. A resubmitted link replaces the stored one (the new
    link may work where the old one did not).
    """
    now = timezone.now()
    fields = {
        "status": Status.PENDING,
        "outcome": None,
        "attempt_count": 0,
        "next_attempt_at": now,
        "last_error_code": "",
        "last_error_message": "",
        "finished_at": None,
        "updated_at": now,
    }
    if identity is not None:
        fields |= {
            "submitted_url": identity.canonical_url,
            "url_fingerprint": identity.url_fingerprint,
        }
    return ReceiptImportJob.objects.filter(condition, pk=job_id).update(**fields) == 1


def _enqueue_on_commit(job_id: UUID) -> None:
    from apps.receipts.tasks import process_import  # tasks import the pipeline

    transaction.on_commit(lambda: process_import.delay(str(job_id)))
