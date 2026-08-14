"""Unified convergence/orographic vertical-motion coupling for C4."""

from __future__ import annotations

import numpy as np

from .circulation import vertical_motion_fields


def orographic_uplift(grid, static, settings):
    diagnostics = vertical_motion_fields(grid, static, settings)
    return {
        "w_orographic_m_s": diagnostics["w_orographic_m_s"],
        "w_convergence_m_s": diagnostics["w_convergence_m_s"],
        "vertical_motion_proxy_m_s": diagnostics["vertical_motion_proxy_m_s"],
        "divergence_s_1": diagnostics["divergence_s_1"],
    }


def apply_orographic_temperature_tendency(grid, static, settings, *, diagnostics=None):
    """Apply one physically linked 2D ascent/descent temperature proxy."""

    fields = vertical_motion_fields(grid, static, settings)
    vertical_motion = fields["vertical_motion_proxy_m_s"]
    seconds = settings.step_minutes * 60.0
    lapse_rate_c_m = (
        settings.value("effective_adiabatic_lapse_rate_c_per_km") / 1000.0
    )
    change = (
        -vertical_motion
        * seconds
        * lapse_rate_c_m
    )
    maximum = max(0.0, settings.value("maximum_vertical_temperature_change_c"))
    change = np.clip(change, -maximum, maximum)
    grid.fields["temperature"] = (
        grid.fields["temperature"].astype(np.float64) + change
    ).astype(np.float32)
    if diagnostics is not None:
        diagnostics["orographic_uplift_cell_count"] = diagnostics.get(
            "orographic_uplift_cell_count", 0
        ) + int(np.count_nonzero(fields["w_orographic_m_s"] > 0.0))
        diagnostics["convergence_uplift_cell_count"] = diagnostics.get(
            "convergence_uplift_cell_count", 0
        ) + int(np.count_nonzero(fields["w_convergence_m_s"] > 0.0))
        diagnostics["maximum_orographic_ascent_m_s"] = max(
            diagnostics.get("maximum_orographic_ascent_m_s", 0.0),
            float(np.max(fields["w_orographic_m_s"], initial=0.0)),
        )
        diagnostics["maximum_convergence_ascent_m_s"] = max(
            diagnostics.get("maximum_convergence_ascent_m_s", 0.0),
            float(np.max(fields["w_convergence_m_s"], initial=0.0)),
        )
        diagnostics["maximum_vertical_motion_proxy_m_s"] = max(
            diagnostics.get("maximum_vertical_motion_proxy_m_s", 0.0),
            float(np.max(np.abs(vertical_motion), initial=0.0)),
        )
        diagnostics["maximum_orographic_cooling_c"] = max(
            diagnostics.get("maximum_orographic_cooling_c", 0.0),
            float(np.max(np.maximum(0.0, -change), initial=0.0)),
        )
    return fields


def apply_orography_and_precipitation(
    grid,
    static,
    settings,
    *,
    relative_humidity=None,
    diagnostics=None,
):
    del relative_humidity
    return apply_orographic_temperature_tendency(
        grid,
        static,
        settings,
        diagnostics=diagnostics,
    )
