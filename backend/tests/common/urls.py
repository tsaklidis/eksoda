"""Test-only routes that exercise HouseholdScopedMixin (used with @pytest.mark.urls)."""

from django.urls import path
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.households import HouseholdScopedMixin
from apps.households.models import HouseholdMember


class ContextView(HouseholdScopedMixin, APIView):
    def get(self, request):
        return Response(
            {
                "household_id": str(self.household.pk),
                "timezone": timezone.get_current_timezone_name(),
            }
        )


class MemberIdSerializer(serializers.ModelSerializer):
    class Meta:
        model = HouseholdMember
        fields = ["id"]


class ScopedMembersView(HouseholdScopedMixin, generics.ListAPIView):
    queryset = HouseholdMember.objects.all()
    serializer_class = MemberIdSerializer
    pagination_class = None


urlpatterns = [
    path("ctx", ContextView.as_view()),
    path("members", ScopedMembersView.as_view()),
]
