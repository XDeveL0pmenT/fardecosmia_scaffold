#!/usr/bin/env python
"""Phase C4.1 hydrological audit for the exact atmospheric solver.

The utility is intentionally outside the ordinary test suite.  It runs the
real solver against reduced World Data, integrates physical precipitation per
cell, and prints JSON suitable for before/after regression reports.
"""

from __future__ import annotations

import argparse
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
from world.services.atmosphere.simulation import (  # noqa: E402
    initialize_atmosphere,
    simulate_step,
)
from world.services.atmosphere.static_grid import build_static_world_grid  # noqa: E402
from world.services.atmosphere.thermodynamics import (  # noqa: E402
    relative_humidity_percent,
    saturation_specific_humidity,
)
from world.services.calendar import TURNS_PER_SEASON  # noqa: E402
from world.services.orbital_climate import CANONICAL_YEAR_MINUTES  # noqa: E402

try:  # C4 diagnostics are optional so the script can audit the C3 commit.
    from world.services.atmosphere.circulation import vertical_motion_fields
except ImportError:  # pragma: no cover - exercised only by historical audit.
    vertical_motion_fields = None

try:
    from world.services.atmosphere.coordinate_sampling import sample_environment_at
except ImportError:  # pragma: no cover - exercised only by historical audit.
    sample_environment_at = None


TURN_MINUTES = 168 * 60


DURATIONS = {
    "vitok": TURN_MINUTES,
    "season": TURNS_PER_SEASON * TURN_MINUTES,
    "year": CANONICAL_YEAR_MINUTES,
}


class Distribution:
    def __init__(self):
        self._parts = []

    def add(self, values):
        self._parts.append(np.asarray(values, dtype=np.float32).reshape(-1).copy())

    def summary(self, percentiles=(50, 90, 99)):
        values = np.concatenate(self._parts).astype(np.float64)
        result = {
            "min": float(np.min(values)),
            "mean": float(np.mean(values)),
            "max": float(np.max(values)),
        }
        for percentile in percentiles:
            result[f"p{percentile}"] = float(np.percentile(values, percentile))
        return result


def _settings(width, height):
    return AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=360,
        world_seed=202,
        ocean_temperature_c=64.0,
        parameters={
            "initial_temperature_noise_c": 0.0,
            "pressure_noise_hpa": 0.0,
        },
    )


def _wettest_cells(
    integrated_mm,
    peak_mm_h,
    rh_sum,
    q_v_sum,
    q_c_sum,
    step_count,
    grid,
    static,
    settings,
    top_n,
):
    geometry = geometry_for(settings)
    indices = np.argsort(integrated_mm)[-top_n:][::-1]
    rows = []
    for index in indices:
        sampled_rate = None
        if sample_environment_at is not None:
            point = sample_environment_at(
                grid,
                static,
                settings,
                float(geometry.latitude[index]),
                float(geometry.longitude[index]),
            )
            sampled_rate = point.values["precipitation_rate"] * 3600.0
        rows.append(
            {
                "index": int(index),
                "latitude": float(geometry.latitude[index]),
                "longitude": float(geometry.longitude[index]),
                "integrated_precipitation_mm": float(integrated_mm[index]),
                "peak_precipitation_mm_h": float(peak_mm_h[index]),
                "mean_rh_percent": float(rh_sum[index] / step_count),
                "mean_q_v": float(q_v_sum[index] / step_count),
                "mean_q_c": float(q_c_sum[index] / step_count),
                "current_sst_c": (
                    float(grid.fields["sea_surface_temperature_c"][index])
                    if bool(static.is_ocean[index])
                    else None
                ),
                "is_ocean": bool(static.is_ocean[index]),
                "raw_current_rate_mm_h": float(
                    grid.fields["precipitation_rate"][index] * 3600.0
                ),
                "coordinate_sampler_current_rate_mm_h": sampled_rate,
            }
        )
    return rows


