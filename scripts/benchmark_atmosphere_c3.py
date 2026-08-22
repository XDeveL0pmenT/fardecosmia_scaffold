#!/usr/bin/env python
"""Phase C3 reduced-grid stability and fast-forward regression benchmark.

This intentionally expensive two-year benchmark is not part of the ordinary
unit-test suite.  It validates cloud water, physical precipitation and the C2.5
boundary solver without creating database rows.
"""

from __future__ import annotations

import json

import numpy as np

from benchmark_atmosphere_c2 import (
    CANONICAL_YEAR_MINUTES,
    HEIGHT,
    SEASON_MINUTES,
    STEP_MINUTES,
    TWO_YEARS_MINUTES,
    WIDTH,
    accuracy,
    exact_two_year_run,
)
from world.services.atmosphere.microphysics import atmospheric_water_mass_diagnostics


def main():
    first = exact_two_year_run(collect_series=True)
    repeat = exact_two_year_run(collect_series=False)
    deterministic = first["grid"].serialize() == repeat["grid"].serialize()
    diagnostics = first["diagnostics"]
    final = first["grid"]
    static = first["static"]
    settings = first["settings"]
    land = ~np.asarray(static.is_ocean, dtype=np.bool_)
    q_v = final.fields["water_vapor_specific_humidity"]
    q_c = final.fields["cloud_condensate_specific_humidity"]
    cloud = final.fields["cloud_cover"]
    season = accuracy(
        first["captured"][SEASON_MINUTES],
        SEASON_MINUTES,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][SEASON_MINUTES],
    )
    year = accuracy(
        first["captured"][CANONICAL_YEAR_MINUTES],
        CANONICAL_YEAR_MINUTES,
        exact_precipitation_mass_kg=first["captured_precipitation_mass"][CANONICAL_YEAR_MINUTES],
    )
    result = {
        "grid": [WIDTH, HEIGHT],
        "step_minutes": STEP_MINUTES,
        "canonical_years": 2,
        "sequential_steps": TWO_YEARS_MINUTES // STEP_MINUTES,
        "exact_wall_seconds": round(first["wall_seconds"], 6),
        "repeat_wall_seconds": round(repeat["wall_seconds"], 6),
        "deterministic_payload": deterministic,
        "bounds": {
            "air_temperature_c": [
                round(first["minimum_air_temperature_c"], 6),
                round(first["maximum_air_temperature_c"], 6),
            ],
            "pressure_hpa": [
                round(first["minimum_pressure_hpa"], 6),
                round(first["maximum_pressure_hpa"], 6),
            ],
            "sst_c": [
                round(first["minimum_sst_c"], 6),
                round(first["maximum_sst_c"], 6),
            ],
            "maximum_q_v": round(first["maximum_specific_humidity"], 9),
            "maximum_q_c": round(
                first["maximum_cloud_condensate_specific_humidity"], 9
            ),
        },
        "water": {
            **atmospheric_water_mass_diagnostics(final, settings),
            "total_precipitated_mass_kg": diagnostics.get(
                "total_precipitated_mass_kg", 0.0
            ),
            "total_evaporated_mass_kg": diagnostics.get(
                "total_evaporated_mass_kg",
                diagnostics.get("total_evaporated_water_kg", 0.0),
            ),
            "condensation_mass_kg": diagnostics.get("condensation_mass_kg", 0.0),
            "cloud_evaporation_mass_kg": diagnostics.get(
                "cloud_evaporation_mass_kg", 0.0
            ),
        },
        "spatial_sanity": {
            "dry_land_cell_fraction": round(
                float(np.mean((q_v[land] < 0.01) & (q_c[land] < 1e-5))), 6
            ),
            "cloudy_cell_fraction": round(float(np.mean(cloud >= 0.5)), 6),
            "maximum_final_q_c": round(float(np.max(q_c)), 9),
        },
        "clamps": {
            "supersaturation_emergency_clamp_hits": diagnostics.get(
                "supersaturation_emergency_clamp_hits", 0
            ),
            "cloud_condensate_emergency_clamp_hits": diagnostics.get(
                "cloud_condensate_emergency_clamp_hits", 0
            ),
            "precipitation_without_condensate_cells": diagnostics.get(
                "precipitation_without_condensate_cells", 0
            ),
            "saturation_pressure_cap_cells": diagnostics.get(
                "saturation_pressure_cap_cells", 0
            ),
            "saturation_adjustment_max_iterations_used": diagnostics.get(
                "saturation_adjustment_max_iterations_used", 0
            ),
        },
        "season_fast_forward": season,
        "year_fast_forward": year,
    }
    finite = all(np.isfinite(values).all() for values in final.fields.values())
    if not deterministic or not finite:
        raise SystemExit(f"C3 determinism/finite-state regression: {result}")
    if first["maximum_specific_humidity"] > 0.6:
        raise SystemExit(f"C3 q_v runaway: {result}")
    if first["maximum_cloud_condensate_specific_humidity"] > 0.2:
        raise SystemExit(f"C3 q_c runaway: {result}")
    if diagnostics.get("precipitation_without_condensate_cells", 0):
        raise SystemExit(f"Precipitation source regression: {result}")
    for item in (season, year):
        if item["mean_absolute_sst_error_c"] > 2.0:
            raise SystemExit(f"C3 fast-forward SST MAE regression: {result}")
        if item["maximum_absolute_sst_error_c"] > 10.0:
            raise SystemExit(f"C3 fast-forward SST maximum regression: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
