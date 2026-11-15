"""Household isolation matrix (requirements §5, TD §18.4).

Every route in the ``api-v1`` namespace must be classified here. A new route that
is neither in ISOLATION_CASES nor in NOT_HOUSEHOLD_SCOPED fails the suite, so no
endpoint can skip the isolation check.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.households.models import HouseholdInvitation, HouseholdMember
from apps.households.services import create_invitation
from apps.merchants.models import Merchant, Store
from apps.products.models import Product, ProductCategory
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from tests.factories import (
    CategoryFactory,
    ImportJobFactory,
    MemberFactory,
    MerchantFactory,
    ProductFactory,
    ReceiptFactory,
    ReceiptItemFactory,
    StoreFactory,
)

# Route name → why it needs no household isolation check.
NOT_HOUSEHOLD_SCOPED = {
    "auth-register": "public",
    "auth-login": "public",
    "auth-refresh": "public",
    "auth-logout": "acts on the caller's own refresh token",
    "auth-me": "the caller's own profile",
    "auth-password-change": "the caller's own account",
    "households-list": "lists only the caller's households (tests/households)",
    "households-join": "takes an invitation code, not a household id",
}


@dataclass(frozen=True)
class Foreign:
    """Objects that belong to household B (the caller is in household A)."""

    owner: HouseholdMember
    member: HouseholdMember
    invitation: HouseholdInvitation
    receipt: Receipt
    job: ReceiptImportJob
    item: ReceiptItem  # a product line waiting for review
    product: Product
    merchant: Merchant  # only household B bought there
    store: Store
    category: ProductCategory  # B's own category


@dataclass(frozen=True)
class Case:
    # "path": the household id is in the URL → expect 404.
    # "header": household-scoped by X-Household-ID → B's header gives 403,
    #           B's object ids give 404.
    scope: str
    kwargs: Callable[[Foreign], dict]
    methods: tuple[str, ...]
    # Without B's object id in the URL (lists, create): instead of a 404, the caller
    # gets their own household's view, which must not contain this id of B's.
    hidden: Callable[[Foreign], object] | None = None


def no_kwargs(_foreign: Foreign) -> dict:
    return {}


ISOLATION_CASES: dict[str, Case] = {
    "households-detail": Case("path", lambda f: {"pk": f.owner.household_id}, ("get", "patch")),
    "household-members": Case("path", lambda f: {"household_id": f.owner.household_id}, ("get",)),
    "household-member-detail": Case(
        "path",
        lambda f: {"household_id": f.owner.household_id, "member_id": f.member.pk},
        ("delete",),
    ),
    "household-invitations": Case(
        "path", lambda f: {"household_id": f.owner.household_id}, ("get", "post")
    ),
    "household-invitation-detail": Case(
        "path",
        lambda f: {"household_id": f.owner.household_id, "invitation_id": f.invitation.pk},
        ("delete",),
    ),
    "receipts-import": Case("header", no_kwargs, ("post",), hidden=lambda f: f.job.pk),
    "receipts-list": Case("header", no_kwargs, ("get",), hidden=lambda f: f.receipt.pk),
    "receipts-detail": Case("header", lambda f: {"pk": f.receipt.pk}, ("get", "patch", "delete")),
    "receipt-imports-list": Case("header", no_kwargs, ("get",), hidden=lambda f: f.job.pk),
    "receipt-imports-detail": Case("header", lambda f: {"pk": f.job.pk}, ("get",)),
    "receipt-imports-retry": Case("header", lambda f: {"pk": f.job.pk}, ("post",)),
    "products-list": Case("header", no_kwargs, ("get", "post"), hidden=lambda f: f.product.pk),
    "products-detail": Case("header", lambda f: {"pk": f.product.pk}, ("get", "patch")),
    "products-prices": Case("header", lambda f: {"pk": f.product.pk}, ("get",)),
    "products-price-comparison": Case("header", lambda f: {"pk": f.product.pk}, ("get",)),
    "products-merge": Case("header", lambda f: {"pk": f.product.pk}, ("post",)),
    "receipt-items-review": Case("header", no_kwargs, ("get",), hidden=lambda f: f.item.pk),
    "receipt-items-detail": Case("header", lambda f: {"pk": f.item.pk}, ("patch",)),
    "receipt-items-match": Case("header", lambda f: {"pk": f.item.pk}, ("post",)),
    "receipt-items-create-product": Case("header", lambda f: {"pk": f.item.pk}, ("post",)),
    "merchants-list": Case("header", no_kwargs, ("get",), hidden=lambda f: f.merchant.pk),
    "merchants-detail": Case("header", lambda f: {"pk": f.merchant.pk}, ("get",)),
    "stores-list": Case("header", no_kwargs, ("get",), hidden=lambda f: f.store.pk),
    "categories-list": Case("header", no_kwargs, ("get", "post"), hidden=lambda f: f.category.pk),
    "categories-detail": Case(
        "header", lambda f: {"pk": f.category.pk}, ("get", "patch", "delete")
    ),
    **{
        f"analytics-{name}": Case("header", no_kwargs, ("get",), hidden=lambda f: f.merchant.pk)
        for name in (
            "summary",
            "spending-by-category",
            "spending-by-merchant",
            "monthly-trend",
            "top-products",
        )
    },
}


def api_route_names() -> set[str]:
    names: set[str] = set()

    def walk(patterns, namespace):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, pattern.namespace or namespace)
            elif isinstance(pattern, URLPattern) and namespace == "api-v1" and pattern.name:
                names.add(pattern.name)

    walk(get_resolver().url_patterns, None)
    return names


@pytest.fixture
def foreign(db) -> Foreign:
    owner = MemberFactory(role=HouseholdMember.Role.OWNER)
    member = MemberFactory(household=owner.household, role=HouseholdMember.Role.MEMBER)
    invitation, _ = create_invitation(household=owner.household, created_by=owner.user)
    merchant = MerchantFactory()
    store = StoreFactory(merchant=merchant)
    receipt = ReceiptFactory(household=owner.household, merchant=merchant, store=store)
    ReceiptItemFactory(receipt=receipt)
    job = ImportJobFactory(
        household=owner.household,
        status=ReceiptImportJob.Status.FAILED,
        last_error_code="provider_format_changed",
        next_attempt_at=None,
    )
    item = ReceiptItemFactory(receipt=receipt, line_number=2)
    category = CategoryFactory(household=owner.household, name="Κάβα")
    product = ProductFactory(household=owner.household, name="ΓΑΛΑ", category=category)
    return Foreign(
        owner=owner,
        member=member,
        invitation=invitation,
        receipt=receipt,
        job=job,
        item=item,
        product=product,
        merchant=merchant,
        store=store,
        category=category,
    )


def call(client, method, url, **extra):
    if method == "get":
        return client.get(url, **extra)
    return getattr(client, method)(url, {}, format="json", **extra)


def test_every_api_route_is_classified():
    names = api_route_names()
    assert names, "no routes found in the api-v1 namespace"
    unclassified = names - ISOLATION_CASES.keys() - NOT_HOUSEHOLD_SCOPED.keys()
    assert not unclassified, f"classify these routes in tests/test_isolation.py: {unclassified}"
    stale = (ISOLATION_CASES.keys() | NOT_HOUSEHOLD_SCOPED.keys()) - names
    assert not stale, f"these routes no longer exist: {stale}"


@pytest.mark.parametrize("name", sorted(ISOLATION_CASES))
def test_other_households_are_invisible(name, owner_client, foreign):
    case = ISOLATION_CASES[name]
    url = reverse(f"api-v1:{name}", kwargs=case.kwargs(foreign))
    for method in case.methods:
        if case.scope == "header":
            header = {"HTTP_X_HOUSEHOLD_ID": str(foreign.owner.household_id)}
            assert call(owner_client, method, url, **header).status_code == 403, method
        response = call(owner_client, method, url)
        if case.hidden is None:
            assert response.status_code == 404, f"{method.upper()} {url} → {response.status_code}"
        else:
            assert response.status_code < 500, f"{method.upper()} {url} → {response.status_code}"
            assert str(case.hidden(foreign)) not in response.content.decode()

    # Nothing in household B changed.
    foreign.owner.household.refresh_from_db()
    foreign.invitation.refresh_from_db()
    foreign.job.refresh_from_db()
    assert HouseholdMember.objects.filter(pk=foreign.member.pk).exists()
    assert foreign.invitation.status == HouseholdInvitation.Status.PENDING
    assert foreign.owner.household.invitations.count() == 1
    assert Receipt.objects.filter(pk=foreign.receipt.pk, user_note="").exists()
    assert foreign.receipt.items.count() == 2
    assert foreign.job.status == ReceiptImportJob.Status.FAILED
    foreign.item.refresh_from_db()
    assert (foreign.item.match_status, foreign.item.product) == ("needs_review", None)
    assert Product.objects.filter(household=foreign.owner.household).get().name == "ΓΑΛΑ"
    assert ProductCategory.objects.filter(pk=foreign.category.pk, name="Κάβα").exists()
