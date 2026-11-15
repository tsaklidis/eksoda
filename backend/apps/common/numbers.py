"""Strict, culture-aware parsing of numbers and dates (pure Python, TD §6.4).

Receipt pages render numbers and dates according to a culture (``el`` or ``en``).
Parsing is strict per culture: ambiguous or malformed text raises instead of being
guessed, because a misread amount silently corrupts financial history.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

Culture = Literal["el", "en"]
DateOrder = Literal["dmy", "mdy", "ymd"]
CULTURES: tuple[Culture, ...] = ("el", "en")


class NumberFormatError(ValueError):
    pass


class DateFormatError(ValueError):
    pass


# culture → (thousands separator, decimal separator)
_SEPARATORS: dict[str, tuple[str, str]] = {"el": (".", ","), "en": (",", ".")}
_NUMBER_RE = {
    culture: re.compile(
        rf"^(?:\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+|\d+)(?:{re.escape(decimal)}\d+)?$"
    )
    for culture, (thousands, decimal) in _SEPARATORS.items()
}
_MINUS_SIGNS = "-−"

_DATE_RE = re.compile(r"^(\d{1,4})[/.-](\d{1,2})[/.-](\d{1,4})$")
_DATETIME_RE = re.compile(
    r"^(?P<date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4})\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2}))?(?:\s*(?P<marker>\S+))?$"
)
_MERIDIEM = {
    "el": {"π.μ.": "am", "μ.μ.": "pm", "πμ": "am", "μμ": "pm"},
    "en": {"am": "am", "pm": "pm", "a.m.": "am", "p.m.": "pm"},
}


def _clean(text: str) -> str:
    # Pages may use (narrow) no-break spaces, e.g. before "π.μ." or "AM".
    return text.replace("\u00a0", " ").replace("\u202f", " ").strip()


def parse_decimal(text: str, culture: Culture) -> Decimal:
    """Parse a number rendered in ``culture``. A trailing ``%`` is allowed and ignored."""
    if culture not in _SEPARATORS:
        raise NumberFormatError(f"unknown culture {culture!r}")
    value = _clean(text)
    if value.endswith("%"):
        value = value[:-1].rstrip()
    negative = bool(value) and value[0] in _MINUS_SIGNS
    if negative:
        value = value[1:].lstrip()
    if not _NUMBER_RE[culture].match(value):
        raise NumberFormatError(f"{text!r} is not a valid {culture} number")
    thousands, decimal = _SEPARATORS[culture]
    number = Decimal(value.replace(thousands, "").replace(decimal, "."))
    return -number if negative else number


def parse_optional_decimal(text: str | None, culture: Culture) -> Decimal | None:
    """Like parse_decimal, but blank text means "not provided" (None)."""
    if text is None or not _clean(text):
        return None
    return parse_decimal(text, culture)


def parse_date(text: str, order: DateOrder) -> date:
    """Parse a date in the given part order; separators may be "/", "-" or "."."""
    match = _DATE_RE.match(_clean(text))
    if not match:
        raise DateFormatError(f"{text!r} is not a date")
    parts = match.groups()
    year_index = 0 if order == "ymd" else 2
    if len(parts[year_index]) != 4 or any(
        len(part) > 2 for index, part in enumerate(parts) if index != year_index
    ):
        raise DateFormatError(f"{text!r} does not match the {order} order")
    first, second, third = (int(part) for part in parts)
    if order == "ymd":
        year, month, day = first, second, third
    elif order == "dmy":
        day, month, year = first, second, third
    else:
        month, day, year = first, second, third
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise DateFormatError(f"{text!r} is not a valid {order} date") from exc


def parse_local_datetime(
    text: str, *, culture: Culture, order: DateOrder, tz: ZoneInfo
) -> datetime:
    """Parse ``d/m/yyyy h:mm[:ss] [am/pm marker]`` as a local time in ``tz``.

    Greek pages use ``π.μ.`` / ``μ.μ.``; English pages ``AM`` / ``PM``. Without a
    marker the time is read as 24-hour. Ambiguous DST times resolve to fold=0.
    """
    match = _DATETIME_RE.match(_clean(text))
    if not match:
        raise DateFormatError(f"{text!r} is not a date and time")
    day = parse_date(match["date"], order)
    hour, minute = int(match["hour"]), int(match["minute"])
    second = int(match["second"] or 0)
    marker = match["marker"]
    if marker is not None:
        meridiem = _MERIDIEM.get(culture, {}).get(marker.lower())
        if meridiem is None or not 1 <= hour <= 12:
            raise DateFormatError(f"{text!r} has an invalid 12-hour time")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    try:
        return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=tz)
    except ValueError as exc:
        raise DateFormatError(f"{text!r} has an invalid time") from exc
