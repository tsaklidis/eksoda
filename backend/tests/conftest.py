import os

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.households.models import HouseholdMember
from tests.factories import MemberFactory
from tests.utils import client_for


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="Rewrite golden files (tests/fixtures/**/expected) instead of comparing.",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(reason="live test: set RUN_LIVE_TESTS=1 (make test-live)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def update_golden(request) -> bool:
    return request.config.getoption("--update-golden")


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in the cache; never let them leak between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(db) -> HouseholdMember:
    """Owner of household A."""
    return MemberFactory(role=HouseholdMember.Role.OWNER)


@pytest.fixture
def member(owner) -> HouseholdMember:
    """Plain member of household A."""
    return MemberFactory(household=owner.household, role=HouseholdMember.Role.MEMBER)


@pytest.fixture
def outsider(db) -> HouseholdMember:
    """Owner of an unrelated household B."""
    return MemberFactory(role=HouseholdMember.Role.OWNER)


@pytest.fixture
def owner_client(owner) -> APIClient:
    return client_for(owner.user)


@pytest.fixture
def member_client(member) -> APIClient:
    return client_for(member.user)


@pytest.fixture
def outsider_client(outsider) -> APIClient:
    return client_for(outsider.user)
