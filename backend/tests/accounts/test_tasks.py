from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.accounts.tasks import flush_expired_tokens

pytestmark = pytest.mark.django_db


def test_flush_expired_tokens_removes_only_expired(owner):
    now = timezone.now()
    OutstandingToken.objects.create(
        user=owner.user, jti="expired", token="t1", expires_at=now - timedelta(days=1)
    )
    OutstandingToken.objects.create(
        user=owner.user, jti="valid", token="t2", expires_at=now + timedelta(days=1)
    )
    flush_expired_tokens()
    assert list(OutstandingToken.objects.values_list("jti", flat=True)) == ["valid"]
