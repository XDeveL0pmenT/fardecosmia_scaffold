from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from campaigns.models import Campaign, CampaignMembership
from campaigns.time_controls import TIME_ADVANCE_UNITS
from world.biomes import BIOME_PALETTE
from world.forms import MapLayerPaintForm, RegionMapForm, RegionPlacementForm
from world.models import AtmosphericConfig, Region
from world.services.astronomy import (
    build_light_bands,
    celestial_positions,
    describe_region_sky,
)
from world.services.map_geometry import polygon_center, polygon_svg_points
from world.services.map_layers import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    effective_biome_cells,
    get_campaign_map_override,
    get_global_map_layer,
    land_only_biome_cells,
    map_defaults_at,
)
from world.services.weather import generate_weather
from world.services.weather_display import build_weather_summary
from world.services.environment_summary import build_environment_summary
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.persistence import latest_atmospheric_cell_diagnostics


SEASON_CODES = {
    "Лето": "summer",
    "Осень": "autumn",
    "Зима": "winter",
    "Весна": "spring",
}
def _gm_campaign_or_403(user, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    is_gm = campaign.memberships.filter(
        user=user,
        role=CampaignMembership.Role.GM,
    ).exists()
    if not is_gm:
        raise PermissionDenied("Карта объективного состояния мира доступна только мастеру.")
    return campaign


def _biome_palette():
    return [
        {"value": value, "label": label, "color": BIOME_PALETTE[value]}
        for value, label in Region.Biome.choices
    ]


@login_required
def global_world_map(request):
    can_view_objective_layers = request.user.campaign_memberships.filter(
        role=CampaignMembership.Role.GM,
    ).exists()
    if not can_view_objective_layers:
        raise PermissionDenied(
            "Общий объективный атлас доступен только мастеру хотя бы одной кампании."
        )
    layer_state = get_global_map_layer() if can_view_objective_layers else None
    return render(
        request,
        "world/global_world_map.html",
        {
            "can_view_objective_layers": can_view_objective_layers,
            "map_grid_width": MAP_GRID_WIDTH,
            "map_grid_height": MAP_GRID_HEIGHT,
            "biome_cells": land_only_biome_cells(layer_state.biome_cells) if layer_state else {},
            "biome_palette": _biome_palette(),
        },
    )


def _latest_weather(region, world_minutes):
    return (
        region.weather_history.filter(world_minutes__lte=world_minutes)
        .order_by("-world_minutes")
        .first()
    )


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
        shapes.append(
            {
                "id": region.pk,
                "name": region.name,
                "polygon": region.map_polygon,
                "points": polygon_svg_points(region.map_polygon),
                "temperature": weather.temperature if weather else None,
                "temperature_color": _temperature_color(weather),
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
            region.save(update_fields=["map_polygon", "map_longitude", "map_latitude"])
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
            region.save()
            boundary = campaign.world_minutes - (
                campaign.world_minutes % region.weather_update_interval_minutes
            )
            generate_weather(region, boundary)
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
    return render(
        request,
        "world/world_map.html",
        {
            "campaign": campaign,
            "create_form": create_form,
            "placement_form": placement_form,
            "regions": regions,
            "region_shapes": shapes,
            "light_bands": build_light_bands(campaign, campaign.world_minutes),
            "celestial": celestial_positions(campaign, campaign.world_minutes),
            "layer_form": layer_form,
            "map_grid_width": MAP_GRID_WIDTH,
            "map_grid_height": MAP_GRID_HEIGHT,
            "biome_cells": effective_biome_cells(global_biomes, campaign_biomes),
            "global_biome_cells": global_biomes,
            "campaign_biome_cells": campaign_biomes,
            "elevation_cells": layer_state.elevation_cells if layer_state else {},
            "biome_palette": _biome_palette(),
            "time_advance_units": TIME_ADVANCE_UNITS,
            "can_advance_time": True,
        },
    )


@login_required
def region_detail(request, campaign_id, region_id):
    campaign = _gm_campaign_or_403(request.user, campaign_id)
    region = get_object_or_404(
        Region.objects.select_related("campaign"),
        pk=region_id,
        campaign=campaign,
    )
    weather = _latest_weather(region, campaign.world_minutes)
    sky = describe_region_sky(region, campaign.world_minutes)
    moment = sky.local_moment
    atmospheric_config = AtmosphericConfig.objects.filter(campaign=campaign).first()
    atmosphere_settings = (
        AtmosphericSettings.from_model(atmospheric_config, campaign)
        if atmospheric_config is not None
        else AtmosphericSettings(world_circumference_km=campaign.world_circumference_km)
    )
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
            "weather_summary": build_weather_summary(weather),
            "environment_summary": environment_summary,
            "sky": sky,
            "calendar": moment,
            "season_code": SEASON_CODES[moment.season],
            "weather_code": weather.condition if weather else "clear",
            "atmosphere_style": atmosphere_style,
            "region_points": polygon_svg_points(region.map_polygon),
            "map_defaults": map_defaults_at(
                campaign,
                sky.longitude,
                sky.latitude,
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
