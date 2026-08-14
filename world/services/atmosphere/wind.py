"""Prognostic C4 momentum driven by reduced pressure on a rotating sphere."""

from __future__ import annotations

import math

import numpy as np

from .advection import advect_momentum
from .circulation import apply_coriolis_rotation, pressure_gradient_acceleration
from .terrain import terrain_metrics


def _apply_terrain_drag(u, v, static, settings, seconds):
    terrain = terrain_metrics(static, settings)
    directional_slope_u = np.where(
        u >= 0.0,
        terrain["rise_from_west"],
        terrain["rise_from_east"],
    )
    directional_slope_v = np.where(
        v >= 0.0,
        terrain["rise_from_south"],
        terrain["rise_from_north"],
    )
    rate = max(0.0, settings.value("terrain_upslope_drag_rate_per_slope_s"))
    upslope_factor_u = np.exp(
        -seconds
        * rate
        * np.maximum(0.0, directional_slope_u)
    )
    upslope_factor_v = np.exp(
        -seconds
        * rate
        * np.maximum(0.0, directional_slope_v)
    )
    u *= upslope_factor_u
    v *= upslope_factor_v
    rugged_factor = np.exp(
        -seconds
        * max(0.0, settings.value("terrain_ruggedness_drag_rate_per_slope_s"))
        * terrain["ruggedness"]
    )
    return u * rugged_factor, v * rugged_factor


def solve_wind(grid, static, settings, *, diagnostics=None):
    previous_u = grid.fields["wind_u"].astype(np.float64)
    previous_v = grid.fields["wind_v"].astype(np.float64)
    advected_u, advected_v = advect_momentum(grid, settings)
    u = advected_u.astype(np.float64)
    v = advected_v.astype(np.float64)
    acceleration_u, acceleration_v = pressure_gradient_acceleration(
        grid.fields["circulation_pressure_hpa"],
        grid.fields["temperature"],
        grid.fields["water_vapor_specific_humidity"],
        settings,
    )
    seconds = settings.step_minutes * 60.0
    u += acceleration_u * seconds
    v += acceleration_v * seconds
    u, v = apply_coriolis_rotation(u, v, settings, seconds=seconds)

    drag_hours = np.where(
        static.is_ocean,
        settings.value("ocean_drag_timescale_hours"),
        settings.value("land_drag_timescale_hours"),
    )
    drag_factor = np.exp(-seconds / np.maximum(1.0, drag_hours * 3600.0))
    u *= drag_factor
    v *= drag_factor
    u, v = _apply_terrain_drag(u, v, static, settings, seconds)

    speed = np.hypot(u, v)
    maximum = max(0.1, settings.value("max_wind_speed_m_s"))
    cap_hits = speed > maximum
    scale = np.ones_like(speed)
    scale[cap_hits] = maximum / speed[cap_hits]
    u *= scale
    v *= scale
    if diagnostics is not None:
        diagnostics["wind_cap_hits"] = diagnostics.get("wind_cap_hits", 0) + int(
            np.count_nonzero(cap_hits)
        )
        diagnostics["maximum_pressure_gradient_acceleration_m_s2"] = max(
            diagnostics.get("maximum_pressure_gradient_acceleration_m_s2", 0.0),
            float(np.max(np.hypot(acceleration_u, acceleration_v), initial=0.0)),
        )
        diagnostics["maximum_wind_speed_m_s"] = max(
            diagnostics.get("maximum_wind_speed_m_s", 0.0),
            float(np.max(np.hypot(u, v), initial=0.0)),
        )
        diagnostics["maximum_wind_change_m_s"] = max(
            diagnostics.get("maximum_wind_change_m_s", 0.0),
            float(np.max(np.hypot(u - previous_u, v - previous_v), initial=0.0)),
        )
    return u.astype(np.float32), v.astype(np.float32)
