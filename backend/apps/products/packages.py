"""Package-size suggestions from item descriptions (pure Python, requirements §9.4).

A suggestion is applied automatically only when it is unambiguous: exactly one size
token, and no multipack (``6X330ML``) or slash pack (``27/250ML``). Percentages
(``1,5%``) are never read as sizes. Otherwise the size stays empty until a person
sets it.

Receipts mix Greek and Latin letters that look alike (``1ΚG``), so unit letters
accept both scripts.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from apps.common.text import strip_diacritics

_NUMBER = r"(\d+(?:\.\d+)?)"
# Unit spellings, tried in this order. Letter classes accept Latin and Greek forms.
_UNITS = {
    "kg": r"[KΚ][GΓ][RΡ]?|[KΚ][IΙ][LΛ][OΟAΑ]?",
    "mg": r"[MΜ][GΓ][RΡ]?",
    "g": r"[GΓ][RΡ]?",
    "ml": r"[MΜ][LΛ]",
    "cl": r"C[LΛ]",
    "l": r"[LΛ][IΙ][TΤ](?:[RΡ][OΟAΑ])?|[LΛ][TΤ][RΡ]?|[LΛ]",
}
_UNIT = "|".join(f"(?P<{unit}>{pattern})" for unit, pattern in _UNITS.items())
# The number starts a token: not inside another number ("1.5" → not "5"), but it may
# follow an abbreviation dot ("ΦΥ.Ζ.195G").
SIZE_TOKEN = re.compile(rf"(?<![\d/])(?<!\d[.,]){_NUMBER}\s?(?:{_UNIT})(?![A-ZΑ-Ω0-9])")
MULTIPACK = re.compile(r"\d\s?[XΧ×]\s?\d")  # 6X330ML, 2 X 1L, 5+1X330ML
SLASH_PACK = re.compile(rf"\d\s?/\s?\d+(?:\.\d+)?\s?(?:{_UNIT})")  # 27/250ML
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s?%")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


@dataclass(frozen=True)
class PackageSuggestion:
    quantity: Decimal
    unit: str  # g | kg | ml | cl | l


def suggest(description: str) -> PackageSuggestion | None:
    text = _prepare(description)
    if MULTIPACK.search(text) or SLASH_PACK.search(text):
        return None
    tokens = list(SIZE_TOKEN.finditer(_PERCENT.sub(" ", text)))
    if len(tokens) != 1:
        return None
    match = tokens[0]
    quantity = Decimal(match.group(1))
    unit = next(name for name in _UNITS if match.group(name))
    if unit == "mg":
        quantity, unit = quantity / 1000, "g"
    if quantity <= 0:
        return None
    return PackageSuggestion(quantity=quantity, unit=unit)


def _prepare(description: str) -> str:
    """Uppercase, accent-free, decimal commas as dots. Not ``normalize_text``: it would
    drop the "/" that marks a slash pack."""
    text = strip_diacritics(unicodedata.normalize("NFKC", description)).upper()
    return _DECIMAL_COMMA.sub(".", text)
