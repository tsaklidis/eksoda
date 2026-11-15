from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, transaction

from apps.common.text import normalize_text
from apps.merchants.models import Merchant, Store
from apps.merchants.services import (
    derive_display_name,
    normalize_address,
    resolve_merchant,
    resolve_store,
)
from apps.receipts.canonical import Address, Branch, Party
from tests.factories import MerchantFactory, StoreFactory

pytestmark = pytest.mark.django_db

JAN = datetime(2026, 1, 10, 12, tzinfo=UTC)
MAR = datetime(2026, 3, 10, 12, tzinfo=UTC)
FEB = datetime(2026, 2, 10, 12, tzinfo=UTC)


def party(**changes) -> Party:
    values = {
        "country_code": "GR",
        "vat_number": "094062259",
        "legal_name": "METRO ΑΕΒΕ ΑΝΩΝΥΜΗ ΕΜΠΟΡΙΚΗ & ΒΙΟΜΗΧΑΝΙΚΗ ΕΤΑΙΡΙΑ",
        "activity": "ΛΙΑΝΙΚΟ ΕΜΠΟΡΙΟ",
        "tax_office": "ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ",
        "address": Address(street="ΣΩΡΟΥ", number="1", city="ΜΕΤΑΜΟΡΦΩΣΗ", postal_code="14451"),
    }
    return Party(**(values | changes))


@pytest.mark.parametrize(
    ("legal_name", "display_name"),
    [
        ("METRO ΑΕΒΕ ΑΝΩΝΥΜΗ ΕΜΠΟΡΙΚΗ & ΒΙΟΜΗΧΑΝΙΚΗ ΕΤΑΙΡΙΑ", "Metro"),
        ("LIDL", "Lidl"),
        ("ΑΛΦΑ ΒΗΤΑ ΒΑΣΙΛΟΠΟΥΛΟΣ ΜΟΝΟΠΡΟ", "Αλφα Βητα Βασιλοπουλος"),  # final sigma kept
        ("ΚΡΙΚΡΙ Α.Ε.", "Κρικρι"),
        ("ΠΑΠΑΔΟΠΟΥΛΟΣ ΚΑΙ ΣΙΑ Ο.Ε.", "Παπαδοπουλος"),
        ("ΜΑΡΚΟΥ & ΣΙΑ ΕΕ", "Μαρκου"),
        ("Μ & Σ ΜΙΚΕ", "Μ & Σ"),
        ("ΦΟΥΡΝΟΣ - ΙΚΕ", "Φουρνος"),
        ("ΑΕ", "Αε"),  # nothing but a legal form: keep the name
    ],
)
def test_display_name_is_the_brand_part_of_the_legal_name(legal_name, display_name):
    assert derive_display_name(legal_name) == display_name


def test_new_merchant_takes_the_receipt_details():
    merchant = resolve_merchant(party(), as_of=JAN)
    assert (merchant.country_code, merchant.vat_number) == ("GR", "094062259")
    assert merchant.display_name == "Metro"
    assert merchant.street == "ΣΩΡΟΥ"
    assert merchant.street_number == "1"
    assert merchant.postal_code == "14451"
    assert merchant.details_as_of == JAN
    assert resolve_merchant(party(), as_of=JAN) == merchant
    assert Merchant.objects.count() == 1


def test_newer_receipts_refresh_details_and_older_ones_only_fill_blanks():
    merchant = resolve_merchant(party(tax_office=None), as_of=FEB)
    moved = Address(street="ΝΕΑ ΟΔΟΣ", number="5", city="ΑΘΗΝΑ", postal_code="10000")

    resolve_merchant(party(address=moved, tax_office="ΔΟΥ Α"), as_of=JAN)  # older
    merchant.refresh_from_db()
    assert merchant.street == "ΣΩΡΟΥ"  # not replaced by an older receipt
    assert merchant.tax_office == "ΔΟΥ Α"  # but blanks are filled
    assert merchant.details_as_of == FEB

    resolve_merchant(party(address=moved), as_of=MAR)  # newer
    merchant.refresh_from_db()
    assert (merchant.street, merchant.city) == ("ΝΕΑ ΟΔΟΣ", "ΑΘΗΝΑ")
    assert merchant.details_as_of == MAR


def test_truncated_legal_names_never_replace_the_full_one():
    merchant = resolve_merchant(
        party(legal_name="ΑΛΦΑ ΒΗΤΑ ΒΑΣΙΛΟΠΟΥΛΟΣ ΜΟΝΟΠΡΟΣΩΠΗ ΑΕ"), as_of=JAN
    )
    resolve_merchant(party(legal_name="ΑΛΦΑ ΒΗΤΑ ΒΑΣΙΛΟΠΟΥΛΟΣ ΜΟΝΟΠΡΟ"), as_of=MAR)
    merchant.refresh_from_db()
    assert merchant.legal_name == "ΑΛΦΑ ΒΗΤΑ ΒΑΣΙΛΟΠΟΥΛΟΣ ΜΟΝΟΠΡΟΣΩΠΗ ΑΕ"


