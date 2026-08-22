"""Spherical C4 circulation operators and diagnostic fields."""

from __future__ import annotations

import numpy as np

from .geometry import geometry_for
from .terrain import terrain_metrics


CIRCULATION_MODEL_VERSION = 1


def virtual_temperature_k(temperature_c, specific_humidity, settings):
    kelvin = np.maximum(120.0, np.asarray(temperature_c, dtype=np.float64) + 273.15)
    q_v = np.maximum(0.0, np.asarray(specific_humidity, dtype=np.float64))
    return kelvin * (
        1.0
        + settings.value("virtual_temperature_moisture_coefficient") * q_v
    )


def air_density_kg_m3(circulation_pressure_hpa, temperature_c, specific_humidity, settings):
    gas_constant = max(1.0, settings.value("dry_air_gas_constant_j_kg_k"))
    return np.maximum(
        0.05,
        np.asarray(circulation_pressure_hpa, dtype=np.float64)
        * 100.0
        / (gas_constant * virtual_temperature_k(temperature_c, specific_humidity, settings)),
    )


def pressure_gradient_acceleration(
    circulation_pressure_hpa,
    temperature_c,
    specific_humidity,
    settings,
):
    geometry = geometry_for(settings)
    pressure_pa = np.asarray(circulation_pressure_hpa, dtype=np.float64) * 100.0
    dp_dx = (
        pressure_pa[geometry.east] - pressure_pa[geometry.west]
    ) * 0.5 * geometry.inverse_east_west_cell_m
    dp_dy = (
        pressure_pa[geometry.north] - pressure_pa[geometry.south]
    ) * 0.5 * geometry.inverse_north_south_cell_m
    density = air_density_kg_m3(
        circulation_pressure_hpa,
        temperature_c,
        specific_humidity,
        settings,
    )
    scale = settings.value("pressure_gradient_acceleration_scale")
    return -scale * dp_dx / density, -scale * dp_dy / density


def apply_coriolis_rotation(wind_u, wind_v, settings, *, seconds=None):
    """Apply the exact local f-plane rotation; speed is conserved."""

    geometry = geometry_for(settings)
    dt = settings.step_minutes * 60.0 if seconds is None else float(seconds)
    angle = geometry.coriolis_parameter_s * dt
    cosine = np.cos(angle)
    sine = np.sin(angle)
    u = np.asarray(wind_u, dtype=np.float64)
    v = np.asarray(wind_v, dtype=np.float64)
    return u * cosine + v * sine, v * cosine - u * sine


def spherical_divergence(wind_u, wind_v, settings):
    geometry = geometry_for(settings)
    u = np.asarray(wind_u, dtype=np.float64)
    v = np.asarray(wind_v, dtype=np.float64)
    du_dx = (u[geometry.east] - u[geometry.west]) * 0.5 * (
        geometry.inverse_east_west_cell_m
    )
    v_cos = v * geometry.cos_latitude
    meridional = (
        v_cos[geometry.north] - v_cos[geometry.south]
    ) * 0.5 * geometry.inverse_north_south_cell_m / geometry.cos_latitude
    return du_dx + meridional


def spherical_relative_vorticity(wind_u, wind_v, settings):
    geometry = geometry_for(settings)
    u = np.asarray(wind_u, dtype=np.float64)
    v = np.asarray(wind_v, dtype=np.float64)
    dv_dx = (v[geometry.east] - v[geometry.west]) * 0.5 * (
        geometry.inverse_east_west_cell_m
    )
    u_cos = u * geometry.cos_latitude
    meridional = (
        u_cos[geometry.north] - u_cos[geometry.south]
    ) * 0.5 * geometry.inverse_north_south_cell_m / geometry.cos_latitude
    return dv_dx - meridional


def vertical_motion_fields(grid, static, settings):
    """Return only state-coupled ascent fields used every solver step."""

    terrain = terrain_metrics(static, settings)
    u = grid.fields["wind_u"].astype(np.float64)
    v = grid.fields["wind_v"].astype(np.float64)
    divergence = spherical_divergence(u, v, settings)
    # Upwind differencing is intentionally used for terrain advection: it
    # preserves both faces of one-cell-wide ridges on the 2-degree grid.
    w_orographic = (
        np.maximum(u, 0.0) * terrain["rise_from_west"]
        + np.maximum(-u, 0.0) * terrain["rise_from_east"]
        + np.maximum(v, 0.0) * terrain["rise_from_south"]
        + np.maximum(-v, 0.0) * terrain["rise_from_north"]
    )
    w_convergence = -settings.value("effective_mixing_depth_m") * divergence
    # u·grad(h) already has the physical unit m/s and must not be attenuated a
    # second time.  Convergence is a single-layer proxy, so only that inferred
    # component receives the configurable coupling coefficient.
    effective_w_convergence = (
        settings.value("vertical_motion_coupling") * w_convergence
    )
    maximum = max(0.0, settings.value("maximum_vertical_motion_proxy_m_s"))
    w_total = np.clip(w_orographic + effective_w_convergence, -maximum, maximum)
    return {
        "divergence_s_1": divergence,
        "convergence_s_1": -divergence,
        "w_orographic_m_s": w_orographic,
        "w_convergence_m_s": w_convergence,
        "effective_w_convergence_m_s": effective_w_convergence,
        "vertical_motion_proxy_m_s": w_total,
        "terrain_slope": terrain["slope_magnitude"],
        "terrain_ruggedness": terrain["ruggedness"],
    }


def circulation_diagnostics(grid, static, settings):
    geometry = geometry_for(settings)
    u = grid.fields["wind_u"].astype(np.float64)
    v = grid.fields["wind_v"].astype(np.float64)
    result = vertical_motion_fields(grid, static, settings)
    vorticity = spherical_relative_vorticity(u, v, settings)
    pressure_u, pressure_v = pressure_gradient_acceleration(
        grid.fields["circulation_pressure_hpa"],
        grid.fields["temperature"],
        grid.fields["water_vapor_specific_humidity"],
        settings,
    )
    coriolis_u = geometry.coriolis_parameter_s * v
    coriolis_v = -geometry.coriolis_parameter_s * u
    drag_hours = np.where(
        static.is_ocean,
        settings.value("ocean_drag_timescale_hours"),
        settings.value("land_drag_timescale_hours"),
    )
    drag_u = -u / np.maximum(1.0, drag_hours * 3600.0)
    drag_v = -v / np.maximum(1.0, drag_hours * 3600.0)
    result.update({
        "relative_vorticity_s_1": vorticity,
        "absolute_vorticity_s_1": vorticity + geometry.coriolis_parameter_s,
        "pressure_acceleration_u_m_s2": pressure_u,
        "pressure_acceleration_v_m_s2": pressure_v,
        "coriolis_parameter_s_1": geometry.coriolis_parameter_s,
        "coriolis_acceleration_u_m_s2": coriolis_u,
        "coriolis_acceleration_v_m_s2": coriolis_v,
        "surface_drag_acceleration_u_m_s2": drag_u,
        "surface_drag_acceleration_v_m_s2": drag_v,
    })
    return result
