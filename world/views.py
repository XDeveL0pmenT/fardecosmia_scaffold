import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from campaigns.models import Campaign
from campaigns.time_controls import TIME_ADVANCE_UNITS
from world.biomes import BIOME_PALETTE
from world.forms import (
    CampaignOverrideForm,
    MapLayerPaintForm,
    RegionMapForm,
    RegionPlacementForm,
    WorldEventDefinitionEditForm,
    WorldEventNowForm,
    WorldEventScheduleForm,
    WorldEntryForm,
)
from world.models import (
    ApprovalRequest,
    AtmosphericConfig,
    AuditLog,
    Region,
    WorldEntry,
    WorldEvent,
    WorldEventOccurrence,
)
from world.services.access import (
    can_manage_campaign,
    can_manage_global_canon,
    require_campaign_member,
    require_campaign_gm,
    require_global_atlas_viewer,
    require_global_canon_editor,
)
from world.services.approvals import (
    ApprovalWorkflowError,
    approval_type_label,
    approve_request,
    cancel_request,
    can_user_approve_request,
    can_user_cancel_request,
    presentation_for,
    reject_request,
)
from world.services.astronomy import (
    build_light_bands,
    celestial_positions,
    describe_region_sky,
)
from world.services.map_geometry import polygon_center, polygon_svg_points
from world.services.atlas import build_atlas_config
from world.services.map_inspection import inspect_map_point
from world.services.map_layers import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    effective_biome_cells,
    get_campaign_map_override,
    get_global_map_layer,
    land_only_biome_cells,
    map_defaults_at,
    update_campaign_biome_layer,
)
from world.services.region_climate import region_climate_at
from world.services.weather_display import build_weather_summary
from world.services.environment_summary import build_environment_summary
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.persistence import latest_atmospheric_cell_diagnostics
from world.services.atmosphere.region_area import build_region_area_weather_summary
from world.services.region_weather import (
    latest_current_area_weather,
    latest_current_point_weather,
)
from world.services.regions import (
    automatic_climate_changes,
    create_region,
    delete_region as delete_region_service,
    placement_changes,
    update_region,
)
from world.services.canon import (
    create_campaign_world_entry,
    create_global_world_entry,
    delete_campaign_world_entry,
    delete_global_world_entry,
    remove_campaign_override,
    set_campaign_override,
    set_campaign_suppression,
    update_campaign_world_entry,
    update_global_world_entry,
)
from world.services.calendar import describe_campaign_time
from world.services.events import (
    WorldEventError,
    create_world_event_definition,
    disable_world_event_definition,
    effect_presentation,
    record_narrative_event_now,
    remove_world_event_definition,
    trigger_presentation,
    trigger_type_label,
    trigger_world_event_now,
    update_world_event_definition,
    world_event_type_label,
)
from world.services.overrides import effective_world_entries, resolve_for_campaign


