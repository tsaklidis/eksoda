"""Opt-in tests against the real sources: `make test-live URLS="<url> <url> ..."`.

Exercises real DNS validation, IP pinning, TLS verification and today's page
formats, for any registered provider, and the whole import (API → worker → stored
receipt) against the test database. Skipped unless RUN_LIVE_TESTS=1 and
LIVE_RECEIPT_URLS (space-separated) is set. Test ids show only the index.
"""

import os

import pytest
from django.urls import reverse

from apps.receipts.conf import default_fetcher
from apps.receipts.models import ReceiptImportJob
from apps.receipts.providers import registry
from apps.receipts.services import pipeline
from apps.receipts.validation import validate

URLS = os.environ.get("LIVE_RECEIPT_URLS", "").split()


@pytest.mark.live
@pytest.mark.parametrize("index", range(len(URLS)) or [None])
def test_live_receipt(index):
    if index is None:
        pytest.skip("LIVE_RECEIPT_URLS is not set")
    provider, identity = registry.resolve_url(URLS[index])
    document = provider.fetch(identity, default_fetcher())
    receipt = provider.parse(document, identity)
    assert receipt.totals.gross > 0
    assert receipt.lines or not receipt.coverage.line_items
    assert [issue.code for issue in validate(receipt)] == [], provider.code


@pytest.mark.live
@pytest.mark.django_db
@pytest.mark.parametrize("index", range(len(URLS)) or [None])
def test_live_import_through_the_api(index, owner_client, enqueued):
    """M3 exit: a real URL submitted through the API becomes a stored receipt."""
    if index is None:
        pytest.skip("LIVE_RECEIPT_URLS is not set")
    response = owner_client.post(reverse("api-v1:receipts-import"), {"url": URLS[index]})
    assert response.status_code == 202
    pipeline.process_import(response.json()["id"])  # the worker's step, with the real fetcher

    job = ReceiptImportJob.objects.get(pk=response.json()["id"])
    assert (job.status, job.outcome, job.last_error_code) == ("completed", "created", "")
    detail = owner_client.get(reverse("api-v1:receipts-detail", kwargs={"pk": job.receipt_id}))
    assert detail.status_code == 200
    assert detail.json()["validation_warnings"] == []
