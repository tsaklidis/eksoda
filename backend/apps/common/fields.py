"""The only money and quantity field factories (requirements §10.1, TD §6.1).

Money and quantities are always Decimal, never float. Precision is fixed here so
every app stores the same kind of value the same way.
"""

from django.db import models


def MoneyField(**kwargs) -> models.DecimalField:
    """Amounts in a currency: Decimal(12, 2)."""
    return models.DecimalField(max_digits=12, decimal_places=2, **kwargs)


def UnitPriceField(**kwargs) -> models.DecimalField:
    """Unit prices and normalized unit prices: Decimal(14, 4)."""
    return models.DecimalField(max_digits=14, decimal_places=4, **kwargs)


def QuantityField(**kwargs) -> models.DecimalField:
    """Purchased quantities and package sizes: Decimal(14, 4)."""
    return models.DecimalField(max_digits=14, decimal_places=4, **kwargs)


def NormalizedQuantityField(**kwargs) -> models.DecimalField:
    """Quantities in a base unit (kg, l, piece): Decimal(16, 6)."""
    return models.DecimalField(max_digits=16, decimal_places=6, **kwargs)


def RateField(**kwargs) -> models.DecimalField:
    """Percentages such as VAT rates: Decimal(5, 2)."""
    return models.DecimalField(max_digits=5, decimal_places=2, **kwargs)