SEASON_CODES = {
    "Лето": "summer",
    "Осень": "autumn",
    "Зима": "winter",
    "Весна": "spring",
}
def _gm_campaign_or_403(user, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    require_campaign_gm(user, campaign)
    return campaign


def _member_campaign_or_403(user, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    require_campaign_member(user, campaign)
    return campaign


def _biome_palette():
    return [
        {"value": value, "label": label, "color": BIOME_PALETTE[value]}
        for value, label in Region.Biome.choices
    ]


def _global_atlas_or_403(user):
    require_global_atlas_viewer(user)


def _filtered_audit_queryset(request, queryset, *, campaign_scope):
    action = request.GET.get("action", "").strip()
    actor = request.GET.get("actor", "").strip()
    target_type = request.GET.get("target_type", "").strip().lower()
    source = request.GET.get("source", "").strip().upper()
    if action:
        queryset = queryset.filter(action=action)
    if actor:
        queryset = queryset.filter(actor_label_snapshot__icontains=actor)
    if "." in target_type:
        app_label, model = target_type.split(".", 1)
        queryset = queryset.filter(
            target_content_type__app_label=app_label,
            target_content_type__model=model,
        )
    if source in AuditLog.Source.values:
        queryset = queryset.filter(source=source)
    if campaign_scope:
        for parameter, lookup in (
            ("world_from", "world_minutes__gte"),
            ("world_to", "world_minutes__lte"),
        ):
            try:
                value = int(request.GET.get(parameter, ""))
            except (TypeError, ValueError):
                continue
            queryset = queryset.filter(**{lookup: value})
    else:
        for parameter, lookup in (
            ("date_from", "occurred_at__date__gte"),
            ("date_to", "occurred_at__date__lte"),
        ):
            value = parse_date(request.GET.get(parameter, ""))
            if value is not None:
                queryset = queryset.filter(**{lookup: value})
    return queryset


def _audit_list_context(request, queryset, *, campaign=None):
    queryset = _filtered_audit_queryset(
        request,
        queryset.select_related(
            "campaign",
            "actor",
            "target_content_type",
        ),
        campaign_scope=campaign is not None,
    ).order_by("-occurred_at", "-id")
    page_obj = Paginator(queryset, 50).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return {
        "campaign": campaign,
        "page_obj": page_obj,
        "audit_rows": page_obj.object_list,
        "audit_sources": AuditLog.Source.choices,
        "filter_query": query.urlencode(),
        "filters": request.GET,
        "time_advance_units": TIME_ADVANCE_UNITS,
        "can_advance_time": campaign is not None,
    }


@login_required
@require_GET
def global_audit_list(request):
    require_global_canon_editor(request.user)
    return render(
        request,
        "world/audit_list.html",
        _audit_list_context(
            request,
            AuditLog.objects.filter(
                campaign__isnull=True,
                campaign_id_snapshot__isnull=True,
            ),
        ),
    )


@login_required
@require_GET
def global_audit_detail(request, audit_id):
    require_global_canon_editor(request.user)
    audit = get_object_or_404(
        AuditLog.objects.select_related(
            "campaign",
            "actor",
            "target_content_type",
        ),
        pk=audit_id,
        campaign__isnull=True,
        campaign_id_snapshot__isnull=True,
    )
    return render(request, "world/audit_detail.html", {"audit": audit})


@login_required
@require_GET
def campaign_audit_list(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    return render(
        request,
        "world/audit_list.html",
        _audit_list_context(
            request,
            AuditLog.objects.filter(campaign=campaign),
            campaign=campaign,
        ),
    )


@login_required
@require_GET
def campaign_audit_detail(request, campaign_id, audit_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    audit = get_object_or_404(
        AuditLog.objects.select_related(
            "campaign",
            "actor",
            "target_content_type",
        ),
        pk=audit_id,
        campaign=campaign,
    )
    return render(
        request,
        "world/audit_detail.html",
        {
            "campaign": campaign,
            "audit": audit,
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )


def _filter_approval_queryset(request, queryset, *, default_status):
    selected_status = request.GET.get("status", default_status).strip().upper()
    now = timezone.now()
    if selected_status == ApprovalRequest.Status.PENDING:
        queryset = queryset.filter(status=ApprovalRequest.Status.PENDING).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
    elif selected_status == ApprovalRequest.Status.EXPIRED:
        queryset = queryset.filter(
            Q(status=ApprovalRequest.Status.EXPIRED)
            | Q(status=ApprovalRequest.Status.PENDING, expires_at__lte=now)
        )
    elif selected_status in ApprovalRequest.Status.values:
        queryset = queryset.filter(status=selected_status)
    elif selected_status != "ALL":
        selected_status = default_status
        if default_status == ApprovalRequest.Status.PENDING:
            queryset = queryset.filter(status=ApprovalRequest.Status.PENDING).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )

    request_type = request.GET.get("request_type", "").strip()
    if request_type:
        queryset = queryset.filter(request_type=request_type)
    requester = request.GET.get("requester", "").strip()
    if requester:
        queryset = queryset.filter(requester_label_snapshot__icontains=requester)
    return queryset, selected_status, request_type, requester


def _approval_type_choices(queryset):
    request_types = queryset.order_by().values_list("request_type", flat=True).distinct()
    return [(request_type, approval_type_label(request_type)) for request_type in request_types]


def _approval_list_context(request, *, campaign, mine):
    base_queryset = ApprovalRequest.objects.filter(campaign=campaign)
    if mine:
        base_queryset = base_queryset.filter(requester=request.user)
    type_choices = _approval_type_choices(base_queryset)
    queryset, selected_status, request_type, requester = _filter_approval_queryset(
        request,
        base_queryset.select_related("requester", "resolved_by"),
        default_status="ALL" if mine else ApprovalRequest.Status.PENDING,
    )
    page_obj = Paginator(queryset.order_by("-requested_at", "-id"), 50 if not mine else 25).get_page(
        request.GET.get("page")
    )
    query = request.GET.copy()
    query.pop("page", None)
    rows = [
        {
            "request": approval,
            "type_label": approval_type_label(approval.request_type),
            "requested_time": describe_campaign_time(
                campaign,
                approval.requested_world_minutes,
            ),
        }
        for approval in page_obj.object_list
    ]
    return {
        "campaign": campaign,
        "mine": mine,
        "approval_rows": rows,
        "page_obj": page_obj,
        "approval_statuses": ApprovalRequest.Status.choices,
        "approval_type_choices": type_choices,
        "selected_status": selected_status,
        "selected_request_type": request_type,
        "selected_requester": requester,
        "filter_query": query.urlencode(),
        "time_advance_units": TIME_ADVANCE_UNITS,
        "can_advance_time": can_manage_campaign(request.user, campaign),
    }


@login_required
@require_GET
def campaign_approval_queue(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    return render(
        request,
        "world/approval_list.html",
        _approval_list_context(request, campaign=campaign, mine=False),
    )


@login_required
@require_GET
def my_approval_requests(request, campaign_id):
    campaign = _member_campaign_or_403(request.user, campaign_id)
    return render(
        request,
        "world/approval_list.html",
        _approval_list_context(request, campaign=campaign, mine=True),
    )


def _approval_detail_or_404(user, campaign, request_id):
    queryset = ApprovalRequest.objects.select_related(
        "campaign",
        "requester",
        "resolved_by",
        "target_content_type",
    ).filter(campaign=campaign)
    if not can_manage_campaign(user, campaign):
        queryset = queryset.filter(requester=user)
    return get_object_or_404(queryset, pk=request_id)


@login_required
@require_GET
def approval_request_detail(request, campaign_id, request_id):
    campaign = _member_campaign_or_403(request.user, campaign_id)
    approval = _approval_detail_or_404(request.user, campaign, request_id)
    requested_time = describe_campaign_time(campaign, approval.requested_world_minutes)
    resolved_time = (
        describe_campaign_time(campaign, approval.resolved_world_minutes)
        if approval.resolved_world_minutes is not None
        else None
    )
    approval_history = AuditLog.objects.filter(
        campaign=campaign,
        operation_id=approval.operation_id,
        action__startswith="approval_request.",
    ).order_by("occurred_at", "id")
    return render(
        request,
        "world/approval_detail.html",
        {
            "campaign": campaign,
            "approval": approval,
            "presentation": presentation_for(approval),
            "requested_time": requested_time,
            "resolved_time": resolved_time,
            "approval_history": approval_history,
            "can_approve_request": can_user_approve_request(request.user, approval),
            "can_cancel_request": can_user_cancel_request(request.user, approval),
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": can_manage_campaign(request.user, campaign),
        },
    )


def _decision_error_message(error):
    if isinstance(error, ValidationError):
        return " ".join(error.messages)
    return str(error)


def _approval_transition_view(request, *, campaign_id, request_id, transition):
    campaign = _member_campaign_or_403(request.user, campaign_id)
    note = request.POST.get("resolution_note", "")
    try:
        transition(
            campaign=campaign,
            request_id=request_id,
            actor=request.user,
            resolution_note=note,
        )
    except (ApprovalWorkflowError, ValidationError) as error:
        messages.error(request, _decision_error_message(error))
    else:
        messages.success(request, "Решение сохранено.")
    return redirect(
        "world:approval_request_detail",
        campaign_id=campaign.pk,
        request_id=request_id,
    )


def _event_time_label(campaign, world_minutes):
    moment = describe_campaign_time(campaign, world_minutes)
    return {
        "moment": moment,
        "label": (
            f"Год {moment.year} · Виток {moment.turn_of_year} · "
            f"{moment.turn_clock} · {moment.season}"
        ),
    }


def _event_remaining_label(campaign, scheduled_world_minutes):
    remaining = max(0, scheduled_world_minutes - campaign.world_minutes)
    if remaining == 0:
        return "сейчас"
    if remaining % campaign.calendar_minutes_per_turn == 0:
        value = remaining // campaign.calendar_minutes_per_turn
        return f"через {value} Виток(ов)"
    if remaining % campaign.calendar_minutes_per_phase == 0:
        value = remaining // campaign.calendar_minutes_per_phase
        return f"через {value} фаз(ы) Витка"
    if remaining % campaign.calendar_minutes_per_hour == 0:
        value = remaining // campaign.calendar_minutes_per_hour
        return f"через {value} час(ов) Витка"
    return f"через {remaining} игровых минут"


def _event_common_context(request, campaign):
    return {
        "campaign": campaign,
        "time_advance_units": TIME_ADVANCE_UNITS,
        "can_advance_time": can_manage_campaign(request.user, campaign),
    }


@login_required
@require_GET
def campaign_event_list(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    selected_tab = request.GET.get("tab", "upcoming")
    if selected_tab not in {"upcoming", "occurred", "disabled", "all"}:
        selected_tab = "upcoming"

    definitions = (
        WorldEvent.objects.filter(campaign=campaign)
        .select_related("region", "created_by")
        .prefetch_related("occurrences")
    )
    occurrences = WorldEventOccurrence.objects.filter(campaign=campaign).select_related(
        "definition", "region", "actor"
    )
    if selected_tab == "upcoming":
        definitions = definitions.filter(
            enabled=True,
            trigger_type=WorldEvent.TriggerType.WORLD_TIME,
            trigger_at__gt=campaign.world_minutes,
            occurrences__isnull=True,
        )
        occurrences = occurrences.none()
    elif selected_tab == "occurred":
        definitions = definitions.none()
    elif selected_tab == "disabled":
        definitions = definitions.filter(enabled=False, occurrences__isnull=True)
        occurrences = occurrences.none()
    else:
        # Once a one-shot definition has fired, its immutable occurrence is the
        # history row shown in the combined view. Avoid presenting the mutable
        # schedule as a second copy of the same fact.
        definitions = definitions.filter(occurrences__isnull=True)

    definition_rows = [
        {
            "definition": definition,
            "type_label": world_event_type_label(definition.event_type),
            "scheduled_time": (
                _event_time_label(campaign, definition.trigger_at)
                if definition.trigger_at is not None
                else None
            ),
            "remaining_label": (
                _event_remaining_label(campaign, definition.trigger_at)
                if definition.trigger_at is not None
                else "запускается GM"
            ),
            "effect_label": effect_presentation(definition),
        }
        for definition in definitions.order_by("trigger_at", "id")[:100]
    ]
    occurrence_rows = [
        {
            "occurrence": occurrence,
            "type_label": world_event_type_label(occurrence.event_type_snapshot),
            "occurred_time": _event_time_label(
                campaign,
                occurrence.occurred_world_minutes,
            ),
            "cause_label": trigger_type_label(occurrence.trigger_type_snapshot),
        }
        for occurrence in occurrences.order_by("-occurred_world_minutes", "-id")[:100]
    ]
    context = _event_common_context(request, campaign)
    context.update(
        {
            "selected_tab": selected_tab,
            "definition_rows": definition_rows,
            "occurrence_rows": occurrence_rows,
        }
    )
    return render(request, "world/event_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def world_event_schedule(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    form = WorldEventScheduleForm(request.POST or None, campaign=campaign)
    if request.method == "POST" and form.is_valid():
        try:
            definition = create_world_event_definition(
                actor=request.user,
                campaign=campaign,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                scheduled_world_minutes=form.cleaned_data["scheduled_world_minutes"],
                region=form.cleaned_data["region"],
            )
        except (ValidationError, WorldEventError) as error:
            form.add_error(None, _decision_error_message(error))
        else:
            messages.success(request, f"Событие «{definition.title}» запланировано.")
            return redirect(
                "world:world_event_definition_detail",
                campaign_id=campaign.pk,
                definition_id=definition.pk,
            )
    context = _event_common_context(request, campaign)
    context.update({"form": form, "form_mode": "schedule"})
    return render(request, "world/event_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def world_event_record_now(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    form = WorldEventNowForm(request.POST or None, campaign=campaign)
    if request.method == "POST" and form.is_valid():
        try:
            occurrence = record_narrative_event_now(
                actor=request.user,
                campaign=campaign,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                region=form.cleaned_data["region"],
            )
        except (ValidationError, WorldEventError) as error:
            form.add_error(None, _decision_error_message(error))
        else:
            messages.success(request, f"Событие «{occurrence.title}» добавлено в историю мира.")
            return redirect(
                "world:world_event_occurrence_detail",
                campaign_id=campaign.pk,
                occurrence_id=occurrence.pk,
            )
    context = _event_common_context(request, campaign)
    context.update({"form": form, "form_mode": "now"})
    return render(request, "world/event_form.html", context)


def _world_event_definition_or_404(campaign, definition_id):
    return get_object_or_404(
        WorldEvent.objects.select_related("campaign", "region", "created_by", "target_content_type"),
        pk=definition_id,
        campaign=campaign,
    )


@login_required
@require_GET
def world_event_definition_detail(request, campaign_id, definition_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    definition = _world_event_definition_or_404(campaign, definition_id)
    occurrences = list(definition.occurrences.select_related("region", "actor"))
    occurrence_rows = [
        {
            "occurrence": occurrence,
            "occurred_time": _event_time_label(
                campaign,
                occurrence.occurred_world_minutes,
            ),
        }
        for occurrence in occurrences
    ]
    context = _event_common_context(request, campaign)
    context.update(
        {
            "definition": definition,
            "type_label": world_event_type_label(definition.event_type),
            "trigger_label": trigger_presentation(definition),
            "effect_label": effect_presentation(definition),
            "scheduled_time": (
                _event_time_label(campaign, definition.trigger_at)
                if definition.trigger_at is not None
                else None
            ),
            "remaining_label": (
                _event_remaining_label(campaign, definition.trigger_at)
                if definition.trigger_at is not None
                else None
            ),
            "has_occurrence": bool(occurrences),
            "occurrence_rows": occurrence_rows,
        }
    )
    return render(request, "world/event_definition_detail.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def world_event_definition_edit(request, campaign_id, definition_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    definition = _world_event_definition_or_404(campaign, definition_id)
    form = WorldEventDefinitionEditForm(
        request.POST or None,
        campaign=campaign,
        initial={
            "title": definition.title,
            "description": definition.description,
            "region": definition.region_id,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            definition = update_world_event_definition(
                actor=request.user,
                campaign=campaign,
                definition=definition,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                region=form.cleaned_data["region"],
            )
        except (ValidationError, WorldEventError) as error:
            form.add_error(None, _decision_error_message(error))
        else:
            messages.success(request, "Определение события обновлено; прошлые срабатывания не изменены.")
            return redirect(
                "world:world_event_definition_detail",
                campaign_id=campaign.pk,
                definition_id=definition.pk,
            )
    context = _event_common_context(request, campaign)
    context.update({"form": form, "form_mode": "edit", "definition": definition})
    return render(request, "world/event_form.html", context)


@login_required
@require_POST
def world_event_definition_disable(request, campaign_id, definition_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    definition = _world_event_definition_or_404(campaign, definition_id)
    disable_world_event_definition(actor=request.user, campaign=campaign, definition=definition)
    messages.success(request, f"Событие «{definition.title}» отключено.")
    return redirect(
        "world:world_event_definition_detail",
        campaign_id=campaign.pk,
        definition_id=definition.pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def world_event_definition_remove(request, campaign_id, definition_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    definition = _world_event_definition_or_404(campaign, definition_id)
    if request.method == "POST":
        title = definition.title
        remove_world_event_definition(actor=request.user, campaign=campaign, definition=definition)
        messages.success(request, f"Определение «{title}» удалено; история сохранена.")
        return redirect("world:campaign_event_list", campaign_id=campaign.pk)
    context = _event_common_context(request, campaign)
    context["definition"] = definition
    return render(request, "world/event_definition_confirm_remove.html", context)


@login_required
@require_POST
def world_event_trigger_now(request, campaign_id, definition_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    definition = _world_event_definition_or_404(campaign, definition_id)
    try:
        occurrence = trigger_world_event_now(
            actor=request.user,
            campaign=campaign,
            definition=definition,
        )
    except (ValidationError, WorldEventError) as error:
        messages.error(request, _decision_error_message(error))
        return redirect(
            "world:world_event_definition_detail",
            campaign_id=campaign.pk,
            definition_id=definition.pk,
        )
    return redirect(
        "world:world_event_occurrence_detail",
        campaign_id=campaign.pk,
        occurrence_id=occurrence.pk,
    )


@login_required
@require_GET
def world_event_occurrence_detail(request, campaign_id, occurrence_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    occurrence = get_object_or_404(
        WorldEventOccurrence.objects.select_related(
            "definition", "region", "actor", "target_content_type"
        ),
        pk=occurrence_id,
        campaign=campaign,
    )
    audit_group = AuditLog.objects.filter(
        campaign=campaign,
        operation_id=occurrence.operation_id,
    ).order_by("occurred_at", "id")
    context = _event_common_context(request, campaign)
    context.update(
        {
            "occurrence": occurrence,
            "type_label": world_event_type_label(occurrence.event_type_snapshot),
            "occurred_time": _event_time_label(
                campaign,
                occurrence.occurred_world_minutes,
            ),
            "cause_label": (
                "Событие было запланировано на это мировое время."
                if occurrence.trigger_type_snapshot == WorldEvent.TriggerType.WORLD_TIME
                else f"Событие зафиксировал Game Master {occurrence.actor_label_snapshot}."
            ),
            "effect_label": (
                "Применено зарегистрированное доменное последствие."
                if occurrence.effect_type_snapshot
                else "Автоматических последствий не применялось. Факт добавлен в историю мира."
            ),
            "audit_group": audit_group,
        }
    )
    return render(request, "world/event_occurrence_detail.html", context)


@login_required
@require_POST
def approve_approval_request(request, campaign_id, request_id):
    return _approval_transition_view(
        request,
        campaign_id=campaign_id,
        request_id=request_id,
        transition=approve_request,
    )


@login_required
@require_POST
def reject_approval_request(request, campaign_id, request_id):
    return _approval_transition_view(
        request,
        campaign_id=campaign_id,
        request_id=request_id,
        transition=reject_request,
    )


@login_required
@require_POST
def cancel_approval_request(request, campaign_id, request_id):
    return _approval_transition_view(
        request,
        campaign_id=campaign_id,
        request_id=request_id,
        transition=cancel_request,
    )


@login_required
@require_GET
def region_climate_preview(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    try:
        if request.GET.get("polygon"):
            longitude, latitude = polygon_center(json.loads(request.GET["polygon"]))
        else:
            latitude = float(request.GET["latitude"])
            longitude = float(request.GET["longitude"])
        climate = region_climate_at(campaign, latitude, longitude)
    except (KeyError, TypeError, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(
        {
            **climate,
            "latitude": latitude,
            "longitude": longitude,
        }
    )


@login_required
@require_GET
def global_world_map(request):
    _global_atlas_or_403(request.user)
    can_view_objective_layers = True
    layer_state = get_global_map_layer()
    global_biomes = land_only_biome_cells(layer_state.biome_cells) if layer_state else {}
    palette = _biome_palette()
    return render(
        request,
        "world/global_world_map.html",
        {
            "can_view_objective_layers": can_view_objective_layers,
            "map_grid_width": MAP_GRID_WIDTH,
            "map_grid_height": MAP_GRID_HEIGHT,
            "biome_cells": global_biomes,
            "biome_palette": palette,
            "atlas_config": build_atlas_config(
                inspect_url=reverse("world:global_point_inspection"),
                global_biome_cells=global_biomes,
                biome_palette=palette,
                active_layer=request.GET.get("mode") or "base",
            ),
        },
    )


@login_required
@require_GET
def global_world_entry_list(request):
    require_global_atlas_viewer(request.user)
    entries = WorldEntry.objects.filter(scope=WorldEntry.Scope.GLOBAL).order_by(
        "kind", "title", "pk"
    )
    return render(
        request,
        "world/global_world_entry_list.html",
        {
            "entries": entries,
            "can_manage_global_canon": can_manage_global_canon(request.user),
        },
    )


@login_required
@require_GET
def global_world_entry_detail(request, entry_id):
    require_global_atlas_viewer(request.user)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.GLOBAL,
    )
    return render(
        request,
        "world/global_world_entry_detail.html",
        {
            "entry": entry,
            "can_manage_global_canon": can_manage_global_canon(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def global_world_entry_create(request):
    require_global_canon_editor(request.user)
    form = WorldEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            entry = create_global_world_entry(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Глобальная запись канона создана.")
            return redirect("world:global_world_entry_detail", entry_id=entry.pk)
    return render(
        request,
        "world/world_entry_form.html",
        {"form": form, "form_title": "Новая запись глобального канона", "is_global_form": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def global_world_entry_edit(request, entry_id):
    require_global_canon_editor(request.user)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.GLOBAL,
    )
    form = WorldEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        try:
            entry = update_global_world_entry(
                actor=request.user,
                entry=entry,
                **form.cleaned_data,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Глобальный канон обновлён.")
            return redirect("world:global_world_entry_detail", entry_id=entry.pk)
    return render(
        request,
        "world/world_entry_form.html",
        {"form": form, "form_title": f"Изменить: {entry.title}", "entry": entry, "is_global_form": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def global_world_entry_delete(request, entry_id):
    require_global_canon_editor(request.user)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.GLOBAL,
    )
    error_message = None
    if request.method == "POST":
        try:
            delete_global_world_entry(actor=request.user, entry=entry)
        except ValidationError as error:
            error_message = "; ".join(error.messages)
        else:
            messages.success(request, "Глобальная запись удалена.")
            return redirect("world:global_world_entry_list")
    return render(
        request,
        "world/world_entry_confirm_delete.html",
        {"entry": entry, "error_message": error_message, "is_global_form": True},
        status=400 if error_message else 200,
    )


@login_required
@require_GET
def campaign_world_entry_list(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    return render(
        request,
        "world/campaign_world_entry_list.html",
        {
            "campaign": campaign,
            "entries": effective_world_entries(campaign, include_suppressed=True),
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def campaign_world_entry_create(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    form = WorldEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_campaign_world_entry(
                actor=request.user,
                campaign=campaign,
                **form.cleaned_data,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Запись только этой кампании создана.")
            return redirect("world:campaign_world_entry_list", campaign_id=campaign.pk)
    return render(
        request,
        "world/world_entry_form.html",
        {"campaign": campaign, "form": form, "form_title": "Новая запись кампании", "time_advance_units": TIME_ADVANCE_UNITS, "can_advance_time": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def campaign_world_entry_edit(request, campaign_id, entry_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.CAMPAIGN,
        campaign=campaign,
    )
    form = WorldEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        try:
            update_campaign_world_entry(
                actor=request.user,
                campaign=campaign,
                entry=entry,
                **form.cleaned_data,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Campaign-запись обновлена.")
            return redirect("world:campaign_world_entry_list", campaign_id=campaign.pk)
    return render(
        request,
        "world/world_entry_form.html",
        {"campaign": campaign, "form": form, "entry": entry, "form_title": f"Изменить: {entry.title}", "time_advance_units": TIME_ADVANCE_UNITS, "can_advance_time": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def campaign_world_entry_delete(request, campaign_id, entry_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.CAMPAIGN,
        campaign=campaign,
    )
    if request.method == "POST":
        delete_campaign_world_entry(
            actor=request.user,
            campaign=campaign,
            entry=entry,
        )
        messages.success(request, "Campaign-запись удалена.")
        return redirect("world:campaign_world_entry_list", campaign_id=campaign.pk)
    return render(
        request,
        "world/world_entry_confirm_delete.html",
        {"campaign": campaign, "entry": entry, "time_advance_units": TIME_ADVANCE_UNITS, "can_advance_time": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def campaign_world_entry_override(request, campaign_id, entry_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.GLOBAL,
    )
    resolved = resolve_for_campaign(entry, campaign)
    initial = {} if resolved.override is None else resolved.override.patch
    form = CampaignOverrideForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        set_campaign_override(
            actor=request.user,
            campaign=campaign,
            target=entry,
            patch=form.patch(),
            is_suppressed=resolved.is_suppressed,
        )
        messages.success(request, "Отличия кампании сохранены.")
        return redirect("world:campaign_world_entry_list", campaign_id=campaign.pk)
    return render(
        request,
        "world/campaign_world_entry_override.html",
        {"campaign": campaign, "entry": entry, "resolved": resolved, "form": form, "time_advance_units": TIME_ADVANCE_UNITS, "can_advance_time": True},
    )


@login_required
@require_POST
def campaign_world_entry_override_action(request, campaign_id, entry_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    entry = get_object_or_404(
        WorldEntry,
        pk=entry_id,
        scope=WorldEntry.Scope.GLOBAL,
    )
    action = request.POST.get("action")
    if action == "suppress":
        set_campaign_suppression(
            actor=request.user,
            campaign=campaign,
            target=entry,
            is_suppressed=True,
        )
        messages.success(request, "Глобальная запись скрыта в этой кампании.")
    elif action == "restore":
        set_campaign_suppression(
            actor=request.user,
            campaign=campaign,
            target=entry,
            is_suppressed=False,
        )
        messages.success(request, "Глобальная запись возвращена в кампанию.")
    elif action == "remove":
        remove_campaign_override(
            actor=request.user,
            campaign=campaign,
            target=entry,
        )
        messages.success(request, "Override удалён; снова наследуется глобальный канон.")
    else:
        raise ValidationError("Неизвестное действие override.")
    return redirect("world:campaign_world_entry_list", campaign_id=campaign.pk)


@login_required
@require_GET
def global_point_inspection(request):
    _global_atlas_or_403(request.user)
    try:
        payload = inspect_map_point(
            float(request.GET["latitude"]),
            float(request.GET["longitude"]),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(payload)


def _latest_weather(region, world_minutes):
    return latest_current_point_weather(region, world_minutes)


def _weather_age_context(state, current_world_minutes, stale_after_minutes):
    if state is None:
        return None
    age_minutes = max(0, int(current_world_minutes) - int(state.world_minutes))
    if age_minutes < 60:
        label = f"{age_minutes} мин."
    elif age_minutes < 1440:
        label = f"{age_minutes / 60:.1f} ч."
    else:
        label = f"{age_minutes / 1440:.1f} суток"
    return {
        "minutes": age_minutes,
        "label": label,
        "is_stale": age_minutes > int(stale_after_minutes),
    }


def _temperature_color(weather):
    if weather is None:
        return "#9aa7bd"
    temperature = weather.temperature
    if temperature <= -20:
        return "#7892ff"
    if temperature <= 0:
        return "#68c7ff"
    if temperature <= 15:
        return "#70ddb1"
    if temperature <= 30:
        return "#ffd36e"
    return "#ff746f"


def _region_shapes(regions, campaign):
    shapes = []
    for region in regions:
        if not region.map_polygon:
            continue
        weather = _latest_weather(region, campaign.world_minutes)
        area_weather = latest_current_area_weather(region, campaign.world_minutes)
        area_summary = build_region_area_weather_summary(area_weather)
        shapes.append(
            {
                "id": region.pk,
                "name": region.name,
                "polygon": region.map_polygon,
                "points": polygon_svg_points(region.map_polygon),
                "temperature": weather.temperature if weather else None,
                "temperature_color": _temperature_color(weather),
                "detail_url": reverse(
                    "world:region_detail",
                    kwargs={"campaign_id": campaign.pk, "region_id": region.pk},
                ),
                "area_summary": (
                    None if area_summary is None else area_summary.description
                ),
                "area_weather": (
                    None
                    if area_weather is None
                    else {
                        "world_minutes": area_weather.world_minutes,
                        "age_minutes": max(
                            0,
                            int(campaign.world_minutes) - int(area_weather.world_minutes),
                        ),
                        "is_stale": (
                            int(campaign.world_minutes) - int(area_weather.world_minutes)
                            > int(region.weather_update_interval_minutes)
                        ),
                        "sampling_mode": area_weather.sampling_mode,
                        "temperature_p10_c": area_weather.temperature_p10_c,
                        "temperature_p90_c": area_weather.temperature_p90_c,
                        "precipitating_area_fraction": area_weather.precipitating_area_fraction,
                    }
                ),
            }
        )
    return shapes


@login_required
def world_map(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    placement_form = RegionPlacementForm(prefix="placement")
    layer_form = MapLayerPaintForm(prefix="layer")

    if request.method == "POST" and request.POST.get("action") == "place":
        placement_form = RegionPlacementForm(request.POST, prefix="placement")
        if placement_form.is_valid():
            region = get_object_or_404(
                campaign.regions,
                pk=placement_form.cleaned_data["region_id"],
            )
            polygon = placement_form.cleaned_data["map_polygon"]
            result = update_region(
                actor=request.user,
                campaign=campaign,
                region=region,
                changes=placement_changes(
                    campaign=campaign,
                    region=region,
                    polygon=polygon,
                ),
                initialize_weather=True,
                summary=f"Изменён контур региона «{region.name}».",
            )
            region = result.region
            return redirect(
                "world:region_detail",
                campaign_id=campaign.pk,
                region_id=region.pk,
            )
        create_form = RegionMapForm(campaign=campaign, prefix="create")
    elif request.method == "POST" and request.POST.get("action") == "save-layer":
        layer_form = MapLayerPaintForm(request.POST, prefix="layer")
        if layer_form.is_valid():
            layer_type = layer_form.cleaned_data["layer_type"]
            update_campaign_biome_layer(
                actor=request.user,
                campaign=campaign,
                cells=layer_form.cleaned_data["layer_cells"],
            )
            url = reverse("world:world_map", kwargs={"campaign_id": campaign.pk})
            return redirect(f"{url}?mode={layer_type}")
        create_form = RegionMapForm(campaign=campaign, prefix="create")
    elif request.method == "POST":
        create_form = RegionMapForm(request.POST, campaign=campaign, prefix="create")
        if create_form.is_valid():
            region = create_form.save(commit=False)
            result = create_region(
                actor=request.user,
                campaign=campaign,
                region=region,
            )
            region = result.region
            return redirect(
                "world:region_detail",
                campaign_id=campaign.pk,
                region_id=region.pk,
            )
    else:
        create_form = RegionMapForm(campaign=campaign, prefix="create")

    regions = list(campaign.regions.all().order_by("name"))
    shapes = _region_shapes(regions, campaign)
    layer_state = get_global_map_layer()
    campaign_layer = get_campaign_map_override(campaign)
    global_biomes = land_only_biome_cells(layer_state.biome_cells) if layer_state else {}
    campaign_biomes = (
        land_only_biome_cells(campaign_layer.biome_cells) if campaign_layer else {}
    )
    palette = _biome_palette()
    light_bands = build_light_bands(campaign, campaign.world_minutes)
    celestial = celestial_positions(campaign, campaign.world_minutes)
    return render(
        request,
        "world/world_map.html",
        {
            "campaign": campaign,
            "create_form": create_form,
            "placement_form": placement_form,
            "regions": regions,
            "region_shapes": shapes,
            "light_bands": light_bands,
            "celestial": celestial,
            "layer_form": layer_form,
            "map_grid_width": MAP_GRID_WIDTH,
            "map_grid_height": MAP_GRID_HEIGHT,
            "biome_cells": effective_biome_cells(global_biomes, campaign_biomes),
            "global_biome_cells": global_biomes,
            "campaign_biome_cells": campaign_biomes,
            "elevation_cells": layer_state.elevation_cells if layer_state else {},
            "biome_palette": palette,
            "atlas_config": build_atlas_config(
                campaign=campaign,
                inspect_url=reverse(
                    "world:campaign_point_inspection",
                    kwargs={"campaign_id": campaign.pk},
                ),
                region_shapes=shapes,
                global_biome_cells=global_biomes,
                campaign_biome_cells=campaign_biomes,
                biome_palette=palette,
                light_bands=light_bands,
                celestial=celestial,
                active_layer=request.GET.get("mode") or "light",
            ),
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )


@login_required
@require_GET
def campaign_point_inspection(request, campaign_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    try:
        payload = inspect_map_point(
            float(request.GET["latitude"]),
            float(request.GET["longitude"]),
            campaign=campaign,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET", "POST"])
def region_detail(request, campaign_id, region_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    region = get_object_or_404(
        Region.objects.select_related("campaign"),
        pk=region_id,
        campaign=campaign,
    )
    if request.method == "POST" and request.POST.get("action") in {
        "refresh-climate",
        "enable-auto-climate",
    }:
        if region.map_latitude is None or region.map_longitude is None:
            messages.error(request, "Сначала расположите регион на карте.")
        elif (
            region.use_manual_climate_overrides
            and request.POST.get("action") == "refresh-climate"
        ):
            messages.info(
                request,
                "Ручные климатические поправки включены; World Data их не перезаписывает.",
            )
        else:
            result = update_region(
                actor=request.user,
                campaign=campaign,
                region=region,
                changes=automatic_climate_changes(
                    campaign=campaign,
                    region=region,
                ),
                initialize_weather=True,
                summary=f"Обновлён климат региона «{region.name}» из World Data.",
            )
            region = result.region
            initialization = result.initialization
            if initialization.pending:
                messages.info(
                    request,
                    "Данные региона обновлены; физическая погода ожидает первый совместимый снимок атмосферы.",
                )
            else:
                messages.success(request, "Данные региона обновлены из World Data.")
        return redirect(
            "world:region_detail",
            campaign_id=campaign.pk,
            region_id=region.pk,
        )
    weather = _latest_weather(region, campaign.world_minutes)
    area_weather = latest_current_area_weather(region, campaign.world_minutes)
    sky = describe_region_sky(region, campaign.world_minutes)
    moment = sky.local_moment
    atmospheric_config = AtmosphericConfig.objects.filter(campaign=campaign).first()
    atmosphere_settings = (
        AtmosphericSettings.from_model(atmospheric_config, campaign)
        if atmospheric_config is not None
        else AtmosphericSettings(world_circumference_km=campaign.world_circumference_km)
    )
    stale_after_minutes = (
        atmospheric_config.step_minutes
        if (
            atmospheric_config is not None
            and atmospheric_config.enabled
            and region.map_latitude is not None
            and region.map_longitude is not None
        )
        else region.weather_update_interval_minutes
    )
    physical_weather_expected = (
        atmospheric_config is not None
        and atmospheric_config.enabled
        and region.map_latitude is not None
        and region.map_longitude is not None
    )
    physical_weather_pending = physical_weather_expected and weather is None
    area_weather_pending = physical_weather_expected and area_weather is None
    radiative_diagnostics = CampaignSkyForcing(
        campaign,
        atmosphere_settings,
    ).diagnostics(
        sky.latitude,
        sky.longitude,
        campaign.world_minutes,
    )
    c2_diagnostics = None
    if (
        atmospheric_config is not None
        and atmospheric_config.enabled
        and region.map_latitude is not None
        and region.map_longitude is not None
    ):
        c2_diagnostics = latest_atmospheric_cell_diagnostics(
            campaign,
            atmospheric_config,
            region.map_latitude,
            region.map_longitude,
            world_minutes=campaign.world_minutes,
            local_elevation_m=region.elevation,
        )
    atmosphere_style = (
        f"--star-opacity:{0.04 + sky.star_intensity * 0.96:.4f};"
        f"--ympha-opacity:{(1 - sky.star_intensity) * sky.ympha_visibility:.4f};"
        f"--dark-opacity:{sky.darkness * 0.99:.4f};"
    )
    environment_summary = build_environment_summary(
        weather,
        sky=sky,
        biome=region.biome,
        elevation_m=region.elevation,
        oxygen_fraction=(
            None if atmospheric_config is None else atmospheric_config.oxygen_fraction
        ),
        parameters=atmosphere_settings.parameters,
    )
    return render(
        request,
        "world/region_detail.html",
        {
            "campaign": campaign,
            "region": region,
            "weather": weather,
            "area_weather": area_weather,
            "area_weather_summary": build_region_area_weather_summary(area_weather),
            "weather_age": _weather_age_context(
                weather,
                campaign.world_minutes,
                stale_after_minutes,
            ),
            "area_weather_age": _weather_age_context(
                area_weather,
                campaign.world_minutes,
                stale_after_minutes,
            ),
            "physical_weather_pending": physical_weather_pending,
            "area_weather_pending": area_weather_pending,
            "weather_summary": build_weather_summary(weather),
            "environment_summary": environment_summary,
            "sky": sky,
            "calendar": moment,
            "season_code": SEASON_CODES[moment.season],
            "weather_code": weather.condition if weather else "clear",
            "atmosphere_style": atmosphere_style,
            "region_points": polygon_svg_points(region.map_polygon),
            "map_defaults": (
                map_defaults_at(campaign, sky.longitude, sky.latitude)
                if sky.location_known
                else None
            ),
            "radiative_diagnostics": radiative_diagnostics,
            "c2_diagnostics": c2_diagnostics,
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def region_delete(request, campaign_id, region_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    region = get_object_or_404(
        Region,
        pk=region_id,
        campaign=campaign,
    )

    if request.method == "POST":
        region_name = region.name
        delete_region_service(
            actor=request.user,
            campaign=campaign,
            region=region,
        )
        messages.success(request, f"Регион «{region_name}» удалён.")
        return redirect("world:world_map", campaign_id=campaign.pk)

    return render(
        request,
        "world/region_confirm_delete.html",
        {
            "campaign": campaign,
            "region": region,
            "weather_state_count": region.weather_history.count(),
            "world_event_count": region.events.count(),
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )
