#!/usr/bin/env python
"""Phase C2 reduced-grid long-run and fast-forward accuracy benchmark.

This script is intentionally outside the ordinary unit-test suite. It performs
two canonical years of sequential 360-minute physics and compares the slow
ocean fast-forward path with exact SST at one season and one year.
"""

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
from world.services.atmosphere.geometry import geometry_for  # noqa: E402
from world.services.atmosphere.ocean import (  # noqa: E402
    advance_ocean_fast_forward,
    ocean_baseline_sst,
    ocean_weighted_mean,
)
from world.services.atmosphere.simulation import (  # noqa: E402
    initialize_atmosphere,
    simulate_step,
)
from world.services.atmosphere.thermodynamics import (  # noqa: E402
    relative_humidity_percent,
)
from world.services.atmosphere.static_grid import build_static_world_grid  # noqa: E402
from world.services.calendar import TURNS_PER_SEASON  # noqa: E402
from world.services.orbital_climate import CANONICAL_YEAR_MINUTES  # noqa: E402


WIDTH = 24
HEIGHT = 12
STEP_MINUTES = 360
TURN_MINUTES = 168 * 60
SEASON_MINUTES = TURNS_PER_SEASON * TURN_MINUTES
TWO_YEARS_MINUTES = 2 * CANONICAL_YEAR_MINUTES


def make_case(parameter_overrides=None):
    parameters = {
        "initial_temperature_noise_c": 0.0,
        "pressure_noise_hpa": 0.0,
    }
    parameters.update(parameter_overrides or {})
    settings = AtmosphericSettings(
        width=WIDTH,
        height=HEIGHT,
        step_minutes=STEP_MINUTES,
        world_seed=202,
        ocean_temperature_c=64.0,
        parameters=parameters,
    )
    static = build_static_world_grid(settings)
    campaign = Campaign()
    forcing = CampaignSkyForcing(campaign, settings)
    grid, _ = initialize_atmosphere(
        settings,
        static=static,
        world_minutes=0,
        forcing=forcing,
    )
    return grid, static, settings, forcing


def exact_two_year_run(*, collect_series):
    grid, static, settings, forcing = make_case()
    baseline = ocean_baseline_sst(static, settings)
    ocean = static.is_ocean
    diagnostics = {}
    daily_sst_anomaly = []
    daily_stellar_anomaly = []
    captured = {}
    captured_precipitation_mass = {}
    minimum_sst = float("inf")
    maximum_sst = float("-inf")
    maximum_q = 0.0
    maximum_q_c = 0.0
    minimum_air_temperature = float("inf")
    maximum_air_temperature = float("-inf")
    minimum_pressure = float("inf")
    maximum_pressure = float("-inf")
    started = perf_counter()
    for world_minutes in range(STEP_MINUTES, TWO_YEARS_MINUTES + 1, STEP_MINUTES):
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=world_minutes // STEP_MINUTES,
            world_minutes=world_minutes,
            forcing=forcing,
            diagnostics=diagnostics,
        )
        if world_minutes in (SEASON_MINUTES, CANONICAL_YEAR_MINUTES):
            captured[world_minutes] = grid.clone()
            captured_precipitation_mass[world_minutes] = diagnostics.get(
                "total_precipitated_mass_kg", 0.0
            )
        sst = grid.fields["sea_surface_temperature_c"]
        q_v = grid.fields["water_vapor_specific_humidity"]
        q_c = grid.fields["cloud_condensate_specific_humidity"]
        temperature = grid.fields["temperature"]
        pressure = grid.fields["pressure_hpa"]
        if not all(np.isfinite(values).all() for values in grid.fields.values()):
            raise SystemExit(f"NaN/Inf detected at {world_minutes}")
        minimum_sst = min(minimum_sst, float(np.min(sst[ocean])))
        maximum_sst = max(maximum_sst, float(np.max(sst[ocean])))
        maximum_q = max(maximum_q, float(np.max(q_v)))
        maximum_q_c = max(maximum_q_c, float(np.max(q_c)))
        minimum_air_temperature = min(minimum_air_temperature, float(np.min(temperature)))
        maximum_air_temperature = max(maximum_air_temperature, float(np.max(temperature)))
        minimum_pressure = min(minimum_pressure, float(np.min(pressure)))
        maximum_pressure = max(maximum_pressure, float(np.max(pressure)))
        if collect_series and world_minutes % 1440 == 0:
            daily_sst_anomaly.append(
                ocean_weighted_mean(sst - baseline, static, settings)
            )
            macro = forcing.ocean_macro_forcing_grid(
                geometry_for(settings),
                world_minutes - 720,
                1440,
            )
            daily_stellar_anomaly.append(
                ocean_weighted_mean(
                    macro.stellar_flux_anomaly_w_m2,
                    static,
                    settings,
                )
            )
    return {
        "grid": grid,
        "static": static,
        "settings": settings,
        "forcing": forcing,
        "captured": captured,
        "captured_precipitation_mass": captured_precipitation_mass,
        "diagnostics": diagnostics,
        "daily_sst_anomaly": np.asarray(daily_sst_anomaly),
        "daily_stellar_anomaly": np.asarray(daily_stellar_anomaly),
        "wall_seconds": perf_counter() - started,
        "minimum_sst_c": minimum_sst,
        "maximum_sst_c": maximum_sst,
        "maximum_specific_humidity": maximum_q,
        "maximum_cloud_condensate_specific_humidity": maximum_q_c,
        "minimum_air_temperature_c": minimum_air_temperature,
        "maximum_air_temperature_c": maximum_air_temperature,
        "minimum_pressure_hpa": minimum_pressure,
        "maximum_pressure_hpa": maximum_pressure,
    }


