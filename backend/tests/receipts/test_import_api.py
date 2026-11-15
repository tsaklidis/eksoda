"""Import endpoints: every response case of requirements §6.2 and §12.4."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.receipts.api.views import ImportDayThrottle, ImportMinuteThrottle
from apps.receipts.models import ReceiptImportJob
from tests.factories import ImportJobFactory, MemberFactory
from tests.receipts import impact
from tests.receipts.importing import IMPACT, LIDL, run, submit
from tests.utils import client_for, error_code

pytestmark = pytest.mark.django_db
IMPORT = reverse("api-v1:receipts-import")
JOBS = reverse("api-v1:receipt-imports-list")
Status = ReceiptImportJob.Status
Outcome = ReceiptImportJob.Outcome


def job_url(job) -> str:
    return reverse("api-v1:receipt-imports-detail", kwargs={"pk": job.pk})


def retry_url(job) -> str:
    return reverse("api-v1:receipt-imports-retry", kwargs={"pk": job.pk})


def post_import(client, url, **extra):
    return client.post(IMPORT, {"url": url}, format="json", **extra)


# --- submission ---------------------------------------------------------------------
def test_new_receipt_link_is_accepted_and_enqueued(
    owner, owner_client, enqueued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = post_import(owner_client, IMPACT.url)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert (body["duplicate"], body["receipt_id"], body["outcome"]) == (False, None, None)
    assert body["provider_code"] == "impact"
    assert body["source_host"] == "einvoice.impact.gr"
    assert body["issuer_vat"] == "094062259"  # known from the Impact URL
    assert (body["attempt_count"], body["next_attempt_at"], body["error"]) == (0, None, None)
    assert "/p/EL094062259/" not in response.content.decode()  # never the URL
    assert len(callbacks) == 1
    assert enqueued == [body["id"]]
    job = ReceiptImportJob.objects.get(pk=body["id"])
    assert (job.household, job.requested_by) == (owner.household, owner.user)
    assert job.submitted_url == IMPACT.url


def test_issuer_vat_is_null_until_known(owner_client, enqueued):
    body = post_import(owner_client, LIDL.url).json()
    assert body["issuer_vat"] is None


def test_same_link_again_returns_the_existing_import(
    owner_client, enqueued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        first = post_import(owner_client, IMPACT.url).json()
    lower_hex = IMPACT.url.replace(impact.UID, impact.UID.lower())  # same canonical identity
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = post_import(owner_client, lower_hex)
    assert callbacks == []
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert response.json()["duplicate"] is True
    assert enqueued == [first["id"]]  # not enqueued twice
    assert ReceiptImportJob.objects.count() == 1


def test_completed_import_is_returned_as_a_duplicate(owner, owner_client, enqueued):
    job = run(submit(owner))
    response = post_import(owner_client, IMPACT.url)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["outcome"], body["receipt_id"]) == (
        "completed",
        "created",
        str(job.receipt_id),
    )


@pytest.mark.parametrize(
    "state",
    [
        {"status": Status.FAILED, "last_error_code": "provider_format_changed"},
        {"status": Status.COMPLETED, "outcome": Outcome.RECEIPT_DELETED},
    ],
)
def test_failed_or_deleted_import_starts_again(
    owner, owner_client, enqueued, state, django_capture_on_commit_callbacks
):
    job = submit(owner)
    ReceiptImportJob.objects.filter(pk=job.pk).update(
        attempt_count=7, next_attempt_at=None, finished_at=timezone.now(), **state
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = post_import(owner_client, IMPACT.url)
    assert response.status_code == 202
    body = response.json()
    assert (body["id"], body["status"], body["duplicate"]) == (str(job.pk), "pending", True)
    assert (body["attempt_count"], body["error"], body["outcome"]) == (0, None, None)
    job.refresh_from_db()
    assert job.finished_at is None
    assert job.next_attempt_at is not None
    assert enqueued == [str(job.pk)]


def test_households_import_the_same_link_independently(owner_client, outsider_client, enqueued):
    first = post_import(owner_client, IMPACT.url)
    second = post_import(outsider_client, IMPACT.url)
    assert (first.status_code, second.status_code) == (202, 202)
    assert first.json()["id"] != second.json()["id"]
    assert second.json()["duplicate"] is False  # nothing reveals the other household


@pytest.mark.parametrize(
    ("url", "status", "code"),
    [
        ("http://einvoice.impact.gr/p/EL094062259/X/Y", 400, "invalid_url"),
        ("https://user@einvoice.impact.gr/p/EL1/A/B", 400, "invalid_url"),
        ("https://einvoice.impact.gr:8443/p/EL1/A/B", 400, "invalid_url"),
        (IMPACT.url + "#fragment", 400, "invalid_url"),
        ("https://" + "a" * 2050 + ".gr/", 400, "invalid_url"),
        ("not a url", 400, "invalid_url"),
        (12345, 400, "invalid_url"),
        ("https://shop.example.com/receipt/1", 422, "unsupported_provider"),
        ("https://einvoice.impact.gr/unknown/path", 422, "unsupported_url_format"),
    ],
)
def test_rejected_links(owner_client, url, status, code, caplog):
    response = post_import(owner_client, url)
    assert response.status_code == status
    assert error_code(response) == code
    assert not ReceiptImportJob.objects.exists()
    assert "/receipt/1" not in caplog.text  # unsupported hosts are logged by host only


def test_unsupported_host_is_logged_by_host(owner_client, caplog):
    post_import(owner_client, "https://shop.example.com/receipt/1")
    assert "host=shop.example.com" in caplog.text


@pytest.mark.parametrize(
    ("body", "content_type", "code"),
    [
        ("{not json", "application/json", "invalid_request"),
        ('{"url": "' + "x" * 5000 + '"}', "application/json", "invalid_request"),  # > 4 KB
        ('{"url": "' + "x" * 20000 + '"}', "application/json", "invalid_request"),  # > 16 KB
        ("{}", "application/json", "validation_error"),
        ("url=x", "application/x-www-form-urlencoded", "unsupported_media_type"),
    ],
)
def test_malformed_requests(owner_client, body, content_type, code):
    response = owner_client.generic("POST", IMPORT, body, content_type=content_type)
    assert response.status_code in (400, 415)
    assert error_code(response) == code


def test_authentication_and_household_selection(owner, api_client):
    assert post_import(api_client, IMPACT.url).status_code == 401
    MemberFactory(user=owner.user)  # a second household
    response = post_import(client_for(owner.user), IMPACT.url)
    assert (response.status_code, error_code(response)) == (400, "household_required")


@pytest.mark.parametrize("throttle", [ImportMinuteThrottle, ImportDayThrottle])
def test_imports_are_rate_limited(owner_client, enqueued, monkeypatch, throttle):
    monkeypatch.setattr(
        throttle,
        "THROTTLE_RATES",
        {throttle.scope: "2/min"}
        | {
            other.scope: "100/min"
            for other in (ImportMinuteThrottle, ImportDayThrottle)
            if other is not throttle
        },
    )
    for _ in range(2):
        assert post_import(owner_client, IMPACT.url).status_code in (200, 202)
    response = post_import(owner_client, IMPACT.url)
    assert response.status_code == 429
    assert error_code(response) == "rate_limited"
    assert "Retry-After" in response


def test_retries_count_against_the_import_limits(owner, owner_client, enqueued, monkeypatch):
    monkeypatch.setattr(
        ImportMinuteThrottle, "THROTTLE_RATES", {"import_minute": "1/min", "import_day": "100/min"}
    )
    job = ImportJobFactory(household=owner.household, status=Status.FAILED, next_attempt_at=None)
    assert owner_client.post(retry_url(job)).status_code == 202
    ReceiptImportJob.objects.filter(pk=job.pk).update(status=Status.FAILED)
    response = owner_client.post(retry_url(job))
    assert (response.status_code, error_code(response)) == (429, "rate_limited")


# --- listing and detail ---------------------------------------------------------------
def test_list_and_filter_imports(owner, owner_client):
    pending = ImportJobFactory(household=owner.household)
    failed = ImportJobFactory(
        household=owner.household,
        status=Status.FAILED,
        last_error_code="provider_format_changed",
        last_error_message="The receipt page format is not recognized.",
        next_attempt_at=None,
    )
    ReceiptImportJob.objects.filter(pk=pending.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )

    body = owner_client.get(JOBS).json()
    assert [row["id"] for row in body["results"]] == [str(failed.pk), str(pending.pk)]
    assert "submitted_url" not in body["results"][0]
    assert body["results"][0]["error"] == {
        "code": "provider_format_changed",
        "message": "The receipt page format is not recognized.",
    }
    rows = owner_client.get(JOBS, {"status": "failed"}).json()["results"]
    assert [row["id"] for row in rows] == [str(failed.pk)]
    today = timezone.localdate().isoformat()
    rows = owner_client.get(JOBS, {"created_from": today}).json()["results"]
    assert [row["id"] for row in rows] == [str(failed.pk)]
    rows = owner_client.get(JOBS, {"created_to": today}).json()["results"]
    assert len(rows) == 2
    two_days_ago = (timezone.localdate() - timedelta(days=2)).isoformat()
    rows = owner_client.get(JOBS, {"created_to": two_days_ago}).json()["results"]
    assert [row["id"] for row in rows] == [str(pending.pk)]
    response = owner_client.get(JOBS, {"status": "nope"})
    assert response.status_code == 400


def test_detail_shows_a_scheduled_retry(owner, owner_client):
    from apps.receipts.errors import ProviderTimeout
    from tests.receipts.importing import FakeFetcher

    job = run(submit(owner), FakeFetcher(ProviderTimeout()))
    body = owner_client.get(job_url(job)).json()
    assert body["status"] == "pending"
    assert body["error"]["code"] == "provider_timeout"
    assert body["next_attempt_at"] is not None
    assert body["attempt_count"] == 1


def test_list_query_count(owner, owner_client, django_assert_max_num_queries):
    for _ in range(5):
        ImportJobFactory(household=owner.household)
    with django_assert_max_num_queries(6):
        assert owner_client.get(JOBS).json()["count"] == 5


# --- retry -----------------------------------------------------------------------------
def test_retry_a_failed_import(owner, owner_client, enqueued, django_capture_on_commit_callbacks):
    job = ImportJobFactory(
        household=owner.household,
        status=Status.FAILED,
        attempt_count=7,
        last_error_code="receipt_not_found",
        next_attempt_at=None,
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(retry_url(job))
    assert response.status_code == 202
    body = response.json()
    assert (body["status"], body["attempt_count"], body["error"]) == ("pending", 0, None)
    assert enqueued == [str(job.pk)]


@pytest.mark.parametrize(
    "state",
    [
        {"status": Status.PENDING},
        {"status": Status.COMPLETED, "outcome": Outcome.CREATED},
        {"status": Status.COMPLETED, "outcome": Outcome.RECEIPT_DELETED},
    ],
)
def test_only_failed_imports_can_be_retried(owner, member_client, enqueued, state):
    job = ImportJobFactory(household=owner.household, **state)
    response = member_client.post(retry_url(job))
    assert (response.status_code, error_code(response)) == (409, "not_retryable")
    assert enqueued == []
