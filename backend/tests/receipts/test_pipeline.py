"""Import pipeline: claim, fetch, parse, persist, failures (requirements §6.3–§6.6)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.merchants.models import Merchant, Store
from apps.receipts import tasks
from apps.receipts.errors import (
    BlockedDestination,
    FormatChanged,
    InconsistentSource,
    ProviderHttpError,
    ProviderTimeout,
    ProviderUnreachable,
    ReceiptNotFound,
    ResponseTooLarge,
    UnexpectedContentType,
)
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.services import imports, persistence, pipeline
from apps.receipts.services.receipts import delete_receipt
from tests.factories import ImportJobFactory, MemberFactory
from tests.receipts.importing import AADE, IMPACT, LIDL, FakeFetcher, run, submit

pytestmark = pytest.mark.django_db

Status = ReceiptImportJob.Status
Outcome = ReceiptImportJob.Outcome
SCHEDULE = (60, 300, 1800, 7200, 21600, 86400)


@pytest.fixture
def member(db):
    return MemberFactory()


# --- happy paths -------------------------------------------------------------------
def test_impact_receipt_is_stored(member):
    job = run(submit(member))

    assert (job.status, job.outcome, job.attempt_count) == (Status.COMPLETED, Outcome.CREATED, 1)
    assert job.error is None
    assert job.next_attempt_at is None
    assert job.finished_at
    assert job.issuer_vat == "094062259"
    receipt = job.receipt
    assert receipt.household == member.household
    assert receipt.imported_by == member.user
    assert receipt.merchant.vat_number == "094062259"
    assert receipt.merchant.display_name == "Metro"
    assert receipt.store.branch_number == "264"
    assert (receipt.provider_code, receipt.parser_version) == ("impact", "impact/1")
    assert receipt.mark == "400015963897868"
    assert receipt.uid == "FA8355776160C1AF53AC6A860C29C0BB1437029F"
    assert receipt.document_number == "7222-546093"
    assert (receipt.document_kind, receipt.document_type_code) == ("sale", "11.1")
    assert receipt.issued_at.isoformat() == "2026-11-07T16:28:00+00:00"
    assert (receipt.gross_total, receipt.net_total, receipt.vat_total) == (
        Decimal("9.15"),
        Decimal("8.10"),
        Decimal("1.05"),
    )
    assert receipt.payment_method == Receipt.PaymentMethod.CARD
    assert receipt.status == Receipt.Status.ACTIVE
    assert receipt.validation_warnings == []
    assert receipt.source_url == IMPACT.url
    assert receipt.source_url_fingerprint == job.url_fingerprint
    assert "source_url" not in receipt.source_data
    assert IMPACT.url not in str(receipt.source_data)
    assert receipt.source_data["coverage"]["line_items"] is True

    items = list(receipt.items.order_by("line_number"))
    assert [item.line_number for item in items] == [1, 2, 3, 4, 5]
    assert {item.line_type for item in items} == {ReceiptItem.LineType.PRODUCT}
    assert {item.match_status for item in items} == {ReceiptItem.MatchStatus.MATCHED}
    assert len({item.product_id for item in items}) == 5  # one new product per item
    assert sum(item.gross_amount for item in items) == Decimal("9.15")
    first = items[0]
    assert first.description == "ADORO LIGHT 10% ΦΡΑΤΖ. ΓΕΡΜΑΝΙΑΣ(Τ.ΚΙΛΟΥ"
    assert first.normalized_description.startswith("ADORO LIGHT 10% ")
    assert (first.quantity, first.unit, first.unit_price) == (
        Decimal("0.622"),
        ReceiptItem.Unit.KG,
        Decimal("7.21"),
    )
    assert (first.net_amount, first.vat_rate, first.vat_amount) == (
        Decimal("3.96"),
        Decimal("13"),
        Decimal("0.52"),
    )
    assert first.merchant_product_code == "127321"
    assert all(item.household_id == member.household_id for item in items)


def test_entersoft_receipt_with_line_discounts(member):
    job = run(submit(member, LIDL), LIDL.fetcher())
    receipt = job.receipt
    assert job.outcome == Outcome.CREATED
    assert receipt.merchant.display_name == "Lidl"
    assert receipt.store.branch_number is None
    assert receipt.store.postal_code == "50100"
    assert receipt.discount_total == Decimal("3.80")
    assert receipt.items.count() == 21
    first = receipt.items.get(line_number=1)
    assert (first.gross_amount, first.discount_amount) == (Decimal("1.36"), Decimal("0.04"))
    assert first.net_amount is None  # Entersoft lines have no tax amounts
    assert receipt.source_data["coverage"]["issue_time"] == "approximate"


def test_cash_register_receipt_without_lines(member):
    job = run(submit(member, AADE), AADE.fetcher())
    receipt = job.receipt
    assert receipt.items.count() == 0
    assert (receipt.mark, receipt.uid) == (None, None)
    assert receipt.source_key == "fhm:FGG18025203:00686373"
    assert receipt.document_type_code is None
    assert receipt.payment_method == Receipt.PaymentMethod.CASH
    assert receipt.store.city == "ΙΛΙΟΝ"


def test_merchants_and_stores_are_shared_between_households(member):
    run(submit(member))
    run(submit(MemberFactory()))
    assert Receipt.objects.count() == 2
    assert Merchant.objects.count() == 1
    assert Store.objects.count() == 1


# --- duplicates and re-execution ------------------------------------------------------
def test_same_receipt_from_another_url_form_is_a_duplicate(member):
    first = run(submit(member))
    other = ImportJobFactory(
        household=member.household,
        url_identity="another-url-form",
        submitted_url=IMPACT.url,
    )
    other = run(other)
    assert (other.status, other.outcome) == (Status.COMPLETED, Outcome.DUPLICATE)
    assert other.receipt == first.receipt
    assert Receipt.objects.count() == 1


def test_concurrent_identical_receipt_becomes_a_duplicate(member, monkeypatch):
    """The receipt create loses on the identity constraint: the winner's row is used."""
    first = run(submit(member))
    other = ImportJobFactory(household=member.household, submitted_url=IMPACT.url)
    real = persistence.find_existing
    calls = []

    def first_lookup_misses(household_id, canonical):
        calls.append(1)
        return None if len(calls) == 1 else real(household_id, canonical)

    monkeypatch.setattr(persistence, "find_existing", first_lookup_misses)
    other = run(other)
    assert (other.outcome, other.receipt) == (Outcome.DUPLICATE, first.receipt)
    assert len(calls) == 2
    assert Receipt.objects.count() == 1


