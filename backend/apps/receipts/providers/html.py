"""HTML helpers shared by provider parsers (pure Python)."""

import re
from collections.abc import Iterable
from decimal import Decimal

from bs4 import Tag

from apps.common.numbers import Culture, NumberFormatError, parse_optional_decimal
from apps.common.text import collapse_whitespace, normalize_text
from apps.receipts.errors import FormatChanged

_CURRENCY_NOISE = re.compile(r"(?i)\s*(?:€|EUR|ευρώ|ευρω)\s*")


def text_of(element: Tag | None) -> str:
    return collapse_whitespace(element.get_text(" ", strip=True)) if element is not None else ""


def key_of(label: str) -> str:
    """Comparison key for labels/headers: normalized text without a trailing colon."""
    return normalize_text(label.strip().rstrip(":"))


def child_cells(row: Tag, name: str = "div") -> list[Tag]:
    return row.find_all(name, recursive=False)


def amount(text: str | None, culture: Culture, where: str) -> Decimal | None:
    """A number that may carry a currency marker ("75,48EUR", "€ 24.87")."""
    if text is None:
        return None
    try:
        return parse_optional_decimal(_CURRENCY_NOISE.sub("", text), culture)
    except NumberFormatError as exc:
        raise FormatChanged(f"{where}: {exc}") from exc


def required(mapping: dict[str, str], key: str, where: str) -> str:
    value = (mapping.get(key) or "").strip()
    if not value:
        raise FormatChanged(f"missing required field {where}")
    return value


def label_map(
    pairs: Iterable[tuple[str, str]], known: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Split (label, value) pairs into (known key → value, unknown label → value).

    ``known`` maps human-written labels to keys; labels are compared with key_of().
    """
    index = {key_of(label): key for label, key in known.items()}
    values: dict[str, str] = {}
    unknown: dict[str, str] = {}
    for label, value in pairs:
        key = index.get(key_of(label))
        if key is None:
            unknown[collapse_whitespace(label)] = value
        else:
            values.setdefault(key, value)
    return values, unknown
