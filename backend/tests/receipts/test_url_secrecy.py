"""Receipt URLs never reach the logs (requirements §15.3, TD §17).

The imports run through the API and the Celery task (inline) with the real logging
configuration; only the network is faked. What the ``stdout`` handler writes is
checked for the full URL and for every secret part of it.
"""

import io
import logging
from urllib.parse import urlsplit

import pytest
from django.urls import reverse

from apps.receipts.errors import ProviderUnreachable, UnsupportedProvider
from apps.receipts.models import ReceiptImportJob
from apps.receipts.services import imports
from tests.receipts.importing import AADE, IMPACT, LIDL, FakeFetcher, Sample, run, submit

pytestmark = pytest.mark.django_db
IMPORT = reverse("api-v1:receipts-import")


def secrets_of(url: str) -> list[str]:
    """The URL, its path and query, and each long token in them."""
    parts = urlsplit(url)
    tokens = [t for t in parts.path.split("/") + parts.query.split("=") if len(t) >= 16]
    return [s for s in (url, parts.path, parts.query, *tokens) if s]


@pytest.fixture
def log_output():
    """What the configured stdout handler writes, after its filters."""
    handler = next(h for h in logging.getLogger().handlers if h.get_name() == "stdout")
    stream = io.StringIO()
    previous = handler.setStream(stream)
    yield stream
    handler.setStream(previous)


def assert_no_secrets(text: str, sample: Sample) -> None:
    for secret in secrets_of(sample.url):
        assert secret not in text


@pytest.mark.parametrize("sample", [IMPACT, LIDL, AADE], ids=lambda s: s.provider)
def test_a_successful_import_logs_no_receipt_url(
    sample,
    owner_client,
    use_fetcher,
    eager_tasks,
    django_capture_on_commit_callbacks,
    log_output,
    caplog,
):
    use_fetcher(sample.fetcher())
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(IMPORT, {"url": sample.url}, format="json")
    assert response.status_code == 202
    assert ReceiptImportJob.objects.get().status == ReceiptImportJob.Status.COMPLETED

    output = log_output.getvalue()
    assert "receipt import submitted" in output
    assert "receipt imported" in output
    assert_no_secrets(output, sample)
    # The code itself logs hosts and fingerprints: the raw records (before the
    # redaction safety net) carry no URL either.
    assert_no_secrets(caplog.text, sample)


def test_failures_log_no_receipt_url(member, log_output):
    """Error details and tracebacks that quote the URL are redacted on the way out."""
    for error in (
        ProviderUnreachable(f"connection to {IMPACT.url} broke"),
        RuntimeError(f"unexpected trouble with {IMPACT.url}"),
    ):
        job = run(submit(member), FakeFetcher(error))
        assert job.last_error_code in ("provider_unreachable", "internal_error")
        ReceiptImportJob.objects.all().delete()

    output = log_output.getvalue()
    assert "receipt import attempt 1 failed" in output
    assert "unexpected error" in output
    assert "Traceback" in output
    assert_no_secrets(output, IMPACT)


def test_rejected_links_log_no_url(member, log_output):
    unsupported = "https://shop.example.com/receipt/" + "S" * 32
    with pytest.raises(UnsupportedProvider):
        imports.submit_import(user=member.user, household=member.household, raw_url=unsupported)
    output = log_output.getvalue()
    assert "host=shop.example.com" in output
    assert "S" * 32 not in output
