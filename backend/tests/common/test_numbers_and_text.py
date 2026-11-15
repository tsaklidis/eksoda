from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.numbers import (
    DateFormatError,
    NumberFormatError,
    parse_date,
    parse_decimal,
    parse_local_datetime,
    parse_optional_decimal,
)
from apps.common.text import collapse_whitespace, fingerprint, normalize_text, strip_diacritics

ATHENS = ZoneInfo("Europe/Athens")


@pytest.mark.parametrize(
    ("text", "culture", "expected"),
    [
        ("0,622", "el", "0.622"),
        ("1.234,56", "el", "1234.56"),
        ("1.234", "el", "1234"),
        ("13,00%", "el", "13.00"),
        ("-0,50", "el", "-0.50"),
        ("−0,50", "el", "-0.50"),
        (" 7,21 ", "el", "7.21"),
        ("0.622", "en", "0.622"),
        ("1,234.56", "en", "1234.56"),
        ("12", "en", "12"),
    ],
)
def test_parse_decimal(text, culture, expected):
    assert parse_decimal(text, culture) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "culture"),
    [
        ("1.0", "el"),  # English decimal in a Greek page
        ("1,0", "en"),
        ("1,2,3", "el"),
        ("12.34.5", "el"),
        ("", "el"),
        ("abc", "el"),
        ("1 000", "el"),
        ("1,0", "fr"),
    ],
)
def test_parse_decimal_rejects_ambiguous_input(text, culture):
    with pytest.raises(NumberFormatError):
        parse_decimal(text, culture)


def test_parse_optional_decimal():
    assert parse_optional_decimal(None, "el") is None
    assert parse_optional_decimal("  ", "el") is None
    assert parse_optional_decimal("0,00", "el") == Decimal("0.00")


def test_parse_date_orders():
    assert parse_date("7/11/2026", "dmy") == date(2026, 11, 7)
    assert parse_date("11/07/2026", "mdy") == date(2026, 11, 7)
    for bad in ("2026-11-07", "31/02/2026", "13/13/2026"):
        with pytest.raises(DateFormatError):
            parse_date(bad, "dmy")


@pytest.mark.parametrize(
    ("text", "culture", "expected"),
    [
        ("07/11/2026 6:28 μ.μ.", "el", datetime(2026, 11, 7, 18, 28, tzinfo=ATHENS)),
        ("07/11/2026 12:05 π.μ.", "el", datetime(2026, 11, 7, 0, 5, tzinfo=ATHENS)),
        ("07/11/2026 12:05 μ.μ.", "el", datetime(2026, 11, 7, 12, 5, tzinfo=ATHENS)),
        ("07/11/2026 6:28 PM", "en", datetime(2026, 11, 7, 18, 28, tzinfo=ATHENS)),
        ("07/11/2026 18:28:09", "el", datetime(2026, 11, 7, 18, 28, 9, tzinfo=ATHENS)),
    ],
)
def test_parse_local_datetime(text, culture, expected):
    parsed = parse_local_datetime(text, culture=culture, order="dmy", tz=ATHENS)
    assert parsed == expected
    assert parsed.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize(
    "text",
    ["yesterday", "07/11/2026 13:28 μ.μ.", "07/11/2026 6:28 XM", "07/11/2026 25:00", "07/11/2026"],
)
def test_parse_local_datetime_rejects(text):
    with pytest.raises(DateFormatError):
        parse_local_datetime(text, culture="el", order="dmy", tz=ATHENS)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Γάλα  φρέσκο", "ΓΑΛΑ ΦΡΕΣΚΟ"),
        ("ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΕΛΑΦΡΥ 1,5% 1L", "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΕΛΑΦΡΥ 1.5% 1L"),
        (
            "ADORO LIGHT 10% ΦΡΑΤΖ. ΓΕΡΜΑΝΙΑΣ(Τ.ΚΙΛΟΥ",
            "ADORO LIGHT 10% ΦΡΑΤΖ ΓΕΡΜΑΝΙΑΣ T ΚΙΛΟΥ",
        ),  # lone look-alike → Latin
        ("ΓAΛA", "ΓΑΛΑ"),  # Latin A inside a Greek word
        ("MИЛK", "MИЛK"),  # other scripts are left alone
        ("ΚΑΚΑΟ", "KAKAO"),  # only look-alike letters: written in Latin
        ("KAKAO", "KAKAO"),
        ("Ψωμί ολικής άλεσης", "ΨΩΜΙ ΟΛΙΚΗΣ ΑΛΕΣΗΣ"),
        ("27/250ML", "27 250ML"),
        ("ΠΙΚ.72", "ΠΙΚ 72"),
        ("Ελαιόλαδο ﬁno", "ΕΛΑΙΟΛΑΔΟ FINO"),
    ],
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


def test_helpers():
    assert strip_diacritics("άέήίόύώϊΐ") == "αεηιουωιι"
    assert collapse_whitespace("  a \n b\t") == "a b"
    assert fingerprint("x") == "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"


def test_date_separators_and_year_first_order():
    assert parse_date("13-07-2026", "dmy") == date(2026, 7, 13)
    assert parse_date("13.07.2026", "dmy") == date(2026, 7, 13)
    assert parse_date("2024-05-17", "ymd") == date(2024, 5, 17)
    with pytest.raises(DateFormatError, match="order"):
        parse_date("2024-05-17", "dmy")
    with pytest.raises(DateFormatError, match="order"):
        parse_date("17-05-2024", "ymd")
    assert parse_local_datetime(
        "2024-05-17 09:51", culture="en", order="ymd", tz=ATHENS
    ) == datetime(2024, 5, 17, 9, 51, tzinfo=ATHENS)
    assert parse_local_datetime(
        "13-07-2026 15:17:11", culture="el", order="dmy", tz=ATHENS
    ) == datetime(2026, 7, 13, 15, 17, 11, tzinfo=ATHENS)
