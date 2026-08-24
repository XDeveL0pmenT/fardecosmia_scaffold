from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from campaigns.models import Campaign, CampaignMembership
from characters.models import Character, CharacterLocationState
from world.services.access import require_campaign_gm, require_campaign_member
from world.services.audit import changed_fields, record_audit


class CharacterConflict(ValidationError):
    pass


class CharacterLocationConflict(CharacterConflict):
    pass


@dataclass(frozen=True, slots=True)
class EffectiveCharacterLocation:
    """Immutable resolver output; future Travel/Party logic can replace source."""

    character_id: int
    latitude: Decimal
    longitude: Decimal
    source: str = "initial_placement"


COORDINATE_QUANTUM = Decimal("0.000001")


def user_label(user):
    return str(user.display_name or user.username)


def membership_label(membership):
    return None if membership is None else user_label(membership.user)


def serialize_character(character):
    owner = character.owner
    return {
        "name": character.name,
        "campaign_id": str(character.campaign_id),
        "controller_membership_id": None if owner is None else owner.pk,
        "controller_label": membership_label(owner),
        "is_active": character.is_active,
        "archived_at": (
            None if character.archived_at is None else character.archived_at.isoformat()
        ),
        "biography": character.biography,
    }


def _coordinate_decimal(raw_value, *, coordinate):
    if isinstance(raw_value, bool):
        raise CharacterLocationConflict(f"{coordinate} должна быть числом.")
    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise CharacterLocationConflict(f"{coordinate} должна быть числом.") from error
    if not value.is_finite():
        raise CharacterLocationConflict(f"{coordinate} должна быть конечным числом.")
    if value.normalize().as_tuple().exponent < -6:
        raise CharacterLocationConflict(
            f"{coordinate} поддерживает не более шести знаков после запятой."
        )
    return value.quantize(COORDINATE_QUANTUM)


def canonical_location_coordinates(*, latitude, longitude):
    latitude = _coordinate_decimal(latitude, coordinate="Широта")
    longitude = _coordinate_decimal(longitude, coordinate="Долгота")
    if not Decimal("-90") <= latitude <= Decimal("90"):
        raise CharacterLocationConflict(
            "Широта должна находиться между -90 и 90 градусами."
        )
    if not Decimal("-180") <= longitude <= Decimal("180"):
        raise CharacterLocationConflict(
            "Долгота должна находиться между -180 и 180 градусами."
        )
    if longitude == Decimal("180"):
        longitude = Decimal("-180").quantize(COORDINATE_QUANTUM)
    return latitude, longitude


def get_effective_character_location(character):
    """Resolve current canonical position through the single future-facing boundary.

    L1 has only the durable initial position. Future Travel/Party phases may add
    domain-controlled branches here without changing Player/weather callers.
    """

    if character is None or character.pk is None:
        return None
    try:
        state = character.location_state
    except CharacterLocationState.DoesNotExist:
        return None
    return EffectiveCharacterLocation(
        character_id=character.pk,
        latitude=state.latitude,
        longitude=state.longitude,
    )


def _locked_campaign_for_gm(*, campaign, actor):
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked)
    return locked


def controlled_characters(*, membership, include_archived=False):
    queryset = Character.objects.filter(
        campaign=membership.campaign,
        owner=membership,
    ).select_related("campaign", "owner__user", "roll20_binding", "location_state")
    if not include_archived:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name", "pk")


def get_active_character(user, campaign):
    """Resolve the persisted active Character, or the sole controlled default.

    The single-character fallback deliberately does not write during GET. This
    keeps page rendering read-only while still giving the common case a useful
    active identity.
    """

    if not user or not user.is_authenticated:
        return None
    membership = (
        CampaignMembership.objects.filter(campaign=campaign, user=user)
        .select_related("active_character", "active_character__location_state")
        .first()
    )
    if membership is None:
        return None
    selected = membership.active_character
    if (
        selected is not None
        and selected.campaign_id == campaign.pk
        and selected.owner_id == membership.pk
        and selected.is_active
    ):
        return selected
    candidates = list(controlled_characters(membership=membership)[:2])
    return candidates[0] if len(candidates) == 1 else None


