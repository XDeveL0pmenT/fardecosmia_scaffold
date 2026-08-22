"""Phase C3 vectorized bulk-column cloud microphysics.

``q_v`` is water vapor and ``q_c`` is one suspended total-condensate
reservoir, both expressed as kg water per kg moist air.  Liquid/ice phase is
diagnostic only in C3.
"""

from __future__ import annotations

import math

import numpy as np

from .geometry import geometry_for
from .thermodynamics import (
    relative_humidity_percent,
    saturation_specific_humidity,
    saturation_specific_humidity_with_temperature_derivative,
)


MICROPHYSICS_VERSION = 1


def _record_float(diagnostics, key, value):
    if diagnostics is not None and value:
        diagnostics[key] = diagnostics.get(key, 0.0) + float(value)


def _cell_areas_m2(settings):
    return geometry_for(settings).cell_areas_m2


def air_column_mass_kg_m2(pressure_hpa, settings):
    gravity = max(1e-6, settings.value("fardecosmia_gravity_m_s2"))
    return np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0 / gravity)


def saturation_adjustment(
    temperature_c,
    pressure_hpa,
    q_v,
    q_c,
    settings,
    *,
    diagnostics=None,
    air_mass_kg_m2_values=None,
    cell_areas_m2=None,
):
    """Couple vapor/condensate and latent heat to saturation.

    A bounded vectorized Newton solve finds the saturated temperature at the
    cell's conserved moist enthalpy.  Cloud-limited dry cells evaporate all
    available condensate instead.  There is no Python loop per cell.
    """

    temperature = np.asarray(temperature_c, dtype=np.float64).copy()
    pressure = np.asarray(pressure_hpa, dtype=np.float64)
    vapor = np.maximum(0.0, np.asarray(q_v, dtype=np.float64).copy())
    condensate = np.maximum(0.0, np.asarray(q_c, dtype=np.float64).copy())
    original_temperature = temperature.copy()
    original_vapor = vapor.copy()
    original_condensate = condensate.copy()
    latent_heat = settings.value("latent_heat_vaporization_j_kg")
    heat_capacity = settings.value("air_heat_capacity_j_kg_k")
    latent_temperature_factor = latent_heat / heat_capacity
    tolerance = max(1e-12, settings.value("saturation_adjustment_tolerance"))
    maximum_iterations = max(1, int(settings.value("saturation_adjustment_max_iterations")))

    q_sat_initial = saturation_specific_humidity(
        temperature,
        pressure,
        latent_heat_j_kg=latent_heat,
        diagnostics=diagnostics,
    )
    condensing = vapor > q_sat_initial + tolerance
    evaporating = (condensate > tolerance) & (vapor < q_sat_initial - tolerance)
    full_evaporation_temperature = temperature.copy()
    saturation_after_full_evaporation = np.zeros_like(temperature)
    evaporation_indices = np.flatnonzero(evaporating)
    if evaporation_indices.size:
        full_evaporation_temperature[evaporation_indices] = (
            temperature[evaporation_indices]
            - latent_temperature_factor * condensate[evaporation_indices]
        )
        saturation_after_full_evaporation[evaporation_indices] = (
            saturation_specific_humidity(
                full_evaporation_temperature[evaporation_indices],
                pressure[evaporation_indices],
                latent_heat_j_kg=latent_heat,
                diagnostics=diagnostics,
            )
        )
    reaches_saturation = evaporating & (
        vapor + condensate >= saturation_after_full_evaporation
    )
    cloud_limited = evaporating & ~reaches_saturation

    equilibrating = condensing | reaches_saturation
    if diagnostics is not None:
        diagnostics["microphysics_cells_seen"] = diagnostics.get(
            "microphysics_cells_seen", 0
        ) + int(temperature.size)
        diagnostics["saturation_adjustment_active_cells"] = diagnostics.get(
            "saturation_adjustment_active_cells", 0
        ) + int(np.count_nonzero(equilibrating))
        diagnostics["cloud_evaporation_active_cells"] = diagnostics.get(
            "cloud_evaporation_active_cells", 0
        ) + int(evaporation_indices.size)
    iterations_used = 0
    if np.any(equilibrating):
        active_indices = np.flatnonzero(equilibrating)
        active_temperature = temperature[active_indices]
        active_pressure = pressure[active_indices]
        active_vapor = vapor[active_indices]
        active_condensing = condensing[active_indices]
        active_reaches_saturation = reaches_saturation[active_indices]
        lower = np.where(
            active_condensing,
            active_temperature,
            np.where(
                active_reaches_saturation,
                full_evaporation_temperature[active_indices],
                active_temperature,
            ),
        )
        upper = np.where(
            active_condensing,
            active_temperature + latent_temperature_factor * active_vapor,
            active_temperature,
        )
        trial = np.clip(active_temperature, lower, upper)
        target_enthalpy = (
            heat_capacity * active_temperature + latent_heat * active_vapor
        )
        converged = np.zeros(active_indices.size, dtype=np.bool_)
        for iteration in range(maximum_iterations):
            unresolved = np.flatnonzero(~converged)
            if not unresolved.size:
                iterations_used = iteration
                break
            q_sat_trial, q_sat_derivative = (
                saturation_specific_humidity_with_temperature_derivative(
                    trial[unresolved],
                    active_pressure[unresolved],
                    latent_heat_j_kg=latent_heat,
                    diagnostics=diagnostics,
                )
            )
            residual = (
                heat_capacity * trial[unresolved]
                + latent_heat * q_sat_trial
                - target_enthalpy[unresolved]
            )
            newly_converged = np.abs(residual) / latent_heat <= tolerance
            converged[unresolved[newly_converged]] = True
            still_active = unresolved[~newly_converged]
            if not still_active.size:
                iterations_used = iteration + 1
                break
            active_residual = residual[~newly_converged]
            lower[still_active] = np.where(
                active_residual < 0.0,
                trial[still_active],
                lower[still_active],
            )
            upper[still_active] = np.where(
                active_residual >= 0.0,
                trial[still_active],
                upper[still_active],
            )
            active_derivative = (
                heat_capacity + latent_heat * q_sat_derivative[~newly_converged]
            )
            newton = (
                trial[still_active]
                - active_residual / np.maximum(1e-9, active_derivative)
            )
            midpoint = (lower[still_active] + upper[still_active]) * 0.5
            inside = (
                (newton > lower[still_active])
                & (newton < upper[still_active])
                & np.isfinite(newton)
            )
            trial[still_active] = np.where(inside, newton, midpoint)
            iterations_used = iteration + 1
        final_q_saturated = saturation_specific_humidity(
            trial,
            active_pressure,
            latent_heat_j_kg=latent_heat,
            diagnostics=diagnostics,
        )
        temperature[active_indices] = (
            target_enthalpy - latent_heat * final_q_saturated
        ) / heat_capacity
        vapor[active_indices] = final_q_saturated
        condensate[active_indices] = (
            original_condensate[active_indices]
            + original_vapor[active_indices]
            - final_q_saturated
        )

    cloud_limited_indices = np.flatnonzero(cloud_limited)
    if cloud_limited_indices.size:
        temperature[cloud_limited_indices] = full_evaporation_temperature[
            cloud_limited_indices
        ]
        vapor[cloud_limited_indices] = (
            original_vapor[cloud_limited_indices]
            + original_condensate[cloud_limited_indices]
        )
        condensate[cloud_limited_indices] = 0.0

    condensation_delta = np.maximum(0.0, original_vapor - vapor)
    evaporation_delta = np.maximum(0.0, vapor - original_vapor)
    vapor = np.maximum(0.0, vapor)
    condensate = np.maximum(0.0, condensate)
    changed = (condensation_delta > 0.0) | (evaporation_delta > 0.0)
    condensation_mass = 0.0
    cloud_evaporation_mass = 0.0
    if diagnostics is not None and np.any(changed):
        if air_mass_kg_m2_values is None:
            changed_air_mass = air_column_mass_kg_m2(pressure[changed], settings)
        else:
            changed_air_mass = np.asarray(
                air_mass_kg_m2_values,
                dtype=np.float64,
            )[changed]
        if cell_areas_m2 is None:
            changed_areas = _cell_areas_m2(settings)[changed]
        else:
            changed_areas = np.asarray(cell_areas_m2, dtype=np.float64)[changed]
        condensation_mass = float(
            np.sum(condensation_delta[changed] * changed_air_mass * changed_areas)
        )
        cloud_evaporation_mass = float(
            np.sum(evaporation_delta[changed] * changed_air_mass * changed_areas)
        )
    _record_float(diagnostics, "condensation_mass_kg", condensation_mass)
    _record_float(diagnostics, "cloud_evaporation_mass_kg", cloud_evaporation_mass)
    if diagnostics is not None:
        diagnostics["saturation_adjustment_max_iterations_used"] = max(
            diagnostics.get("saturation_adjustment_max_iterations_used", 0),
            iterations_used,
        )
    return {
        "temperature": temperature,
        "q_v": vapor,
        "q_c": condensate,
        "condensation_delta_q": condensation_delta,
        "cloud_evaporation_delta_q": evaporation_delta,
    }


