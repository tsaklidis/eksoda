"""Merchant and store resolution for imported receipts (requirements §8.4, §8.5, TD §12.5).

Runs inside the import transaction. Concurrent imports of a new merchant or store are
resolved by the unique constraints (``get_or_create`` re-reads the winner's row).

Public details are refreshed from receipts:
- an empty field is filled from any receipt;
- a filled field is replaced only by a receipt issued at the same time or later than
  the one that last set the details, and never by a truncated copy of itself (some
  sources cut long names).
"""

from datetime import datetime

from django.db import models

from apps.common.text import normalize_text
from apps.merchants.models import Merchant, Store
from apps.receipts.canonical import Address, Branch, Party

# Legal-form words that end the brand part of a legal name, compared on
# normalize_text() keys with spaces removed ("Α.Ε." and "ΑΕ" give the same key).
_LEGAL_FORMS = frozenset(
    "".join(normalize_text(form).split())
    for form in (
        "ΑΕ",
        "ΑΕΒΕ",
        "ΑΒΕΕ",
        "ΑΒΕ",
        "ΑΕΕ",
        "ΑΕΒΕΕ",
        "ΙΚΕ",
        "ΜΙΚΕ",
        "ΟΕ",
        "ΕΕ",
        "ΕΠΕ",
        "ΜΕΠΕ",
        "ΑΝΩΝΥΜΗ",  # spelled-out forms
        "ΙΔΙΩΤΙΚΗ",
        "ΟΜΟΡΡΥΘΜΗ",
        "ΕΤΕΡΟΡΡΥΘΜΗ",
        "ΜΟΝΟΠΡΟΣΩΠΗ",
        "ΜΟΝΟΠΡΟΣΩΠΟΣ",
        "ΜΟΝΟΠΡΟ",  # cut short by cash-register pages
        "SA",
        "S.A.",
        "LTD",
        "GMBH",
    )
)
_AND = normalize_text("ΚΑΙ")  # "ΚΑΙ ΣΙΑ" / "& ΣΙΑ" (and partners) also ends the brand part
_PARTNERS = normalize_text("ΣΙΑ")


def _key(word: str) -> str:
    return "".join(normalize_text(word).split())


def _title(word: str) -> str:
    lowered = word.lower()  # lower() of the whole word keeps the Greek final sigma right
    return lowered[:1].upper() + lowered[1:]


def derive_display_name(legal_name: str) -> str:
    """The brand part of a legal name, title-cased: ``METRO ΑΕΒΕ …`` → ``Metro``."""
    words = legal_name.split()
    cut = len(words)
    for index, word in enumerate(words[1:], start=1):
        following = _key(words[index + 1]) if index + 1 < len(words) else ""
        if _key(word) in _LEGAL_FORMS or (
            (word == "&" or _key(word) == _AND) and following == _PARTNERS
        ):
            cut = index
            break
    brand = words[:cut]
    while brand and not _key(brand[-1]):  # a trailing "&", "-", "," …
        brand.pop()
    name = " ".join(_title(word) for word in brand) or legal_name.strip()
    return _fit(name, Merchant, "display_name")


def normalize_address(address: Address | None) -> str:
    """The store matching key: street, number, postal code and city (country omitted)."""
    if address is None:
        return ""
    return _address_key(address.street, address.number, address.postal_code, address.city)


def _address_key(*parts: str | None) -> str:
    key = normalize_text(" ".join(part for part in parts if part))
    return _fit(key, Store, "normalized_address")


def resolve_merchant(issuer: Party, *, as_of: datetime) -> Merchant:
    address = issuer.address or Address()
    details = _fitted(
        Merchant,
        legal_name=issuer.legal_name,
        activity_description=issuer.activity,
        tax_office=issuer.tax_office,
        gemi_number=issuer.gemi_number,
        street=address.street,
        street_number=address.number,
        city=address.city,
        postal_code=address.postal_code,
    )
    merchant, created = Merchant.objects.get_or_create(
        country_code=issuer.country_code,
        vat_number=issuer.vat_number,
        defaults={
            **details,
            "display_name": derive_display_name(details["legal_name"]),
            "details_as_of": as_of,
        },
    )
    if not created:
        # A new legal name renames the merchant only while its display name is still the
        # derived one: a name staff set in the admin is kept.
        previous_default = derive_display_name(merchant.legal_name)
        changed = _refresh(merchant, details, as_of)
        if "legal_name" in changed and merchant.display_name == previous_default:
            merchant.display_name = derive_display_name(merchant.legal_name)
            changed.append("display_name")
        _save(merchant, changed)
    return merchant


def resolve_store(merchant: Merchant, branch: Branch | None, *, as_of: datetime) -> Store | None:
    """By branch number; else by normalized address; without either, no store."""
    if branch is None:
        return None
    address = branch.address or Address()
    street = " ".join(part for part in (address.street, address.number) if part)
    details = _fitted(Store, street=street, city=address.city, postal_code=address.postal_code)
    normalized = normalize_address(address)
    defaults = {
        **details,
        "country_code": merchant.country_code,
        "normalized_address": normalized,
        "details_as_of": as_of,
    }

    if branch.number:
        store, created = Store.objects.get_or_create(
            merchant=merchant, branch_number=branch.number, defaults=defaults
        )
        if not created:
            changed = _refresh(store, details, as_of)
            if set(changed) & details.keys():  # the address moved: keep its key in step
                store.normalized_address = _address_key(store.street, store.postal_code, store.city)
                changed.append("normalized_address")
            _save(store, changed)
        return store

    if not normalized:
        return None
    store, _ = Store.objects.get_or_create(
        merchant=merchant, branch_number=None, normalized_address=normalized, defaults=defaults
    )
    return store


# --- helpers -----------------------------------------------------------------------
def _fit(value: str, model: type[models.Model], field: str) -> str:
    max_length = model._meta.get_field(field).max_length
    return value[:max_length].strip() if max_length else value


def _fitted(model: type[models.Model], **values: str | None) -> dict[str, str]:
    """Strip values and cut them to the column size (public data: cutting is harmless)."""
    return {field: _fit((value or "").strip(), model, field) for field, value in values.items()}


def _refresh(obj: Merchant | Store, details: dict[str, str], as_of: datetime) -> list[str]:
    newer = obj.details_as_of is None or as_of >= obj.details_as_of
    changed = []
    for field, value in details.items():
        current = getattr(obj, field)
        if not value or value == current:
            continue
        if not current or (newer and not current.startswith(value)):
            setattr(obj, field, value)
            changed.append(field)
    if newer and obj.details_as_of != as_of:
        obj.details_as_of = as_of
        changed.append("details_as_of")
    return changed


def _save(obj: Merchant | Store, changed: list[str]) -> None:
    if changed:
        obj.save(update_fields=[*changed, "updated_at"])
