import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from campaigns.models import Campaign, CampaignMembership
from world.services.access import require_campaign_gm
from world.services.audit import record_audit


class MembershipConflict(Exception):
    pass


def _user_label(user):
    return str(user.display_name or user.username)


def _serialize_membership(membership):
    return {
        "user_label": _user_label(membership.user),
        "role": membership.role,
    }


@transaction.atomic
def change_membership_role(*, campaign, membership_id, actor, new_role):
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked_campaign)
    membership = (
        CampaignMembership.objects.select_for_update()
        .select_related("user")
        .get(pk=membership_id, campaign=locked_campaign)
    )
    if new_role not in CampaignMembership.Role.values:
        raise ValidationError("Неизвестная роль участника.")
    if membership.role == new_role:
        return membership
    if (
        membership.role == CampaignMembership.Role.GM
        and new_role == CampaignMembership.Role.PLAYER
        and CampaignMembership.objects.filter(
            campaign=locked_campaign,
            role=CampaignMembership.Role.GM,
        ).count()
        <= 1
    ):
        raise MembershipConflict(
            "В кампании должен остаться хотя бы один Game Master."
        )
    before = _serialize_membership(membership)
    membership.role = new_role
    membership.save(update_fields=["role"])
    after = _serialize_membership(membership)
    record_audit(
        action="campaign_member.role_changed",
        actor=actor,
        campaign=locked_campaign,
        target=membership,
        summary=(
            f"Роль {_user_label(membership.user)} изменена: "
            f"{dict(CampaignMembership.Role.choices)[before['role']]} → "
            f"{membership.get_role_display()}."
        ),
        before_state=before,
        after_state=after,
    )
    return membership


@transaction.atomic
def remove_campaign_member(*, campaign, membership_id, actor):
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked_campaign)
    membership = (
        CampaignMembership.objects.select_for_update()
        .select_related("user")
        .get(pk=membership_id, campaign=locked_campaign)
    )
    if membership.role == CampaignMembership.Role.GM:
        gm_count = CampaignMembership.objects.filter(
            campaign=locked_campaign,
            role=CampaignMembership.Role.GM,
        ).count()
        if gm_count <= 1:
            raise MembershipConflict(
                "В кампании должен остаться хотя бы один Game Master."
            )
        raise MembershipConflict(
            "Сначала измените роль Game Master на «Игрок», затем удалите участника."
        )
    from characters.models import Character
    from characters.services import serialize_character

    operation_id = uuid.uuid4()
    assigned_characters = list(
        Character.objects.select_for_update()
        .select_related("owner__user")
        .filter(owner=membership)
        .order_by("pk")
    )
    before = _serialize_membership(membership)
    before["assigned_character_count"] = len(assigned_characters)
    label = _user_label(membership.user)
    if membership.active_character_id:
        active = membership.active_character
        membership.active_character = None
        membership.save(update_fields=["active_character"])
        record_audit(
            action="character.active_changed",
            actor=actor,
            campaign=locked_campaign,
            target=membership,
            target_label=f"Активный персонаж {label}",
            summary=f"Активный персонаж {label} очищен при удалении из кампании.",
            before_state={"character_id": active.pk, "name": active.name},
            after_state={"character_id": None, "name": None},
            operation_id=operation_id,
        )
    for character in assigned_characters:
        character_before = serialize_character(character)
        character.owner = None
        character.save(update_fields=["owner", "updated_at"])
        record_audit(
            action="character.unassigned",
            actor=actor,
            campaign=locked_campaign,
            target=character,
            summary=(
                f"Персонаж «{character.name}» остался без игрока после удаления "
                f"{label} из кампании."
            ),
            before_state=character_before,
            after_state=serialize_character(character),
            operation_id=operation_id,
        )
    membership.delete()
    record_audit(
        action="campaign_member.removed",
        actor=actor,
        campaign=locked_campaign,
        target=locked_campaign,
        target_label=f"Участник {label}",
        summary=f"Игрок {label} удалён из кампании.",
        before_state=before,
        after_state={
            "user_label": label,
            "removed": True,
            "unassigned_character_count": len(assigned_characters),
        },
        operation_id=operation_id,
    )
    return label