def _record_active_change(*, membership, before, after, actor, campaign, operation_id):
    if before == after:
        return
    before_label = None if before is None else before.name
    after_label = None if after is None else after.name
    record_audit(
        action="character.active_changed",
        actor=actor,
        campaign=campaign,
        target=membership,
        target_label=f"Активный персонаж {user_label(membership.user)}",
        summary=(
            f"Активный персонаж {user_label(membership.user)} изменён: "
            f"{before_label or 'не выбран'} → {after_label or 'не выбран'}."
        ),
        before_state={"character_id": None if before is None else before.pk, "name": before_label},
        after_state={"character_id": None if after is None else after.pk, "name": after_label},
        operation_id=operation_id,
    )


@transaction.atomic
def create_character(*, campaign, actor, name, biography=""):
    campaign = _locked_campaign_for_gm(campaign=campaign, actor=actor)
    character = Character(
        campaign=campaign,
        name=str(name).strip(),
        biography=str(biography).strip(),
    )
    character.full_clean()
    character.save()
    record_audit(
        action="character.created",
        actor=actor,
        campaign=campaign,
        target=character,
        summary=f"Создан персонаж «{character.name}».",
        before_state=None,
        after_state=serialize_character(character),
    )
    return character


@transaction.atomic
def initialize_character_location(
    *,
    campaign,
    character_id,
    actor,
    latitude,
    longitude,
):
    """Perform the only supported L1 location write: one-time initialization."""

    campaign = _locked_campaign_for_gm(campaign=campaign, actor=actor)
    character = (
        Character.objects.select_for_update()
        .select_related("owner__user")
        .get(pk=character_id, campaign=campaign)
    )
    if not character.is_active:
        raise CharacterLocationConflict(
            "Архивному персонажу нельзя задавать исходное положение."
        )
    if CharacterLocationState.objects.select_for_update().filter(
        character=character
    ).exists():
        raise CharacterLocationConflict(
            "Исходное положение этого персонажа уже установлено."
        )
    latitude, longitude = canonical_location_coordinates(
        latitude=latitude,
        longitude=longitude,
    )
    state = CharacterLocationState(
        character=character,
        latitude=latitude,
        longitude=longitude,
    )
    state.full_clean()
    state.save()
    coordinates = {
        "latitude": format(state.latitude, ".6f"),
        "longitude": format(state.longitude, ".6f"),
        "source": "initial_placement",
    }
    record_audit(
        action="character.location_initialized",
        actor=actor,
        campaign=campaign,
        target=character,
        summary=f"Установлено исходное положение персонажа «{character.name}».",
        before_state={"location": None},
        after_state=coordinates,
        metadata={"coordinate_system": "fardecosmia_planetary_lonlat"},
    )
    return state


@transaction.atomic
def update_character(*, campaign, character_id, actor, name, biography=""):
    campaign = _locked_campaign_for_gm(campaign=campaign, actor=actor)
    character = (
        Character.objects.select_for_update()
        .select_related("owner__user")
        .get(pk=character_id, campaign=campaign)
    )
    before = serialize_character(character)
    character.name = str(name).strip()
    character.biography = str(biography).strip()
    character.full_clean()
    after = serialize_character(character)
    if before == after:
        return character
    character.save(update_fields=["name", "biography", "updated_at"])
    record_audit(
        action="character.updated",
        actor=actor,
        campaign=campaign,
        target=character,
        summary=f"Обновлена основная информация персонажа «{character.name}».",
        before_state=before,
        after_state=after,
        metadata={"changed_fields": changed_fields(before, after)},
    )
    return character


