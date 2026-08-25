from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction

from campaigns.models import Campaign, CampaignMembership
from characters.models import Character, CharacterNote
from characters.services import get_active_character
from world.services.access import require_campaign_member


class CharacterNotesUnavailable(PermissionDenied):
    """The requester has no active controlled Character for this note space."""


def get_active_note_character(*, actor, campaign):
    """Resolve the only Character whose private thoughts ``actor`` may access."""

    membership = require_campaign_member(actor, campaign)
    if membership is None or membership.role != CampaignMembership.Role.PLAYER:
        raise CharacterNotesUnavailable(
            "Личные мысли доступны только текущему игроку персонажа."
        )
    character = get_active_character(actor, campaign)
    if character is None:
        raise CharacterNotesUnavailable(
            "Сначала выберите активного персонажа."
        )
    return membership, character


def personal_notes_for(*, actor, campaign):
    """Return a Character-scoped queryset without widening access for GM."""

    _membership, character = get_active_note_character(actor=actor, campaign=campaign)
    return character, CharacterNote.objects.filter(character=character)


def get_personal_note(*, actor, campaign, note_id):
    character, notes = personal_notes_for(actor=actor, campaign=campaign)
    return character, notes.get(pk=note_id)


def _locked_active_note_character(*, actor, campaign):
    """Serialize note writes with supported assignment/active-selection writes."""

    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    membership, character = get_active_note_character(
        actor=actor,
        campaign=locked_campaign,
    )
    character = Character.objects.select_for_update().get(
        pk=character.pk,
        campaign=locked_campaign,
        owner=membership,
        is_active=True,
    )
    return locked_campaign, character


@transaction.atomic
def hold_personal_note(*, actor, campaign, memo, body):
    """Hold a thought for the current Character without creating world audit data."""

    _campaign, character = _locked_active_note_character(
        actor=actor,
        campaign=campaign,
    )
    note = CharacterNote(character=character, memo=memo, body=body)
    note.full_clean()
    note.save()
    return note


@transaction.atomic
def return_to_personal_note(*, actor, campaign, note_id, memo, body):
    """Edit one thought scoped to the current Character."""

    _campaign, character = _locked_active_note_character(
        actor=actor,
        campaign=campaign,
    )
    note = CharacterNote.objects.select_for_update().get(
        pk=note_id,
        character=character,
    )
    note.memo = memo
    note.body = body
    note.full_clean()
    note.save(update_fields=("memo", "body", "updated_at"))
    return note


@transaction.atomic
def release_personal_note(*, actor, campaign, note_id):
    """Release one thought scoped to the current Character."""

    _campaign, character = _locked_active_note_character(
        actor=actor,
        campaign=campaign,
    )
    note = CharacterNote.objects.select_for_update().get(
        pk=note_id,
        character=character,
    )
    note.delete()

