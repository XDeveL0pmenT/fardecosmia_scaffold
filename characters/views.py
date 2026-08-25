from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from campaigns.models import Campaign, CampaignMembership
from campaigns.time_controls import TIME_ADVANCE_UNITS
from characters.forms import (
    CharacterAssignmentForm,
    CharacterIdentityForm,
    CharacterInitialPlacementForm,
    CharacterNoteForm,
)
from characters.models import Character, CharacterNote
from characters.notes import (
    CharacterNotesUnavailable,
    get_active_note_character,
    get_personal_note,
    hold_personal_note,
    personal_notes_for,
    release_personal_note,
    return_to_personal_note,
)
from characters.services import (
    CharacterConflict,
    CharacterLocationConflict,
    assign_character,
    create_character,
    get_effective_character_location,
    initialize_character_location,
    set_active_character,
    set_character_archived,
    update_character,
)
from characters.workspace import build_character_workspace_context
from world.services.access import require_campaign_gm, require_campaign_member
from world.services.atlas import build_atlas_config


def _campaign(campaign_id):
    return get_object_or_404(Campaign, pk=campaign_id)


def _gm_context(campaign, **extra):
    return {
        "campaign": campaign,
        "can_advance_time": True,
        "time_advance_units": TIME_ADVANCE_UNITS,
        **extra,
    }


@login_required
def gm_character_list(request, campaign_id):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    selected_tab = request.GET.get("tab", "active")
    queryset = campaign.characters.select_related(
        "owner__user", "roll20_binding"
    ).order_by("name", "pk")
    if selected_tab == "archive":
        queryset = queryset.filter(is_active=False)
    elif selected_tab == "unassigned":
        queryset = queryset.filter(is_active=True, owner__isnull=True)
    elif selected_tab == "all":
        pass
    else:
        selected_tab = "active"
        queryset = queryset.filter(is_active=True)
    return render(
        request,
        "characters/gm_character_list.html",
        _gm_context(campaign, characters=queryset, selected_tab=selected_tab),
    )


@login_required
def gm_character_create(request, campaign_id):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    form = CharacterIdentityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        character = create_character(
            campaign=campaign,
            actor=request.user,
            name=form.cleaned_data["name"],
            biography=form.cleaned_data["biography"],
        )
        messages.success(request, f"Персонаж «{character.name}» создан.")
        return redirect("characters:detail", campaign.pk, character.pk)
    return render(
        request,
        "characters/character_form.html",
        _gm_context(campaign, form=form, mode="create", character=None),
    )


@login_required
def gm_character_edit(request, campaign_id, character_id):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    character = get_object_or_404(Character, pk=character_id, campaign=campaign)
    form = CharacterIdentityForm(request.POST or None, instance=character)
    if request.method == "POST" and form.is_valid():
        character = update_character(
            campaign=campaign,
            character_id=character.pk,
            actor=request.user,
            name=form.cleaned_data["name"],
            biography=form.cleaned_data["biography"],
        )
        messages.success(request, "Основная информация персонажа обновлена.")
        return redirect("characters:detail", campaign.pk, character.pk)
    return render(
        request,
        "characters/character_form.html",
        _gm_context(campaign, form=form, mode="edit", character=character),
    )


