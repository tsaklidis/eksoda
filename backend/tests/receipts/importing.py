"""Helpers for import pipeline tests: fixture receipts served by a fake fetcher.

The pipeline runs for real (claim, provider fetch logic, parser, validation,
persistence); only the network is replaced.
"""

import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from apps.receipts.canonical import CanonicalReceipt, Party
from apps.receipts.fetching import FetchedDocument
from apps.receipts.models import Receipt, ReceiptImportJob
from apps.receipts.providers import registry
from apps.receipts.services import imports, pipeline
from apps.receipts.services.persistence import persist

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def page(provider: str, name: str) -> str:
    return (FIXTURES / provider / f"{name}.html").read_text(encoding="utf-8")


def url(provider: str, name: str) -> str:
    meta = json.loads((FIXTURES / provider / f"{name}.meta.json").read_text(encoding="utf-8"))
    return meta["url"]


def fetched(body: str, status: int = 200) -> FetchedDocument:
    return FetchedDocument(body.encode(), status)


class FakeFetcher:
    """Answers each GET with the next response (the last one repeats). A response that
    is an exception is raised instead."""

    def __init__(self, *responses: FetchedDocument | Exception):
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(self, url, *, allowed_hosts, accept_statuses=frozenset()):
        self.calls.append(url.host)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


@dataclass(frozen=True)
class Sample:
    """A fixture receipt: its URL and the pages its provider fetches, in order."""

    provider: str
    name: str
    pages: tuple[str, ...]

    @property
    def url(self) -> str:
        return url(self.provider, self.name)

    def fetcher(self) -> FakeFetcher:
        return FakeFetcher(*(fetched(body) for body in self.pages))


IMPACT = Sample("impact", "sample_el", (page("impact", "sample_el"),))
IMPACT_EN = Sample("impact", "sample_en", (page("impact", "sample_en"),))
LIDL = Sample(
    "entersoft", "lidl_21_lines", (page("entersoft", "shell"), page("entersoft", "lidl_21_lines"))
)
AADE = Sample("aade_fhm", "ab_ilion_2024", (page("aade_fhm", "ab_ilion_2024"),))


def submit(member, sample: Sample = IMPACT) -> ReceiptImportJob:
    return imports.submit_import(
        user=member.user, household=member.household, raw_url=sample.url
    ).job


def run(job: ReceiptImportJob, fetcher: FakeFetcher | None = None) -> ReceiptImportJob:
    """Run the job now (as the worker would once it is due) and reload it."""
    ReceiptImportJob.objects.filter(pk=job.pk).update(next_attempt_at=datetime.now(UTC))
    pipeline.process_import(job.pk, fetcher=fetcher or IMPACT.fetcher())
    job.refresh_from_db()
    return job


def parsed(sample: Sample = IMPACT) -> CanonicalReceipt:
    provider, identity = registry.resolve_url(sample.url)
    return provider.parse(fetched(sample.pages[-1]), identity)


def elsewhere(
    canonical: CanonicalReceipt,
    *,
    vat: str = "099999999",
    name: str = "ΑΛΛΟ ΚΑΤΑΣΤΗΜΑ ΑΕ",
    key: str = "2",
    prices: dict[int, str] | None = None,
) -> CanonicalReceipt:
    """The same purchase as another receipt, by default from another merchant (with the
    original VAT number: the same merchant), optionally with other line prices
    ({line number: gross})."""
    if vat == canonical.issuer.vat_number:
        name = canonical.issuer.legal_name
    lines = tuple(
        dataclasses.replace(line, gross=Decimal(prices[line.line_number]))
        if prices and line.line_number in prices
        else line
        for line in canonical.lines
    )
    identity = dataclasses.replace(canonical.identity, mark=f"9{key:0>14}", uid=f"UID{key}")
    issuer = Party(country_code="GR", vat_number=vat, legal_name=name)
    return dataclasses.replace(
        canonical, issuer=issuer, identity=identity, lines=lines, branch=None
    )


def store(member, canonical: CanonicalReceipt) -> Receipt:
    """Persist a canonical receipt for the member's household, as the pipeline does."""
    job = ReceiptImportJob.objects.create(
        household=member.household,
        requested_by=member.user,
        provider_code=canonical.provider_code,
        url_identity=f"test:{canonical.identity.mark}",
        submitted_url=canonical.source_url,
        url_fingerprint="0" * 64,
        next_attempt_at=datetime.now(UTC),
    )
    with transaction.atomic():
        receipt, _outcome = persist(job, canonical, [])
    return receipt
