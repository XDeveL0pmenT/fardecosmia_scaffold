from django.urls import path

from world import views


app_name = "world"

urlpatterns = [
    path("world-map/", views.global_world_map, name="global_world_map"),
    path(
        "campaign/<uuid:campaign_id>/gm/world-map/",
        views.world_map,
        name="world_map",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/regions/<int:region_id>/",
        views.region_detail,
        name="region_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/gm/regions/<int:region_id>/delete/",
        views.region_delete,
        name="region_delete",
    ),
]