def fast_forward_to(
    end_world_minutes,
    *,
    parameter_overrides=None,
    initial_spinup_steps=0,
):
    grid, static, settings, forcing = make_case(parameter_overrides)
    spinup_start = max(0, end_world_minutes - TURN_MINUTES)
    diagnostics = {}
    macro_start = 0
    for step in range(1, min(initial_spinup_steps, spinup_start // STEP_MINUTES) + 1):
        macro_start = step * STEP_MINUTES
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=step,
            world_minutes=macro_start,
            forcing=forcing,
            diagnostics=diagnostics,
        )
    macro = advance_ocean_fast_forward(
        grid,
        static,
        settings,
        forcing,
        start_world_minutes=macro_start,
        end_world_minutes=spinup_start,
        diagnostics=diagnostics,
    )
    grid, _ = initialize_atmosphere(
        settings,
        static=static,
        world_minutes=spinup_start,
        forcing=forcing,
        restart_grid=grid,
    )
    for world_minutes in range(
        spinup_start + STEP_MINUTES,
        end_world_minutes + 1,
        STEP_MINUTES,
    ):
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=world_minutes // STEP_MINUTES,
            world_minutes=world_minutes,
            forcing=forcing,
            diagnostics=diagnostics,
        )
    return grid, static, settings, macro, diagnostics


