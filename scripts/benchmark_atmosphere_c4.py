#!/usr/bin/env python
"""Phase C4 reduced-grid circulation stability/fast-forward benchmark.

This intentionally slow two-year benchmark is not part of the unit-test suite.
It extends the C2/C3 physical reference run with circulation, terrain and
numerical-pattern diagnostics required by the C4 acceptance document.
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
from world.services.atmosphere.circulation import (
    spherical_divergence,
    spherical_relative_vorticity,
)


def field_statistics(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "minimum": round(float(np.min(values)), 8),
        "maximum": round(float(np.max(values)), 8),
        "mean": round(float(np.mean(values)), 8),
    }


def main():
    first = exact_two_year_run(collect_series=False)
    repeat = exact_two_year_run(collect_series=False)
    grid = first["grid"]
    settings = first["settings"]
    diagnostics = first["diagnostics"]
    speed = np.hypot(grid.fields["wind_u"], grid.fields["wind_v"])
    divergence = spherical_divergence(
        grid.fields["wind_u"], grid.fields["wind_v"], settings
    )
    vorticity = spherical_relative_vorticity(
        grid.fields["wind_u"], grid.fields["wind_v"], settings
    )
    pressure = grid.fields["circulation_pressure_hpa"].reshape(HEIGHT, WIDTH)
    checkerboard = np.fromfunction(
        lambda y, x: ((x + y) % 2) * 2 - 1,
        (HEIGHT, WIDTH),
        dtype=int,
    )
    pressure_anomaly = pressure - float(np.mean(pressure))
    checkerboard_fraction = abs(float(np.sum(pressure_anomaly * checkerboard))) / max(
        1e-12,
        float(np.sum(np.abs(pressure_anomaly))),
    )
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
        "canonical_years": 2,
        "sequential_steps": TWO_YEARS_MINUTES // STEP_MINUTES,
        "exact_wall_seconds": round(first["wall_seconds"], 6),
        "repeat_wall_seconds": round(repeat["wall_seconds"], 6),
        "deterministic_payload": grid.serialize() == repeat["grid"].serialize(),
        "final_statistics": {
            "temperature_c": field_statistics(grid.fields["temperature"]),
            "surface_pressure_hpa": field_statistics(grid.fields["pressure_hpa"]),
            "circulation_pressure_hpa": field_statistics(
                grid.fields["circulation_pressure_hpa"]
            ),
            "wind_m_s": {
                "median": round(float(np.median(speed)), 8),
                "p90": round(float(np.percentile(speed, 90)), 8),
                "p95": round(float(np.percentile(speed, 95)), 8),
                "p99": round(float(np.percentile(speed, 99)), 8),
                "maximum": round(float(np.max(speed)), 8),
            },
            "divergence_s_1": field_statistics(divergence),
            "relative_vorticity_s_1": field_statistics(vorticity),
            "maximum_q_v": round(
                float(np.max(grid.fields["water_vapor_specific_humidity"])), 9
            ),
            "maximum_q_c": round(
                float(np.max(grid.fields["cloud_condensate_specific_humidity"])), 9
            ),
        },
        "integrated_precipitation_kg": diagnostics.get(
            "total_precipitated_mass_kg", 0.0
        ),
        "numerical_safeguards": {
            "wind_cap_hits": diagnostics.get("wind_cap_hits", 0),
            "pressure_cap_hits": diagnostics.get("pressure_cap_hits", 0),
            "supersaturation_emergency_clamp_hits": diagnostics.get(
                "supersaturation_emergency_clamp_hits", 0
            ),
        },
        "checkerboard_pressure_fraction": round(checkerboard_fraction, 8),
        "season_fast_forward": season,
        "year_fast_forward": year,
    }
    finite = all(np.isfinite(values).all() for values in grid.fields.values())
    if not result["deterministic_payload"] or not finite:
        raise SystemExit(f"C4 determinism/finite-state regression: {result}")
    if diagnostics.get("wind_cap_hits", 0) or diagnostics.get("pressure_cap_hits", 0):
        raise SystemExit(f"C4 emergency pressure/wind caps were active: {result}")
    if result["final_statistics"]["wind_m_s"]["maximum"] >= settings.value(
        "max_wind_speed_m_s"
    ) * 0.95:
        raise SystemExit(f"C4 wind is regulated by the emergency cap: {result}")
    if checkerboard_fraction > 0.25:
        raise SystemExit(f"C4 pressure checkerboard regression: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
