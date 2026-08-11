from dataclasses import dataclass

from world.atmosphere_defaults import (
    ATMOSPHERIC_FORMAT_VERSION,
    ATMOSPHERIC_SOLVER_VERSION,
)
from world.models import AtmosphericSnapshot
from world.services.world_data import coordinates_to_grid

from .config import AtmosphericSettings
from .fingerprint import atmospheric_input_fingerprint
from .forcing import CampaignSkyForcing
from .geometry import geometry_for
from .grid import AtmosphericGrid
from .ocean import (
    advance_ocean_fast_forward,
    atmospheric_vapor_mass_proxy_kg,
    cell_ocean_diagnostics,
    ocean_baseline_sst,
    ocean_weighted_mean,
)
from .microphysics import atmospheric_water_mass_diagnostics
from .sampling import AtmosphericRegionSampler
from .simulation import initialize_atmosphere, simulate_step
from .static_grid import cached_static_world_grid


MAX_ATMOSPHERIC_STEPS_PER_ADVANCE = 10_000
SNAPSHOT_BULK_SIZE = 16


@dataclass
class AtmosphericAdvanceResult:
    weather_states: list
    simulated_steps: int = 0
    snapshots_written: int = 0
    snapshot_bytes_written: int = 0
    snapshots_pruned: int = 0
    input_fingerprint: str | None = None
    ocean_summary: dict | None = None
    numerical_diagnostics: dict | None = None


def grid_from_snapshot(snapshot):
    if snapshot.format_version != ATMOSPHERIC_FORMAT_VERSION:
        raise ValueError("Версия формата атмосферного снимка не поддерживается.")
    if snapshot.solver_version != ATMOSPHERIC_SOLVER_VERSION:
        raise ValueError("Версия решателя атмосферного снимка не поддерживается.")
    return AtmosphericGrid.deserialize(
        snapshot.grid_width,
        snapshot.grid_height,
        snapshot.payload,
    )


def save_snapshot(
    campaign,
    world_minutes,
    grid,
    *,
    input_fingerprint="",
    is_checkpoint=True,
):
    snapshot, created = AtmosphericSnapshot.objects.update_or_create(
        campaign=campaign,
        world_minutes=world_minutes,
        input_fingerprint=input_fingerprint,
        defaults={
            "grid_width": grid.width,
            "grid_height": grid.height,
            "format_version": ATMOSPHERIC_FORMAT_VERSION,
            "solver_version": ATMOSPHERIC_SOLVER_VERSION,
            "is_checkpoint": is_checkpoint,
            "payload": grid.serialize(),
        },
    )
    return snapshot, created


def _checkpoint_interval(campaign, config):
    return config.checkpoint_interval_minutes or campaign.calendar_minutes_per_turn


def _latest_compatible_snapshot(campaign, settings, old_time, fingerprint):
    snapshot = (
        campaign.atmospheric_snapshots.filter(
            input_fingerprint=fingerprint,
            world_minutes__lte=old_time,
        )
        .order_by("-world_minutes", "-created_at")
        .first()
    )
    # Legacy rows with an empty fingerprint are deliberately not adopted
    # automatically: their historical static maps/config cannot be proven.
    # They stay intact for an explicit, operator-controlled recovery path.
    if snapshot is not None and (snapshot.grid_width, snapshot.grid_height) != (
        settings.width,
        settings.height,
    ):
        raise ValueError(
            "Размер AtmosphericConfig не совпадает с совместимым checkpoint. "
            "Создайте новую последовательность снимков явно."
        )
    return snapshot


def _prune_current_history(campaign, config, fingerprint):
    latest = (
        campaign.atmospheric_snapshots.filter(input_fingerprint=fingerprint)
        .order_by("-world_minutes", "-created_at")
        .first()
    )
    if latest is None:
        return 0
    deleted = 0
    stale_latest = campaign.atmospheric_snapshots.filter(
        input_fingerprint=fingerprint,
        is_checkpoint=False,
    ).exclude(pk=latest.pk)
    count, _ = stale_latest.delete()
    deleted += count

    retention = config.checkpoint_retention_count
    if retention is not None:
        keep_ids = list(
            campaign.atmospheric_snapshots.filter(
                input_fingerprint=fingerprint,
                is_checkpoint=True,
            )
            .order_by("-world_minutes", "-created_at")
            .values_list("pk", flat=True)[:retention]
        )
        old_checkpoints = campaign.atmospheric_snapshots.filter(
            input_fingerprint=fingerprint,
            is_checkpoint=True,
        ).exclude(pk__in=keep_ids)
        if not latest.is_checkpoint:
            old_checkpoints = old_checkpoints.exclude(pk=latest.pk)
        count, _ = old_checkpoints.delete()
        deleted += count
    return deleted


