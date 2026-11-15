from django.urls import path

from apps.households.api import views

household_list = views.HouseholdViewSet.as_view({"get": "list"})
household_detail = views.HouseholdViewSet.as_view({"get": "retrieve", "patch": "partial_update"})

urlpatterns = [
    path("households", household_list, name="households-list"),
    path("households/join", views.JoinHouseholdView.as_view(), name="households-join"),
    path("households/<uuid:pk>", household_detail, name="households-detail"),
    path(
        "households/<uuid:household_id>/members",
        views.MemberListView.as_view(),
        name="household-members",
    ),
    path(
        "households/<uuid:household_id>/members/<uuid:member_id>",
        views.MemberDetailView.as_view(),
        name="household-member-detail",
    ),
    path(
        "households/<uuid:household_id>/invitations",
        views.InvitationListCreateView.as_view(),
        name="household-invitations",
    ),
    path(
        "households/<uuid:household_id>/invitations/<uuid:invitation_id>",
        views.InvitationDetailView.as_view(),
        name="household-invitation-detail",
    ),
]
