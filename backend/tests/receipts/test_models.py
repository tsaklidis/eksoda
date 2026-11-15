"""Database constraints on receipts, lines and import jobs (requirements §6.3, §8)."""

import pytest
from django.db import IntegrityError, transaction

from apps.receipts.models import ReceiptImportJob, ReceiptItem
from tests.factories import (
    HouseholdFactory,
    ImportJobFactory,
    ReceiptFactory,
    ReceiptItemFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "identity",
    [
        {"mark": "400015963897868"},
        {"mark": None, "uid": "ABC", "issuer_country": "GR", "issuer_vat": "094062259"},
        {"mark": None, "source_key": "fhm:FGG18025203:00686373"},
    ],
)
def test_receipt_identity_is_unique_per_household(identity):
    household = HouseholdFactory()
    ReceiptFactory(household=household, **identity)
    with pytest.raises(IntegrityError), transaction.atomic():
        ReceiptFactory(household=household, **identity)
    ReceiptFactory(household=HouseholdFactory(), **identity)  # another household may


def test_receipts_without_identity_values_do_not_collide():
    household = HouseholdFactory()
    ReceiptFactory(household=household, mark=None, uid=None, source_key=None)
    ReceiptFactory(household=household, mark=None, uid=None, source_key=None)


def test_job_identity_is_unique_per_household():
    job = ImportJobFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ImportJobFactory(household=job.household, url_identity=job.url_identity)
    ImportJobFactory(url_identity=job.url_identity)


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (ReceiptImportJob.Status.COMPLETED, None),
        (ReceiptImportJob.Status.PENDING, ReceiptImportJob.Outcome.CREATED),
        (ReceiptImportJob.Status.FAILED, ReceiptImportJob.Outcome.DUPLICATE),
    ],
)
def test_only_completed_jobs_have_an_outcome(status, outcome):
    with pytest.raises(IntegrityError), transaction.atomic():
        ImportJobFactory(status=status, outcome=outcome)


def test_line_numbers_are_unique_per_receipt():
    item = ReceiptItemFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ReceiptItemFactory(receipt=item.receipt, line_number=item.line_number)


@pytest.mark.parametrize(
    ("line_type", "match_status"),
    [
        (ReceiptItem.LineType.PRODUCT, ReceiptItem.MatchStatus.NOT_A_PRODUCT),
        (ReceiptItem.LineType.DISCOUNT, ReceiptItem.MatchStatus.NEEDS_REVIEW),
        (ReceiptItem.LineType.FEE, ReceiptItem.MatchStatus.MATCHED),
    ],
)
def test_only_product_lines_are_matched_or_reviewed(line_type, match_status):
    with pytest.raises(IntegrityError), transaction.atomic():
        ReceiptItemFactory(line_type=line_type, match_status=match_status)


def test_deleting_a_receipt_keeps_its_jobs():
    item = ReceiptItemFactory()
    job = ImportJobFactory(
        household=item.household,
        status=ReceiptImportJob.Status.COMPLETED,
        outcome=ReceiptImportJob.Outcome.CREATED,
        receipt=item.receipt,
    )
    item.receipt.delete()
    job.refresh_from_db()
    assert job.receipt is None
    assert not ReceiptItem.objects.exists()


def test_job_properties():
    job = ImportJobFactory.build(
        submitted_url="https://einvoice.impact.gr/p/EL1/X/Y", last_error_code=""
    )
    assert job.source_host == "einvoice.impact.gr"
    assert job.error is None
    assert job.scheduled_retry_at is None  # pending without an error: new or leased
    job.last_error_code, job.last_error_message = "provider_timeout", "Slow."
    assert job.error == {"code": "provider_timeout", "message": "Slow."}
    assert job.scheduled_retry_at == job.next_attempt_at
    assert "impact" in str(job)
    assert str(ReceiptItemFactory.build(line_number=2, description="ΓΑΛΑ")) == "2. ΓΑΛΑ"
