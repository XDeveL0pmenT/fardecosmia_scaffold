#!/usr/bin/env python
"""Trace one current exact-step precipitation diagnostic through persistence.

The command is read-only.  It advances the latest compatible campaign grid by
one exact timestep in memory, selects that step's wettest cell, round-trips the
grid payload and samples the exact cell centre without creating a Region.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from campaigns.models import Campaign  # noqa: E402
from world.services.atmosphere.config import AtmosphericSettings  # noqa: E402
from world.services.atmosphere.coordinate_sampling import sample_environment_at  # noqa: E402
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint  # noqa: E402
from world.services.atmosphere.forcing import CampaignSkyForcing  # noqa: E402
from world.services.atmosphere.geometry import geometry_for  # noqa: E402
from world.services.atmosphere.grid import AtmosphericGrid  # noqa: E402
from world.services.atmosphere.microphysics import rain_and_snow_fraction  # noqa: E402
from world.services.atmosphere.ocean import air_column_mass_kg_m2  # noqa: E402
from world.services.atmosphere.persistence import grid_from_snapshot  # noqa: E402
from world.services.atmosphere.sampling import _weather_from_grid_at_time  # noqa: E402
from world.services.atmosphere.simulation import simulate_step  # noqa: E402
from world.services.atmosphere.static_grid import cached_static_world_grid  # noqa: E402
from world.services.environment_summary import build_environment_summary  # noqa: E402
from world.services.weather_display import build_weather_summary  # noqa: E402


def trace(campaign_id):
    campaign = Campaign.objects.get(pk=campaign_id)
    config = campaign.atmospheric_config
    if not config.enabled:
        raise ValueError("Атмосфера кампании отключена.")
    settings = AtmosphericSettings.from_model(config, campaign)
    fingerprint = atmospheric_input_fingerprint(campaign, config)
    snapshot = (
        campaign.atmospheric_snapshots.filter(
            input_fingerprint=fingerprint,
            world_minutes__lte=campaign.world_minutes,
        )
        .order_by("-world_minutes", "-created_at")
        .first()
    )
    if snapshot is None:
        raise ValueError("Нет совместимого AtmosphericSnapshot.")

    previous = grid_from_snapshot(snapshot)
    static = cached_static_world_grid(settings)
    next_minutes = snapshot.world_minutes + settings.step_minutes
    diagnostics = {}
    exact = simulate_step(
        previous,
        static,
        settings,
        step_index=next_minutes // settings.step_minutes,
        world_minutes=next_minutes,
        forcing=CampaignSkyForcing(campaign, settings),
        diagnostics=diagnostics,
    )
    rate = exact.fields["precipitation_rate"].astype(np.float64)
    index = int(np.argmax(rate))
    if rate[index] <= 0.0:
        raise ValueError("В следующем exact timestep нет мокрых клеток.")

    geometry = geometry_for(settings)
    latitude = float(geometry.latitude[index])
    longitude = float(geometry.longitude[index])
    seconds = settings.step_minutes * 60.0
    air_mass = float(
        air_column_mass_kg_m2(exact.fields["pressure_hpa"], settings)[index]
    )
    removed_q_c = float(rate[index] * seconds / air_mass)
    post_fallout_q_c = float(
        exact.fields["cloud_condensate_specific_humidity"][index]
    )
    rain, snow = rain_and_snow_fraction(
        float(exact.fields["temperature"][index]),
        settings,
    )

    payload = exact.serialize()
    restored = AtmosphericGrid.deserialize(exact.width, exact.height, payload)
    point = sample_environment_at(
        restored,
        static,
        settings,
        latitude,
        longitude,
    )
    transient_region = campaign.regions.model(
        campaign=campaign,
        name="C4.2 trace (not saved)",
        map_latitude=latitude,
        map_longitude=longitude,
    )
    weather = _weather_from_grid_at_time(
        transient_region,
        next_minutes,
        restored,
        parameters=config.parameters,
        settings=settings,
        static=static,
    )
    weather_display = build_weather_summary(weather)
    environment = build_environment_summary(
        weather,
        elevation_m=point.elevation_m,
        parameters=settings.parameters,
    )
    return {
        "source_snapshot_world_minutes": snapshot.world_minutes,
        "traced_exact_world_minutes": next_minutes,
        "grid": [settings.width, settings.height],
        "wet_cells_in_exact_step": int(np.count_nonzero(rate > 0.0)),
        "visible_wet_cells_in_exact_step": int(
            np.count_nonzero(
                rate * 3600.0
                >= settings.value("condition_precipitation_rate_mm_h")
            )
        ),
        "cell": {
            "index": index,
            "latitude": latitude,
            "longitude": longitude,
            "derived_pre_fallout_q_c": post_fallout_q_c + removed_q_c,
            "removed_q_c": removed_q_c,
            "post_fallout_q_c": post_fallout_q_c,
            "raw_microphysics_rate_mm_h": float(rate[index] * 3600.0),
            "raw_microphysics_amount_mm_this_step": float(rate[index] * seconds),
            "rain_fraction": float(np.asarray(rain).reshape(-1)[0]),
            "snow_fraction": float(np.asarray(snow).reshape(-1)[0]),
            "serialized_payload_bytes": len(payload),
            "snapshot_roundtrip_rate_mm_h": float(
                restored.fields["precipitation_rate"][index] * 3600.0
            ),
            "coordinate_sampler_rate_mm_h": float(
                point.values["precipitation_rate"] * 3600.0
            ),
            "weather_state_rate_mm_h": weather.precipitation_rate_mm_h,
            "weather_state_amount_mm": weather.precipitation_amount_mm,
            "weather_state_condition": weather.condition,
            "weather_display": weather_display["precipitation"],
            "environment_precipitation": environment.precipitation_label,
        },
        "diagnostics": {
            "precipitation_active_cells": diagnostics.get(
                "precipitation_active_cells", 0
            ),
            "total_precipitated_mass_kg": diagnostics.get(
                "total_precipitated_mass_kg", 0.0
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_id")
    args = parser.parse_args()
    print(json.dumps(trace(args.campaign_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