def condensate_ice_fraction(temperature_c, settings):
    temperature = np.asarray(temperature_c, dtype=np.float64)
    ice_temperature = settings.value("cloud_ice_temperature_c")
    liquid_temperature = settings.value("cloud_liquid_temperature_c")
    if liquid_temperature <= ice_temperature:
        return (temperature <= ice_temperature).astype(np.float64)
    return np.clip(
        (liquid_temperature - temperature) / (liquid_temperature - ice_temperature),
        0.0,
        1.0,
    )


def rain_and_snow_fraction(temperature_c, settings):
    snow = condensate_ice_fraction(temperature_c, settings)
    return 1.0 - snow, snow


def precipitation_fallout(
    q_c,
    pressure_hpa,
    temperature_c,
    settings,
    *,
    timestep_seconds=None,
    diagnostics=None,
    air_mass_kg_m2_values=None,
    cell_areas_m2=None,
    include_phase_partition=True,
):
    """Autoconvert suspended condensate into a physical surface mass flux."""

    condensate = np.maximum(0.0, np.asarray(q_c, dtype=np.float64))
    pressure = np.asarray(pressure_hpa, dtype=np.float64)
    seconds = (
        settings.step_minutes * 60.0
        if timestep_seconds is None
        else max(1e-9, float(timestep_seconds))
    )
    threshold = max(0.0, settings.value("precipitation_condensate_threshold"))
    timescale = max(1.0, settings.value("precipitation_fallout_timescale_seconds"))
    excess = np.maximum(0.0, condensate - threshold)
    fallout_fraction = 1.0 - math.exp(-seconds / timescale)
    removed_q = np.minimum(condensate, excess * fallout_fraction)
    emergency_limit = max(
        threshold,
        settings.value("maximum_cloud_condensate_specific_humidity"),
    )
    emergency_excess = np.maximum(0.0, condensate - removed_q - emergency_limit)
    if diagnostics is not None and np.any(emergency_excess > 0.0):
        diagnostics["cloud_condensate_emergency_clamp_hits"] = diagnostics.get(
            "cloud_condensate_emergency_clamp_hits", 0
        ) + int(np.count_nonzero(emergency_excess > 0.0))
    removed_q = np.minimum(condensate, removed_q + emergency_excess)
    remaining = condensate - removed_q
    precipitating = removed_q > 0.0
    if diagnostics is not None:
        diagnostics["precipitation_active_cells"] = diagnostics.get(
            "precipitation_active_cells", 0
        ) + int(np.count_nonzero(precipitating))
    precipitation_rate = np.zeros_like(removed_q)
    if np.any(precipitating):
        if air_mass_kg_m2_values is None:
            active_air_mass = air_column_mass_kg_m2(
                pressure[precipitating],
                settings,
            )
        else:
            active_air_mass = np.asarray(
                air_mass_kg_m2_values,
                dtype=np.float64,
            )[precipitating]
        precipitation_rate[precipitating] = (
            removed_q[precipitating] * active_air_mass / seconds
        )
    if diagnostics is not None:
        invalid_source = (precipitation_rate > 0.0) & (condensate <= 0.0)
        if np.any(invalid_source):
            diagnostics["precipitation_without_condensate_cells"] = diagnostics.get(
                "precipitation_without_condensate_cells", 0
            ) + int(np.count_nonzero(invalid_source))
        diagnostics["maximum_pre_fallout_q_c"] = max(
            diagnostics.get("maximum_pre_fallout_q_c", 0.0),
            float(np.max(condensate, initial=0.0)),
        )
    if include_phase_partition:
        rain_fraction, snow_fraction = rain_and_snow_fraction(
            temperature_c,
            settings,
        )
    else:
        rain_fraction = None
        snow_fraction = None
    total_mass = 0.0
    if diagnostics is not None and np.any(precipitating):
        if cell_areas_m2 is None:
            active_areas = _cell_areas_m2(settings)[precipitating]
        else:
            active_areas = np.asarray(cell_areas_m2, dtype=np.float64)[
                precipitating
            ]
        total_mass = float(
            np.sum(
                precipitation_rate[precipitating]
                * seconds
                * active_areas
            )
        )
    _record_float(diagnostics, "total_precipitated_mass_kg", total_mass)
    _record_float(diagnostics, "surface_precipitation_sink_kg", total_mass)
    return {
        "q_c": remaining,
        "rate_kg_m2_s": precipitation_rate,
        "rate_mm_h": precipitation_rate * 3600.0,
        "amount_mm_per_step": precipitation_rate * seconds,
        "rain_fraction": rain_fraction,
        "snow_fraction": snow_fraction,
        "removed_delta_q": removed_q,
    }


