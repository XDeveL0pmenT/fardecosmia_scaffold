#!/usr/bin/env python
"""Slow C1 stability benchmark on a reduced grid (not part of unit tests)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from time import perf_counter

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from campaigns.models import Campaign  # noqa: E402
from world.services.atmosphere.config import AtmosphericSettings  # noqa: E402
from world.services.atmosphere.forcing import CampaignSkyForcing  # noqa: E402
from world.services.atmosphere.simulation import initialize_atmosphere, simulate_step  # noqa: E402
from world.services.atmosphere.static_grid import StaticWorldGrid  # noqa: E402
from world.services.orbital_climate import CANONICAL_YEAR_MINUTES, orbital_climate_state  # noqa: E402


def main():
    width, height, step = 24, 12, 360
    size = width * height
    settings = AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=step,
        ocean_temperature_c=45,
        parameters={
            "initial_temperature_noise_c": 0.0,
            "pressure_noise_hpa": 0.0,
        },
    )
    static = StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=np.zeros(size, dtype=np.bool_),
        elevation=np.zeros(size, dtype=np.float32),
        mean_temperature=np.full(size, 15.0, dtype=np.float32),
        biome=tuple(None for _ in range(size)),
    )
    campaign = Campaign()
    forcing = CampaignSkyForcing(campaign, settings)
    star_only_settings = AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=step,
        ocean_temperature_c=45,
        parameters={
            "initial_temperature_noise_c": 0.0,
            "pressure_noise_hpa": 0.0,
            "ympha_response_c": 0.0,
        },
    )
    star_only_forcing = CampaignSkyForcing(campaign, star_only_settings)
    grid, _ = initialize_atmosphere(
        settings,
        static=static,
        world_minutes=0,
        forcing=forcing,
    )
    controlled_repeat, _ = initialize_atmosphere(
        star_only_settings,
        static=static,
        world_minutes=CANONICAL_YEAR_MINUTES,
        forcing=star_only_forcing,
    )
    initial_mean = float(np.mean(grid.fields["temperature"]))
    minimum = float("inf")
    maximum = float("-inf")
    started = perf_counter()
    for world_minutes in range(step, CANONICAL_YEAR_MINUTES + 1, step):
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=world_minutes // step,
            world_minutes=world_minutes,
            forcing=forcing,
        )
        values = grid.fields["temperature"]
        if not np.isfinite(values).all():
            raise SystemExit("NaN/Inf detected")
        minimum = min(minimum, float(np.min(values)))
        maximum = max(maximum, float(np.max(values)))
    elapsed = perf_counter() - started
    first_orbit = orbital_climate_state(0)
    wrapped_orbit = orbital_climate_state(CANONICAL_YEAR_MINUTES)
    result = {
        "grid": [width, height],
        "steps": CANONICAL_YEAR_MINUTES // step,
        "wall_seconds": round(elapsed, 6),
        "temperature_min_c": round(minimum, 4),
        "temperature_max_c": round(maximum, 4),
        "temperature_mean_drift_c": round(
            float(np.mean(grid.fields["temperature"])) - initial_mean,
            6,
        ),
        "controlled_stellar_surface_repeat_max_error_c": float(
            np.max(
                np.abs(
                    controlled_repeat.fields["surface_temperature"]
                    - initialize_atmosphere(
                        star_only_settings,
                        static=static,
                        world_minutes=0,
                        forcing=star_only_forcing,
                    )[0].fields["surface_temperature"]
                )
            )
        ),
        "orbital_distance_wrap_error_au": abs(
            first_orbit.star_distance_au - wrapped_orbit.star_distance_au
        ),
    }
    if not (-150.0 <= minimum <= maximum <= 150.0):
        raise SystemExit(f"Temperature bounds failed: {result}")
    if result["controlled_stellar_surface_repeat_max_error_c"] > 1e-5:
        raise SystemExit(f"Controlled seasonal repeat failed: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
