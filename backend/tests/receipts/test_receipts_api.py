"""Receipt endpoints: list, detail, edit, delete (requirements §12.5, D10)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from tests.factories import ReceiptFactory, ReceiptItemFactory, StoreFactory
from tests.receipts.importing import AADE, run, submit
from tests.utils import error_code

pytestmark = pytest.mark.django_db
RECEIPTS = reverse("api-v1:receipts-list")


def detail_url(receipt) -> str:
    return reverse("api-v1:receipts-detail", kwargs={"pk": receipt.pk})


@pytest.fixture
def imported(owner) -> Receipt:
    return run(submit(owner)).receipt


def test_list_receipts(owner, owner_client):
    now = timezone.now()
    older = ReceiptFactory(household=owner.household, issued_at=now - timedelta(days=2))
    newer = ReceiptFactory(
        household=owner.household, issued_at=now, gross_total=Decimal("3.00"), store=StoreFactory()
    )
    ReceiptItemFactory(receipt=newer)
    ReceiptItemFactory(receipt=newer, line_type=ReceiptItem.LineType.FEE)
    ReceiptItemFactory(receipt=older, line_type=ReceiptItem.LineType.DISCOUNT)

    body = owner_client.get(RECEIPTS).json()
    assert body["count"] == 2
    first, second = body["results"]
    assert [first["id"], second["id"]] == [str(newer.pk), str(older.pk)]  # newest first
    assert first["merchant"] == {
        "id": str(newer.merchant_id),
        "display_name": newer.merchant.display_name,
        "vat_number": newer.merchant.vat_number,
    }
    assert first["store"]["name"] == newer.store.label
    assert second["store"] is None
    assert (first["item_count"], first["needs_review"]) == (2, True)
    assert (second["item_count"], second["needs_review"]) == (1, False)
    assert first["gross_total"] == "3.00"  # amounts are strings
    assert first["currency"] == "EUR"
    assert first["has_warnings"] is False
    assert "source_url" not in first
    assert "items" not in first

    ordered = owner_client.get(RECEIPTS, {"ordering": "gross_total"}).json()["results"]
    assert [row["id"] for row in ordered] == [str(newer.pk), str(older.pk)]


def test_list_query_count(owner, owner_client, django_assert_max_num_queries):
    for _ in range(5):
        ReceiptItemFactory(receipt=ReceiptFactory(household=owner.household, store=StoreFactory()))
    with django_assert_max_num_queries(6):
        assert owner_client.get(RECEIPTS).json()["count"] == 5


def test_receipt_detail(owner_client, imported, django_assert_max_num_queries):
    with django_assert_max_num_queries(7):
        body = owner_client.get(detail_url(imported)).json()

    assert body["id"] == str(imported.pk)
    assert body["issued_at"] == "2026-11-07T18:28:00+02:00"  # household timezone
    assert body["document_number"] == "7222-546093"
    assert (body["mark"], body["uid"]) == (imported.mark, imported.uid)
    assert body["parser_version"] == "impact/1"
    assert body["source_url"] == imported.source_url  # only here, for household members
    assert body["validation_warnings"] == []
    assert body["coverage"]["line_items"] is True
    assert body["payments"] == [
        {"amount": "9.15", "method": "card", "method_label": "VISA", "derived": False}
    ]
    assert {entry["rate"] for entry in body["vat_breakdown"]} >= {"13.00"}
    assert [item["line_number"] for item in body["items"]] == [1, 2, 3, 4, 5]
    first = body["items"][0]
    assert (first["quantity"], first["unit"], first["unit_price"]) == ("0.6220", "kg", "7.2100")
    assert (first["gross_amount"], first["vat_rate"]) == ("4.48", "13.00")
    assert (first["line_type"], first["match_status"]) == ("product", "matched")
    assert first["product"]["name"] == "ADORO LIGHT 10% ΦΡΑΤΖ. ΓΕΡΜΑΝΙΑΣ(Τ.ΚΙΛΟΥ"
    assert (first["normalized_unit"], first["normalized_unit_price"]) == ("kg", "7.2026")
    assert body["needs_review"] is False


def test_summary_receipt_detail(owner, owner_client):
    receipt = run(submit(owner, AADE), AADE.fetcher()).receipt
    body = owner_client.get(detail_url(receipt)).json()
    assert body["items"] == []
    assert body["coverage"]["line_items"] is False
    assert body["payments"][0]["derived"] is True
    assert (body["item_count"], body["needs_review"]) == (0, False)


def test_detail_shows_validation_warnings(owner, owner_client):
    warning = {
        "code": "totals_mismatch",
        "message": "Line totals differ from the receipt total.",
        "line_number": None,
        "expected": "9.15",
        "actual": "9.10",
    }
    receipt = ReceiptFactory(household=owner.household, validation_warnings=[warning])
    body = owner_client.get(detail_url(receipt)).json()
    assert body["validation_warnings"] == [warning]
    assert body["has_warnings"] is True
    assert body["coverage"] is None  # no source data (not imported)
    assert (body["payments"], body["vat_breakdown"]) == ([], [])


def test_edit_user_fields(owner_client, imported):
    store = StoreFactory(merchant=imported.merchant)
    response = owner_client.patch(
        detail_url(imported),
        {
            "user_note": "Weekly shopping",
            "excluded_from_analytics": True,
            "store_id": str(store.pk),
            "gross_total": "1.00",  # source values are read-only: ignored
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["user_note"], body["excluded_from_analytics"]) == ("Weekly shopping", True)
    assert body["store"]["id"] == str(store.pk)
    assert body["gross_total"] == "9.15"
    imported.refresh_from_db()
    assert imported.gross_total == Decimal("9.15")
    assert imported.store == store

    response = owner_client.patch(detail_url(imported), {"store_id": None}, format="json")
    assert response.json()["store"] is None


def test_store_must_belong_to_the_receipt_merchant(owner_client, imported):
    response = owner_client.patch(
        detail_url(imported), {"store_id": str(StoreFactory().pk)}, format="json"
    )
    assert (response.status_code, error_code(response)) == (400, "validation_error")
    assert "store_id" in response.json()["error"]["details"]


def test_members_can_edit_and_delete(member_client, imported):
    response = member_client.patch(detail_url(imported), {"user_note": "x"}, format="json")
    assert response.status_code == 200
    assert member_client.delete(detail_url(imported)).status_code == 204


def test_delete_receipt(owner_client, imported):
    job = imported.import_jobs.get()
    response = owner_client.delete(detail_url(imported))
    assert response.status_code == 204
    assert not Receipt.objects.exists()
    assert not ReceiptItem.objects.exists()
    job.refresh_from_db()
    assert (job.outcome, job.receipt) == (ReceiptImportJob.Outcome.RECEIPT_DELETED, None)
    assert owner_client.get(detail_url(imported)).status_code == 404


def test_put_is_not_allowed_and_auth_is_required(owner_client, api_client, imported):
    assert owner_client.put(detail_url(imported), {}, format="json").status_code == 405
    assert api_client.get(RECEIPTS).status_code == 401


def test_update_service_rejects_source_fields_and_foreign_stores(imported):
    from apps.receipts.services.receipts import update_receipt

    with pytest.raises(ValueError, match="not editable"):
        update_receipt(imported, gross_total=Decimal("1"))
    with pytest.raises(ValueError, match="another merchant"):
        update_receipt(imported, store=StoreFactory())
