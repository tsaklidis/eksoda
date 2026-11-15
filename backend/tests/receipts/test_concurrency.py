"""Concurrent submissions and imports never create duplicates (requirements §6.3).

These tests use real transactions in two threads (each with its own connection), so
the unique constraints decide the race exactly as in production.
"""

import threading

import pytest
from django.db import connection

from apps.products.models import MerchantProductMapping, Product
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.services import imports, pipeline
from tests.factories import ImportJobFactory, MemberFactory
from tests.receipts.importing import IMPACT, elsewhere, parsed, store

pytestmark = pytest.mark.django_db(transaction=True)


def in_parallel(*calls):
    """Run the calls at the same moment in separate threads; return their results."""
    barrier = threading.Barrier(len(calls))
    results, errors = [None] * len(calls), []

    def worker(index, call):
        try:
            barrier.wait(timeout=10)
            results[index] = call()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=item) for item in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors
    return results


def test_concurrent_submissions_create_one_job(enqueued):
    member = MemberFactory()

    def submit():
        return imports.submit_import(
            user=member.user, household=member.household, raw_url=IMPACT.url
        )

    results = in_parallel(submit, submit)
    assert ReceiptImportJob.objects.count() == 1
    assert sorted(result.created for result in results) == [False, True]
    assert len({result.job.pk for result in results}) == 1
    assert len(enqueued) == 1


def test_concurrent_imports_of_one_receipt_store_it_once():
    member = MemberFactory()
    jobs = [
        ImportJobFactory(household=member.household, submitted_url=IMPACT.url) for _ in range(2)
    ]

    def process(job):
        return lambda: pipeline.process_import(job.pk, fetcher=IMPACT.fetcher())

    in_parallel(*(process(job) for job in jobs))
    assert Receipt.objects.count() == 1
    outcomes = sorted(ReceiptImportJob.objects.values_list("outcome", flat=True))
    assert outcomes == ["created", "duplicate"]
    assert {job.receipt_id for job in ReceiptImportJob.objects.all()} == {Receipt.objects.get().pk}


def test_concurrent_imports_of_a_new_item_create_one_product():
    """Two different receipts with the same new items, stored at the same moment."""
    member = MemberFactory()
    first, second = parsed(), elsewhere(parsed(), vat=parsed().issuer.vat_number, key="7")
    in_parallel(lambda: store(member, first), lambda: store(member, second))
    assert Receipt.objects.count() == 2
    assert Product.objects.count() == 5
    assert MerchantProductMapping.objects.count() == 5
    by_line = {}
    for item in ReceiptItem.objects.all():
        by_line.setdefault(item.line_number, set()).add(item.product_id)
    assert all(len(products) == 1 for products in by_line.values())
