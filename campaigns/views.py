from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import OperationalError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.services.email import send_campaign_invitation_email
from accounts.services.verification import has_verified_transactional_email
from .forms import (
    CampaignBasicForm,
    CampaignCreateForm,
    CampaignInvitationForm,
    TimeSimulationSettingsForm,
)
from .models import Campaign, CampaignInvitation, CampaignMembership
from .services.invitations import (
    InvitationEmailMismatch,
    InvitationNotFound,
    InvitationUnavailable,
    accept_campaign_invitation,
    accept_campaign_invitation_by_id,
    create_campaign_invitation,
    record_invitation_delivery,
    resolve_invitation_token,
    revoke_campaign_invitation,
)
from .services.lifecycle import create_campaign, update_campaign_basics
from .services.memberships import (
    MembershipConflict,
    change_membership_role,
    remove_campaign_member,
)
from world.forms import AtmosphericConfigForm
from world.models import ApprovalRequest, AtmosphericConfig
from world.services.astronomy import calculate_local_sky, describe_region_sky
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.calendar import minutes_for_time_step
from world.services.region_weather import latest_current_point_weather
from world.services.time import advance_world
from world.services.access import require_campaign_gm, require_campaign_member
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
    return render(
        request,
        "campaigns/campaign_list.html",
        {
            "memberships": memberships,
            "can_create_campaign": has_verified_transactional_email(request.user),
        },
    )


@login_required
def campaign_detail(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    membership = require_campaign_member(request.user, campaign)
    return render(
        request,
        "campaigns/campaign_detail.html",
        {
            "campaign": campaign,
            "membership": membership,
            "is_campaign_gm": request.user.is_superuser
            or membership.role == CampaignMembership.Role.GM,
        },
    )


@login_required
def campaign_create_view(request):
    if not has_verified_transactional_email(request.user):
        messages.warning(request, "Для создания кампании подтвердите email.")
        return redirect("accounts:verify_email")
    form = CampaignCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = create_campaign(
            actor=request.user,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
        )
        messages.success(request, f"Кампания «{campaign.name}» создана.")
        return redirect("campaigns:gm_dashboard", campaign_id=campaign.pk)
    return render(request, "campaigns/campaign_form.html", {"form": form, "mode": "create"})


@login_required
def campaign_edit_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    form = CampaignBasicForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        campaign = update_campaign_basics(
            campaign=campaign,
            actor=request.user,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
        )
        messages.success(request, "Описание кампании обновлено.")
        return redirect("campaigns:campaign_detail", campaign_id=campaign.pk)
    return render(
        request,
        "campaigns/campaign_form.html",
        {"campaign": campaign, "form": form, "mode": "edit"},
    )


def _members_context(campaign, *, invite_form=None, created_invite_url="", mail_sent=None):
    memberships = campaign.memberships.select_related("user").order_by(
        "role", "user__display_name", "user__username"
    )
    invitations = campaign.invitations.select_related(
        "created_by", "accepted_by", "revoked_by"
    ).order_by("-created_at", "-id")[:50]
    return {
        "campaign": campaign,
        "memberships": memberships,
        "invitations": invitations,
        "invite_form": invite_form or CampaignInvitationForm(),
        "created_invite_url": created_invite_url,
        "mail_sent": mail_sent,
        "can_advance_time": True,
        "time_advance_units": TIME_ADVANCE_UNITS,
    }


@login_required
def campaign_members_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    return render(request, "campaigns/members.html", _members_context(campaign))


@login_required
@require_POST
def create_invitation_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    _gm_membership_or_403(request.user, campaign)
    form = CampaignInvitationForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "campaigns/members.html",
            _members_context(campaign, invite_form=form),
            status=400,
        )
    try:
        result = create_campaign_invitation(
            campaign=campaign,
            actor=request.user,
            email=form.cleaned_data["email"],
        )
    except (InvitationUnavailable, ValidationError) as error:
        form.add_error("email", str(error))
        return render(
            request,
            "campaigns/members.html",
            _members_context(campaign, invite_form=form),
            status=400,
        )
    invite_url = request.build_absolute_uri(
        reverse("campaigns:invitation_detail", args=[result.token])
    )
    delivery = send_campaign_invitation_email(
        invitation=result.invitation,
        invite_url=invite_url,
    )
    record_invitation_delivery(invitation=result.invitation, sent=delivery.sent)
    if delivery.sent:
        messages.success(request, "Приглашение отправлено. Ссылку также можно скопировать ниже.")
    else:
        messages.warning(
            request,
            "Приглашение создано, но письмо сейчас не отправлено. Скопируйте ссылку ниже.",
        )
    return render(
        request,
        "campaigns/members.html",
        _members_context(
            campaign,
            created_invite_url=invite_url,
            mail_sent=delivery.sent,
        ),
    )


