from django.core.exceptions import PermissionDenied
from django.db import transaction

from accounts.services.verification import has_verified_transactional_email
from campaigns.models import Campaign, CampaignMembership
from world.services.access import require_campaign_gm
from world.services.audit import changed_fields, record_audit


def serialize_campaign_basics(campaign):
    return {
        "name": campaign.name,
        "description": campaign.description,
    }


@transaction.atomic
def create_campaign(*, actor, name, description=""):
    if not has_verified_transactional_email(actor):
        raise PermissionDenied("Для создания кампании подтвердите email.")
    campaign = Campaign.objects.create(
        name=str(name).strip(),
        description=str(description).strip(),
    )
    CampaignMembership.objects.create(
        campaign=campaign,
        user=actor,
        role=CampaignMembership.Role.GM,
    )
    record_audit(
        action="campaign.created",
        actor=actor,
        campaign=campaign,
        target=campaign,
        summary=f"Создана кампания «{campaign.name}».",
        before_state=None,
        after_state=serialize_campaign_basics(campaign),
    )
    return campaign


@transaction.atomic
def update_campaign_basics(*, campaign, actor, name, description=""):
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked)
    before = serialize_campaign_basics(locked)
    locked.name = str(name).strip()
    locked.description = str(description).strip()
    locked.full_clean()
    locked.save(update_fields=["name", "description"])
    after = serialize_campaign_basics(locked)
    if before != after:
        record_audit(
            action="campaign.updated",
            actor=actor,
            campaign=locked,
            target=locked,
            summary=f"Обновлено описание кампании «{locked.name}».",
            before_state=before,
            after_state=after,
            metadata={"changed_fields": changed_fields(before, after)},
        )
    return locked
