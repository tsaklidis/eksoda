"""Line classification into four types (pure Python, requirements §9.1, TD §13.1).

The first matching rule wins:

1. A negative amount: ``discount`` when the description names a discount, otherwise
   ``other`` (returns, adjustments).
2. Keywords on the normalized description: discount, then fee keywords. A keyword
   matches the start of a word; a two-word keyword matches two consecutive words
   (``ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ`` matches ``ΠΕΡΙΒΑΛΛΟΝΤΙΚΟ ΤΕΛΟΣ``).
3. A zero net amount that carries only fees or other taxes: ``fee``.
4. Everything else: ``product``.

The keyword lists are plain constants. A new keyword is a code change with a test.
"""

from decimal import Decimal
from enum import StrEnum

from apps.common.text import normalize_text
from apps.receipts.canonical import Line


class LineType(StrEnum):
    PRODUCT = "product"
    DISCOUNT = "discount"
    FEE = "fee"
    OTHER = "other"


DISCOUNT_KEYWORDS = ("ΕΚΠΤΩΣ", "ΚΟΥΠΟΝ", "DISCOUNT")
# Carrier-bag environmental fee and deposit. Never the bare word "ΣΑΚΟΥΛ": real LIDL
# receipts sell bags and garbage bags as products (docs/providers/entersoft.md §5).
FEE_KEYWORDS = ("ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ", "ΕΓΓΥΗΣ")

# Compared as normalize_text() keys, like the descriptions.
_DISCOUNT_KEYS = tuple(normalize_text(word) for word in DISCOUNT_KEYWORDS)
_FEE_KEYS = tuple(normalize_text(word) for word in FEE_KEYWORDS)
_ZERO = Decimal("0")


def _has(normalized_description: str, keys: tuple[str, ...]) -> bool:
    words = normalized_description.split()
    for key in keys:
        parts = key.split()
        for start in range(len(words) - len(parts) + 1):
            if all(words[start + i].startswith(part) for i, part in enumerate(parts)):
                return True
    return False


def classify(line: Line, normalized_description: str | None = None) -> LineType:
    text = (
        normalize_text(line.description)
        if normalized_description is None
        else normalized_description
    )
    if line.gross < _ZERO:
        return LineType.DISCOUNT if _has(text, _DISCOUNT_KEYS) else LineType.OTHER
    if _has(text, _DISCOUNT_KEYS):
        return LineType.DISCOUNT
    if _has(text, _FEE_KEYS):
        return LineType.FEE
    charges = (line.fees or _ZERO) + (line.other_taxes or _ZERO)
    if line.net is not None and line.net == _ZERO and charges > _ZERO:
        return LineType.FEE
    return LineType.PRODUCT
