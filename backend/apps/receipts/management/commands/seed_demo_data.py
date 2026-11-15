"""Demo receipts for one household: dashboards, list performance and manual testing.

Receipts are built as canonical receipts and stored through the import's own
persistence, so lines are classified, matched to products and priced exactly as
real imports are. The data is deterministic for a ``--seed``: running the command
again with the same seed adds nothing (the receipts are duplicates).

    make manage ARGS="seed_demo_data --household <id> --receipts 200"
"""

import random
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.households.models import Household
from apps.merchants.models import Merchant
from apps.products.models import ProductCategory
from apps.receipts.canonical import (
    Address,
    Branch,
    CanonicalReceipt,
    Coverage,
    Document,
    Identity,
    Line,
    Party,
    Payment,
    Totals,
)
from apps.receipts.models import ReceiptImportJob
from apps.receipts.mydata import DocumentKind, PaymentMethod, Unit
from apps.receipts.services.persistence import persist

CENT = Decimal("0.01")

# Demo shops (VAT numbers 99000000x) with their items: (code, description, unit, price).
# A shop without items issues summary-only receipts, like the AADE cash-register page.
CATALOG = [
    {
        "vat": "990000001",
        "legal_name": "ΔΕΙΓΜΑ ΣΟΥΠΕΡ ΜΑΡΚΕΤ ΑΕ",
        "street": "ΠΑΥΛΟΥ ΜΕΛΑ 10",
        "category": "groceries",
        "weight": 6,
        "items": [
            ("D001", "ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L", "piece", "1.29"),
            ("D002", "ΓΙΑΟΥΡΤΙ ΣΤΡΑΓΓΙΣΤΟ 1KG", "piece", "4.20"),
            ("D003", "ΦΕΤΑ ΠΟΠ", "kg", "11.90"),
            ("D004", "ΨΩΜΙ ΤΟΣΤ 700G", "piece", "1.95"),
            ("D005", "ΜΗΛΑ ΣΤΑΡΚΙΝ", "kg", "1.80"),
            ("D006", "ΖΥΜΑΡΙΚΑ ΣΠΑΓΓΕΤΙ 500G", "piece", "0.99"),
            ("D007", "ΕΛΑΙΟΛΑΔΟ ΠΑΡΘΕΝΟ 1L", "piece", "9.50"),
            ("D008", "ΑΠΟΡΡΥΠΑΝΤΙΚΟ ΠΙΑΤΩΝ 900ML", "piece", "2.60"),
            ("D009", "ΚΟΤΟΠΟΥΛΟ ΦΙΛΕΤΟ", "kg", "8.90"),
            ("D010", "ΝΕΡΟ ΕΜΦΙΑΛΩΜΕΝΟ 1,5L", "piece", "0.45"),
        ],
    },
    {
        "vat": "990000002",
        "legal_name": "ΔΕΙΓΜΑ ΦΟΥΡΝΟΣ ΟΕ",
        "street": "ΔΗΜΟΚΡΑΤΙΑΣ 3",
        "category": "bakery",
        "weight": 3,
        "items": [
            ("B001", "ΧΩΡΙΑΤΙΚΟ ΨΩΜΙ 1KG", "piece", "2.40"),
            ("B002", "ΚΟΥΛΟΥΡΙ ΘΕΣΣΑΛΟΝΙΚΗΣ", "piece", "0.70"),
            ("B003", "ΤΥΡΟΠΙΤΑ", "piece", "1.80"),
        ],
    },
    {
        "vat": "990000003",
        "legal_name": "ΔΕΙΓΜΑ ΦΑΡΜΑΚΕΙΟ ΙΚΕ",
        "street": "ΕΘΝ. ΑΝΤΙΣΤΑΣΕΩΣ 7",
        "category": "pharmacy-and-health",
        "weight": 1,
        "items": [
            ("P001", "ΒΙΤΑΜΙΝΗ C ΑΝΑΒΡΑΖΟΝΤΑ", "piece", "6.50"),
            ("P002", "ΟΔΟΝΤΟΚΡΕΜΑ 75ML", "piece", "3.20"),
        ],
    },
    {
        "vat": "990000004",
        "legal_name": "ΔΕΙΓΜΑ ΚΑΥΣΙΜΑ ΑΕ",
        "street": "ΕΘΝΙΚΗ ΟΔΟΣ ΚΟΖΑΝΗΣ",
        "category": "fuel-and-transport",
        "weight": 2,
        "items": [],
    },
]


