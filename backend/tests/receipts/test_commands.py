"""parse_receipt and sanitize_fixture. No django_db marker: any DB access fails."""

import io
import json

import pytest
from django.core.management import CommandError, call_command

from apps.receipts.fetching import FetchedDocument
from apps.receipts.management.commands import parse_receipt as parse_command
from apps.receipts.providers.sanitizing import SanitizeError
from tests.receipts import impact

FIXTURES = impact.FIXTURES.parent
SAMPLE = str(impact.FIXTURES / "sample_el.html")


def run(*args) -> str:
    out = io.StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


def test_parse_saved_page_summary():
    output = run("parse_receipt", SAMPLE)
    assert "Merchant:  METRO" in output
    assert "Lines (5):" in output
    assert "Validation: no warnings" in output
    assert "0" * 32 not in output  # access token masked
    assert "/********" in output


def test_parse_saved_page_json():
    data = json.loads(run("parse_receipt", SAMPLE, "--json"))
    assert data["validation"] == []
    assert data["receipt"]["totals"]["gross"] == "9.15"
    assert data["receipt"]["source_url"].endswith("/********")


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("entersoft/lidl_21_lines.html", "Lines (21):"),
        ("aade_fhm/ab_ilion_2024.html", "Payment:   cash 34.93 (derived)"),
        ("aade_fhm/signature_mismatch.html", "signature_mismatch"),
    ],
)
def test_parse_uses_the_meta_file_url(fixture, expected):
    output = run("parse_receipt", str(FIXTURES / fixture))
    assert expected in output
    assert "?********" in output or "/********" in output


def test_parse_url_uses_the_safe_fetcher(monkeypatch):
    class FakeFetcher:
        def get(self, url, *, allowed_hosts, accept_statuses=frozenset()):
            return FetchedDocument(impact.read().encode())

    monkeypatch.setattr(parse_command, "default_fetcher", FakeFetcher)
    assert "Lines (5):" in run("parse_receipt", impact.SAMPLE_URL)


def test_parse_reports_receipt_errors():
    with pytest.raises(CommandError, match="receipt_not_found"):
        run("parse_receipt", str(impact.FIXTURES / "not_found.html"), "--url", impact.SAMPLE_URL)
    with pytest.raises(CommandError, match="unsupported_provider"):
        run("parse_receipt", "https://example.com/receipt")


def test_parse_finds_a_receipt_link_on_the_page(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '<a href="https://example.com/x">x</a>'
        + impact.read().replace(impact.SAMPLE_URL, impact.SAMPLE_URL),
        encoding="utf-8",
    )
    assert "Lines (5):" in run("parse_receipt", str(page))


def test_parse_input_errors(tmp_path):
    with pytest.raises(CommandError, match="cannot read"):
        run("parse_receipt", str(tmp_path / "missing.html"))
    page_without_url = tmp_path / "page.html"
    page_without_url.write_text(
        "<html><a href='https://example.com/a'>a</a></html>", encoding="utf-8"
    )
    with pytest.raises(CommandError, match="--url"):
        run("parse_receipt", str(page_without_url))


def test_parse_summary_lists_warnings_and_drift(tmp_path):
    soup = impact.page()
    impact.set_field(soup, "UnitPrice", "7,50")  # unit price no longer matches the total
    soup.select_one(".section-identity .field").append(
        soup.new_tag("span", attrs={"class": "field field-NewThing"})
    )
    soup.select_one(".field-NewThing").append(soup.new_tag("span", attrs={"class": "value"}))
    soup.select_one(".field-NewThing .value").string = "new"
    page = tmp_path / "page.html"
    page.write_text(str(soup), encoding="utf-8")
    output = run("parse_receipt", str(page), "--url", impact.SAMPLE_URL)
    assert "unit_price_mismatch" in output
    assert "commercial.identity.NewThing" in output


def test_sanitize_command(tmp_path):
    target = tmp_path / "out" / "fixture.html"
    output = run("sanitize_fixture", "impact", SAMPLE, str(target))
    assert "Wrote" in output
    assert "meta.json" in output
    assert target.exists()
    with pytest.raises(CommandError, match="exists"):
        run("sanitize_fixture", "impact", SAMPLE, str(target))
    run("sanitize_fixture", "impact", SAMPLE, str(target), "--force")
    with pytest.raises(CommandError, match="cannot read"):
        run("sanitize_fixture", "impact", str(tmp_path / "missing.html"), str(tmp_path / "x.html"))
    with pytest.raises(CommandError, match="unknown provider"):
        run("sanitize_fixture", "nope", SAMPLE, str(tmp_path / "x.html"))


def test_sanitize_command_refuses_leaks(tmp_path, monkeypatch):
    from apps.receipts.providers import registry

    def leaking(_html):
        raise SanitizeError("values still present after sanitizing: counterparty")

    monkeypatch.setattr(registry.get("impact"), "sanitize", leaking)
    with pytest.raises(CommandError, match="refusing"):
        run("sanitize_fixture", "impact", SAMPLE, str(tmp_path / "x.html"))


@pytest.mark.django_db
def test_seed_demo_data(owner, settings):

    from apps.analytics import queries
    from apps.analytics.periods import Period
    from apps.receipts.models import Receipt

    with pytest.raises(CommandError, match="--force"):
        call_command("seed_demo_data", household=str(owner.household_id), receipts=5)
    out = io.StringIO()
    call_command(
        "seed_demo_data", household=str(owner.household_id), receipts=40, force=True, stdout=out
    )
    assert "Created 40 demo receipt(s)" in out.getvalue()
    assert Receipt.objects.filter(household=owner.household).count() == 40
    # The same seed again adds nothing.
    call_command("seed_demo_data", household=str(owner.household_id), receipts=40, force=True)
    assert Receipt.objects.filter(household=owner.household).count() == 40

    receipts = Receipt.objects.filter(household=owner.household)
    first = receipts.order_by("issued_at").first().issued_at.date()
    last = receipts.order_by("issued_at").last().issued_at.date()
    period = Period(first, last)
    breakdown = queries.spending_by_category(owner.household, period)
    assert sum(bucket.total for bucket in breakdown.buckets) == breakdown.spending
    with pytest.raises(CommandError, match="No household"):
        call_command("seed_demo_data", household="00000000-0000-0000-0000-000000000000", force=True)
