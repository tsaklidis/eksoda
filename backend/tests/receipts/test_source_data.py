"""What is stored from a receipt page (requirements §15.3): an allowlist, no values of
unknown fields, nothing shaped like a card number."""

import dataclasses

import pytest

from apps.receipts.services.persistence import drop_card_numbers, source_data
from tests.receipts.importing import IMPACT, parsed


def test_unknown_fields_are_stored_by_name_only():
    canonical = dataclasses.replace(
        parsed(IMPACT),
        unknown_fields={"commercial.payment.TerminalId": "T-99812", "remark.Κάρτα μέλους:": "77"},
    )
    data = source_data(canonical)
    assert data["unknown_fields"] == {
        "commercial.payment.TerminalId": "",
        "remark.Κάρτα μέλους:": "",
    }
    assert "T-99812" not in str(data)


def test_card_numbers_are_dropped_from_payment_labels():
    canonical = parsed(IMPACT)
    payment = dataclasses.replace(canonical.payments[0], method_label="VISA 4111 1111 1111 1111")
    data = source_data(dataclasses.replace(canonical, payments=(payment,)))
    assert data["payments"][0]["method_label"] == "VISA <card>"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4111111111111111", "<card>"),
        ("5500-0000-0000-0004 ok", "<card> ok"),
        ("4111111111111112", "4111111111111112"),  # fails the Luhn check
        ("MARK 400015963897868", "MARK 400015963897868"),
        ("****1111", "****1111"),
        ("VISA", "VISA"),
    ],
)
def test_drop_card_numbers(text, expected):
    assert drop_card_numbers(text) == expected


def test_the_impact_payload_keeps_only_known_fields():
    commercial = parsed(IMPACT).provider_payload["commercial"]
    assert "misc" not in commercial
    assert set(commercial["identity"]) == {
        "DateIssued",
        "InvoiceType",
        "IssuerFormatedInvoiceSeriesNumber",
    }
