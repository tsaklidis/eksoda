"""Validation rules R4–R12 (requirements §10.2), using the real sample as the base."""

from dataclasses import replace
from decimal import Decimal

import pytest

from apps.receipts.canonical import Payment, VatEntry
from apps.receipts.validation import validate
from tests.receipts import impact


@pytest.fixture(scope="module")
def sample():
    return impact.parse(impact.read())


def codes(receipt):
    return [issue.code for issue in validate(receipt)]


def with_line(receipt, index=0, **changes):
    lines = list(receipt.lines)
    lines[index] = replace(lines[index], **changes)
    return replace(receipt, lines=tuple(lines))


def test_the_real_sample_is_clean(sample):
    assert validate(sample) == []


def test_r4_line_composition(sample):
    issues = validate(with_line(sample, gross=Decimal("4.50"), unit_price=None))
    assert "line_amount_mismatch" in [i.code for i in issues]
    issue = next(i for i in issues if i.code == "line_amount_mismatch")
    assert (issue.line_number, issue.expected, issue.actual) == (1, "4.48", "4.50")


def test_r4_includes_fees_and_withholdings(sample):
    receipt = with_line(sample, fees=Decimal("0.10"), withheld=Decimal("0.10"))
    assert "line_amount_mismatch" not in codes(receipt)


def test_r4_skips_lines_without_net_or_vat(sample):
    assert "line_amount_mismatch" not in codes(with_line(sample, net=None, gross=Decimal("9")))


def test_r5_unit_price(sample):
    assert "unit_price_mismatch" in codes(with_line(sample, unit_price=Decimal("7.50")))
    assert "unit_price_mismatch" not in codes(
        with_line(sample, unit_price=Decimal("7.50"), discount=Decimal("0.18"))
    )
    net_basis = with_line(sample, unit_price=Decimal("6.37"), unit_price_basis="net")
    assert "unit_price_mismatch" not in codes(net_basis)
    unknown = with_line(sample, unit_price=Decimal("99"), unit_price_basis="unknown")
    assert "unit_price_mismatch" not in codes(unknown)


def test_r6_vat_rate(sample):
    assert "vat_rate_mismatch" in codes(with_line(sample, vat_rate=Decimal("24")))


def test_r7_totals_match_lines(sample):
    receipt = replace(sample, totals=replace(sample.totals, net=Decimal("8.20")))
    assert codes(receipt).count("total_mismatch") == 1
    within_tolerance = replace(sample, totals=replace(sample.totals, net=Decimal("8.12")))
    assert "total_mismatch" not in codes(within_tolerance)


def test_r8_receipt_composition(sample):
    receipt = replace(sample, totals=replace(sample.totals, fees=Decimal("0.50")))
    assert "receipt_amount_mismatch" in codes(receipt)


def test_r9_vat_breakdown(sample):
    receipt = replace(sample, vat_breakdown=(VatEntry(net=Decimal("8.10"), vat=Decimal("0.99")),))
    assert codes(receipt) == ["vat_breakdown_mismatch"]


def test_r10_payments(sample):
    receipt = replace(sample, payments=(Payment(amount=Decimal("9.00")),))
    assert codes(receipt) == ["payment_mismatch"]
    assert "payment_mismatch" not in codes(replace(sample, payments=()))


def test_r11_mark(sample):
    missing = replace(sample, identity=replace(sample.identity, mark=None))
    assert codes(missing) == ["mark_missing"]
    excused = replace(
        sample, identity=replace(sample.identity, mark=None, transmission_failure=True)
    )
    assert codes(excused) == []


def test_r12_currency(sample):
    receipt = replace(sample, document=replace(sample.document, currency="USD"))
    assert codes(receipt) == ["non_eur_currency"]


def test_issue_serialization(sample):
    issue = validate(replace(sample, document=replace(sample.document, currency="USD")))[0]
    assert issue.to_dict() == {
        "code": "non_eur_currency",
        "message": "The receipt is not in EUR.",
        "line_number": None,
        "expected": "EUR",
        "actual": "USD",
    }


# --- rules added for sources with discounts, partial data or no lines (M2b) ---------
def test_r5_and_r13_use_the_value_before_discount(sample):
    discounted = with_line(
        sample,
        gross_before_discount=Decimal("4.48"),
        discount=Decimal("0.10"),
        gross=Decimal("4.38"),
        net=None,
        vat=None,
    )
    assert codes(discounted) == ["total_mismatch"]  # only R7 gross: lines no longer add up
    wrong = with_line(
        sample, gross_before_discount=Decimal("4.50"), discount=Decimal("0.02"), net=None, vat=None
    )
    assert set(codes(wrong)) == {"unit_price_mismatch"}
    bad_discount = with_line(
        sample, gross_before_discount=Decimal("4.48"), discount=Decimal("0.10")
    )
    assert "discount_mismatch" in codes(bad_discount)


def test_r7_ignores_values_missing_on_some_lines(sample):
    receipt = with_line(sample, net=None, vat=None)
    assert "total_mismatch" not in codes(receipt)


def test_summary_only_receipts(sample):
    from apps.receipts.canonical import Coverage

    summary = replace(
        sample, lines=(), coverage=Coverage(line_items=False, mydata_registered=False)
    )
    summary = replace(summary, identity=replace(summary.identity, mark=None))
    assert codes(summary) == []


def test_r14_breakdown_rates(sample):
    entry = VatEntry(net=Decimal("8.10"), vat=Decimal("1.05"), rate=Decimal("24"))
    assert "vat_breakdown_rate_mismatch" in codes(replace(sample, vat_breakdown=(entry,)))


def test_r15_unknown_document_kind(sample):
    from apps.receipts.mydata import DocumentKind

    receipt = replace(sample, document=replace(sample.document, kind=DocumentKind.OTHER))
    assert codes(receipt) == ["unknown_document_type"]


def test_r16_total_discount(sample):
    totals = replace(
        sample.totals, gross_before_discount=Decimal("10.00"), discount=Decimal("0.50")
    )
    assert codes(replace(sample, totals=totals)) == ["total_discount_mismatch"]


def test_provider_notices_become_warnings(sample):
    from apps.receipts.canonical import Notice

    receipt = replace(sample, notices=(Notice("signature_mismatch", "QR differs."),))
    assert validate(receipt)[-1].to_dict()["code"] == "signature_mismatch"


def test_r9_checks_net_too(sample):
    entry = VatEntry(net=Decimal("8.00"), vat=Decimal("1.05"))
    assert codes(replace(sample, vat_breakdown=(entry,))) == ["vat_breakdown_mismatch"]
