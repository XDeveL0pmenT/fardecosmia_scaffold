#!/usr/bin/env python
"""Profile one atmospheric advancement without committing development data.

Run each scenario in a fresh process so PeakWorkingSetSize is comparable::

    python scripts/benchmark_atmosphere.py CAMPAIGN_UUID --steps 1
    python scripts/benchmark_atmosphere.py CAMPAIGN_UUID --steps 4
    python scripts/benchmark_atmosphere.py CAMPAIGN_UUID --steps 28
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter, process_time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

from campaigns.models import Campaign  # noqa: E402
from world.models import AtmosphericConfig, Region  # noqa: E402
from world.biomes import Biome  # noqa: E402
from world.services import time as time_service  # noqa: E402
from world.services.calendar import minutes_for_time_step  # noqa: E402
from world.services.atmosphere import (  # noqa: E402
    fingerprint as fingerprint_module,
    persistence,
    region_area,
    sampling,
    simulation,
)
from world.services.atmosphere.grid import AtmosphericGrid  # noqa: E402


class StageTimings:
    def __init__(self):
        self.seconds = {}
        self.calls = {}
        self._originals = []

    def patch(self, owner, attribute, label):
        original = getattr(owner, attribute)

        def measured(*args, **kwargs):
            started = perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds[label] = self.seconds.get(label, 0.0) + (
                    perf_counter() - started
                )
                self.calls[label] = self.calls.get(label, 0) + 1

        self._originals.append((owner, attribute, original))
        setattr(owner, attribute, measured)

    def restore(self):
        for owner, attribute, original in reversed(self._originals):
            setattr(owner, attribute, original)


class DatabaseTimings:
    def __init__(self):
        self.total_seconds = 0.0
        self.write_seconds = 0.0
        self.queries = 0
        self.write_queries = 0

    def __call__(self, execute, sql, params, many, context):
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed = perf_counter() - started
            self.total_seconds += elapsed
            self.queries += 1
            operation = sql.lstrip().split(None, 1)[0].upper()
            if operation in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
                self.write_seconds += elapsed
                self.write_queries += 1


def windows_memory_info():
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "working_set_mib": counters.WorkingSetSize / 1024 / 1024,
        "peak_working_set_mib": counters.PeakWorkingSetSize / 1024 / 1024,
    }


def install_stage_probes(timings):
    timings.patch(persistence, "cached_static_world_grid", "static_grid_access")
    timings.patch(
        persistence,
        "atmospheric_input_fingerprint",
        "input_fingerprint",
    )
    timings.patch(persistence, "grid_from_snapshot", "deserialization")
    timings.patch(AtmosphericGrid, "serialize", "serialization_compression")
    timings.patch(simulation, "advect_heat_and_moisture", "advection")
    timings.patch(simulation, "apply_surface_exchange", "surface_exchange")
    timings.patch(
        simulation,
        "apply_ocean_surface_exchange",
        "ocean_surface_exchange",
    )
    timings.patch(
        simulation,
        "derive_relative_humidity_and_apply_safety",
        "supersaturation_safeguard",
    )
    timings.patch(simulation, "saturation_adjustment", "cloud_microphysics")
    timings.patch(simulation, "precipitation_fallout", "precipitation_fallout")
    timings.patch(
        persistence,
        "advance_ocean_fast_forward",
        "ocean_fast_forward",
    )
    timings.patch(simulation, "solve_pressure", "pressure")
    timings.patch(simulation, "solve_wind", "wind")
    timings.patch(
        simulation,
        "apply_orographic_temperature_tendency",
        "orography",
    )
    timings.patch(sampling.AtmosphericRegionSampler, "sample", "regional_sampling")
    timings.patch(sampling.AtmosphericRegionSampler, "save", "regional_bulk_save")
    timings.patch(
        region_area,
        "region_contour_mask",
        "region_area_mask_access",
    )
    timings.patch(
        region_area.AtmosphericRegionAreaSampler,
        "sample",
        "region_area_sampling",
    )
    timings.patch(
        region_area.AtmosphericRegionAreaSampler,
        "save",
        "region_area_bulk_save",
    )


def benchmark(
    campaign_id,
    steps=None,
    profile_output=None,
    report_user=None,
    *,
    requested_unit=None,
    requested_amount=1,
    parameter_overrides=None,
    extra_regions=0,
):
    campaign = Campaign.objects.get(pk=campaign_id)
    config = AtmosphericConfig.objects.get(campaign=campaign, enabled=True)
    gm = get_user_model().objects.get(username=report_user) if report_user else None
    if requested_unit is None:
        minutes = steps * config.step_minutes
        report_amount = minutes // 60
        report_unit = "hours"
    else:
        minutes = minutes_for_time_step(campaign, requested_amount, requested_unit)
        report_amount = requested_amount
        report_unit = requested_unit
        steps = max(1, math.ceil(minutes / config.step_minutes))
    if (config.grid_width, config.grid_height, config.step_minutes) != (180, 90, 360):
        raise SystemExit(
            "Benchmark acceptance mode requires grid 180x90 and step_minutes=360."
        )

    timings = StageTimings()
    database = DatabaseTimings()
    captured = {}
    original_advance = time_service.advance_atmosphere_for_period

    def capture_advance(*args, **kwargs):
        result = original_advance(*args, **kwargs)
        captured["result"] = result
        return result

    profiler = cProfile.Profile() if profile_output else None
    with transaction.atomic():
        if extra_regions:
            synthetic = []
            for index in range(extra_regions):
                x = ((index * 37) % 170 + 5) / 180.0
                y = ((index * 23) % 80 + 5) / 90.0
                half_width = 0.0025
                half_height = 0.005
                synthetic.append(
                    Region(
                        campaign=campaign,
                        name=f"__R1 benchmark region {index}",
                        biome=Biome.MEADOW,
                        map_longitude=x * 360.0 - 180.0,
                        map_latitude=90.0 - y * 180.0,
                        map_polygon=[
                            [x - half_width, y - half_height],
                            [x + half_width, y - half_height],
                            [x + half_width, y + half_height],
                            [x - half_width, y + half_height],
                        ],
                    )
                )
            Region.objects.bulk_create(synthetic, batch_size=500)
        captured["region_count"] = campaign.regions.count()
        if parameter_overrides:
            config.parameters = {**config.parameters, **parameter_overrides}
            config.save(update_fields=["parameters"])
        # A new solver/fingerprint branch must initialize at the benchmark's
        # current time.  Never relabel an older solver payload as compatible.
        fingerprint_module._file_digest.cache_clear()

        install_stage_probes(timings)
        time_service.advance_atmosphere_for_period = capture_advance
        gc.collect()
        memory_before = windows_memory_info()
        wall_started = perf_counter()
        cpu_started = process_time()
        try:
            with connection.execute_wrapper(database):
                if profiler:
                    profiler.enable()
                outcome = time_service.advance_world(
                    campaign.pk,
                    minutes,
                    advanced_by=gm,
                    requested_amount=report_amount,
                    requested_unit=report_unit,
                )
                captured["report_created"] = outcome.report is not None
                captured["report_summary_bytes"] = (
                    len(
                        json.dumps(
                            outcome.report.summary,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    if outcome.report is not None
                    else 0
                )
                if profiler:
                    profiler.disable()
        finally:
            timings.restore()
            time_service.advance_atmosphere_for_period = original_advance
        cpu_seconds = process_time() - cpu_started
        wall_seconds = perf_counter() - wall_started
        memory_after = windows_memory_info()
        if profiler:
            profiler.dump_stats(profile_output)
        transaction.set_rollback(True)

    result = captured["result"]
    stage_names = (
        "static_grid_access",
        "input_fingerprint",
        "deserialization",
        "advection",
        "surface_exchange",
        "ocean_surface_exchange",
        "cloud_microphysics",
        "precipitation_fallout",
        "supersaturation_safeguard",
        "ocean_fast_forward",
        "pressure",
        "wind",
        "orography",
        "serialization_compression",
        "regional_sampling",
        "regional_bulk_save",
        "region_area_mask_access",
        "region_area_sampling",
        "region_area_bulk_save",
    )
    return {
        "campaign_id": str(campaign.pk),
        "grid": [config.grid_width, config.grid_height],
        "step_minutes": config.step_minutes,
        "requested_steps": steps,
        "region_count": captured["region_count"],
        "extra_synthetic_regions": extra_regions,
        "requested_minutes": minutes,
        "requested_unit": requested_unit,
        "simulated_steps": result.simulated_steps,
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "peak_ram_mib": (
            None if memory_after is None else round(memory_after["peak_working_set_mib"], 3)
        ),
        "working_set_before_mib": (
            None if memory_before is None else round(memory_before["working_set_mib"], 3)
        ),
        "working_set_after_mib": (
            None if memory_after is None else round(memory_after["working_set_mib"], 3)
        ),
        "stage_seconds": {
            name: round(timings.seconds.get(name, 0.0), 6) for name in stage_names
        },
        "stage_calls": {name: timings.calls.get(name, 0) for name in stage_names},
        "db_seconds": round(database.total_seconds, 6),
        "db_write_seconds": round(database.write_seconds, 6),
        "db_queries": database.queries,
        "db_write_queries": database.write_queries,
        "snapshots_written": result.snapshots_written,
        "snapshot_bytes_written": result.snapshot_bytes_written,
        "weather_states_written": len(result.weather_states),
        "region_area_states_written": len(result.area_weather_states),
        "snapshots_pruned": result.snapshots_pruned,
        "benchmark_legacy_clone": False,
        "transaction_rolled_back": True,
        "report_created": captured.get("report_created", False),
        "report_summary_bytes": captured.get("report_summary_bytes", 0),
        "cprofile_output": profile_output,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_id")
    request = parser.add_mutually_exclusive_group(required=True)
    request.add_argument(
        "--steps",
        type=int,
        help=(
            "Requested 360-minute boundaries. Values above the campaign exact "
            "threshold exercise the fast-forward path."
        ),
    )
    request.add_argument(
        "--unit",
        choices=("minutes", "hours", "phases", "turns", "seasons", "years"),
        help="Benchmark a calendar-aware time-control unit.",
    )
    parser.add_argument("--amount", type=int, default=1)
    parser.add_argument("--profile-output")
    parser.add_argument(
        "--parameters-json",
        default="{}",
        help="Temporary AtmosphericConfig parameter overrides; transaction is rolled back.",
    )
    parser.add_argument(
        "--parameter",
        action="append",
        default=[],
        metavar="NAME=NUMBER",
        help="Repeatable numeric AtmosphericConfig override for shell-friendly benchmarks.",
    )
    parser.add_argument(
        "--report-user",
        help="Also create a rolled-back TimeAdvanceReport for this GM username.",
    )
    parser.add_argument(
        "--extra-regions",
        type=int,
        default=0,
        help="Add temporary synthetic Region contours inside the rolled-back transaction.",
    )
    args = parser.parse_args()
    try:
        parameter_overrides = json.loads(args.parameters_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--parameters-json is invalid JSON: {exc}")
    if not isinstance(parameter_overrides, dict):
        parser.error("--parameters-json must decode to an object")
    for item in args.parameter:
        name, separator, raw_value = item.partition("=")
        if not separator or not name:
            parser.error("--parameter must use NAME=NUMBER")
        try:
            parameter_overrides[name] = float(raw_value)
        except ValueError:
            parser.error(f"--parameter value must be numeric: {item}")
    if args.steps is not None and args.steps < 1:
        parser.error("--steps must be positive")
    if args.amount < 1:
        parser.error("--amount must be positive")
    if args.extra_regions < 0:
        parser.error("--extra-regions cannot be negative")
    print(
        json.dumps(
            benchmark(
                args.campaign_id,
                args.steps,
                args.profile_output,
                args.report_user,
                requested_unit=args.unit,
                requested_amount=args.amount,
                parameter_overrides=parameter_overrides,
                extra_regions=args.extra_regions,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