def test_display_name_follows_the_legal_name_until_staff_change_it():
    merchant = resolve_merchant(party(legal_name="ΠΑΛΙΟ ΟΝΟΜΑ ΑΕ"), as_of=JAN)
    resolve_merchant(party(legal_name="ΝΕΟ ΟΝΟΜΑ ΑΕ"), as_of=FEB)
    merchant.refresh_from_db()
    assert merchant.display_name == "Νεο Ονομα"

    Merchant.objects.filter(pk=merchant.pk).update(display_name="My grocer")
    resolve_merchant(party(legal_name="ΑΛΛΟ ΟΝΟΜΑ ΑΕ"), as_of=MAR)
    merchant.refresh_from_db()
    assert merchant.legal_name == "ΑΛΛΟ ΟΝΟΜΑ ΑΕ"
    assert merchant.display_name == "My grocer"


def test_long_public_values_are_cut_to_the_column_size():
    merchant = resolve_merchant(party(legal_name="Χ" * 300, gemi_number="1" * 40), as_of=JAN)
    assert len(merchant.legal_name) == 255
    assert len(merchant.gemi_number) == 32


def test_store_by_branch_number_refreshes_its_address():
    merchant = MerchantFactory()
    branch = Branch(number="264", address=Address(street="ΜΙΝΩΤΗ", city="ΚΟΖΑΝΗ"))
    store = resolve_store(merchant, branch, as_of=JAN)
    assert store.branch_number == "264"
    assert store.normalized_address == normalize_text("ΜΙΝΩΤΗ ΚΟΖΑΝΗ")

    moved = Branch(number="264", address=Address(street="ΠΑΥΛΟΥ ΜΕΛΑ", number="3", city="ΚΟΖΑΝΗ"))
    assert resolve_store(merchant, moved, as_of=FEB) == store
    store.refresh_from_db()
    assert store.street == "ΠΑΥΛΟΥ ΜΕΛΑ 3"
    assert store.normalized_address == normalize_text("ΠΑΥΛΟΥ ΜΕΛΑ 3 ΚΟΖΑΝΗ")
    assert Store.objects.count() == 1


def test_store_without_branch_number_is_matched_on_its_address():
    merchant = MerchantFactory()
    address = Address(street="2 ΧΛΜ Ε.Ο. ΚΟΖΑΝΗΣ", city="ΚΟΖΑΝΗΣ", postal_code="50100")
    store = resolve_store(merchant, Branch(address=address), as_of=JAN)
    assert store.branch_number is None
    same = Address(street="2 χλμ Ε.Ο. Κοζάνης", city="Κοζάνης", postal_code="50100")
    assert resolve_store(merchant, Branch(address=same), as_of=FEB) == store
    other = Address(street="ΑΛΛΗ ΟΔΟΣ", city="ΚΟΖΑΝΗΣ", postal_code="50100")
    assert resolve_store(merchant, Branch(address=other), as_of=FEB) != store
    # Another merchant at the same address is another store.
    assert resolve_store(MerchantFactory(), Branch(address=address), as_of=JAN) != store


@pytest.mark.parametrize("branch", [None, Branch(), Branch(address=Address(country="ΕΛΛΑΔΑ"))])
def test_no_store_without_branch_number_or_address(branch):
    assert resolve_store(MerchantFactory(), branch, as_of=JAN) is None
    assert normalize_address(branch.address if branch else None) == ""


def test_merchant_and_store_uniqueness():
    merchant = MerchantFactory(vat_number="123456789")
    with pytest.raises(IntegrityError), transaction.atomic():
        MerchantFactory(vat_number="123456789")
    StoreFactory(merchant=merchant, branch_number="1")
    with pytest.raises(IntegrityError), transaction.atomic():
        StoreFactory(merchant=merchant, branch_number="1")
    StoreFactory(merchant=merchant, branch_number=None, normalized_address="Α 1")
    with pytest.raises(IntegrityError), transaction.atomic():
        StoreFactory(merchant=merchant, branch_number=None, normalized_address="Α 1")
    # Stores without an address key are not constrained.
    StoreFactory(merchant=merchant, branch_number=None, normalized_address="")
    StoreFactory(merchant=merchant, branch_number=None, normalized_address="")


def test_store_label():
    assert StoreFactory.build(display_name="Main").label == "Main"
    assert StoreFactory.build(street="ΟΔΟΣ 1", city="ΚΟΖΑΝΗ").label == "ΟΔΟΣ 1, ΚΟΖΑΝΗ"
    assert StoreFactory.build(street="", city="", branch_number="7").label == "#7"