@login_required
@require_POST
def revoke_invitation_view(request, campaign_id, invitation_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        revoke_campaign_invitation(
            campaign=campaign,
            invitation_id=invitation_id,
            actor=request.user,
        )
    except InvitationNotFound as error:
        raise Http404(str(error)) from error
    except InvitationUnavailable as error:
        messages.warning(request, str(error))
    else:
        messages.success(request, "Приглашение отозвано.")
    return redirect("campaigns:members", campaign_id=campaign.pk)


def invitation_detail_view(request, token):
    try:
        invitation = resolve_invitation_token(token)
    except InvitationNotFound as error:
        raise Http404(str(error)) from error
    request.session["pending_campaign_invite_id"] = invitation.pk
    normalized_user_email = ""
    email_matches = False
    if request.user.is_authenticated:
        from accounts.services.email_addresses import normalize_email_address

        normalized_user_email = normalize_email_address(request.user.email)
        email_matches = normalized_user_email == invitation.email_normalized
    return render(
        request,
        "campaigns/invitation_detail.html",
        {
            "invitation": invitation,
            "invitation_token": token,
            "resume_mode": False,
            "email_matches": email_matches,
            "user_email_verified": bool(
                request.user.is_authenticated and request.user.has_verified_email
            ),
        },
    )


@login_required
def invitation_resume_view(request):
    invitation_id = request.session.get("pending_campaign_invite_id")
    if not invitation_id:
        raise Http404("Контекст приглашения не найден.")
    invitation = get_object_or_404(
        CampaignInvitation.objects.select_related("campaign", "created_by"),
        pk=invitation_id,
    )
    from accounts.services.email_addresses import normalize_email_address

    return render(
        request,
        "campaigns/invitation_detail.html",
        {
            "invitation": invitation,
            "resume_mode": True,
            "email_matches": (
                normalize_email_address(request.user.email)
                == invitation.email_normalized
            ),
            "user_email_verified": request.user.has_verified_email,
        },
    )


@login_required
@require_POST
def accept_invitation_view(request, token):
    try:
        result = accept_campaign_invitation(token=token, actor=request.user)
    except InvitationNotFound as error:
        raise Http404(str(error)) from error
    except (InvitationUnavailable, InvitationEmailMismatch) as error:
        messages.error(request, str(error))
        return redirect("campaigns:invitation_detail", token=token)
    if result.already_member:
        messages.info(request, "Вы уже состоите в этой кампании.")
    else:
        messages.success(request, f"Вы присоединились к кампании «{result.invitation.campaign.name}».")
    request.session.pop("pending_campaign_invite_id", None)
    return redirect("campaigns:campaign_detail", campaign_id=result.invitation.campaign_id)


@login_required
@require_POST
def accept_resumed_invitation_view(request):
    invitation_id = request.session.get("pending_campaign_invite_id")
    if not invitation_id:
        raise Http404("Контекст приглашения не найден.")
    try:
        result = accept_campaign_invitation_by_id(
            invitation_id=invitation_id,
            actor=request.user,
        )
    except InvitationNotFound as error:
        raise Http404(str(error)) from error
    except (InvitationUnavailable, InvitationEmailMismatch) as error:
        messages.error(request, str(error))
        return redirect("campaigns:invitation_resume")
    request.session.pop("pending_campaign_invite_id", None)
    if result.already_member:
        messages.info(request, "Вы уже состоите в этой кампании.")
    else:
        messages.success(request, f"Вы присоединились к кампании «{result.invitation.campaign.name}».")
    return redirect("campaigns:campaign_detail", campaign_id=result.invitation.campaign_id)


def _membership_action(request, campaign_id, membership_id, *, role=None, remove=False):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        if remove:
            label = remove_campaign_member(
                campaign=campaign,
                membership_id=membership_id,
                actor=request.user,
            )
            messages.success(request, f"{label} удалён из кампании.")
        else:
            membership = change_membership_role(
                campaign=campaign,
                membership_id=membership_id,
                actor=request.user,
                new_role=role,
            )
            messages.success(
                request,
                f"Роль {membership.user} изменена: {membership.get_role_display()}.",
            )
    except (MembershipConflict, CampaignMembership.DoesNotExist) as error:
        messages.error(request, str(error) or "Участник не найден.")
    return redirect("campaigns:members", campaign_id=campaign.pk)


@login_required
@require_POST
def promote_member_view(request, campaign_id, membership_id):
    return _membership_action(
        request,
        campaign_id,
        membership_id,
        role=CampaignMembership.Role.GM,
    )


@login_required
@require_POST
def demote_member_view(request, campaign_id, membership_id):
    return _membership_action(
        request,
        campaign_id,
        membership_id,
        role=CampaignMembership.Role.PLAYER,
    )


@login_required
@require_POST
def remove_member_view(request, campaign_id, membership_id):
    return _membership_action(
        request,
        campaign_id,
        membership_id,
        remove=True,
    )


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
