"""Cached large-scale terrain metrics for the C4 single-layer atmosphere."""

from __future__ import annotations

import numpy as np

from .geometry import geometry_for


def terrain_metrics(static, settings):
    """Return physical slopes/ruggedness, cached on the immutable static grid."""

    cache_key = (
        settings.width,
        settings.height,
        float(settings.world_circumference_km),
        settings.value("minimum_polar_cell_cosine"),
    )
    cache = getattr(static, "_terrain_metrics_cache", None)
    if cache is None:
        cache = {}
        static._terrain_metrics_cache = cache
    if cache_key in cache:
        return cache[cache_key]

    geometry = geometry_for(settings)
    elevation = np.asarray(static.elevation, dtype=np.float64)
    slope_x = (
        elevation[geometry.east] - elevation[geometry.west]
    ) * 0.5 * geometry.inverse_east_west_cell_m
    # v is northward, so the latitude derivative is north minus south.
    slope_y = (
        elevation[geometry.north] - elevation[geometry.south]
    ) * 0.5 * geometry.inverse_north_south_cell_m
    slope_magnitude = np.hypot(slope_x, slope_y)
    # One-sided, upwind-ready slopes retain the windward and lee faces of a
    # ridge that may occupy only one coarse atmospheric cell.
    rise_from_west = (
        elevation - elevation[geometry.west]
    ) * geometry.inverse_east_west_cell_m
    rise_from_east = (
        elevation - elevation[geometry.east]
    ) * geometry.inverse_east_west_cell_m
    rise_from_south = (
        elevation - elevation[geometry.south]
    ) * geometry.inverse_north_south_cell_m
    rise_from_north = (
        elevation - elevation[geometry.north]
    ) * geometry.inverse_north_south_cell_m
    neighbor_high = np.maximum.reduce(
        (
            elevation[geometry.west],
            elevation[geometry.east],
            elevation[geometry.north],
            elevation[geometry.south],
        )
    )
    neighbor_low = np.minimum.reduce(
        (
            elevation[geometry.west],
            elevation[geometry.east],
            elevation[geometry.north],
            elevation[geometry.south],
        )
    )
    characteristic_distance = np.minimum(
        geometry.east_west_cell_m_flat,
        geometry.north_south_cell_m,
    )
    ruggedness = (neighbor_high - neighbor_low) / np.maximum(
        1.0,
        2.0 * characteristic_distance,
    )
    result = {
        "slope_x": slope_x,
        "slope_y": slope_y,
        "slope_magnitude": slope_magnitude,
        "rise_from_west": rise_from_west,
        "rise_from_east": rise_from_east,
        "rise_from_south": rise_from_south,
        "rise_from_north": rise_from_north,
        "ruggedness": ruggedness,
    }
    for values in result.values():
        values.flags.writeable = False
    cache[cache_key] = result
    return result
