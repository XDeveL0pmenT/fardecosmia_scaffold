from campaigns.models import CampaignMembership


def campaign_permissions(request):
    if not request.user.is_authenticated:
        return {"can_view_global_atlas": False}
    return {
        "can_view_global_atlas": request.user.campaign_memberships.filter(
            role=CampaignMembership.Role.GM,
        ).exists()
    }
