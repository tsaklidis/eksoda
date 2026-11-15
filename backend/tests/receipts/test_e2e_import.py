"""End-to-end acceptance (requirements §18, steps 1–7).

Everything is real except the network: the API enqueues the job after the commit,
the Celery task runs inline, and the fetcher serves the saved Impact sample.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from tests.receipts.importing import IMPACT

pytestmark = pytest.mark.django_db
IMPORT = reverse("api-v1:receipts-import")


def test_import_lifecycle(
    owner_client, use_fetcher, eager_tasks, django_capture_on_commit_callbacks
):
    fetcher = use_fetcher(IMPACT.fetcher())

    # 1. Submit the URL: a job is created and the API answers 202.
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(IMPORT, {"url": IMPACT.url}, format="json")
    assert response.status_code == 202
    import_id = response.json()["id"]

    # 2. The worker ran (inline): metadata, merchant, store, lines, totals, no warnings.
    job = owner_client.get(reverse("api-v1:receipt-imports-detail", kwargs={"pk": import_id}))
    job = job.json()
    assert (job["status"], job["outcome"], job["error"]) == ("completed", "created", None)
    receipt_url = reverse("api-v1:receipts-detail", kwargs={"pk": job["receipt_id"]})
    receipt = owner_client.get(receipt_url).json()
    assert receipt["merchant"]["vat_number"] == "094062259"
    assert receipt["store"]["branch_number"] == "264"
    assert len(receipt["items"]) == 5
    assert (receipt["net_total"], receipt["vat_total"], receipt["gross_total"]) == (
        "8.10",
        "1.05",
        "9.15",
    )
    assert receipt["validation_warnings"] == []
    assert fetcher.calls == ["einvoice.impact.gr"]

    # 3. Line types; all 5 lines matched to products; 5 normalized prices, two in kg.
    items = receipt["items"]
    assert {item["line_type"] for item in items} == {"product"}
    assert {item["match_status"] for item in items} == {"matched"}
    assert len({item["product"]["id"] for item in items}) == 5
    assert all(item["normalized_unit_price"] for item in items)
    assert [item["normalized_unit"] for item in items].count("kg") == 2
    assert receipt["needs_review"] is False

    # 4. Submit again: 200 duplicate, no new receipt, nothing fetched.
    with django_capture_on_commit_callbacks(execute=True):
        again = owner_client.post(IMPORT, {"url": IMPACT.url}, format="json")
    assert again.status_code == 200
    assert (again.json()["id"], again.json()["duplicate"]) == (import_id, True)
    assert Receipt.objects.count() == 1
    assert len(fetcher.calls) == 1

    # 5. Run the job again: nothing changes.
    from apps.receipts.tasks import process_import

    process_import.delay(import_id)
    assert Receipt.objects.count() == 1
    assert ReceiptItem.objects.count() == 5
    assert len(fetcher.calls) == 1

    # 6. Delete the receipt: its lines are gone, the job has outcome receipt_deleted.
    assert owner_client.delete(receipt_url).status_code == 204
    assert not ReceiptItem.objects.exists()
    stored_job = ReceiptImportJob.objects.get(pk=import_id)
    assert stored_job.outcome == ReceiptImportJob.Outcome.RECEIPT_DELETED

    # 7. Resubmit: the receipt is imported again.
    with django_capture_on_commit_callbacks(execute=True):
        resubmitted = owner_client.post(IMPORT, {"url": IMPACT.url}, format="json")
    assert resubmitted.status_code == 202
    assert resubmitted.json()["id"] == import_id
    stored_job.refresh_from_db()
    assert stored_job.outcome == ReceiptImportJob.Outcome.CREATED
    assert stored_job.receipt.items.count() == 5
    assert stored_job.receipt.gross_total == Decimal("9.15")
    assert len(fetcher.calls) == 2