def cloud_water_path_kg_m2(q_c, pressure_hpa, settings):
    return np.maximum(0.0, np.asarray(q_c, dtype=np.float64)) * air_column_mass_kg_m2(
        pressure_hpa,
        settings,
    )


def cloud_cover_from_condensate(q_c, pressure_hpa, settings):
    path = cloud_water_path_kg_m2(q_c, pressure_hpa, settings)
    optical_depth = max(0.0, settings.value("cloud_optical_coefficient_m2_kg")) * path
    return np.clip(1.0 - np.exp(-optical_depth), 0.0, 1.0)


def fog_potential(
    q_v,
    q_c,
    temperature_c,
    pressure_hpa,
    wind_speed_m_s,
    elevation_m,
    settings,
):
    rh = relative_humidity_percent(
        q_v,
        temperature_c,
        pressure_hpa,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
    )
    rh_threshold = settings.value("fog_rh_threshold_percent")
    rh_factor = np.clip((rh - rh_threshold) / max(1.0, 100.0 - rh_threshold), 0.0, 1.0)
    condensate_factor = np.clip(
        np.asarray(q_c, dtype=np.float64)
        / max(1e-12, settings.value("fog_condensate_threshold")),
        0.0,
        1.0,
    )
    wind_factor = np.clip(
        1.0
        - np.asarray(wind_speed_m_s, dtype=np.float64)
        / max(0.1, settings.value("fog_wind_max_m_s")),
        0.0,
        1.0,
    )
    lowland_factor = np.clip(
        1.0
        - np.maximum(0.0, np.asarray(elevation_m, dtype=np.float64))
        / max(1.0, settings.value("fog_lowland_elevation_m")),
        0.0,
        1.0,
    )
    return np.clip(
        rh_factor * condensate_factor * (0.75 + 0.25 * lowland_factor) * wind_factor,
        0.0,
        1.0,
    )


def atmospheric_water_mass_diagnostics(grid, settings):
    pressure = grid.fields["pressure_hpa"].astype(np.float64)
    air_mass = air_column_mass_kg_m2(pressure, settings)
    areas = _cell_areas_m2(settings)
    return {
        "total_vapor_mass_proxy_kg": float(
            np.sum(grid.fields["water_vapor_specific_humidity"] * air_mass * areas)
        ),
        "total_cloud_condensate_mass_proxy_kg": float(
            np.sum(grid.fields["cloud_condensate_specific_humidity"] * air_mass * areas)
        ),
    }
