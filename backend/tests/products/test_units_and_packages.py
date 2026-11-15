from decimal import Decimal

import pytest

from apps.products.packages import PackageSuggestion, suggest
from apps.products.units import to_base


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("500", "g", ("0.500", "kg")),
        ("250", "mg", ("0.000250", "kg")),
        ("2", "kg", ("2", "kg")),
        ("330", "ml", ("0.330", "l")),
        ("75", "cl", ("0.75", "l")),
        ("1.5", "l", ("1.5", "l")),
        ("6", "piece", ("6", "piece")),
    ],
)
def test_to_base(quantity, unit, expected):
    value, base = to_base(Decimal(quantity), unit)
    assert (value, base) == (Decimal(expected[0]), expected[1])


def test_unknown_units_are_refused():
    with pytest.raises(ValueError, match="unknown unit"):
        to_base(Decimal(1), "oz")


def size(quantity: str, unit: str) -> PackageSuggestion:
    return PackageSuggestion(Decimal(quantity), unit)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        # requirements §9.4
        ("ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L", size("1", "l")),
        ("ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΕΛΑΦΡΥ 1,5% 1L", size("1", "l")),
        ("MY GUSTO ΧΥΜΟΣ MULTIV. 9 ΦΡΟΥΤΑ 27/250ML", None),
        # TD §13.3 edge cases
        ("500GR", size("500", "g")),
        ("1,5LT", size("1.5", "l")),
        ("2 X 1L", None),
        ("ΓΑΛΑ 3,5% 1L", size("1", "l")),
        # real LIDL lines: abbreviation dots, glued tokens, mixed scripts, multipacks
        ("MSC ΦΙ.ΤΟ.ΦΥ.Ζ.195G", size("195", "g")),
        ("ΕΛΛ. ΚΑΦ. ΚΛΑΣΣ.340G", size("340", "g")),
        ("7DAYS MINI BA.RO150G", size("150", "g")),
        ("XAΡ.ΚΟΥΖ.2ΠΛΑ ΦΥΛ1ΚG", size("1", "kg")),
        ("FAIRY REGULAR 900ml", size("900", "ml")),
        ("ΜΑΓION.LIG.27% 500ML", size("500", "ml")),
        ("CO.COLA ZE.5+1X330ML", None),
        ("ΜΙΝΙ ΞΥΛΑΚΙΑ 12X36G", None),
        ("SEPTO.ΜΩΡΟ.ALOE3X60Τ", None),
        ("ΤΟΝΟΣΑΛΑΤΑ MEXICANA", None),
        ("ΟΔΟΝΤΟΓΛΥΦΙΔΕΣ400ΤΕΜ", None),
        # Greek unit spellings and others
        ("ΝΕΡΟ 1,5 ΛΙΤΡΑ", size("1.5", "l")),
        ("ΤΥΡΙ 200Γ", size("200", "g")),
        ("ΑΛΑΤΙ 500 ΓΡ.", size("500", "g")),
        ("ΚΡΑΣΙ 75CL", size("75", "cl")),
        ("ΒΙΤΑΜΙΝΗ 500MG", size("0.5", "g")),
        ("ΓΑΛΑ 1L ΚΑΙ ΓΙΑΟΥΡΤΙ 200G", None),  # two sizes: ambiguous
        ("ΓΑΛΑ 0L", None),
        ("ΣΟΚΟΛΑΤΑ 3 ΓΕΥΣΕΙΣ", None),  # a number followed by a word, not a unit
    ],
)
def test_suggest(description, expected):
    assert suggest(description) == expected
