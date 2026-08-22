#!/usr/bin/env python
"""Phase C2 ocean fast-forward attribution benchmark.

This is intentionally outside the unit-test suite.  Every scenario changes
only the skipped-period approximation; the exact reference and physical
coefficients remain untouched except in explicitly named sensitivity probes.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import benchmark_atmosphere_c2 as benchmark


LEGACY = {
    "fast_forward_ocean_boundary_layer_enabled": 0.0,
    "fast_forward_ocean_step_minutes": 10080.0,
    "fast_forward_ocean_max_steps": 512.0,
    "fast_forward_forcing_samples": 7.0,
    "fast_forward_legacy_rotation_mean": 1.0,
    "fast_forward_analytic_deep_relaxation": 0.0,
}


SCENARIOS = {
    "legacy_old": LEGACY,
    "macro_step_6h_only": {
        **LEGACY,
        "fast_forward_ocean_step_minutes": 360.0,
        "fast_forward_ocean_max_steps": 2000.0,
    },
    "canonical_stellar_sampling_only": {
        **LEGACY,
        "fast_forward_legacy_rotation_mean": 0.0,
    },
    "spatial_wind_only": {
        **LEGACY,
        "fast_forward_wind_spinup_iterations": 4.0,
    },
    "without_sensible_probe": {
        **LEGACY,
        "ocean_sensible_transfer_coefficient": 0.0,
    },
    "without_latent_probe": {
        **LEGACY,
        "ocean_evaporation_transfer_coefficient": 0.0,
    },
    "without_deep_probe": {
        **LEGACY,
        "ocean_deep_relaxation_days": 1.0e12,
    },
    "analytic_deep_only": {
        **LEGACY,
        "fast_forward_analytic_deep_relaxation": 1.0,
    },
    "new_boundary_surrogate": {},
}


def compact(result):
    return {
        key: result[key]
        for key in (
            "macro_steps",
            "wall_seconds",
            "mean_absolute_sst_error_c",
            "maximum_absolute_sst_error_c",
        )
    }


def main():
    exact = benchmark.exact_two_year_run(collect_series=False)
    output = {}
    for name, parameters in SCENARIOS.items():
        output[name] = {
            "season": compact(
                benchmark.accuracy(
                    exact["captured"][benchmark.SEASON_MINUTES],
                    benchmark.SEASON_MINUTES,
                    parameter_overrides=parameters,
                )
            ),
            "year": compact(
                benchmark.accuracy(
                    exact["captured"][benchmark.CANONICAL_YEAR_MINUTES],
                    benchmark.CANONICAL_YEAR_MINUTES,
                    parameter_overrides=parameters,
                )
            ),
        }
    old_season = output["legacy_old"]["season"]["mean_absolute_sst_error_c"]
    old_year = output["legacy_old"]["year"]["mean_absolute_sst_error_c"]
    for result in output.values():
        result["season"]["mae_delta_from_old_c"] = round(
            result["season"]["mean_absolute_sst_error_c"] - old_season,
            6,
        )
        result["year"]["mae_delta_from_old_c"] = round(
            result["year"]["mean_absolute_sst_error_c"] - old_year,
            6,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
