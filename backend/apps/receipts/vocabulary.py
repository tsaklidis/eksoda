"""Label vocabularies shared by every provider (pure Python).

Sources that print labels instead of myDATA codes ("Απόδειξη Λιανικής Πώλησης",
"TEMAXIO", "POS / e-POS", …) are mapped here. Keys are compared after
``normalize_text`` (case, accents, Latin/Greek look-alike letters, punctuation), so
"ΤΕΜΑΧΙΟ" and "TEMAXIO" are the same key. Extend these tables when a new label
appears: unknown labels never crash a parser, they become ``None``/OTHER and are
reported as format drift.
"""

from decimal import Decimal

from apps.common.text import normalize_text
from apps.receipts import mydata
from apps.receipts.mydata import DocumentKind, PaymentMethod, Unit


def _index(table: dict[str, object]) -> dict[str, object]:
    return {normalize_text(label): value for label, value in table.items()}


DOCUMENT_TYPE_LABELS = _index(
    {
        "Απόδειξη Λιανικής Πώλησης": "11.1",
        "ΑΛΠ": "11.1",
        "ΑΛΠ (Απόδειξη Λιανικής Πώλησης)": "11.1",
        "Απόδειξη Παροχής Υπηρεσιών": "11.2",
        "ΑΠΥ": "11.2",
        "Απλοποιημένο Τιμολόγιο": "11.3",
        "Πιστωτικό Στοιχείο Λιανικής": "11.4",
        "Πιστωτικό Στοιχ. Λιανικής": "11.4",
        "Απόδειξη Λιανικής Πώλησης για Λογαριασμό Τρίτων": "11.5",
        "Τιμολόγιο Πώλησης": "1.1",
        "Τιμολόγιο Παροχής Υπηρεσιών": "2.1",
    }
)

UNIT_LABELS = _index(
    {
        "ΤΕΜΑΧΙΟ": Unit.PIECE,
        "ΤΕΜΑΧΙΑ": Unit.PIECE,
        "ΤΕΜΑΧ": Unit.PIECE,
        "ΤΕΜ": Unit.PIECE,
        "ΤΜΧ": Unit.PIECE,
        "PCS": Unit.PIECE,
        "ΚΙΛΑ": Unit.KG,
        "ΚΙΛΟ": Unit.KG,
        "ΚΙΛ": Unit.KG,
        "KG": Unit.KG,
        "ΛΙΤΡΑ": Unit.L,
        "ΛΙΤΡΟ": Unit.L,
        "LT": Unit.L,
        "L": Unit.L,
    }
)

PAYMENT_LABELS = _index(
    {
        "POS / e-POS": PaymentMethod.CARD,
        "POS": PaymentMethod.CARD,
        "e-POS": PaymentMethod.CARD,
        "ΚΑΡΤΑ": PaymentMethod.CARD,
        "ΠΙΣΤΩΤΙΚΗ ΚΑΡΤΑ": PaymentMethod.CARD,
        "ΧΡΕΩΣΤΙΚΗ ΚΑΡΤΑ": PaymentMethod.CARD,
        "VISA": PaymentMethod.CARD,
        "MASTERCARD": PaymentMethod.CARD,
        "MAESTRO": PaymentMethod.CARD,
        "AMEX": PaymentMethod.CARD,
        "AMERICAN EXPRESS": PaymentMethod.CARD,
        "ΜΕΤΡΗΤΑ": PaymentMethod.CASH,
        "CASH": PaymentMethod.CASH,
        "WEB BANKING": PaymentMethod.BANK,
        "IRIS": PaymentMethod.BANK,
        "ΚΑΤΑΘΕΣΗ": PaymentMethod.BANK,
        "ΕΠΙ ΠΙΣΤΩΣΕΙ": PaymentMethod.OTHER,
        "ΕΠΙΤΑΓΗ": PaymentMethod.OTHER,
    }
)

CURRENCY_LABELS = _index(
    {
        "EUR": "EUR",
        "ΕΥΡΩ": "EUR",
        "0# Euro Member Countries": "EUR",
    }
)


def document_type(label: str | None) -> tuple[str | None, DocumentKind]:
    """(myDATA code or None, kind) for a printed document type label."""
    key = normalize_text(label or "")
    code = DOCUMENT_TYPE_LABELS.get(key)
    if code is not None:
        return code, mydata.document_kind(code)
    # Combined or unknown labels: decide the kind from keywords. Refunds and returns
    # ("ΑΠΟΔΕΙΞΗ ΕΠΙΣΤΡΟΦΗΣ") reduce spending; cancellations are left for review.
    if "ΠΙΣΤΩΤΙΚ" in key or "ΕΠΙΣΤΡΟΦ" in key:
        return None, DocumentKind.CREDIT_NOTE
    if "ΑΚΥΡΩΤ" in key:
        return None, DocumentKind.OTHER
    if "ΑΠΟΔΕΙΞΗ" in key or "ΤΙΜΟΛΟΓΙΟ" in key:
        return None, DocumentKind.SALE
    return None, DocumentKind.OTHER


def unit(label: str | None) -> Unit | None:
    """The unit for a printed label; None when the label is unknown or blank."""
    return UNIT_LABELS.get(normalize_text(label or ""))


def payment_method(label: str | None) -> PaymentMethod | None:
    return PAYMENT_LABELS.get(normalize_text(label or ""))


def currency(label: str | None) -> str | None:
    if "€" in (label or ""):
        return "EUR"
    key = normalize_text(label or "")
    if not key:
        return None
    if key in CURRENCY_LABELS:
        return CURRENCY_LABELS[key]
    return key if len(key) == 3 and key.isalpha() and key.isascii() else None


def vat_category_for_rate(rate: Decimal | None) -> str | None:
    """The myDATA VAT category for a rate, when the rate identifies exactly one category."""
    if rate is None:
        return None
    matches = [code for code, value in mydata.VAT_RATES.items() if value == rate]
    return matches[0] if len(matches) == 1 else None