def test_running_a_finished_job_again_changes_nothing(member):
    job = run(submit(member))
    before = (job.updated_at, job.attempt_count, ReceiptItem.objects.count())
    pipeline.process_import(job.pk, fetcher=FakeFetcher(RuntimeError("must not fetch")))
    job.refresh_from_db()
    assert (job.updated_at, job.attempt_count, ReceiptItem.objects.count()) == before
    assert Receipt.objects.count() == 1


def test_complete_refuses_jobs_that_are_no_longer_pending(member):
    receipt = run(submit(member)).receipt
    failed = ImportJobFactory(status=Status.FAILED, next_attempt_at=None)
    with pytest.raises(pipeline.JobChanged):
        pipeline.complete(failed, receipt, Outcome.DUPLICATE)
    failed.refresh_from_db()
    assert (failed.status, failed.receipt) == (Status.FAILED, None)


def test_a_job_that_stops_being_pending_is_rolled_back(member, monkeypatch):
    def changed(*args, **kwargs):
        raise pipeline.JobChanged()

    monkeypatch.setattr(pipeline, "complete", changed)
    job = run(submit(member))
    assert not Receipt.objects.exists()  # the receipt was rolled back
    assert job.status == Status.PENDING
    assert job.last_error_code == ""  # left to its owner


