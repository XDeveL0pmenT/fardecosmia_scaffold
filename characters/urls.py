from django.urls import path

from . import views


app_name = "characters"

urlpatterns = [
    path(
        "campaign/<uuid:campaign_id>/characters/",
        views.gm_character_list,
        name="gm_list",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/create/",
        views.gm_character_create,
        name="create",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/",
        views.character_detail,
        name="detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/edit/",
        views.gm_character_edit,
        name="edit",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/assign/",
        views.gm_character_assign,
        name="assign",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/initial-placement/",
        views.gm_character_initial_placement,
        name="initial_placement",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/archive/",
        views.gm_character_archive,
        name="archive",
    ),
    path(
        "campaign/<uuid:campaign_id>/characters/<int:character_id>/restore/",
        views.gm_character_restore,
        name="restore",
    ),
    path(
        "campaign/<uuid:campaign_id>/my-characters/",
        views.player_character_list,
        name="player_list",
    ),
    path(
        "campaign/<uuid:campaign_id>/my-characters/active/",
        views.player_character_switch,
        name="switch_active",
    ),
    path(
        "campaign/<uuid:campaign_id>/thoughts/",
        views.personal_note_list,
        name="personal_note_list",
    ),
    path(
        "campaign/<uuid:campaign_id>/thoughts/hold/",
        views.personal_note_hold,
        name="personal_note_hold",
    ),
    path(
        "campaign/<uuid:campaign_id>/thoughts/<uuid:note_id>/",
        views.personal_note_detail,
        name="personal_note_detail",
    ),
    path(
        "campaign/<uuid:campaign_id>/thoughts/<uuid:note_id>/return/",
        views.personal_note_return,
        name="personal_note_return",
    ),
    path(
        "campaign/<uuid:campaign_id>/thoughts/<uuid:note_id>/release/",
        views.personal_note_release,
        name="personal_note_release",
    ),
]
