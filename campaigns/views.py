from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import OperationalError, transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import TimeSimulationSettingsForm
from .models import Campaign
from world.forms import AtmosphericConfigForm
from world.models import ApprovalRequest, AtmosphericConfig
from world.services.astronomy import calculate_local_sky, describe_region_sky
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.calendar import minutes_for_time_step
from world.services.region_weather import latest_current_point_weather
from world.services.time import advance_world
from world.services.access import require_campaign_gm
from world.services.audit import (
    changed_fields,
    record_audit,
    serialize_atmospheric_config,
    serialize_time_simulation_settings,
)

from .time_controls import TIME_ADVANCE_LIMITS, TIME_ADVANCE_UNITS


def _gm_membership_or_403(user, campaign):
    return require_campaign_gm(user, campaign)


@login_required
def campaign_list(request):
    memberships = (
        request.user.campaign_memberships
        .select_related("campaign")
        .order_by("campaign__name")
    )
    return render(request, "campaigns/campaign_list.html", {"memberships": memberships})


def _gm_dashboard_context(campaign, *, atmosphere_form=None, time_settings_form=None):
    regions = list(campaign.regions.all().order_by("name"))
    weather_rows = []
    for region in regions:
        weather_rows.append(
            {
                "region": region,
                "weather": latest_current_point_weather(
                    region,
                    campaign.world_minutes,
                ),
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
    atmosphere_settings = (
        AtmosphericSettings.from_model(atmospheric_config, campaign)
        if atmospheric_config is not None
        else AtmosphericSettings(world_circumference_km=campaign.world_circumference_km)
    )
    orbital_diagnostics = CampaignSkyForcing(
        campaign,
        atmosphere_settings,
    ).diagnostics(0.0, 0.0, campaign.world_minutes)
    if atmosphere_form is None:
        atmosphere_form = AtmosphericConfigForm(
            instance=atmospheric_config or AtmosphericConfig(campaign=campaign),
        )
    if time_settings_form is None:
        time_settings_form = TimeSimulationSettingsForm(instance=campaign)
    latest_atmospheric_snapshot = (
        campaign.atmospheric_snapshots.order_by("-world_minutes").first()
    )
    pending_approval_requests = (
        ApprovalRequest.objects.filter(
            campaign=campaign,
            status=ApprovalRequest.Status.PENDING,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .select_related("requester")
        .order_by("requested_at", "id")[:5]
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
        "time_settings_form": time_settings_form,
        "atmospheric_snapshot_count": campaign.atmospheric_snapshots.count(),
        "latest_atmospheric_snapshot": latest_atmospheric_snapshot,
        "orbital_diagnostics": orbital_diagnostics,
        "pending_approval_requests": pending_approval_requests,
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
@transaction.atomic
def configure_atmosphere_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    existing = AtmosphericConfig.objects.filter(campaign=campaign).first()
    before_state = None if existing is None else serialize_atmospheric_config(existing)
    form = AtmosphericConfigForm(
        request.POST,
        instance=existing or AtmosphericConfig(campaign=campaign),
    )
    if form.is_valid():
        config = form.save()
        after_state = serialize_atmospheric_config(config)
        if before_state != after_state:
            record_audit(
                action="campaign.atmosphere_configured",
                actor=request.user,
                campaign=campaign,
                target=config,
                summary=f"Обновлена конфигурация атмосферы кампании «{campaign.name}».",
                before_state=before_state,
                after_state=after_state,
                metadata={
                    "changed_fields": (
                        sorted(after_state)
                        if before_state is None
                        else changed_fields(before_state, after_state)
                    )
                },
            )
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
@transaction.atomic
def configure_time_simulation_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    before_state = serialize_time_simulation_settings(campaign)
    form = TimeSimulationSettingsForm(request.POST, instance=campaign)
    if form.is_valid():
        campaign = form.save()
        after_state = serialize_time_simulation_settings(campaign)
        if before_state != after_state:
            record_audit(
                action="campaign.time_simulation_configured",
                actor=request.user,
                campaign=campaign,
                target=campaign,
                summary=f"Обновлён режим времени кампании «{campaign.name}».",
                before_state=before_state,
                after_state=after_state,
                metadata={"changed_fields": changed_fields(before_state, after_state)},
            )
        messages.success(request, "Режим продвижения времени обновлён.")
        return redirect("campaigns:gm_dashboard", campaign_id=campaign.pk)
    return render(
        request,
        "campaigns/gm_dashboard.html",
        _gm_dashboard_context(campaign, time_settings_form=form),
        status=400,
    )


def _with_report_query(url, report_id):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["advance_report"] = str(report_id)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
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
        result = advance_world(
            campaign.pk,
            minutes,
            advanced_by=request.user,
            requested_amount=amount,
            requested_unit=unit,
        )
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
        return redirect(_with_report_query(next_url, result.report.pk))
    dashboard_url = redirect("campaigns:gm_dashboard", campaign_id=campaign.pk).url
    return redirect(_with_report_query(dashboard_url, result.report.pk))
