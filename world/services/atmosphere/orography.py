"""Terrain-driven cooling/warming for Phase C3 cloud microphysics."""

import numpy as np

from .geometry import geometry_for


def orographic_uplift(grid, static, settings):
    """Return wind-aligned climb/descent and a normalized flow factor."""

    geometry = geometry_for(settings)
    u = grid.fields["wind_u"].astype(np.float64)
    v = grid.fields["wind_v"].astype(np.float64)
    upwind_x = (geometry.flat_x - np.sign(u).astype(np.int32)) % grid.width
    upwind_y = np.clip(
        geometry.flat_y + np.sign(v).astype(np.int32),
        0,
        grid.height - 1,
    )
    upwind = upwind_y * grid.width + upwind_x
    elevation = np.asarray(static.elevation, dtype=np.float64)
    delta = elevation - elevation[upwind]
    speed_factor = np.minimum(1.0, np.hypot(u, v) / 10.0)
    return {
        "climb_m": np.maximum(0.0, delta),
        "descent_m": np.maximum(0.0, -delta),
        "speed_factor": speed_factor,
    }


def apply_orographic_temperature_tendency(grid, static, settings, *, diagnostics=None):
    """Cool rising flow and warm descending flow before saturation adjustment.

    No moisture is created or destroyed here.  Windward condensation and lee
    dryness emerge later from saturation, fallout, and downwind transport.
    """

    uplift = orographic_uplift(grid, static, settings)
    cooling = (
        uplift["climb_m"]
        / 1000.0
        * settings.value("orographic_cooling_c_per_1000m")
        * uplift["speed_factor"]
    )
    warming = (
        uplift["descent_m"]
        / 1000.0
        * settings.value("orographic_descent_warming_c_per_1000m")
        * uplift["speed_factor"]
    )
    maximum = max(0.0, settings.value("orographic_max_temperature_change_c"))
    temperature_change = np.clip(warming - cooling, -maximum, maximum)
    grid.fields["temperature"] = (
        grid.fields["temperature"].astype(np.float64) + temperature_change
    ).astype(np.float32)
    if diagnostics is not None:
        diagnostics["orographic_uplift_cell_count"] = diagnostics.get(
            "orographic_uplift_cell_count", 0
        ) + int(np.count_nonzero(cooling > 0.0))
        diagnostics["maximum_orographic_cooling_c"] = max(
            diagnostics.get("maximum_orographic_cooling_c", 0.0),
            float(np.max(np.maximum(0.0, -temperature_change), initial=0.0)),
        )
    return uplift


def apply_orography_and_precipitation(
    grid,
    static,
    settings,
    *,
    relative_humidity=None,
    diagnostics=None,
):
    """Deprecated compatibility wrapper; C3 precipitation lives in microphysics."""

    del relative_humidity
    return apply_orographic_temperature_tendency(
        grid,
        static,
        settings,
        diagnostics=diagnostics,
    )
