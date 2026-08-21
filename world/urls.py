from django.urls import path

from world import views


app_name = "world"

urlpatterns = [
    path("world-map/", views.global_world_map, name="global_world_map"),
    path(
        "world-map/inspect/",
        views.global_point_inspection,
        name="global_point_inspection",
    ),
    path("world-canon/", views.global_world_entry_list, name="global_world_entry_list"),
    path("world-audit/", views.global_audit_list, name="global_audit_list"),
    path(
        "world-audit/<int:audit_id>/",
        views.global_audit_detail,
        name="global_audit_detail",
    ),
    path("world-canon/new/", views.global_world_entry_create, name="global_world_entry_create"),
    path("world-canon/<int:entry_id>/", views.global_world_entry_detail, name="global_world_entry_detail"),
    path("world-canon/<int:entry_id>/edit/", views.global_world_entry_edit, name="global_world_entry_edit"),
    path("world-canon/<int:entry_id>/delete/", views.global_world_entry_delete, name="global_world_entry_delete"),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/",
        views.campaign_world_entry_list,
        name="campaign_world_entry_list",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/audit/",
        views.campaign_audit_list,
        name="campaign_audit_list",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/audit/<int:audit_id>/",
        views.campaign_audit_detail,
        name="campaign_audit_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/approvals/",
        views.campaign_approval_queue,
        name="campaign_approval_queue",
    ),
    path(
        "campaign/<uuid:campaign_id>/approvals/mine/",
        views.my_approval_requests,
        name="my_approval_requests",
    ),
    path(
        "campaign/<uuid:campaign_id>/approvals/<int:request_id>/",
        views.approval_request_detail,
        name="approval_request_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/approvals/<int:request_id>/approve/",
        views.approve_approval_request,
        name="approve_approval_request",
    ),
    path(
        "campaign/<uuid:campaign_id>/approvals/<int:request_id>/reject/",
        views.reject_approval_request,
        name="reject_approval_request",
    ),
    path(
        "campaign/<uuid:campaign_id>/approvals/<int:request_id>/cancel/",
        views.cancel_approval_request,
        name="cancel_approval_request",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/new/",
        views.campaign_world_entry_create,
        name="campaign_world_entry_create",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/<int:entry_id>/edit/",
        views.campaign_world_entry_edit,
        name="campaign_world_entry_edit",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/<int:entry_id>/delete/",
        views.campaign_world_entry_delete,
        name="campaign_world_entry_delete",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/<int:entry_id>/override/",
        views.campaign_world_entry_override,
        name="campaign_world_entry_override",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-canon/<int:entry_id>/override/action/",
        views.campaign_world_entry_override_action,
        name="campaign_world_entry_override_action",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-map/",
        views.world_map,
        name="world_map",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/world-map/inspect/",
        views.campaign_point_inspection,
        name="campaign_point_inspection",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/regions/<int:region_id>/",
        views.region_detail,
        name="region_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/regions/climate-preview/",
        views.region_climate_preview,
        name="region_climate_preview",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/regions/<int:region_id>/delete/",
        views.region_delete,
        name="region_delete",
    ),
]