class Command(BaseCommand):
    help = "Create deterministic demo receipts for a household (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--household", required=True, help="Household id.")
        parser.add_argument("--receipts", type=int, default=150)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--seed", type=int, default=1)
        parser.add_argument(
            "--force", action="store_true", help="Allow it when DEBUG is off (never in production)."
        )

    def handle(self, *args, household, receipts, months, seed, force, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Demo data is for development: pass --force to run without DEBUG.")
        target = Household.objects.filter(pk=household).first()
        if target is None:
            raise CommandError(f"No household {household}.")
        member = target.members.select_related("user").order_by("joined_at").first()
        rng = random.Random(seed)  # noqa: S311 (reproducible demo data, not security)
        today = timezone.localdate(timezone=ZoneInfo(target.timezone))
        created = 0
        for index in range(receipts):
            canonical = demo_receipt(
                rng, seed, index, today=today, months=months, tz=target.timezone
            )
            job = ReceiptImportJob(household=target, requested_by=member.user if member else None)
            with transaction.atomic():
                _receipt, outcome = persist(job, canonical, [])
            created += outcome == ReceiptImportJob.Outcome.CREATED
        set_default_categories()
        self.stdout.write(f"Created {created} demo receipt(s) for {target.name}.")


def set_default_categories() -> None:
    for shop in CATALOG:
        category = ProductCategory.objects.filter(household=None, slug=shop["category"]).first()
        Merchant.objects.filter(vat_number=shop["vat"], default_category=None).update(
            default_category=category
        )


def demo_receipt(
    rng: random.Random, seed: int, index: int, *, today, months: int, tz: str
) -> CanonicalReceipt:
    shop = rng.choices(CATALOG, weights=[entry["weight"] for entry in CATALOG])[0]
    day = today - timedelta(days=rng.randrange(max(months, 1) * 30))
    issued_at = datetime.combine(day, time(rng.randrange(8, 21), rng.randrange(60)), ZoneInfo(tz))
    credit_note = rng.random() < 0.02
    lines = _lines(rng, shop) if shop["items"] else ()
    gross = (
        sum((line.gross for line in lines), Decimal(0))
        if lines
        else Decimal(rng.randrange(3000, 7000)) / 100
    )
    net = (gross / Decimal("1.24")).quantize(CENT, ROUND_HALF_UP)
    return CanonicalReceipt(
        provider_code="demo",
        parser_version="demo/1",
        culture="el",
        source_url=f"https://demo.invalid/receipts/{seed}/{index}",
        issuer=Party(country_code="GR", vat_number=shop["vat"], legal_name=shop["legal_name"]),
        branch=Branch(address=Address(street=shop["street"], city="ΚΟΖΑΝΗ", postal_code="50100")),
        document=Document(
            kind=DocumentKind.CREDIT_NOTE if credit_note else DocumentKind.SALE,
            issued_at=issued_at,
            issued_date=day,
            currency="EUR",
            type_code="11.4" if credit_note else "11.1",
            number=str(index),
        ),
        identity=Identity(mark=f"8{seed:04d}{index:010d}"),
        totals=Totals(gross=gross, net=net, vat=gross - net),
        lines=lines,
        coverage=Coverage(line_items=bool(shop["items"])),
        payments=(
            Payment(amount=gross, method=rng.choice([PaymentMethod.CARD, PaymentMethod.CASH])),
        ),
    )


def _lines(rng: random.Random, shop: dict) -> tuple[Line, ...]:
    count = rng.randrange(1, min(len(shop["items"]), 8) + 1)
    lines = []
    for number, item in enumerate(rng.sample(shop["items"], count), start=1):
        code, description, unit, price = item
        weighed = unit == "kg"
        quantity = (
            Decimal(rng.randrange(200, 1500)) / 1000 if weighed else Decimal(rng.randrange(1, 4))
        )
        unit_price = (Decimal(price) * Decimal(rng.uniform(0.9, 1.15))).quantize(CENT)
        lines.append(
            Line(
                line_number=number,
                description=description,
                gross=(quantity * unit_price).quantize(CENT, ROUND_HALF_UP),
                quantity=quantity,
                unit=Unit.KG if weighed else Unit.PIECE,
                unit_price=unit_price,
                merchant_product_code=code,
            )
        )
    if shop["items"] and rng.random() < 0.15:
        lines.append(
            Line(line_number=len(lines) + 1, description="ΕΚΠΤΩΣΗ ΚΟΥΠΟΝΙ", gross=Decimal("-1.00"))
        )
    return tuple(lines)
