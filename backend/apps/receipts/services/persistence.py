"""Canonical receipt → merchant, store, receipt and lines (requirements §6.6, TD §12.5).

Runs inside the pipeline's transaction, so a failure leaves nothing behind. The
identity constraints on Receipt are the final guard against a second copy: a
concurrent import of the same receipt makes this one a ``duplicate``.

Lines are classified, product lines matched to household products (creating new
ones for new items), and normalized prices computed before the lines are written.
"""

import re
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.common.text import fingerprint, normalize_text
from apps.merchants.services import resolve_merchant, resolve_store
from apps.products.matching import match_items
from apps.products.prices import apply_prices
from apps.receipts.canonical import CanonicalReceipt, Document, Identity, Payment
from apps.receipts.classification import LineType, classify
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.validation import ValidationIssue

Outcome = ReceiptImportJob.Outcome


def persist(
    job: ReceiptImportJob, canonical: CanonicalReceipt, issues: list[ValidationIssue]
) -> tuple[Receipt, str]:
    """Store the receipt for the job's household, or find the copy it already has."""
    issued_at = canonical.document.issued_at
    merchant = resolve_merchant(canonical.issuer, as_of=issued_at)
    store = resolve_store(merchant, canonical.branch, as_of=issued_at)

    existing = find_existing(job.household_id, canonical)
    if existing is not None:
        return existing, Outcome.DUPLICATE
    try:
        with transaction.atomic():
            receipt = Receipt.objects.create(
                household_id=job.household_id,
                imported_by_id=job.requested_by_id,
                merchant=merchant,
                store=store,
                **receipt_values(canonical, issues),
            )
    except IntegrityError:  # a concurrent import stored the same receipt first
        existing = find_existing(job.household_id, canonical)
        if existing is None:
            raise
        return existing, Outcome.DUPLICATE

    items = build_items(receipt, canonical)
    match_items(items, merchant=merchant)  # may create products and mappings
    for item in items:
        apply_prices(item)
    ReceiptItem.objects.bulk_create(items)
    return receipt, Outcome.CREATED


def find_existing(household_id, canonical: CanonicalReceipt) -> Receipt | None:
    """The household's receipt with the same MARK, (country, VAT, UID) or source key."""
    identity = canonical.identity
    matches = Q()
    if identity.mark:
        matches |= Q(mark=identity.mark)
    if identity.uid:
        matches |= Q(
            issuer_country=canonical.issuer.country_code,
            issuer_vat=canonical.issuer.vat_number,
            uid=identity.uid,
        )
    if identity.source_key:
        matches |= Q(source_key=identity.source_key)
    if not matches:
        return None
    return Receipt.objects.filter(matches, household_id=household_id).first()


def receipt_values(canonical: CanonicalReceipt, issues: list[ValidationIssue]) -> dict[str, Any]:
    identity, document, totals = canonical.identity, canonical.document, canonical.totals
    return {
        "provider_code": canonical.provider_code,
        "parser_version": canonical.parser_version,
        "issuer_country": canonical.issuer.country_code,
        "issuer_vat": canonical.issuer.vat_number,
        "uid": identity.uid or None,
        "mark": identity.mark or None,
        "cancellation_mark": identity.cancellation_mark or None,
        "source_key": identity.source_key or None,
        "document_kind": document.kind.value,
        "document_type_code": document.type_code or None,
        "document_number": document_number(document),
        "issued_at": document.issued_at,
        "currency": document.currency,
        "gross_total": totals.gross,
        "net_total": totals.net,
        "vat_total": totals.vat,
        "discount_total": totals.discount,
        "payment_method": payment_method(canonical.payments),
        "status": Receipt.Status.CANCELLED if is_cancelled(identity) else Receipt.Status.ACTIVE,
        "validation_warnings": [issue.to_dict() for issue in issues],
        "source_url": canonical.source_url,
        "source_url_fingerprint": fingerprint(canonical.source_url),
        "source_data": source_data(canonical),
    }


def build_items(receipt: Receipt, canonical: CanonicalReceipt) -> list[ReceiptItem]:
    items = []
    for line in canonical.lines:
        normalized = normalize_text(line.description)
        line_type = classify(line, normalized)
        items.append(
            ReceiptItem(
                receipt=receipt,
                household_id=receipt.household_id,
                line_number=line.line_number,
                line_type=line_type.value,
                description=line.description,
                normalized_description=normalized,
                merchant_product_code=line.merchant_product_code or None,
                quantity=line.quantity,
                unit=line.unit.value if line.unit else None,
                unit_price=line.unit_price,
                gross_amount=line.gross,
                net_amount=line.net,
                vat_rate=line.vat_rate,
                vat_amount=line.vat,
                discount_amount=line.discount,
                match_status=(
                    ReceiptItem.MatchStatus.NEEDS_REVIEW
                    if line_type is LineType.PRODUCT
                    else ReceiptItem.MatchStatus.NOT_A_PRODUCT
                ),
            )
        )
    return items


def document_number(document: Document) -> str:
    if document.formatted_number:
        return document.formatted_number
    return "-".join(part for part in (document.series, document.number) if part)


def payment_method(payments: tuple[Payment, ...]) -> str:
    """The one method used; ``mixed`` for several different ones; ``unknown`` for none."""
    methods = {payment.method.value if payment.method else "unknown" for payment in payments}
    if not methods:
        return Receipt.PaymentMethod.UNKNOWN
    if len(methods) > 1:
        return Receipt.PaymentMethod.MIXED
    return methods.pop()


def is_cancelled(identity: Identity) -> bool:
    """A non-zero cancellation MARK means the receipt was cancelled (requirements §8.6)."""
    return bool(identity.cancellation_mark and identity.cancellation_mark.strip("0"))


def source_data(canonical: CanonicalReceipt) -> dict[str, Any]:
    """The canonical receipt as stored (requirements §15.3):

    - without its URL (a credential, stored only in ``source_url``)
    - with the names of unknown fields but not their values: an unknown field was not
      allowlisted, so it may hold personal data (a loyalty code, a terminal id)
    - without anything shaped like a card number in payment labels
    """
    data = canonical.to_json()
    data.pop("source_url", None)
    data["unknown_fields"] = dict.fromkeys(canonical.unknown_fields, "")
    for payment in data.get("payments") or []:
        if payment.get("method_label"):
            payment["method_label"] = drop_card_numbers(payment["method_label"])
    return data


_CARD_NUMBER_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")


def drop_card_numbers(text: str) -> str:
    """Replaces digit runs of card-number length that pass the Luhn check."""

    def replace(match: re.Match) -> str:
        digits = [int(c) for c in match.group() if c.isdigit()]
        total = sum(
            d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2)
            for i, d in enumerate(reversed(digits))
        )
        return "<card>" if total % 10 == 0 else match.group()

    return _CARD_NUMBER_RE.sub(replace, text)
