"""Region weather lifecycle and source-precedence rules for R1."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from world.models import AtmosphericConfig
from world.services.atmosphere.persistence import (
    initialize_region_weather_from_latest_snapshot,
)
from world.services.weather import generate_weather


@dataclass(frozen=True)
class RegionWeatherInitialization:
    point_weather: object | None
    area_weather: object | None
    mode: str

    @property
    def pending(self):
        return self.mode == "physical_pending"


def latest_current_point_weather(region, world_minutes):
    """Return weather for the Region's current geometry revision only."""

    revision_filter = Q(region_weather_revision=region.weather_geometry_revision)
    # Runtime-created legacy fixtures/integrations may still omit provenance;
    # migration 0016 assigns those historical rows to revision zero.
    if region.weather_geometry_revision == 0:
        revision_filter |= Q(region_weather_revision__isnull=True)
    return (
        region.weather_history.filter(revision_filter, world_minutes__lte=world_minutes)
        .order_by("-world_minutes", "-pk")
        .first()
    )


def latest_current_area_weather(region, world_minutes):
    """Return contour weather for the Region's current geometry revision."""

    return (
        region.area_weather_history.filter(
            region_weather_revision=region.weather_geometry_revision,
            world_minutes__lte=world_minutes,
        )
        .order_by("-world_minutes", "-pk")
        .first()
    )


def initialize_region_weather(region):
    """Initialize/refresh weather according to the campaign's active source.

    Located regions in an enabled atmospheric campaign may use only a
    compatible persisted physical snapshot.  Missing snapshots are represented
    as pending data.  Legacy generation remains available only when the global
    grid is disabled/missing or the Region has no map coordinates.
    """

    config = AtmosphericConfig.objects.filter(campaign=region.campaign).first()
    located = region.map_latitude is not None and region.map_longitude is not None
    if config is not None and config.enabled and located:
        initialize_region_weather_from_latest_snapshot(region, config)
        point = latest_current_point_weather(
            region,
            region.campaign.world_minutes,
        )
        area = latest_current_area_weather(
            region,
            region.campaign.world_minutes,
        )
        return RegionWeatherInitialization(
            point_weather=point,
            area_weather=area,
            mode="physical" if point is not None else "physical_pending",
        )

    boundary = region.campaign.world_minutes - (
        region.campaign.world_minutes % region.weather_update_interval_minutes
    )
    point = generate_weather(region, boundary)
    return RegionWeatherInitialization(
        point_weather=point,
        area_weather=None,
        mode="legacy",
    )