def exact_audit(duration_name, width, height, top_n):
    settings = _settings(width, height)
    static = build_static_world_grid(settings)
    forcing = CampaignSkyForcing(Campaign(), settings)
    grid, _ = initialize_atmosphere(
        settings,
        static=static,
        world_minutes=0,
        forcing=forcing,
    )
    duration_minutes = DURATIONS[duration_name]
    step_seconds = settings.step_minutes * 60.0
    step_count = duration_minutes // settings.step_minutes
    size = grid.size
    areas = geometry_for(settings).cell_areas_m2
    threshold_q_c = settings.value("precipitation_condensate_threshold")

    distributions = {
        name: Distribution()
        for name in ("q_v", "rh", "q_sat", "q_c", "temperature", "pressure", "wind")
    }
    integrated_mm = np.zeros(size, dtype=np.float64)
    peak_mm_h = np.zeros(size, dtype=np.float64)
    rh_sum = np.zeros(size, dtype=np.float64)
    q_v_sum = np.zeros(size, dtype=np.float64)
    q_c_sum = np.zeros(size, dtype=np.float64)
    precipitating_cell_steps = 0
    precipitation_steps = 0
    visibly_wet_cell_steps = 0
    q_c_positive_cell_steps = 0
    q_c_above_threshold_cell_steps = 0
    rh_90_cell_steps = 0
    rh_100_cell_steps = 0
    condensation_active_cell_steps = 0
    evaporation_active_cell_steps = 0
    meaningful_ascent_cell_steps = 0
    precipitation_wet_rate_sum = 0.0
    precipitation_rates = []
    precipitation_peak = 0.0
    evaporation_peak = 0.0
    condensation_peak = 0.0
    vertical_minimums = {"orographic": float("inf"), "convergence": float("inf"), "total": float("inf")}
    vertical_maximums = {"orographic": float("-inf"), "convergence": float("-inf"), "total": float("-inf")}
    diagnostics = {}

    started = perf_counter()
    for step in range(1, step_count + 1):
        world_minutes = step * settings.step_minutes
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=step,
            world_minutes=world_minutes,
            forcing=forcing,
            diagnostics=diagnostics,
        )
        temperature = grid.fields["temperature"].astype(np.float64)
        pressure = grid.fields["pressure_hpa"].astype(np.float64)
        q_v = grid.fields["water_vapor_specific_humidity"].astype(np.float64)
        q_c = grid.fields["cloud_condensate_specific_humidity"].astype(np.float64)
        q_sat = saturation_specific_humidity(
            temperature,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
        rh = relative_humidity_percent(
            q_v,
            temperature,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
        wind = np.hypot(grid.fields["wind_u"], grid.fields["wind_v"])
        rate_mm_h = grid.fields["precipitation_rate"].astype(np.float64) * 3600.0
        evaporation = grid.fields["evaporation_flux_kg_m2_s"].astype(np.float64)
        condensation = grid.fields["condensation_rate_kg_m2_s"].astype(np.float64)

        for name, values in (
            ("q_v", q_v),
            ("rh", rh),
            ("q_sat", q_sat),
            ("q_c", q_c),
            ("temperature", temperature),
            ("pressure", pressure),
            ("wind", wind),
        ):
            distributions[name].add(values)
        integrated_mm += rate_mm_h * settings.step_minutes / 60.0
        peak_mm_h = np.maximum(peak_mm_h, rate_mm_h)
        rh_sum += rh
        q_v_sum += q_v
        q_c_sum += q_c
        wet = rate_mm_h > 0.0
        visible_wet = rate_mm_h >= settings.value(
            "condition_precipitation_rate_mm_h"
        )
        precipitating_cell_steps += int(np.count_nonzero(wet))
        visibly_wet_cell_steps += int(np.count_nonzero(visible_wet))
        precipitation_steps += int(np.any(wet))
        precipitation_wet_rate_sum += float(np.sum(rate_mm_h[wet]))
        if np.any(wet):
            precipitation_rates.append(rate_mm_h[wet].astype(np.float32).copy())
        precipitation_peak = max(precipitation_peak, float(np.max(rate_mm_h, initial=0.0)))
        q_c_positive_cell_steps += int(np.count_nonzero(q_c > 0.0))
        q_c_above_threshold_cell_steps += int(np.count_nonzero(q_c > threshold_q_c))
        rh_90_cell_steps += int(np.count_nonzero(rh >= 90.0))
        rh_100_cell_steps += int(np.count_nonzero(rh >= 100.0))
        condensation_active_cell_steps += int(np.count_nonzero(condensation > 0.0))
        evaporation_active_cell_steps += int(np.count_nonzero(evaporation > 0.0))
        evaporation_peak = max(evaporation_peak, float(np.max(evaporation, initial=0.0)))
        condensation_peak = max(
            condensation_peak,
            float(np.max(condensation, initial=0.0)),
        )

        if vertical_motion_fields is not None:
            vertical = vertical_motion_fields(grid, static, settings)
            for label, key in (
                ("orographic", "w_orographic_m_s"),
                ("convergence", "w_convergence_m_s"),
                ("total", "vertical_motion_proxy_m_s"),
            ):
                values = vertical[key]
                vertical_minimums[label] = min(vertical_minimums[label], float(np.min(values)))
                vertical_maximums[label] = max(vertical_maximums[label], float(np.max(values)))
            meaningful_ascent_cell_steps += int(
                np.count_nonzero(vertical["vertical_motion_proxy_m_s"] > 1e-4)
            )

    elapsed = perf_counter() - started
    wet_cell_count = int(np.count_nonzero(integrated_mm > 0.0))
    total_evaporation = float(
        diagnostics.get(
            "total_evaporated_water_kg",
            np.sum(
                grid.fields["evaporation_flux_kg_m2_s"].astype(np.float64)
                * areas
                * step_seconds
            ),
        )
    )
    return {
        "mode": "exact",
        "duration": duration_name,
        "duration_minutes": duration_minutes,
        "grid": [width, height],
        "steps": step_count,
        "wall_seconds": elapsed,
        "distributions": {name: item.summary() for name, item in distributions.items()},
        "counts": {
            "rh_gte_90_cell_steps": rh_90_cell_steps,
            "rh_gte_100_cell_steps": rh_100_cell_steps,
            "q_c_positive_cell_steps": q_c_positive_cell_steps,
            "q_c_above_threshold_cell_steps": q_c_above_threshold_cell_steps,
            "condensation_active_cell_steps": condensation_active_cell_steps,
            "ocean_evaporation_active_cell_steps": evaporation_active_cell_steps,
            "precipitating_cell_steps": precipitating_cell_steps,
            "visibly_wet_cell_steps": visibly_wet_cell_steps,
            "timesteps_with_precipitation": precipitation_steps,
            "integrated_wet_cells": wet_cell_count,
            "meaningful_ascent_cell_steps": meaningful_ascent_cell_steps,
        },
        "thresholds": {
            "precipitation_condensate_q_c": threshold_q_c,
            "condition_precipitation_rate_mm_h": settings.value(
                "condition_precipitation_rate_mm_h"
            ),
        },
        "mass_and_flux": {
            "total_evaporation_kg": total_evaporation,
            "maximum_evaporation_kg_m2_s": evaporation_peak,
            "total_condensation_kg": float(diagnostics.get("condensation_mass_kg", 0.0)),
            "maximum_condensation_rate_kg_m2_s": condensation_peak,
            "total_cloud_evaporation_kg": float(
                diagnostics.get("cloud_evaporation_mass_kg", 0.0)
            ),
            "total_precipitation_kg": float(
                diagnostics.get("total_precipitated_mass_kg", 0.0)
            ),
            "maximum_precipitation_mm_h": precipitation_peak,
            "mean_precipitation_over_wet_cell_steps_mm_h": (
                precipitation_wet_rate_sum / precipitating_cell_steps
                if precipitating_cell_steps
                else 0.0
            ),
            "positive_precipitation_rate_percentiles_mm_h": (
                {}
                if not precipitation_rates
                else {
                    f"p{percentile}": float(
                        np.percentile(np.concatenate(precipitation_rates), percentile)
                    )
                    for percentile in (50, 90, 99)
                }
            ),
        },
        "vertical_motion_m_s": {
            label: {
                "min": None if value == float("inf") else value,
                "max": None if vertical_maximums[label] == float("-inf") else vertical_maximums[label],
            }
            for label, value in vertical_minimums.items()
        },
        "diagnostics": diagnostics,
        "wettest_cells": _wettest_cells(
            integrated_mm,
            peak_mm_h,
            rh_sum,
            q_v_sum,
            q_c_sum,
            step_count,
            grid,
            static,
            settings,
            top_n,
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", choices=DURATIONS, default="vitok")
    parser.add_argument("--width", type=int, default=24)
    parser.add_argument("--height", type=int, default=12)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            exact_audit(args.duration, args.width, args.height, args.top),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