@login_required
def character_detail(request, campaign_id, character_id):
    campaign = _campaign(campaign_id)
    membership = require_campaign_member(request.user, campaign)
    is_gm = request.user.is_superuser or membership.role == CampaignMembership.Role.GM
    queryset = Character.objects.select_related(
        "owner__user", "campaign", "roll20_binding", "location_state"
    ).filter(campaign=campaign)
    if not is_gm:
        queryset = queryset.filter(owner=membership, is_active=True)
    character = get_object_or_404(queryset, pk=character_id)
    if not is_gm:
        # Compatibility route only: normal Player navigation is the Campaign
        # index, which now is the active Character Workspace.
        return redirect("campaigns:campaign_detail", campaign_id=campaign.pk)
    assignment_form = None
    assignment_form = CharacterAssignmentForm(
        campaign=campaign,
        initial={"player": character.owner_id},
    )
    return render(
        request,
        "characters/character_detail.html",
        {
            "campaign": campaign,
            "character": character,
            "membership": membership,
            "is_campaign_gm": is_gm,
            "assignment_form": assignment_form,
            "character_location": get_effective_character_location(character),
            "is_active_character": False,
            "can_advance_time": True,
            "time_advance_units": TIME_ADVANCE_UNITS,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def gm_character_initial_placement(request, campaign_id, character_id):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    character = get_object_or_404(
        Character.objects.select_related("location_state"),
        pk=character_id,
        campaign=campaign,
    )
    if not character.is_active:
        raise PermissionDenied(
            "Архивному персонажу нельзя задавать исходное положение."
        )
    if get_effective_character_location(character) is not None:
        messages.info(request, "Исходное положение этого персонажа уже установлено.")
        return redirect("characters:detail", campaign.pk, character.pk)

    form = CharacterInitialPlacementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            initialize_character_location(
                campaign=campaign,
                character_id=character.pk,
                actor=request.user,
                latitude=form.cleaned_data["latitude"],
                longitude=form.cleaned_data["longitude"],
            )
        except CharacterLocationConflict as error:
            messages.error(request, error.messages[0])
            return redirect("characters:detail", campaign.pk, character.pk)
        messages.success(
            request,
            f"Исходное положение персонажа «{character.name}» сохранено.",
        )
        return redirect("characters:detail", campaign.pk, character.pk)

    return render(
        request,
        "characters/character_initial_placement.html",
        _gm_context(
            campaign,
            character=character,
            form=form,
            atlas_config=build_atlas_config(
                campaign=campaign,
                active_layer="base",
            ),
        ),
    )


@login_required
@require_POST
def gm_character_assign(request, campaign_id, character_id):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    character = get_object_or_404(Character, pk=character_id, campaign=campaign)
    form = CharacterAssignmentForm(request.POST, campaign=campaign)
    if not form.is_valid():
        messages.error(request, "Выберите игрока из этой кампании.")
        return redirect("characters:detail", campaign.pk, character.pk)
    player = form.cleaned_data["player"]
    try:
        character = assign_character(
            campaign=campaign,
            character_id=character.pk,
            actor=request.user,
            membership_id=None if player is None else player.pk,
        )
    except (CampaignMembership.DoesNotExist, CharacterConflict, ValidationError):
        messages.error(request, "Назначить можно только игрока из этой кампании.")
        return redirect("characters:detail", campaign.pk, character.pk)
    if character.owner is None:
        messages.success(request, "Назначение игроку снято; персонаж сохранён в кампании.")
    else:
        messages.success(request, f"Персонаж назначен игроку {character.owner.user}.")
    return redirect("characters:detail", campaign.pk, character.pk)


def _set_archive(request, campaign_id, character_id, *, archived):
    campaign = _campaign(campaign_id)
    require_campaign_gm(request.user, campaign)
    try:
        character = set_character_archived(
            campaign=campaign,
            character_id=character_id,
            actor=request.user,
            archived=archived,
        )
    except Character.DoesNotExist as error:
        raise Http404("Персонаж не найден.") from error
    messages.success(
        request,
        (
            f"Персонаж «{character.name}» перемещён в архив."
            if archived
            else f"Персонаж «{character.name}» возвращён из архива."
        ),
    )
    return redirect("characters:detail", campaign.pk, character.pk)


@login_required
@require_POST
def gm_character_archive(request, campaign_id, character_id):
    return _set_archive(request, campaign_id, character_id, archived=True)


@login_required
@require_POST
def gm_character_restore(request, campaign_id, character_id):
    return _set_archive(request, campaign_id, character_id, archived=False)


@login_required
def player_character_list(request, campaign_id):
    campaign = _campaign(campaign_id)
    membership = require_campaign_member(request.user, campaign)
    if membership is None or membership.role != CampaignMembership.Role.PLAYER:
        raise PermissionDenied("Для рабочего пространства персонажа нужно участие в кампании.")
    return render(
        request,
        "characters/character_workspace.html",
        build_character_workspace_context(
            campaign=campaign,
            membership=membership,
        ),
    )


@login_required
@require_POST
def player_character_switch(request, campaign_id):
    campaign = _campaign(campaign_id)
    try:
        character_id = int(request.POST.get("character", ""))
        character = set_active_character(
            campaign=campaign,
            actor=request.user,
            character_id=character_id,
        )
    except (TypeError, ValueError, Character.DoesNotExist, CharacterConflict):
        raise PermissionDenied("Нельзя выбрать этого персонажа.")
    messages.success(request, f"Теперь активный персонаж — {character.name}.")
    return redirect("campaigns:campaign_detail", campaign_id=campaign.pk)


def _thought_context(*, campaign, character, **extra):
    from world.services.ambience import build_character_ambience

    return {
        "campaign": campaign,
        "active_character": character,
        "character_ambience": build_character_ambience(character, campaign),
        **extra,
    }


@login_required
def personal_note_list(request, campaign_id):
    from django.core.paginator import Paginator

    campaign = _campaign(campaign_id)
    character, notes = personal_notes_for(
        actor=request.user,
        campaign=campaign,
    )
    page = Paginator(notes, 24).get_page(request.GET.get("page"))
    return render(
        request,
        "characters/personal_note_list.html",
        _thought_context(campaign=campaign, character=character, page=page),
    )


@login_required
@require_http_methods(["GET", "POST"])
def personal_note_hold(request, campaign_id):
    campaign = _campaign(campaign_id)
    _membership, character = get_active_note_character(
        actor=request.user,
        campaign=campaign,
    )
    form = CharacterNoteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            note = hold_personal_note(
                actor=request.user,
                campaign=campaign,
                memo=form.cleaned_data["memo"],
                body=form.cleaned_data["body"],
            )
        except CharacterNotesUnavailable:
            raise PermissionDenied("Активный персонаж изменился.")
        messages.success(request, "Мысль удержана.")
        return redirect("characters:personal_note_detail", campaign.pk, note.pk)
    return render(
        request,
        "characters/personal_note_form.html",
        _thought_context(
            campaign=campaign,
            character=character,
            form=form,
            editing=False,
        ),
    )


@login_required
def personal_note_detail(request, campaign_id, note_id):
    campaign = _campaign(campaign_id)
    try:
        character, note = get_personal_note(
            actor=request.user,
            campaign=campaign,
            note_id=note_id,
        )
    except CharacterNote.DoesNotExist as error:
        raise Http404("Мысль не найдена.") from error
    return render(
        request,
        "characters/personal_note_detail.html",
        _thought_context(campaign=campaign, character=character, note=note),
    )


@login_required
@require_http_methods(["GET", "POST"])
def personal_note_return(request, campaign_id, note_id):
    campaign = _campaign(campaign_id)
    try:
        character, note = get_personal_note(
            actor=request.user,
            campaign=campaign,
            note_id=note_id,
        )
    except CharacterNote.DoesNotExist as error:
        raise Http404("Мысль не найдена.") from error
    form = CharacterNoteForm(request.POST or None, instance=note)
    if request.method == "POST" and form.is_valid():
        try:
            note = return_to_personal_note(
                actor=request.user,
                campaign=campaign,
                note_id=note.pk,
                memo=form.cleaned_data["memo"],
                body=form.cleaned_data["body"],
            )
        except CharacterNote.DoesNotExist as error:
            raise Http404("Мысль не найдена.") from error
        messages.success(request, "Мысль вновь обрела форму.")
        return redirect("characters:personal_note_detail", campaign.pk, note.pk)
    return render(
        request,
        "characters/personal_note_form.html",
        _thought_context(
            campaign=campaign,
            character=character,
            form=form,
            editing=True,
            note=note,
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def personal_note_release(request, campaign_id, note_id):
    campaign = _campaign(campaign_id)
    try:
        character, note = get_personal_note(
            actor=request.user,
            campaign=campaign,
            note_id=note_id,
        )
    except CharacterNote.DoesNotExist as error:
        raise Http404("Мысль не найдена.") from error
    if request.method == "POST":
        try:
            release_personal_note(
                actor=request.user,
                campaign=campaign,
                note_id=note.pk,
            )
        except CharacterNote.DoesNotExist as error:
            raise Http404("Мысль не найдена.") from error
        messages.success(request, "Мысль отпущена.")
        return redirect("characters:personal_note_list", campaign.pk)
    return render(
        request,
        "characters/personal_note_release.html",
        _thought_context(campaign=campaign, character=character, note=note),
    )
