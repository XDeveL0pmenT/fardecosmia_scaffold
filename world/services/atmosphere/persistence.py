from world.atmosphere_defaults import ATMOSPHERIC_FORMAT_VERSION
from world.models import AtmosphericSnapshot

from .config import AtmosphericSettings
from .forcing import CampaignSkyForcing
from .grid import AtmosphericGrid
from .simulation import initialize_atmosphere, simulate_step
from .static_grid import cached_static_world_grid


MAX_ATMOSPHERIC_STEPS_PER_ADVANCE = 10_000
SNAPSHOT_BULK_SIZE = 16


def grid_from_snapshot(snapshot):
    if snapshot.format_version != ATMOSPHERIC_FORMAT_VERSION:
        raise ValueError("Версия атмосферного снимка не поддерживается.")
    return AtmosphericGrid.deserialize(
        snapshot.grid_width,
        snapshot.grid_height,
        snapshot.payload,
    )


def save_snapshot(campaign, world_minutes, grid):
    snapshot, created = AtmosphericSnapshot.objects.get_or_create(
        campaign=campaign,
        world_minutes=world_minutes,
        defaults={
            "grid_width": grid.width,
            "grid_height": grid.height,
            "format_version": ATMOSPHERIC_FORMAT_VERSION,
            "payload": grid.serialize(),
        },
    )
    if not created and (snapshot.grid_width, snapshot.grid_height) != (
        grid.width,
        grid.height,
    ):
        raise ValueError("Существующий атмосферный снимок имеет другой размер сетки.")
    return snapshot, created


def advance_atmosphere_for_period(campaign, config, old_time, new_time):
    """Advance every fixed boundary sequentially and persist compact snapshots."""
    if new_time < old_time:
        raise ValueError("Атмосферу нельзя прокручивать назад этим сервисом.")
    settings = AtmosphericSettings.from_model(config, campaign)
    settings.require_ocean_temperature()
    snapshot = (
        campaign.atmospheric_snapshots.filter(world_minutes__lte=old_time)
        .order_by("-world_minutes")
        .first()
    )
    generated = []

    if snapshot is not None and (snapshot.grid_width, snapshot.grid_height) != (
        settings.width,
        settings.height,
    ):
        raise ValueError(
            "Размер AtmosphericConfig изменён при существующих снимках. "
            "Создайте новую последовательность снимков явно."
        )

    # Most UI advances are smaller than one atmospheric interval. Once an
    # initial snapshot exists, such advances need no raster loading, grid
    # allocation, decompression, or simulation at all.
    if (
        snapshot is not None
        and snapshot.world_minutes + settings.step_minutes > new_time
    ):
        return generated

    static = cached_static_world_grid(settings)
    forcing = CampaignSkyForcing(campaign, settings)

    if snapshot is None:
        boundary = old_time - old_time % settings.step_minutes
        grid, _ = initialize_atmosphere(
            settings,
            static=static,
            world_minutes=boundary,
        )
        snapshot, created = save_snapshot(campaign, boundary, grid)
        if created:
            generated.append(snapshot)
    else:
        grid = grid_from_snapshot(snapshot)
        boundary = snapshot.world_minutes

    transitions = max(0, (new_time - boundary) // settings.step_minutes)
    if transitions > MAX_ATMOSPHERIC_STEPS_PER_ADVANCE:
        raise ValueError(
            "Шаг времени пересекает слишком много интервалов атмосферы. "
            "Увеличьте step_minutes или продвигайте мир меньшими шагами."
        )

    future_boundaries = range(
        boundary + settings.step_minutes,
        new_time + 1,
        settings.step_minutes,
    )
    existing_by_time = {
        item.world_minutes: item
        for item in campaign.atmospheric_snapshots.filter(
            world_minutes__in=future_boundaries,
        )
    }
    pending = []

    def flush_pending():
        if not pending:
            return
        AtmosphericSnapshot.objects.bulk_create(
            pending,
            batch_size=SNAPSHOT_BULK_SIZE,
        )
        pending.clear()

    while boundary + settings.step_minutes <= new_time:
        boundary += settings.step_minutes
        existing = existing_by_time.get(boundary)
        if existing is not None:
            grid = grid_from_snapshot(existing)
            snapshot = existing
        else:
            grid = simulate_step(
                grid,
                static,
                settings,
                step_index=boundary // settings.step_minutes,
                world_minutes=boundary,
                forcing=forcing,
            )
            snapshot = AtmosphericSnapshot(
                campaign=campaign,
                world_minutes=boundary,
                grid_width=grid.width,
                grid_height=grid.height,
                format_version=ATMOSPHERIC_FORMAT_VERSION,
                payload=grid.serialize(),
            )
            pending.append(snapshot)
            if len(pending) >= SNAPSHOT_BULK_SIZE:
                flush_pending()
        if boundary > old_time:
            generated.append(snapshot)
    flush_pending()
    return generated


def snapshot_storage_estimate(width=180, height=90):
    fields = 9
    uncompressed = int(width) * int(height) * fields * 4
    return {
        "fields": fields,
        "cells": int(width) * int(height),
        "uncompressed_bytes": uncompressed,
        "uncompressed_kib": round(uncompressed / 1024, 1),
    }
