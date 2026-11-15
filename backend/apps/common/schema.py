"""drf-spectacular extensions (imported in CommonConfig.ready)."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.openapi import AutoSchema as SpectacularAutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

HOUSEHOLD_PARAMETER = OpenApiParameter(
    name="X-Household-ID",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=False,
    description="The household to act on. Required only when you belong to several.",
)


class JWTScheme(SimpleJWTScheme):
    """Documents apps.common.authentication.JWTAuthentication as Bearer JWT."""

    target_class = "apps.common.authentication.JWTAuthentication"
    name = "jwtAuth"


class AutoSchema(SpectacularAutoSchema):
    """Documents the X-Household-ID header on every household-scoped operation."""

    def get_override_parameters(self):
        from apps.common.households import HouseholdScopedMixin

        parameters = super().get_override_parameters()
        if isinstance(self.view, HouseholdScopedMixin):
            parameters = [*parameters, HOUSEHOLD_PARAMETER]
        return parameters
