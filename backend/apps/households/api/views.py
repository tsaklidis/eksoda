"""Household, membership and invitation endpoints (requirements §12.3).

These routes take the household from the URL path. A household the caller does
not belong to answers 404, like any object outside the caller's scope.
"""

from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.households import services
from apps.households.api.serializers import (
    CreatedInvitationSerializer,
    HouseholdSerializer,
    InvitationSerializer,
    JoinSerializer,
    MemberSerializer,
)
from apps.households.models import Household, HouseholdInvitation, HouseholdMember


class JoinRateThrottle(UserRateThrottle):
    scope = "join"


@extend_schema(tags=["households"])
class HouseholdViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HouseholdSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return Household.objects.none()
        role = HouseholdMember.objects.filter(
            household=OuterRef("pk"), user=self.request.user
        ).values("role")[:1]
        return (
            Household.objects.filter(members__user=self.request.user)
            .annotate(role=Subquery(role))
            .order_by("name")
        )

    def update(self, request, *args, **kwargs):
        # Check ownership before validating input: members get 403 whatever they send.
        services.require_owner(services.get_membership_or_404(request.user, kwargs["pk"]))
        return super().update(request, *args, **kwargs)


@extend_schema(tags=["households"])
class MemberListView(generics.ListAPIView):
    serializer_class = MemberSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return HouseholdMember.objects.none()
        membership = services.get_membership_or_404(self.request.user, self.kwargs["household_id"])
        return HouseholdMember.objects.filter(household=membership.household).select_related("user")


@extend_schema(tags=["households"])
class MemberDetailView(generics.DestroyAPIView):
    """Owners remove members; any member may remove themselves (leave)."""

    serializer_class = MemberSerializer

    def get_object(self):
        self.actor = services.get_membership_or_404(self.request.user, self.kwargs["household_id"])
        return generics.get_object_or_404(
            HouseholdMember, household=self.actor.household, pk=self.kwargs["member_id"]
        )

    def perform_destroy(self, instance):
        services.remove_member(actor=self.actor, target=instance)


@extend_schema(tags=["households"])
class InvitationListCreateView(generics.ListCreateAPIView):
    pagination_class = None

    def get_serializer_class(self):
        return (
            CreatedInvitationSerializer if self.request.method == "POST" else InvitationSerializer
        )

    def _owner_membership(self) -> HouseholdMember:
        membership = services.get_membership_or_404(self.request.user, self.kwargs["household_id"])
        services.require_owner(membership)
        return membership

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return HouseholdInvitation.objects.none()
        membership = self._owner_membership()
        return HouseholdInvitation.objects.filter(household=membership.household).select_related(
            "created_by"
        )

    @extend_schema(request=InvitationSerializer, responses={201: CreatedInvitationSerializer})
    def create(self, request, *args, **kwargs):
        membership = self._owner_membership()
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, code = services.create_invitation(
            household=membership.household,
            created_by=request.user,
            role=serializer.validated_data.get("role", HouseholdMember.Role.MEMBER),
        )
        invitation.code = code
        return Response(
            CreatedInvitationSerializer(invitation).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["households"])
class InvitationDetailView(generics.DestroyAPIView):
    """Revoke a pending invitation (owner only)."""

    serializer_class = InvitationSerializer

    def get_object(self):
        membership = services.get_membership_or_404(self.request.user, self.kwargs["household_id"])
        services.require_owner(membership)
        return generics.get_object_or_404(
            HouseholdInvitation, household=membership.household, pk=self.kwargs["invitation_id"]
        )

    def perform_destroy(self, instance):
        services.revoke_invitation(instance)


@extend_schema(tags=["households"])
class JoinHouseholdView(APIView):
    throttle_classes = [JoinRateThrottle]

    @extend_schema(request=JoinSerializer, responses={201: MemberSerializer})
    def post(self, request):
        serializer = JoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            code=serializer.validated_data["code"], user=request.user
        )
        return Response(MemberSerializer(membership).data, status=status.HTTP_201_CREATED)
