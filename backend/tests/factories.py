from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.common.text import fingerprint, normalize_text
from apps.households.models import Household, HouseholdMember
from apps.merchants.models import Merchant, Store
from apps.products.models import MerchantProductMapping, Product, ProductCategory
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem

DEFAULT_PASSWORD = "Correct-Horse-Battery-9"  # passes Django's password validators


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    display_name = factory.Sequence(lambda n: f"User {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", DEFAULT_PASSWORD)
        return model_class.objects.create_user(*args, password=password, **kwargs)


class HouseholdFactory(DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Household {n}")


class MemberFactory(DjangoModelFactory):
    class Meta:
        model = HouseholdMember

    household = factory.SubFactory(HouseholdFactory)
    user = factory.SubFactory(UserFactory)
    role = HouseholdMember.Role.OWNER


class MerchantFactory(DjangoModelFactory):
    class Meta:
        model = Merchant

    country_code = "GR"
    vat_number = factory.Sequence(lambda n: f"{800000000 + n:09d}")
    legal_name = factory.Sequence(lambda n: f"SHOP {n} ΑΕ")
    display_name = factory.Sequence(lambda n: f"Shop {n}")


class StoreFactory(DjangoModelFactory):
    class Meta:
        model = Store

    merchant = factory.SubFactory(MerchantFactory)
    branch_number = factory.Sequence(lambda n: str(n))
    street = factory.Sequence(lambda n: f"ΟΔΟΣ {n}")
    city = "ΚΟΖΑΝΗ"
    postal_code = "50100"


class ReceiptFactory(DjangoModelFactory):
    class Meta:
        model = Receipt

    household = factory.SubFactory(HouseholdFactory)
    merchant = factory.SubFactory(MerchantFactory)
    store = None
    provider_code = "impact"
    parser_version = "impact/1"
    issuer_country = "GR"
    issuer_vat = factory.SelfAttribute("merchant.vat_number")
    mark = factory.Sequence(lambda n: f"{400000000000000 + n}")
    document_kind = Receipt.Kind.SALE
    document_type_code = "11.1"
    document_number = factory.Sequence(lambda n: f"1-{n}")
    issued_at = factory.LazyFunction(timezone.now)
    gross_total = Decimal("9.15")
    net_total = Decimal("8.10")
    vat_total = Decimal("1.05")
    payment_method = Receipt.PaymentMethod.CARD
    source_url = factory.Sequence(lambda n: f"https://einvoice.impact.gr/p/EL1/{n:040d}/{'0' * 32}")
    source_url_fingerprint = factory.LazyAttribute(lambda o: fingerprint(o.source_url))


class ReceiptItemFactory(DjangoModelFactory):
    class Meta:
        model = ReceiptItem

    receipt = factory.SubFactory(ReceiptFactory)
    household = factory.SelfAttribute("receipt.household")
    line_number = factory.Sequence(lambda n: n + 1)
    line_type = ReceiptItem.LineType.PRODUCT
    description = "ΓΑΛΑ ΦΡΕΣΚΟ 1L"
    normalized_description = factory.LazyAttribute(lambda o: normalize_text(o.description))
    quantity = Decimal("1")
    unit = ReceiptItem.Unit.PIECE
    unit_price = Decimal("1.50")
    gross_amount = Decimal("1.50")
    match_status = factory.LazyAttribute(
        lambda o: (
            ReceiptItem.MatchStatus.NEEDS_REVIEW
            if o.line_type == ReceiptItem.LineType.PRODUCT
            else ReceiptItem.MatchStatus.NOT_A_PRODUCT
        )
    )


class ImportJobFactory(DjangoModelFactory):
    class Meta:
        model = ReceiptImportJob

    household = factory.SubFactory(HouseholdFactory)
    requested_by = None
    provider_code = "impact"
    url_identity = factory.Sequence(lambda n: f"GR:094062259:{n:040X}")
    submitted_url = factory.Sequence(
        lambda n: f"https://einvoice.impact.gr/p/EL094062259/{n:040X}/{'0' * 32}"
    )
    url_fingerprint = factory.LazyAttribute(lambda o: fingerprint(o.submitted_url))
    issuer_vat = "094062259"
    status = ReceiptImportJob.Status.PENDING
    next_attempt_at = factory.LazyFunction(timezone.now)


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = ProductCategory

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"ΠΡΟΪΟΝ {n}")


class MappingFactory(DjangoModelFactory):
    class Meta:
        model = MerchantProductMapping

    household = factory.SelfAttribute("product.household")
    merchant = factory.SubFactory(MerchantFactory)
    product = factory.SubFactory(ProductFactory)
    merchant_product_code = factory.Sequence(lambda n: f"C{n}")
    normalized_description = factory.LazyAttribute(lambda o: normalize_text(o.product.name))
    last_seen_description = factory.SelfAttribute("product.name")