def advance_atmosphere_for_period(
    campaign,
    config,
    old_time,
    new_time,
    *,
    regions=(),
    force_initialize=False,
    fast_forward_start=None,
):
    """Advance every physics boundary in memory and persist sparse checkpoints."""
    if new_time < old_time:
        raise ValueError("Атмосферу нельзя прокручивать назад этим сервисом.")
    settings = AtmosphericSettings.from_model(config, campaign)
    result = AtmosphericAdvanceResult(weather_states=[], numerical_diagnostics={})

    next_boundary = (old_time // settings.step_minutes + 1) * settings.step_minutes
    if next_boundary > new_time:
        # The ordinary short-click path deliberately avoids fingerprinting,
        # static rasters, snapshot queries/decompression and solver allocation.
        return result

    fingerprint = atmospheric_input_fingerprint(campaign, config)
    result.input_fingerprint = fingerprint
    snapshot = None
    if not force_initialize:
        snapshot = _latest_compatible_snapshot(
            campaign,
            settings,
            old_time,
            fingerprint,
        )
    static = cached_static_world_grid(settings)
    forcing = CampaignSkyForcing(campaign, settings)
    checkpoint_interval = _checkpoint_interval(campaign, config)

    pending_snapshots = []
    pending_times = set()

    def flush_snapshots():
        if not pending_snapshots:
            return
        AtmosphericSnapshot.objects.bulk_create(
            pending_snapshots,
            batch_size=SNAPSHOT_BULK_SIZE,
            update_conflicts=True,
            update_fields=(
                "grid_width",
                "grid_height",
                "format_version",
                "solver_version",
                "is_checkpoint",
                "payload",
            ),
            unique_fields=("campaign", "world_minutes", "input_fingerprint"),
        )
        result.snapshots_written += len(pending_snapshots)
        result.snapshot_bytes_written += sum(
            len(bytes(item.payload)) for item in pending_snapshots
        )
        pending_snapshots.clear()

    def queue_snapshot(world_minutes, grid, *, is_checkpoint):
        if world_minutes in pending_times:
            return
        payload = grid.serialize()
        pending_snapshots.append(
            AtmosphericSnapshot(
                campaign=campaign,
                world_minutes=world_minutes,
                grid_width=grid.width,
                grid_height=grid.height,
                format_version=ATMOSPHERIC_FORMAT_VERSION,
                solver_version=ATMOSPHERIC_SOLVER_VERSION,
                input_fingerprint=fingerprint,
                is_checkpoint=is_checkpoint,
                payload=payload,
            )
        )
        pending_times.add(world_minutes)
        if len(pending_snapshots) >= SNAPSHOT_BULK_SIZE:
            flush_snapshots()

    macro_summary = None
    if force_initialize and fast_forward_start is not None and fast_forward_start < old_time:
        slow_snapshot = _latest_compatible_snapshot(
            campaign,
            settings,
            fast_forward_start,
            fingerprint,
        )
        if slow_snapshot is None:
            slow_boundary = fast_forward_start - fast_forward_start % settings.step_minutes
            slow_grid, _ = initialize_atmosphere(
                settings,
                static=static,
                world_minutes=slow_boundary,
                forcing=forcing,
            )
        else:
            slow_boundary = slow_snapshot.world_minutes
            slow_grid = grid_from_snapshot(slow_snapshot)
        boundary = old_time - old_time % settings.step_minutes
        macro_summary = advance_ocean_fast_forward(
            slow_grid,
            static,
            settings,
            forcing,
            start_world_minutes=slow_boundary,
            end_world_minutes=boundary,
            diagnostics=result.numerical_diagnostics,
        )
        grid, _ = initialize_atmosphere(
            settings,
            static=static,
            world_minutes=boundary,
            forcing=forcing,
            restart_grid=slow_grid,
        )
        initial_state_created = True
    elif snapshot is None:
        boundary = old_time - old_time % settings.step_minutes
        grid, _ = initialize_atmosphere(
            settings,
            static=static,
            world_minutes=boundary,
            forcing=forcing,
        )
        initial_state_created = True
    else:
        boundary = snapshot.world_minutes
        grid = grid_from_snapshot(snapshot)
        initial_state_created = False

    baseline_sst = ocean_baseline_sst(static, settings)
    ocean_mask = static.is_ocean
    exact_start_mean = ocean_weighted_mean(
        grid.fields["sea_surface_temperature_c"],
        static,
        settings,
    )
    start_vapor_mass_proxy = atmospheric_vapor_mass_proxy_kg(grid, settings)
    maximum_sst_anomaly = (
        None
        if not ocean_mask.any()
        else float(
            (
                grid.fields["sea_surface_temperature_c"].astype("float64")
                - baseline_sst
            )[ocean_mask].max()
        )
    )

    transitions = max(0, (new_time - boundary) // settings.step_minutes)
    if transitions > MAX_ATMOSPHERIC_STEPS_PER_ADVANCE:
        raise ValueError(
            "Шаг времени пересекает слишком много интервалов атмосферы. "
            "Увеличьте step_minutes или продвигайте мир меньшими шагами."
        )

    sampler = AtmosphericRegionSampler(
        regions,
        boundary,
        new_time,
        parameters=config.parameters,
        settings=settings,
    )
    if initial_state_created:
        if boundary == old_time or force_initialize:
            sampler.sample(boundary, grid)
        if boundary % checkpoint_interval == 0:
            queue_snapshot(boundary, grid, is_checkpoint=True)

    final_boundary = boundary
    while boundary + settings.step_minutes <= new_time:
        boundary += settings.step_minutes
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=boundary // settings.step_minutes,
            world_minutes=boundary,
            forcing=forcing,
            diagnostics=result.numerical_diagnostics,
        )
        result.simulated_steps += 1
        final_boundary = boundary
        if boundary > old_time:
            sampler.sample(boundary, grid)
        if boundary % checkpoint_interval == 0:
            queue_snapshot(boundary, grid, is_checkpoint=True)
        if ocean_mask.any():
            maximum_sst_anomaly = max(
                maximum_sst_anomaly,
                float(
                    (
                        grid.fields["sea_surface_temperature_c"].astype("float64")
                        - baseline_sst
                    )[ocean_mask].max()
                ),
            )

    if final_boundary not in pending_times:
        queue_snapshot(
            final_boundary,
            grid,
            is_checkpoint=final_boundary % checkpoint_interval == 0,
        )
    flush_snapshots()
    result.weather_states = sampler.save()
    final_mean_sst = ocean_weighted_mean(
        grid.fields["sea_surface_temperature_c"],
        static,
        settings,
    )
    baseline_mean_sst = ocean_weighted_mean(baseline_sst, static, settings)
    final_vapor_mass_proxy = atmospheric_vapor_mass_proxy_kg(grid, settings)
    final_water_masses = atmospheric_water_mass_diagnostics(grid, settings)
    start_mean_sst = (
        macro_summary["start_mean_sst_c"]
        if macro_summary is not None
        else exact_start_mean
    )
    result.ocean_summary = {
        "mode": "fast_forward" if macro_summary is not None else "exact",
        "macro_steps": 0 if macro_summary is None else macro_summary["macro_steps"],
        "boundary_grid_width": (
            None if macro_summary is None else macro_summary.get("boundary_grid_width")
        ),
        "boundary_grid_height": (
            None if macro_summary is None else macro_summary.get("boundary_grid_height")
        ),
        "start_mean_sst_c": start_mean_sst,
        "spinup_start_mean_sst_c": exact_start_mean,
        "end_mean_sst_c": final_mean_sst,
        "mean_sst_change_c": (
            None
            if start_mean_sst is None or final_mean_sst is None
            else final_mean_sst - start_mean_sst
        ),
        "end_mean_sst_anomaly_c": (
            None
            if final_mean_sst is None or baseline_mean_sst is None
            else final_mean_sst - baseline_mean_sst
        ),
        "maximum_sst_anomaly_c": max(
            value
            for value in (
                maximum_sst_anomaly,
                None if macro_summary is None else macro_summary["maximum_sst_anomaly_c"],
            )
            if value is not None
        ) if final_mean_sst is not None else None,
        "maximum_evaporation_kg_m2_s": result.numerical_diagnostics.get(
            "maximum_evaporation_kg_m2_s", 0.0
        ) if macro_summary is None else max(
            result.numerical_diagnostics.get("maximum_evaporation_kg_m2_s", 0.0),
            macro_summary["maximum_evaporation_kg_m2_s"],
        ),
        "maximum_evaporation_kg_m2_day": 86_400.0 * (
            result.numerical_diagnostics.get("maximum_evaporation_kg_m2_s", 0.0)
            if macro_summary is None
            else max(
                result.numerical_diagnostics.get(
                    "maximum_evaporation_kg_m2_s", 0.0
                ),
                macro_summary["maximum_evaporation_kg_m2_s"],
            )
        ),
        "total_evaporated_water_kg": result.numerical_diagnostics.get(
            "total_evaporated_water_kg",
            0.0,
        ) + (0.0 if macro_summary is None else macro_summary["total_evaporated_water_kg"]),
        "integrated_macro_precipitation_mass_kg": (
            0.0
            if macro_summary is None
            else macro_summary.get("integrated_macro_precipitation_mass_kg", 0.0)
        ),
        "start_atmospheric_vapor_mass_proxy_kg": start_vapor_mass_proxy,
        "end_atmospheric_vapor_mass_proxy_kg": final_vapor_mass_proxy,
        "atmospheric_vapor_mass_proxy_change_kg": (
            final_vapor_mass_proxy - start_vapor_mass_proxy
        ),
        "atmospheric_vapor_mass_proxy_change_percent": (
            None
            if start_vapor_mass_proxy == 0
            else 100.0
            * (final_vapor_mass_proxy - start_vapor_mass_proxy)
            / start_vapor_mass_proxy
        ),
    }
    result.numerical_diagnostics["total_atmospheric_vapor_mass_proxy_kg"] = (
        final_vapor_mass_proxy
    )
    result.numerical_diagnostics.update(final_water_masses)
    result.snapshots_pruned = _prune_current_history(campaign, config, fingerprint)
    return result


def snapshot_storage_estimate(width=180, height=90):
    fields = len(AtmosphericGrid.empty(4, 2).fields)
    uncompressed = int(width) * int(height) * fields * 4
    return {
        "fields": fields,
        "cells": int(width) * int(height),
        "uncompressed_bytes": uncompressed,
        "uncompressed_kib": round(uncompressed / 1024, 1),
    }


def latest_atmospheric_cell_diagnostics(
    campaign,
    config,
    latitude,
    longitude,
    *,
    world_minutes=None,
):
    """Read-only GM diagnostics; never initializes or mutates atmosphere on GET."""
    settings = AtmosphericSettings.from_model(config, campaign)
    fingerprint = atmospheric_input_fingerprint(campaign, config)
    target = campaign.world_minutes if world_minutes is None else world_minutes
    snapshot = _latest_compatible_snapshot(
        campaign,
        settings,
        target,
        fingerprint,
    )
    if snapshot is None:
        return None
    grid = grid_from_snapshot(snapshot)
    static = cached_static_world_grid(settings)
    _x, _y, index = coordinates_to_grid(
        latitude,
        longitude,
        width=grid.width,
        height=grid.height,
    )
    forcing = CampaignSkyForcing(campaign, settings)
    radiative_grid = forcing.forcing_grid(
        geometry_for(settings),
        snapshot.world_minutes,
    )
    diagnostics = cell_ocean_diagnostics(
        grid,
        static,
        settings,
        index,
        radiative_grid=radiative_grid,
    )
    diagnostics["snapshot_world_minutes"] = snapshot.world_minutes
    return diagnostics
