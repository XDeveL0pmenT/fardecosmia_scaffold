import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from campaigns.models import Campaign
from campaigns.time_controls import TIME_ADVANCE_UNITS
from world.biomes import BIOME_PALETTE
from world.forms import (
    CampaignOverrideForm,
    MapLayerPaintForm,
    RegionMapForm,
    RegionPlacementForm,
    WorldEntryForm,
)
from world.models import AtmosphericConfig, Region, WorldEntry
from world.services.access import (
    can_manage_global_canon,
    require_campaign_gm,
    require_global_atlas_viewer,
    require_global_canon_editor,
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
)
from world.services.region_climate import apply_region_climate, region_climate_at
from world.services.weather_display import build_weather_summary
from world.services.environment_summary import build_environment_summary
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.persistence import latest_atmospheric_cell_diagnostics
from world.services.atmosphere.region_area import build_region_area_weather_summary
from world.services.region_weather import (
    initialize_region_weather,
    latest_current_area_weather,
    latest_current_point_weather,
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


def _biome_palette():
    return [
        {"value": value, "label": label, "color": BIOME_PALETTE[value]}
        for value, label in Region.Biome.choices
    ]


def _global_atlas_or_403(user):
    require_global_atlas_viewer(user)


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
            longitude, latitude = polygon_center(polygon)
            region.map_polygon = polygon
            region.map_longitude = longitude
            region.map_latitude = latitude
            climate = region_climate_at(campaign, latitude, longitude)
            climate_fields = apply_region_climate(region, climate)
            region.save(
                update_fields=[
                    "map_polygon",
                    "map_longitude",
                    "map_latitude",
                    *climate_fields,
                ]
            )
            initialize_region_weather(region)
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
            layer_state = get_campaign_map_override(campaign, create=True)
            layer_state.biome_cells = layer_form.cleaned_data["layer_cells"]
            layer_state.save(update_fields=["biome_cells", "updated_at"])
            url = reverse("world:world_map", kwargs={"campaign_id": campaign.pk})
            return redirect(f"{url}?mode={layer_type}")
        create_form = RegionMapForm(campaign=campaign, prefix="create")
    elif request.method == "POST":
        create_form = RegionMapForm(request.POST, campaign=campaign, prefix="create")
        if create_form.is_valid():
            region = create_form.save(commit=False)
            region.campaign = campaign
            longitude, latitude = polygon_center(region.map_polygon)
            region.map_longitude = longitude
            region.map_latitude = latitude
            apply_region_climate(
                region,
                region_climate_at(campaign, latitude, longitude),
            )
            region.save()
            initialize_region_weather(region)
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
            region.use_manual_climate_overrides = False
            updated = apply_region_climate(
                region,
                region_climate_at(
                    campaign,
                    region.map_latitude,
                    region.map_longitude,
                ),
            )
            region.save(
                update_fields=["use_manual_climate_overrides", *updated]
            )
            initialization = initialize_region_weather(region)
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
        region.delete()
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
