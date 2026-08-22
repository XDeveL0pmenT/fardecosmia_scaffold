from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("", views.campaign_list, name="list"),
    path("campaign/create/", views.campaign_create_view, name="create"),
    path("invite/resume/", views.invitation_resume_view, name="invitation_resume"),
    path(
        "invite/resume/accept/",
        views.accept_resumed_invitation_view,
        name="invitation_resume_accept",
    ),
    path("invite/<str:token>/", views.invitation_detail_view, name="invitation_detail"),
    path(
        "invite/<str:token>/accept/",
        views.accept_invitation_view,
        name="invitation_accept",
    ),
    path(
        "campaign/<uuid:campaign_id>/",
        views.campaign_detail,
        name="campaign_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/edit/",
        views.campaign_edit_view,
        name="edit",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/",
        views.campaign_members_view,
        name="members",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/invite/",
        views.create_invitation_view,
        name="invitation_create",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/invite/<int:invitation_id>/revoke/",
        views.revoke_invitation_view,
        name="invitation_revoke",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/<int:membership_id>/promote/",
        views.promote_member_view,
        name="member_promote",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/<int:membership_id>/demote/",
        views.demote_member_view,
        name="member_demote",
    ),
    path(
        "campaign/<uuid:campaign_id>/members/<int:membership_id>/remove/",
        views.remove_member_view,
        name="member_remove",
    ),
    path("campaign/<uuid:campaign_id>/gm/", views.gm_dashboard, name="gm_dashboard"),
    path(
        "campaign/<uuid:campaign_id>/gm/advance-time/",
        views.advance_time_view,
        name="advance_time",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/atmosphere/",
        views.configure_atmosphere_view,
        name="configure_atmosphere",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/time-simulation/",
        views.configure_time_simulation_view,
        name="configure_time_simulation",
    ),
]
