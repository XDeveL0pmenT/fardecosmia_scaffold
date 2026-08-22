#!/usr/bin/env python
"""Focused Phase C3.5 boundary fast-forward performance benchmark.

Unlike the C3 accuracy benchmark, this script does not rebuild an exact
two-year reference.  It measures only the skipped-period boundary surrogate
plus the unchanged final exact spin-up.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from benchmark_atmosphere_c2 import (  # noqa: E402
    CANONICAL_YEAR_MINUTES,
    SEASON_MINUTES,
    fast_forward_to,
)


def measure(target_minutes, repeats):
    timings = []
    payloads = []
    last_macro = None
    last_diagnostics = None
    for _ in range(repeats):
        started = perf_counter()
        grid, _static, _settings, macro, diagnostics = fast_forward_to(
            target_minutes
        )
        timings.append(perf_counter() - started)
        payloads.append(grid.serialize())
        last_macro = macro
        last_diagnostics = diagnostics
    cells_seen = max(1, last_diagnostics.get("microphysics_cells_seen", 0))
    return {
        "repeats": repeats,
        "median_wall_seconds": round(statistics.median(timings), 6),
        "minimum_wall_seconds": round(min(timings), 6),
        "maximum_wall_seconds": round(max(timings), 6),
        "macro_steps": last_macro["macro_steps"],
        "deterministic_payload": len(set(payloads)) == 1,
        "saturation_active_cell_fraction": round(
            last_diagnostics.get("saturation_adjustment_active_cells", 0)
            / cells_seen,
            6,
        ),
        "cloud_evaporation_active_cell_fraction": round(
            last_diagnostics.get("cloud_evaporation_active_cells", 0)
            / cells_seen,
            6,
        ),
        "precipitation_active_cell_fraction": round(
            last_diagnostics.get("precipitation_active_cells", 0)
            / cells_seen,
            6,
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--target",
        choices=("season", "year", "both"),
        default="both",
    )
    args = parser.parse_args()
    repeats = max(1, args.repeats)
    result = {
        "grid": [24, 12],
        "step_minutes": 360,
    }
    if args.target in {"season", "both"}:
        result["season"] = measure(SEASON_MINUTES, repeats)
    if args.target in {"year", "both"}:
        result["year"] = measure(CANONICAL_YEAR_MINUTES, repeats)
    if not all(
        value["deterministic_payload"]
        for key, value in result.items()
        if key in {"season", "year"}
    ):
        raise SystemExit(f"C3.5 fast-forward determinism regression: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
