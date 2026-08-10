from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import OperationalError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Campaign, CampaignMembership
from world.forms import AtmosphericConfigForm
from world.models import AtmosphericConfig
from world.services.astronomy import calculate_local_sky, describe_region_sky
from world.services.calendar import minutes_for_time_step
from world.services.time import advance_world

from .time_controls import TIME_ADVANCE_LIMITS, TIME_ADVANCE_UNITS


def _gm_membership_or_403(user, campaign):
    membership = campaign.memberships.filter(user=user).first()
    if not membership or membership.role != CampaignMembership.Role.GM:
        raise PermissionDenied("Доступ только для мастера этой кампании.")
    return membership


@login_required
def campaign_list(request):
    memberships = (
        request.user.campaign_memberships
        .select_related("campaign")
        .order_by("campaign__name")
    )
    return render(request, "campaigns/campaign_list.html", {"memberships": memberships})


def _gm_dashboard_context(campaign, *, atmosphere_form=None):
    regions = list(campaign.regions.all().order_by("name"))
    weather_rows = []
    for region in regions:
        weather_rows.append(
            {
                "region": region,
                "weather": region.weather_history.filter(
                    world_minutes__lte=campaign.world_minutes,
                ).order_by("-world_minutes").first(),
                "sky": describe_region_sky(region, campaign.world_minutes),
            }
        )
    reference_sky = calculate_local_sky(
        campaign,
        campaign.world_minutes,
        0,
        location_known=True,
    )
    calendar = reference_sky.local_moment

    upcoming_events = campaign.events.filter(
        status="planned",
        trigger_at__gte=campaign.world_minutes,
    ).order_by("trigger_at")[:10]

    atmospheric_config = AtmosphericConfig.objects.filter(campaign=campaign).first()
    if atmosphere_form is None:
        atmosphere_form = AtmosphericConfigForm(
            instance=atmospheric_config or AtmosphericConfig(campaign=campaign),
        )
    latest_atmospheric_snapshot = (
        campaign.atmospheric_snapshots.order_by("-world_minutes").first()
    )
    return {
        "campaign": campaign,
        "calendar": calendar,
        "reference_sky": reference_sky,
        "time_advance_units": TIME_ADVANCE_UNITS,
        "can_advance_time": True,
        "weather_rows": weather_rows,
        "characters": campaign.characters.select_related("owner__user").order_by("name"),
        "upcoming_events": upcoming_events,
        "atmospheric_config": atmospheric_config,
        "atmosphere_form": atmosphere_form,
        "atmospheric_snapshot_count": campaign.atmospheric_snapshots.count(),
        "latest_atmospheric_snapshot": latest_atmospheric_snapshot,
    }


@login_required
def gm_dashboard(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    return render(
        request,
        "campaigns/gm_dashboard.html",
        _gm_dashboard_context(campaign),
    )


@login_required
@require_POST
def configure_atmosphere_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    existing = AtmosphericConfig.objects.filter(campaign=campaign).first()
    form = AtmosphericConfigForm(
        request.POST,
        instance=existing or AtmosphericConfig(campaign=campaign),
    )
    if form.is_valid():
        form.save()
        state = "включена" if form.instance.enabled else "выключена"
        messages.success(request, f"Глобальная атмосфера {state}.")
        return redirect("campaigns:gm_dashboard", campaign_id=campaign.pk)
    return render(
        request,
        "campaigns/gm_dashboard.html",
        _gm_dashboard_context(campaign, atmosphere_form=form),
        status=400,
    )


@login_required
@require_POST
def advance_time_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)

    try:
        amount = int(request.POST.get("amount", "0"))
    except ValueError:
        amount = 0
    unit = request.POST.get("unit", "")

    if unit not in TIME_ADVANCE_LIMITS or not 1 <= amount <= TIME_ADVANCE_LIMITS[unit]:
        return HttpResponseBadRequest("Недопустимый шаг времени.")

    try:
        minutes = minutes_for_time_step(campaign, amount, unit)
        advance_world(campaign.pk, minutes)
    except ValueError as error:
        return HttpResponseBadRequest(str(error))
    except OperationalError as error:
        if "database is locked" not in str(error).lower():
            raise
        return HttpResponse(
            "SQLite занят другим процессом. Закройте незавершённую транзакцию в "
            "Database Console/PyCharm и повторите действие. Время мира не изменено.",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("campaigns:gm_dashboard", campaign_id=campaign.pk)
