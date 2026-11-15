"""Admin pages for imports, receipts, merchants and stores (the interim operations UI)."""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.receipts.models import ReceiptImportJob
from tests.factories import ImportJobFactory
from tests.receipts.importing import run, submit

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x-Secret-123")
    client.force_login(admin)
    return client


def test_admin_pages_load_without_receipt_urls(admin_client, owner):
    job = run(submit(owner))
    receipt, item = job.receipt, job.receipt.items.first()
    urls = [
        reverse("admin:receipts_receiptimportjob_changelist"),
        reverse("admin:receipts_receiptimportjob_changelist")
        + "?status=failed&provider_code=impact",
        reverse("admin:receipts_receiptimportjob_change", args=[job.pk]),
        reverse("admin:receipts_receipt_changelist") + "?parser_version=impact/1",
        reverse("admin:receipts_receipt_change", args=[receipt.pk]),
        reverse("admin:receipts_receiptitem_changelist") + "?match_status=needs_review",
        reverse("admin:receipts_receiptitem_change", args=[item.pk]),
        reverse("admin:merchants_merchant_changelist") + "?q=094062259",
        reverse("admin:merchants_merchant_change", args=[receipt.merchant_id]),
        reverse("admin:merchants_store_changelist"),
        reverse("admin:merchants_store_change", args=[receipt.store_id]),
    ]
    for url in urls:
        response = admin_client.get(url)
        assert response.status_code == 200, url
        assert "/p/EL094062259/" not in response.content.decode(), url  # URLs are credentials


def test_retry_action(admin_client, owner, enqueued, django_capture_on_commit_callbacks):
    failed = ImportJobFactory(
        household=owner.household,
        status=ReceiptImportJob.Status.FAILED,
        last_error_code="provider_format_changed",
        next_attempt_at=None,
    )
    pending = ImportJobFactory(household=owner.household)
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(
            reverse("admin:receipts_receiptimportjob_changelist"),
            {"action": "retry_imports", "_selected_action": [failed.pk, pending.pk]},
            follow=True,
        )
    messages = [str(message) for message in response.context["messages"]]
    assert "Retried 1 import(s)." in messages
    assert "Skipped 1 import(s) that have not failed." in messages
    failed.refresh_from_db()
    assert failed.status == ReceiptImportJob.Status.PENDING
    assert enqueued == [str(failed.pk)]


def test_imports_and_receipts_cannot_be_added_by_hand(admin_client):
    for model in ("receiptimportjob", "receipt", "receiptitem"):
        assert admin_client.get(reverse(f"admin:receipts_{model}_add")).status_code == 403
