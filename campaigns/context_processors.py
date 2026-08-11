from campaigns.models import CampaignMembership, TimeAdvanceReport


def campaign_permissions(request):
    if not request.user.is_authenticated:
        return {"can_view_global_atlas": False, "time_advance_report": None}
    context = {
        "can_view_global_atlas": request.user.campaign_memberships.filter(
            role=CampaignMembership.Role.GM,
        ).exists()
    }
    try:
        report_id = int(request.GET.get("advance_report", ""))
    except (TypeError, ValueError):
        report_id = None
    campaign_id = None
    if request.resolver_match is not None:
        campaign_id = request.resolver_match.kwargs.get("campaign_id")
    report = None
    if report_id and campaign_id:
        report = (
            TimeAdvanceReport.objects.select_related("campaign")
            .filter(pk=report_id, campaign_id=campaign_id, gm=request.user)
            .first()
        )
    context["time_advance_report"] = report
    return context
