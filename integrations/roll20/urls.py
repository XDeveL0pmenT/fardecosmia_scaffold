from django.urls import path

from . import views

app_name = "roll20"

urlpatterns = [
    path("ping/", views.ping, name="ping"),
    path("sync/", views.sync_character, name="sync"),
]