def accuracy(
    exact_grid,
    target_minutes,
    *,
    exact_precipitation_mass_kg=0.0,
    parameter_overrides=None,
    initial_spinup_steps=0,
):
    started = perf_counter()
    approximate, static, settings, macro, diagnostics = fast_forward_to(
        target_minutes,
        parameter_overrides=parameter_overrides,
        initial_spinup_steps=initial_spinup_steps,
    )
    elapsed = perf_counter() - started
    ocean = static.is_ocean
    difference = np.abs(
        approximate.fields["sea_surface_temperature_c"][ocean]
        - exact_grid.fields["sea_surface_temperature_c"][ocean]
    )
    baseline = ocean_baseline_sst(static, settings)
    exact_sst = exact_grid.fields["sea_surface_temperature_c"]
    approximate_sst = approximate.fields["sea_surface_temperature_c"]
    exact_rh = relative_humidity_percent(
        exact_grid.fields["water_vapor_specific_humidity"],
        exact_grid.fields["temperature"],
        exact_grid.fields["pressure_hpa"],
    )
    approximate_rh = relative_humidity_percent(
        approximate.fields["water_vapor_specific_humidity"],
        approximate.fields["temperature"],
        approximate.fields["pressure_hpa"],
    )
    exact_anomaly = exact_sst - baseline
    exact_q_c = exact_grid.fields["cloud_condensate_specific_humidity"]
    approximate_q_c = approximate.fields["cloud_condensate_specific_humidity"]
    exact_ocean_indices = np.flatnonzero(ocean)
    peak_index = int(exact_ocean_indices[np.argmax(exact_anomaly[ocean])])
    geometry = geometry_for(settings)
    absolute_error = np.abs(approximate_sst - exact_sst)
    worst_indices = exact_ocean_indices[
        np.argsort(absolute_error[exact_ocean_indices])[-10:][::-1]
    ]
    top_errors = []
    for index in worst_indices:
        neighbors = (
            geometry.west[index],
            geometry.east[index],
            geometry.north[index],
            geometry.south[index],
        )
        latitude = float(geometry.latitude[index])
        top_errors.append(
            {
                "index": int(index),
                "latitude": round(latitude, 6),
                "longitude": round(float(geometry.longitude[index]), 6),
                "exact_sst_c": round(float(exact_sst[index]), 6),
                "fast_forward_sst_c": round(float(approximate_sst[index]), 6),
                "signed_error_c": round(
                    float(approximate_sst[index] - exact_sst[index]),
                    6,
                ),
                "absolute_error_c": round(float(absolute_error[index]), 6),
                "baseline_sst_c": round(float(baseline[index]), 6),
                "is_coastal_cell": any(not ocean[neighbor] for neighbor in neighbors),
                "latitude_band": (
                    "polar"
                    if abs(latitude) >= 60.0
                    else "equatorial"
                    if abs(latitude) <= 15.0
                    else "mid_latitude"
                ),
            }
        )
    return {
        "target_minutes": target_minutes,
        "macro_steps": macro["macro_steps"],
        "wall_seconds": round(elapsed, 6),
        "mean_absolute_sst_error_c": round(float(np.mean(difference)), 6),
        "maximum_absolute_sst_error_c": round(float(np.max(difference)), 6),
        "exact_mean_sst_c": round(
            ocean_weighted_mean(exact_sst, static, settings), 6
        ),
        "fast_forward_mean_sst_c": round(
            ocean_weighted_mean(approximate_sst, static, settings), 6
        ),
        "exact_maximum_sst_anomaly_c": round(
            float(np.max((exact_sst - baseline)[ocean])), 6
        ),
        "fast_forward_maximum_sst_anomaly_c": round(
            float(np.max((approximate_sst - baseline)[ocean])), 6
        ),
        "peak_exact_cell": {
            "index": peak_index,
            "baseline_sst_c": round(float(baseline[peak_index]), 6),
            "exact_sst_c": round(float(exact_sst[peak_index]), 6),
            "fast_forward_sst_c": round(float(approximate_sst[peak_index]), 6),
            "exact_air_c": round(
                float(exact_grid.fields["temperature"][peak_index]), 6
            ),
            "fast_forward_air_c": round(
                float(approximate.fields["temperature"][peak_index]), 6
            ),
            "exact_q_v": round(
                float(exact_grid.fields["water_vapor_specific_humidity"][peak_index]),
                8,
            ),
            "fast_forward_q_v": round(
                float(approximate.fields["water_vapor_specific_humidity"][peak_index]),
                8,
            ),
            "exact_wind_m_s": round(float(np.hypot(
                exact_grid.fields["wind_u"][peak_index],
                exact_grid.fields["wind_v"][peak_index],
            )), 6),
            "fast_forward_wind_m_s": round(float(np.hypot(
                approximate.fields["wind_u"][peak_index],
                approximate.fields["wind_v"][peak_index],
            )), 6),
        },
        "final_air_temperature_mae_c": round(
            float(np.mean(np.abs(
                approximate.fields["temperature"] - exact_grid.fields["temperature"]
            ))),
            6,
        ),
        "final_surface_pressure_mae_hpa": round(
            float(np.mean(np.abs(
                approximate.fields["pressure_hpa"]
                - exact_grid.fields["pressure_hpa"]
            ))),
            6,
        ),
        "final_circulation_pressure_mae_hpa": round(
            float(np.mean(np.abs(
                approximate.fields["circulation_pressure_hpa"]
                - exact_grid.fields["circulation_pressure_hpa"]
            ))),
            6,
        ),
        "final_wind_vector_mae_m_s": round(
            float(np.mean(np.hypot(
                approximate.fields["wind_u"] - exact_grid.fields["wind_u"],
                approximate.fields["wind_v"] - exact_grid.fields["wind_v"],
            ))),
            6,
        ),
        "final_specific_humidity_mae": round(
            float(np.mean(np.abs(
                approximate.fields["water_vapor_specific_humidity"]
                - exact_grid.fields["water_vapor_specific_humidity"]
            ))),
            8,
        ),
        "final_specific_humidity_max_error": round(
            float(np.max(np.abs(
                approximate.fields["water_vapor_specific_humidity"]
                - exact_grid.fields["water_vapor_specific_humidity"]
            ))),
            8,
        ),
        "final_cloud_condensate_mae": round(
            float(np.mean(np.abs(approximate_q_c - exact_q_c))),
            8,
        ),
        "final_cloud_condensate_max_error": round(
            float(np.max(np.abs(approximate_q_c - exact_q_c))),
            8,
        ),
        "final_air_temperature_max_error_c": round(
            float(np.max(np.abs(
                approximate.fields["temperature"] - exact_grid.fields["temperature"]
            ))),
            6,
        ),
        "final_relative_humidity_mae_percent": round(
            float(np.mean(np.abs(approximate_rh - exact_rh))),
            6,
        ),
        "fast_forward_integrated_precipitation_mass_kg": round(
            float(diagnostics.get("total_precipitated_mass_kg", 0.0)),
            3,
        ),
        "exact_integrated_precipitation_mass_kg": round(
            float(exact_precipitation_mass_kg),
            3,
        ),
        "integrated_precipitation_relative_error": (
            None
            if exact_precipitation_mass_kg == 0
            else round(
                abs(
                    diagnostics.get("total_precipitated_mass_kg", 0.0)
                    - exact_precipitation_mass_kg
                )
                / exact_precipitation_mass_kg,
                6,
            )
        ),
        "clamps": diagnostics,
        "top_10_sst_errors": top_errors,
    }


