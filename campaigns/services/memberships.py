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
    before = _serialize_membership(membership)
    label = _user_label(membership.user)
    membership.delete()
    record_audit(
        action="campaign_member.removed",
        actor=actor,
        campaign=locked_campaign,
        target=locked_campaign,
        target_label=f"Участник {label}",
        summary=f"Игрок {label} удалён из кампании.",
        before_state=before,
        after_state={"user_label": label, "removed": True},
    )
    return label
