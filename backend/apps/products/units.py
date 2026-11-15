"""Package units and their base units (pure Python, requirements §9.4, TD §13.3).

Mass converts to kg and volume to l. Mass and volume are never converted into each
other, so a price per kg is never compared with a price per liter.
"""

from decimal import Decimal

TO_BASE: dict[str, tuple[str, Decimal]] = {
    "mg": ("kg", Decimal("0.000001")),
    "g": ("kg", Decimal("0.001")),
    "kg": ("kg", Decimal("1")),
    "ml": ("l", Decimal("0.001")),
    "cl": ("l", Decimal("0.01")),
    "l": ("l", Decimal("1")),
    "piece": ("piece", Decimal("1")),
}


def to_base(quantity: Decimal, unit: str) -> tuple[Decimal, str]:
    """``quantity`` of ``unit`` in its base unit: (0.5, "l") for (500, "ml")."""
    try:
        base, factor = TO_BASE[unit]
    except KeyError:
        raise ValueError(f"unknown unit {unit!r}") from None
    return quantity * factor, base