@transaction.atomic
def assign_character(*, campaign, character_id, actor, membership_id=None):
    campaign = _locked_campaign_for_gm(campaign=campaign, actor=actor)
    character = (
        Character.objects.select_for_update()
        .select_related("owner__user")
        .get(pk=character_id, campaign=campaign)
    )
    target = None
    if membership_id:
        if not character.is_active:
            raise CharacterConflict(
                "Архивного персонажа нельзя назначить игроку до восстановления."
            )
        target = (
            CampaignMembership.objects.select_for_update()
            .select_related("user", "active_character")
            .get(
                pk=membership_id,
                campaign=campaign,
                role=CampaignMembership.Role.PLAYER,
            )
        )
    previous = character.owner
    if previous == target:
        return character

    operation_id = uuid.uuid4()
    before = serialize_character(character)
    if previous is not None:
        previous = (
            CampaignMembership.objects.select_for_update()
            .select_related("user", "active_character")
            .get(pk=previous.pk)
        )
        if previous.active_character_id == character.pk:
            previous_active = previous.active_character
            previous.active_character = None
            previous.save(update_fields=["active_character"])
            _record_active_change(
                membership=previous,
                before=previous_active,
                after=None,
                actor=actor,
                campaign=campaign,
                operation_id=operation_id,
            )

    character.owner = target
    character.full_clean()
    character.save(update_fields=["owner", "updated_at"])

    if target is not None and target.active_character_id is None:
        has_other = Character.objects.filter(
            campaign=campaign,
            owner=target,
            is_active=True,
        ).exclude(pk=character.pk).exists()
        if not has_other and character.is_active:
            target.active_character = character
            target.save(update_fields=["active_character"])
            _record_active_change(
                membership=target,
                before=None,
                after=character,
                actor=actor,
                campaign=campaign,
                operation_id=operation_id,
            )

    character = Character.objects.select_related("owner__user").get(pk=character.pk)
    after = serialize_character(character)
    if target is None:
        action = "character.unassigned"
        summary = f"С персонажа «{character.name}» снято назначение игроку."
    elif previous is None:
        action = "character.assigned"
        summary = f"Персонаж «{character.name}» назначен игроку {membership_label(target)}."
    else:
        action = "character.assigned"
        summary = (
            f"Персонаж «{character.name}» переназначен: "
            f"{membership_label(previous)} → {membership_label(target)}."
        )
    record_audit(
        action=action,
        actor=actor,
        campaign=campaign,
        target=character,
        summary=summary,
        before_state=before,
        after_state=after,
        operation_id=operation_id,
    )
    return character


@transaction.atomic
def set_active_character(*, campaign, actor, character_id):
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    membership = require_campaign_member(actor, campaign)
    if membership is None:
        raise CharacterConflict("Для выбора активного персонажа нужно состоять в кампании.")
    membership = (
        CampaignMembership.objects.select_for_update()
        .select_related("user", "active_character")
        .get(pk=membership.pk, campaign=campaign)
    )
    character = Character.objects.select_for_update().get(
        pk=character_id,
        campaign=campaign,
        owner=membership,
        is_active=True,
    )
    before = membership.active_character
    if before == character:
        return character
    membership.active_character = character
    membership.full_clean()
    membership.save(update_fields=["active_character"])
    _record_active_change(
        membership=membership,
        before=before,
        after=character,
        actor=actor,
        campaign=campaign,
        operation_id=uuid.uuid4(),
    )
    return character


@transaction.atomic
def set_character_archived(*, campaign, character_id, actor, archived):
    campaign = _locked_campaign_for_gm(campaign=campaign, actor=actor)
    character = (
        Character.objects.select_for_update()
        .select_related("owner__user")
        .get(pk=character_id, campaign=campaign)
    )
    desired_active = not archived
    if character.is_active == desired_active:
        return character
    operation_id = uuid.uuid4()
    before = serialize_character(character)
    memberships = list(
        CampaignMembership.objects.select_for_update()
        .select_related("user", "active_character")
        .filter(active_character=character)
    )
    for membership in memberships:
        old_active = membership.active_character
        membership.active_character = None
        membership.save(update_fields=["active_character"])
        _record_active_change(
            membership=membership,
            before=old_active,
            after=None,
            actor=actor,
            campaign=campaign,
            operation_id=operation_id,
        )
    character.is_active = desired_active
    character.archived_at = None if desired_active else timezone.now()
    character.full_clean()
    character.save(update_fields=["is_active", "archived_at", "updated_at"])
    action = "character.restored" if desired_active else "character.archived"
    verb = "возвращён из архива" if desired_active else "перемещён в архив"
    record_audit(
        action=action,
        actor=actor,
        campaign=campaign,
        target=character,
        summary=f"Персонаж «{character.name}» {verb}.",
        before_state=before,
        after_state=serialize_character(character),
        operation_id=operation_id,
    )
    return character