# --- claim and lease -------------------------------------------------------------------
def test_claim_leases_the_job(member, settings):
    job = submit(member)
    claimed = pipeline.claim(job.pk)
    assert claimed.attempt_count == 1
    lease = claimed.next_attempt_at - timezone.now()
    assert timedelta(minutes=4) < lease <= timedelta(minutes=5)
    assert pipeline.claim(job.pk) is None  # a second worker gets nothing


def test_an_expired_lease_is_claimed_again(member):
    job = submit(member)
    pipeline.claim(job.pk)
    ReceiptImportJob.objects.filter(pk=job.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )
    assert pipeline.claim(job.pk).attempt_count == 2


def test_jobs_that_are_not_pending_or_not_due_are_not_claimed(member):
    job = submit(member)
    ReceiptImportJob.objects.filter(pk=job.pk).update(
        next_attempt_at=timezone.now() + timedelta(minutes=1)
    )
    assert pipeline.claim(job.pk) is None
    ReceiptImportJob.objects.filter(pk=job.pk).update(
        status=Status.FAILED, next_attempt_at=timezone.now()
    )
    assert pipeline.claim(job.pk) is None


def test_attempts_exhausted_by_crashes_fail_the_job(member):
    job = submit(member)
    ReceiptImportJob.objects.filter(pk=job.pk).update(attempt_count=len(SCHEDULE) + 1)
    assert pipeline.claim(job.pk) is None
    job.refresh_from_db()
    assert job.status == Status.FAILED
    assert job.last_error_code == "internal_error"
    assert job.next_attempt_at is None
    assert job.finished_at


# --- failures --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error", [ProviderUnreachable, ProviderTimeout, ProviderHttpError, ReceiptNotFound]
)
def test_retryable_errors_schedule_the_next_attempt(member, error):
    job = run(submit(member), FakeFetcher(error("detail")))
    assert job.status == Status.PENDING
    assert job.attempt_count == 1
    assert job.last_error_code == error.code
    assert job.error == {"code": error.code, "message": error.public_message}
    delay = (job.next_attempt_at - timezone.now()).total_seconds()
    assert 60 * 0.9 - 2 <= delay <= 60 * 1.1
    assert job.scheduled_retry_at == job.next_attempt_at


@pytest.mark.parametrize(
    "error",
    [
        BlockedDestination,
        ResponseTooLarge,
        UnexpectedContentType,
        FormatChanged,
        InconsistentSource,
    ],
)
def test_other_errors_fail_the_job(member, error):
    job = run(submit(member), FakeFetcher(error("detail")))
    assert (job.status, job.last_error_code) == (Status.FAILED, error.code)
    assert job.next_attempt_at is None
    assert job.finished_at
    assert job.outcome is None
    assert job.receipt is None


def test_unexpected_errors_fail_the_job_without_details(member, caplog):
    job = run(submit(member), FakeFetcher(RuntimeError("boom at https://secret.example/x")))
    assert (job.status, job.last_error_code) == (Status.FAILED, "internal_error")
    assert "boom" not in job.last_error_message
    assert "unexpected error" in caplog.text


def test_the_retry_schedule_then_failure(member):
    job = submit(member)
    for attempt, wait in enumerate(SCHEDULE, start=1):
        job = run(job, FakeFetcher(ReceiptNotFound()))
        assert (job.status, job.attempt_count) == (Status.PENDING, attempt)
        delay = (job.next_attempt_at - timezone.now()).total_seconds()
        assert wait * 0.9 - 2 <= delay <= wait * 1.1
    job = run(job, FakeFetcher(ReceiptNotFound()))  # attempt 7: the schedule is used up
    assert (job.status, job.attempt_count) == (Status.FAILED, len(SCHEDULE) + 1)
    assert job.last_error_code == "receipt_not_found"


def test_a_retry_that_succeeds_clears_the_error(member):
    job = run(submit(member), FakeFetcher(ProviderTimeout()))
    job = run(job)
    assert (job.status, job.outcome, job.attempt_count) == (Status.COMPLETED, Outcome.CREATED, 2)
    assert job.error is None


