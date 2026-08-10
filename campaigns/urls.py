from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("", views.campaign_list, name="list"),
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
]
