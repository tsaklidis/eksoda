"""Household context resolution and queryset scoping (TD §6.3, requirements §5, §12.2).

Every household-scoped API view mixes in ``HouseholdScopedMixin``. It resolves the
household from the ``X-Household-ID`` header (or the user's only membership),
activates the household timezone, and filters ``get_queryset()`` so objects of other
households are never visible (they produce 404).
"""

import uuid
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.common.errors import HouseholdForbidden, HouseholdRequired
from apps.common.logging import bind_log_context
from apps.households.models import Household


def resolve_household(request) -> Household:
    """Return the household the request acts on.

    - Header present: it must name a household the user belongs to. Unknown and
      foreign households get the same 403, so ids cannot be probed.
    - No header: the user's only household. Several → 400; none → 403.
    """
    households = Household.objects.filter(members__user=request.user)
    raw = request.headers.get("X-Household-ID", "").strip()
    if raw:
        try:
            household = households.filter(pk=uuid.UUID(raw)).first()
        except ValueError:
            household = None
        if household is None:
            raise HouseholdForbidden()
        return household

    found = list(households[:2])
    if len(found) == 1:
        return found[0]
    if not found:
        raise HouseholdForbidden("You are not a member of any household.")
    raise HouseholdRequired()


class HouseholdScopedMixin:
    """Mix into DRF views whose data belongs to the request's household.

    Set ``household_lookup`` when the model reaches the household through a relation
    (e.g. ``"receipt__household"``).
    """

    household_lookup = "household"
    # Set in initial(); absent during OpenAPI generation, which never calls initial().
    household: Household

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # authentication, permissions, throttles
        self.household = resolve_household(request)
        bind_log_context(household_id=self.household.pk)
        timezone.activate(ZoneInfo(self.household.timezone))

    def finalize_response(self, request, response, *args, **kwargs):
        timezone.deactivate()
        return super().finalize_response(request, response, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation: no request user
            return super().get_queryset().none()
        return self.scope_queryset(super().get_queryset(), self.household)

    def scope_queryset(self, queryset, household):
        """Restrict ``queryset`` to the household. Override for data the household reaches
        indirectly (e.g. merchants through its receipts); never skip it."""
        return queryset.filter(**{self.household_lookup: household})
