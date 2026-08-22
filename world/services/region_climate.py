"""Region climate metadata derived from objective World Data.

AtmosphericGrid remains the source of current weather.  This module only
builds the map climatology shown on a Region and the legacy fallback baseline.
"""

from __future__ import annotations

from world.models import (
    AtmosphericConfig,
    CampaignWorldMapOverride,
    GlobalWorldMapLayer,
    Region,
)
from world.services.atmosphere.climatology import (
    initial_relative_humidity_percent,
)
from world.services.atmosphere.config import AtmosphericSettings
from world.services.world_data import SurfaceType, WorldData, coordinates_to_grid


DERIVED_REGION_FIELDS = (
    "biome",
    "base_temperature",
    "humidity",
    "elevation",
)

LEGACY_CLIMATE_FIELDS = (
    "seasonal_amplitude",
    "weather_volatility",
    "precipitation_bias",
)


def atmospheric_settings_for_campaign(campaign):
    config = AtmosphericConfig.objects.filter(campaign=campaign).first()
    if config is not None:
        return AtmosphericSettings.from_model(config, campaign)
    return AtmosphericSettings(
        world_circumference_km=campaign.world_circumference_km,
    )


def climatological_humidity_at(
    latitude,
    longitude,
    *,
    campaign=None,
    settings=None,
    world_data=None,
):
    """Return map-baseline RH using the same logic as grid initialization."""

    world_data = world_data or WorldData()
    if settings is None:
        settings = (
            atmospheric_settings_for_campaign(campaign)
            if campaign is not None
            else AtmosphericSettings()
        )
    surface = world_data.surface_at(latitude, longitude)
    value = initial_relative_humidity_percent(
        surface == SurfaceType.OCEAN,
        settings,
    )
    return float(value)


def region_climate_at(campaign, latitude, longitude):
    """Return the one canonical backend preview used by forms and saves."""

    global_layer = GlobalWorldMapLayer.objects.filter(
        slug=GlobalWorldMapLayer.FARDECOSMIA_SLUG,
    ).first()
    world_data = WorldData(layer=global_layer)
    surface = world_data.surface_at(latitude, longitude)
    biome = world_data.biome_at(latitude, longitude)
    biome_source = "global_atlas" if biome else "unknown"

    campaign_layer = CampaignWorldMapOverride.objects.filter(
        campaign=campaign,
    ).first()
    if campaign_layer is not None and surface == SurfaceType.LAND:
        _, _, index = coordinates_to_grid(
            latitude,
            longitude,
            width=campaign_layer.grid_width,
            height=campaign_layer.grid_height,
        )
        override = campaign_layer.biome_cells.get(str(index))
        if override is not None:
            biome = override
            biome_source = "campaign_override"

    settings = atmospheric_settings_for_campaign(campaign)
    elevation = world_data.elevation_at(latitude, longitude)
    biome_labels = dict(Region.Biome.choices)
    return {
        "biome": biome or "",
        "biome_label": biome_labels.get(biome, "Не задан"),
        "biome_source": biome_source,
        "base_temperature": round(
            world_data.mean_temperature_at(latitude, longitude),
            3,
        ),
        "humidity": round(
            climatological_humidity_at(
                latitude,
                longitude,
                settings=settings,
                world_data=world_data,
            ),
            3,
        ),
        "elevation": None if elevation is None else round(elevation, 3),
        "surface_type": surface.value,
        "surface_label": "Суша" if surface == SurfaceType.LAND else "Океан",
    }


def apply_region_climate(region, climate, *, reset_legacy=True):
    """Apply derived map values unless the GM explicitly owns the numbers."""

    if region.use_manual_climate_overrides:
        return []
    region.biome = climate["biome"]
    region.base_temperature = climate["base_temperature"]
    region.humidity = climate["humidity"]
    region.elevation = climate["elevation"]
    updated = list(DERIVED_REGION_FIELDS)
    if reset_legacy:
        for field_name in LEGACY_CLIMATE_FIELDS:
            model_field = Region._meta.get_field(field_name)
            setattr(region, field_name, model_field.get_default())
        updated.extend(LEGACY_CLIMATE_FIELDS)
    return updated