def test_failure_during_persistence_leaves_nothing_behind(member, monkeypatch):
    """An exception after the receipt and its lines were written rolls everything back."""

    def fail(*args, **kwargs):
        assert ReceiptItem.objects.count() == 5  # written, not committed
        raise RuntimeError("injected")

    monkeypatch.setattr(pipeline, "complete", fail)
    job = run(submit(member))
    assert (job.status, job.last_error_code) == (Status.FAILED, "internal_error")
    for model in (Receipt, ReceiptItem, Merchant, Store):
        assert not model.objects.exists(), model


# --- deletion and re-import --------------------------------------------------------------
def test_deleted_receipt_is_imported_again_on_resubmission(member, enqueued):
    job = run(submit(member))
    delete_receipt(job.receipt)
    job.refresh_from_db()
    assert (job.status, job.outcome, job.receipt) == (
        Status.COMPLETED,
        Outcome.RECEIPT_DELETED,
        None,
    )
    assert not ReceiptItem.objects.exists()

    result = imports.submit_import(user=member.user, household=member.household, raw_url=IMPACT.url)
    assert (result.created, result.requeued, result.job.pk) == (False, True, job.pk)
    job = run(result.job)
    assert (job.outcome, job.attempt_count) == (Outcome.CREATED, 1)
    assert job.receipt.items.count() == 5


# --- tasks ----------------------------------------------------------------------------------
def test_run_due_imports_enqueues_due_pending_jobs(member, enqueued):
    now = timezone.now()
    due = ImportJobFactory(next_attempt_at=now - timedelta(seconds=5))
    ImportJobFactory(next_attempt_at=now + timedelta(minutes=5))  # leased or scheduled later
    ImportJobFactory(status=Status.FAILED, next_attempt_at=None)
    ImportJobFactory(
        status=Status.COMPLETED, outcome=Outcome.CREATED, next_attempt_at=now - timedelta(days=1)
    )
    assert tasks.run_due_imports() == 1
    assert enqueued == [str(due.pk)]


def test_process_import_task_runs_the_pipeline(member, use_fetcher):
    use_fetcher(IMPACT.fetcher())
    job = submit(member)
    tasks.process_import(str(job.pk))
    job.refresh_from_db()
    assert job.outcome == Outcome.CREATED


def test_beat_runs_due_imports_every_minute(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["run-due-imports"]
    assert (entry["task"], entry["schedule"]) == ("receipts.run_due_imports", 60.0)
    assert tasks.process_import.name.startswith("receipts.")  # routed to the imports queue


# --- persistence helpers --------------------------------------------------------------------
def test_payment_method_summary():
    from apps.receipts.canonical import Payment
    from apps.receipts.mydata import PaymentMethod

    def pay(method):
        return Payment(amount=Decimal("1"), method=method)

    assert persistence.payment_method(()) == "unknown"
    assert persistence.payment_method((pay(PaymentMethod.CARD),)) == "card"
    assert persistence.payment_method((pay(PaymentMethod.CARD), pay(PaymentMethod.CARD))) == "card"
    assert persistence.payment_method((pay(PaymentMethod.CARD), pay(PaymentMethod.CASH))) == "mixed"
    assert persistence.payment_method((pay(None),)) == "unknown"


def test_cancellation_and_document_number():
    from apps.receipts.canonical import Identity

    assert persistence.is_cancelled(Identity(cancellation_mark="400000000000001"))
    assert not persistence.is_cancelled(Identity(cancellation_mark="000"))
    assert not persistence.is_cancelled(Identity())


def test_cancelled_receipts_are_stored_as_cancelled(member, monkeypatch):
    import dataclasses

    real_values = persistence.receipt_values

    def cancelled(canonical, issues):
        identity = dataclasses.replace(canonical.identity, cancellation_mark="400099999999999")
        return real_values(dataclasses.replace(canonical, identity=identity), issues)

    monkeypatch.setattr(persistence, "receipt_values", cancelled)
    receipt = run(submit(member)).receipt
    assert receipt.status == Receipt.Status.CANCELLED
    assert receipt.cancellation_mark == "400099999999999"