def main():
    first = exact_two_year_run(collect_series=True)
    repeat = exact_two_year_run(collect_series=False)
    deterministic = first["grid"].serialize() == repeat["grid"].serialize()
    days_per_year = CANONICAL_YEAR_MINUTES // 1440
    sst = first["daily_sst_anomaly"]
    star = first["daily_stellar_anomaly"]
    first_year_sst = sst[:days_per_year]
    second_year_sst = sst[days_per_year : 2 * days_per_year]
    first_year_star = star[:days_per_year]
    peak_star_day = int(np.argmax(first_year_star))
    peak_sst_day = int(np.argmax(first_year_sst))
    lag_days = (peak_sst_day - peak_star_day) % days_per_year
    normal_cell_steps = WIDTH * HEIGHT * (TWO_YEARS_MINUTES // STEP_MINUTES)
    clamp_keys = {
        key: value
        for key, value in first["diagnostics"].items()
        if key.endswith("_cells")
    }
    legacy_parameters = {
        "fast_forward_ocean_boundary_layer_enabled": 0.0,
        "fast_forward_ocean_step_minutes": 10080.0,
        "fast_forward_ocean_max_steps": 512.0,
        "fast_forward_forcing_samples": 7.0,
        "fast_forward_legacy_rotation_mean": 1.0,
        "fast_forward_analytic_deep_relaxation": 0.0,
    }
    season_new = accuracy(
        first["captured"][SEASON_MINUTES],
        SEASON_MINUTES,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][SEASON_MINUTES],
    )
    year_new = accuracy(
        first["captured"][CANONICAL_YEAR_MINUTES],
        CANONICAL_YEAR_MINUTES,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][CANONICAL_YEAR_MINUTES],
    )
    season_old = accuracy(
        first["captured"][SEASON_MINUTES],
        SEASON_MINUTES,
        parameter_overrides=legacy_parameters,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][SEASON_MINUTES],
    )
    year_old = accuracy(
        first["captured"][CANONICAL_YEAR_MINUTES],
        CANONICAL_YEAR_MINUTES,
        parameter_overrides=legacy_parameters,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][CANONICAL_YEAR_MINUTES],
    )
    result = {
        "grid": [WIDTH, HEIGHT],
        "step_minutes": STEP_MINUTES,
        "years": 2,
        "sequential_steps": TWO_YEARS_MINUTES // STEP_MINUTES,
        "exact_wall_seconds": round(first["wall_seconds"], 6),
        "repeat_wall_seconds": round(repeat["wall_seconds"], 6),
        "deterministic_payload": deterministic,
        "sst_minimum_c": round(first["minimum_sst_c"], 6),
        "sst_maximum_c": round(first["maximum_sst_c"], 6),
        "maximum_specific_humidity": round(first["maximum_specific_humidity"], 8),
        "peak_stellar_day": peak_star_day,
        "peak_sst_day": peak_sst_day,
        "seasonal_sst_lag_days": lag_days,
        "year_to_year_sst_pattern_mae_c": round(
            float(np.mean(np.abs(second_year_sst - first_year_sst))),
            6,
        ),
        "cap_cell_counts": clamp_keys,
        "maximum_cap_cell_fraction": (
            0.0
            if not clamp_keys
            else round(max(clamp_keys.values()) / normal_cell_steps, 8)
        ),
        "legacy_fast_forward": {
            "season": season_old,
            "year": year_old,
        },
        "season_fast_forward": season_new,
        "year_fast_forward": year_new,
    }
    if not deterministic:
        raise SystemExit(f"Determinism failed: {result}")
    if not (-120.0 <= first["minimum_sst_c"] <= first["maximum_sst_c"] <= 120.0):
        raise SystemExit(f"SST bounds failed: {result}")
    if not 0.0 <= first["maximum_specific_humidity"] <= 0.6:
        raise SystemExit(f"q_v bounds failed: {result}")
    if lag_days == 0:
        raise SystemExit(f"Seasonal SST lag was not observed: {result}")
    if result["year_to_year_sst_pattern_mae_c"] > 2.0:
        raise SystemExit(f"Seasonal pattern did not settle: {result}")
    if result["maximum_cap_cell_fraction"] > 0.02:
        raise SystemExit(f"Numerical caps are too frequent: {result}")
    if result["season_fast_forward"]["mean_absolute_sst_error_c"] > 2.0:
        raise SystemExit(f"Season fast-forward SST tolerance failed: {result}")
    if result["year_fast_forward"]["mean_absolute_sst_error_c"] > 2.0:
        raise SystemExit(f"Year fast-forward SST tolerance failed: {result}")
    if result["season_fast_forward"]["maximum_absolute_sst_error_c"] > 10.0:
        raise SystemExit(f"Season local SST tolerance failed: {result}")
    if result["year_fast_forward"]["maximum_absolute_sst_error_c"] > 10.0:
        raise SystemExit(f"Year local SST tolerance failed: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
