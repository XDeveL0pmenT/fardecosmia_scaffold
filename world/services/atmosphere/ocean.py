"""Phase C2 dynamic ocean mixed layer and bulk air-sea exchange."""

from __future__ import annotations

import math

import numpy as np

from .geometry import geometry_for
from .microphysics import (
    cloud_cover_from_condensate,
    cloud_water_path_kg_m2,
    fog_potential,
    precipitation_fallout,
    rain_and_snow_fraction,
    saturation_adjustment,
)
from .orography import apply_orographic_temperature_tendency
from .pressure import solve_pressure
from .thermodynamics import (
    relative_humidity_percent,
    saturation_specific_humidity,
    specific_humidity_from_relative_humidity,
    vapor_pressure_from_specific_humidity,
    saturation_vapor_pressure_pa,
)
from .wind import solve_wind


OCEAN_MODEL_VERSION = 2


def ocean_baseline_sst(static, settings):
    """Return map climatology, using the legacy config only for invalid pixels."""
    baseline = np.asarray(static.mean_temperature, dtype=np.float64).copy()
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    invalid = ocean & ~np.isfinite(baseline)
    if np.any(invalid):
        baseline[invalid] = settings.require_ocean_temperature()
    return baseline


def open_water_fraction(static):
    """C2 sea-ice hook: all mapped ocean is open water until a later phase."""
    return np.asarray(static.is_ocean, dtype=np.float64)


def ocean_heat_capacity_j_m2_k(settings):
    return (
        settings.value("water_density_kg_m3")
        * settings.value("water_heat_capacity_j_kg_k")
        * settings.value("ocean_mixed_layer_depth_m")
    )


def air_column_mass_kg_m2(pressure_hpa, settings):
    gravity = max(1e-6, settings.value("fardecosmia_gravity_m_s2"))
    return np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0 / gravity)


def _ocean_area_weights(settings):
    return geometry_for(settings).cell_areas_m2


def ocean_weighted_mean(values, static, settings):
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    if not np.any(ocean):
        return None
    weights = _ocean_area_weights(settings)[ocean]
    return float(np.average(np.asarray(values, dtype=np.float64)[ocean], weights=weights))


def atmospheric_vapor_mass_proxy_kg(grid, settings):
    """Return bulk-column vapor mass over the whole grid.

    This diagnostic deliberately remains a proxy until C3 closes the water
    cycle with condensate and precipitation mass.
    """
    areas = _ocean_area_weights(settings)
    air_mass = air_column_mass_kg_m2(grid.fields["pressure_hpa"], settings)
    q_v = np.asarray(
        grid.fields["water_vapor_specific_humidity"],
        dtype=np.float64,
    )
    return float(np.sum(q_v * air_mass * areas))


def _horizontal_anomaly_flux(sst, baseline, static, settings):
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    geometry = geometry_for(settings)
    anomaly = sst - baseline
    neighbor_total = np.zeros_like(anomaly)
    for neighbor in (geometry.west, geometry.east, geometry.north, geometry.south):
        neighbor_total += np.where(ocean[neighbor], anomaly[neighbor], anomaly)
    neighbor_mean = neighbor_total / 4.0
    coefficient = max(0.0, settings.value("ocean_horizontal_mixing_w_m2_k"))
    return np.where(ocean, coefficient * (neighbor_mean - anomaly), 0.0)


def _advect_boundary_scalar(values, wind_u, wind_v, geometry, settings, minutes):
    """Cheap semi-Lagrangian transport for the ocean boundary-layer surrogate."""
    seconds = float(minutes) * 60.0
    width = settings.width
    height = settings.height
    u_2d = np.asarray(wind_u, dtype=np.float64).reshape(height, width)
    v_2d = np.asarray(wind_v, dtype=np.float64).reshape(height, width)
    source_x = (
        geometry.x
        - u_2d * seconds / geometry.east_west_cell_m[:, np.newaxis]
    ) % width
    source_y = np.clip(
        geometry.y + v_2d * seconds / geometry.north_south_cell_m,
        0.0,
        height - 1.0,
    )
    x0 = np.floor(source_x).astype(np.int32)
    y0 = np.floor(source_y).astype(np.int32)
    x1 = (x0 + 1) % width
    y1 = np.minimum(height - 1, y0 + 1)
    tx = source_x - x0
    ty = source_y - y0
    source = np.asarray(values, dtype=np.float64).reshape(height, width)
    top = source[y0, x0] * (1.0 - tx) + source[y0, x1] * tx
    bottom = source[y1, x0] * (1.0 - tx) + source[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).reshape(-1)


def _ocean_flux_components(
    sst,
    baseline,
    air_temperature,
    pressure_hpa,
    specific_humidity,
    wind_speed,
    static,
    settings,
    *,
    stellar_flux_anomaly_w_m2,
    ympha_temperature_anomaly_c,
    diagnostics=None,
):
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    open_fraction = open_water_fraction(static)
    air_density = settings.value("air_density_kg_m3")
    air_cp = settings.value("air_heat_capacity_j_kg_k")
    sensible_wind = np.maximum(
        np.asarray(wind_speed, dtype=np.float64),
        settings.value("ocean_sensible_min_wind_m_s"),
    )
    evaporation_wind = np.maximum(
        np.asarray(wind_speed, dtype=np.float64),
        settings.value("ocean_evaporation_min_wind_m_s"),
    )
    sensible = (
        air_density
        * air_cp
        * settings.value("ocean_sensible_transfer_coefficient")
        * sensible_wind
        * (sst - air_temperature)
    )
    sensible = np.where(ocean, sensible, 0.0)

    q_sat_surface = saturation_specific_humidity(
        sst,
        pressure_hpa,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        diagnostics=diagnostics,
    )
    evaporation = (
        air_density
        * settings.value("ocean_evaporation_transfer_coefficient")
        * evaporation_wind
        * np.maximum(0.0, q_sat_surface - specific_humidity)
        * open_fraction
    )
    evaporation_cap = max(0.0, settings.value("maximum_evaporation_kg_m2_s"))
    capped_evaporation = evaporation > evaporation_cap
    if diagnostics is not None and np.any(capped_evaporation):
        diagnostics["evaporation_cap_cells"] = diagnostics.get(
            "evaporation_cap_cells", 0
        ) + int(np.count_nonzero(capped_evaporation))
    evaporation = np.minimum(evaporation, evaporation_cap)
    latent = settings.value("latent_heat_vaporization_j_kg") * evaporation
    # The static SST map already contains the climatological mean energy
    # balance.  Preserve it by integrating the latent-flux anomaly while the
    # full evaporation flux still adds real water vapor to the atmosphere.
    baseline_q_sat = saturation_specific_humidity(
        baseline,
        pressure_hpa,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        diagnostics=diagnostics,
    )
    baseline_q_air = specific_humidity_from_relative_humidity(
        settings.value("initial_ocean_humidity"),
        baseline,
        pressure_hpa,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        diagnostics=diagnostics,
    )
    climatological_wind = max(
        settings.value("ocean_climatological_evaporation_wind_m_s"),
        settings.value("ocean_evaporation_min_wind_m_s"),
    )
    baseline_evaporation = (
        air_density
        * settings.value("ocean_evaporation_transfer_coefficient")
        * climatological_wind
        * np.maximum(0.0, baseline_q_sat - baseline_q_air)
        * open_fraction
    )
    baseline_evaporation = np.minimum(baseline_evaporation, evaporation_cap)
    # The authoritative SST raster already embeds a climatological surface
    # energy balance.  Integrate only the latent-flux anomaly around that
    # baseline so the unresolved compensating flux is not counted twice.
    latent_anomaly = settings.value("latent_heat_vaporization_j_kg") * np.maximum(
        0.0,
        evaporation - baseline_evaporation,
    )
    star = np.where(
        ocean,
        settings.value("ocean_absorptivity")
        * np.asarray(stellar_flux_anomaly_w_m2, dtype=np.float64),
        0.0,
    )
    heat_capacity = ocean_heat_capacity_j_m2_k(settings)
    deep_seconds = max(
        1.0,
        settings.value("ocean_deep_relaxation_days") * 86_400.0,
    )
    # Ympha remains the explicit C1 temperature proxy; it is not mislabeled
    # as a measured radiative flux.  It only shifts the slow relaxation target.
    deep_target = baseline + np.asarray(
        ympha_temperature_anomaly_c,
        dtype=np.float64,
    )
    deep = np.where(
        ocean,
        heat_capacity * (deep_target - sst) / deep_seconds,
        0.0,
    )
    horizontal = _horizontal_anomaly_flux(sst, baseline, static, settings)
    return {
        "star": star,
        "sensible": sensible,
        "evaporation": evaporation,
        "latent": latent,
        "latent_anomaly": latent_anomaly,
        "deep": deep,
        "deep_target": deep_target,
        "deep_relaxation_seconds": deep_seconds,
        "horizontal": horizontal,
        "q_sat_surface": q_sat_surface,
    }


def _update_sst(
    sst,
    fluxes,
    static,
    settings,
    seconds,
    diagnostics=None,
    *,
    cap_step_scale=1.0,
    analytic_deep_relaxation=False,
):
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    non_deep_tendency = (
        fluxes["star"]
        - fluxes["sensible"]
        - fluxes["latent_anomaly"]
        + fluxes["horizontal"]
    )
    heat_capacity = ocean_heat_capacity_j_m2_k(settings)
    if analytic_deep_relaxation:
        relaxation_seconds = fluxes["deep_relaxation_seconds"]
        equilibrium = (
            fluxes["deep_target"]
            + non_deep_tendency * relaxation_seconds / heat_capacity
        )
        decay = math.exp(-seconds / relaxation_seconds)
        change = equilibrium + (sst - equilibrium) * decay - sst
    else:
        tendency = non_deep_tendency + fluxes["deep"]
        change = tendency * seconds / heat_capacity
    maximum_change = max(
        0.0,
        settings.value("ocean_max_sst_change_per_step_c") * cap_step_scale,
    )
    capped = ocean & (np.abs(change) > maximum_change)
    if diagnostics is not None and np.any(capped):
        diagnostics["sst_step_cap_cells"] = diagnostics.get("sst_step_cap_cells", 0) + int(
            np.count_nonzero(capped)
        )
    change = np.clip(change, -maximum_change, maximum_change)
    updated = np.where(ocean, sst + change, sst)
    minimum = settings.value("ocean_min_sst_c")
    maximum = settings.value("ocean_max_sst_c")
    bounded = ocean & ((updated < minimum) | (updated > maximum))
    if diagnostics is not None and np.any(bounded):
        diagnostics["sst_absolute_cap_cells"] = diagnostics.get(
            "sst_absolute_cap_cells", 0
        ) + int(np.count_nonzero(bounded))
    return np.where(ocean, np.clip(updated, minimum, maximum), sst)


def apply_ocean_surface_exchange(
    grid,
    static,
    settings,
    *,
    radiative_grid=None,
    diagnostics=None,
):
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    grid.fields["evaporation_flux_kg_m2_s"].fill(0.0)
    if not np.any(ocean):
        return None

    seconds = settings.step_minutes * 60.0
    baseline = ocean_baseline_sst(static, settings)
    sst = grid.fields["sea_surface_temperature_c"].astype(np.float64)
    air_temperature = grid.fields["temperature"].astype(np.float64)
    pressure = grid.fields["pressure_hpa"].astype(np.float64)
    q_v = grid.fields["water_vapor_specific_humidity"].astype(np.float64)
    wind_speed = np.hypot(grid.fields["wind_u"], grid.fields["wind_v"]).astype(
        np.float64
    )
    if radiative_grid is None:
        star = np.zeros(grid.size, dtype=np.float64)
        ympha = np.zeros(grid.size, dtype=np.float64)
    else:
        star = radiative_grid.stellar_flux_anomaly_w_m2
        ympha = radiative_grid.ympha_temperature_anomaly_c
    fluxes = _ocean_flux_components(
        sst,
        baseline,
        air_temperature,
        pressure,
        q_v,
        wind_speed,
        static,
        settings,
        stellar_flux_anomaly_w_m2=star,
        ympha_temperature_anomaly_c=ympha,
        diagnostics=diagnostics,
    )
    updated_sst = _update_sst(
        sst,
        fluxes,
        static,
        settings,
        seconds,
        diagnostics=diagnostics,
    )

    air_mass = air_column_mass_kg_m2(pressure, settings)
    air_change = (
        fluxes["sensible"]
        * seconds
        / (settings.value("air_heat_capacity_j_kg_k") * air_mass)
    )
    maximum_air_change = max(
        0.0,
        settings.value("air_max_sensible_change_per_step_c"),
    )
    air_capped = ocean & (np.abs(air_change) > maximum_air_change)
    if diagnostics is not None and np.any(air_capped):
        diagnostics["air_sensible_cap_cells"] = diagnostics.get(
            "air_sensible_cap_cells", 0
        ) + int(np.count_nonzero(air_capped))
    air_change = np.clip(air_change, -maximum_air_change, maximum_air_change)
    updated_air = air_temperature + np.where(ocean, air_change, 0.0)

    q_change = fluxes["evaporation"] * seconds / air_mass
    maximum_q_change = max(
        0.0,
        settings.value("max_specific_humidity_change_per_step"),
    )
    q_change_capped = ocean & (q_change > maximum_q_change)
    if diagnostics is not None and np.any(q_change_capped):
        diagnostics["specific_humidity_step_cap_cells"] = diagnostics.get(
            "specific_humidity_step_cap_cells", 0
        ) + int(np.count_nonzero(q_change_capped))
    q_v += np.where(ocean, np.minimum(q_change, maximum_q_change), 0.0)
    q_v = np.maximum(0.0, q_v)

    grid.fields["sea_surface_temperature_c"] = updated_sst.astype(np.float32)
    grid.fields["surface_temperature"] = np.where(
        ocean,
        updated_sst,
        grid.fields["surface_temperature"],
    ).astype(np.float32)
    grid.fields["temperature"] = updated_air.astype(np.float32)
    grid.fields["water_vapor_specific_humidity"] = q_v.astype(np.float32)
    grid.fields["evaporation_flux_kg_m2_s"] = fluxes["evaporation"].astype(np.float32)

    areas = _ocean_area_weights(settings)
    total_evaporated = float(
        np.sum(fluxes["evaporation"][ocean] * areas[ocean] * seconds)
    )
    maximum_anomaly = float(np.max((updated_sst - baseline)[ocean]))
    maximum_evaporation = float(np.max(fluxes["evaporation"][ocean]))
    if diagnostics is not None:
        diagnostics["total_evaporated_water_kg"] = diagnostics.get(
            "total_evaporated_water_kg", 0.0
        ) + total_evaporated
        diagnostics["maximum_sst_anomaly_c"] = max(
            diagnostics.get("maximum_sst_anomaly_c", -math.inf),
            maximum_anomaly,
        )
        diagnostics["maximum_evaporation_kg_m2_s"] = max(
            diagnostics.get("maximum_evaporation_kg_m2_s", 0.0),
            maximum_evaporation,
        )
    return {
        "mean_sst_c": ocean_weighted_mean(updated_sst, static, settings),
        "maximum_sst_anomaly_c": maximum_anomaly,
        "maximum_evaporation_kg_m2_s": maximum_evaporation,
        "total_evaporated_water_kg": total_evaporated,
    }


def _resample_equirectangular(values, source_width, source_height, target_width, target_height):
    """Bilinearly resample cell-centred global data with wrapped longitude."""
    source = np.asarray(values, dtype=np.float64).reshape(source_height, source_width)
    target_x, target_y = np.meshgrid(
        np.arange(target_width, dtype=np.float64),
        np.arange(target_height, dtype=np.float64),
    )
    source_x = (target_x + 0.5) * source_width / target_width - 0.5
    source_y = np.clip(
        (target_y + 0.5) * source_height / target_height - 0.5,
        0.0,
        source_height - 1.0,
    )
    x0_unwrapped = np.floor(source_x).astype(np.int32)
    x0 = x0_unwrapped % source_width
    x1 = (x0 + 1) % source_width
    y0 = np.floor(source_y).astype(np.int32)
    y1 = np.minimum(source_height - 1, y0 + 1)
    tx = source_x - x0_unwrapped
    ty = source_y - y0
    top = source[y0, x0] * (1.0 - tx) + source[y0, x1] * tx
    bottom = source[y1, x0] * (1.0 - tx) + source[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).reshape(-1)


def _advance_ocean_on_boundary_grid(
    grid,
    static,
    settings,
    forcing,
    *,
    start_world_minutes,
    end_world_minutes,
    boundary_width,
    boundary_height,
    diagnostics,
):
    """Run the boundary-layer surrogate coarsely while retaining fine SST detail."""
    # Local imports avoid the simulation -> ocean module cycle at import time.
    from .config import AtmosphericSettings
    from .simulation import initialize_atmosphere
    from .static_grid import cached_static_world_grid

    boundary_settings = AtmosphericSettings(
        width=boundary_width,
        height=boundary_height,
        step_minutes=settings.step_minutes,
        world_seed=settings.world_seed,
        world_circumference_km=settings.world_circumference_km,
        ocean_temperature_c=settings.ocean_temperature_c,
        parameters=settings.parameters,
    )
    boundary_static = cached_static_world_grid(boundary_settings)
    boundary_grid, _ = initialize_atmosphere(
        boundary_settings,
        static=boundary_static,
        world_minutes=start_world_minutes,
        forcing=forcing,
    )
    for field in (
        "temperature",
        "water_vapor_specific_humidity",
        "cloud_condensate_specific_humidity",
        "circulation_pressure_hpa",
        "pressure_hpa",
        "wind_u",
        "wind_v",
        "cloud_cover",
        "precipitation_rate",
    ):
        boundary_grid.fields[field] = _resample_equirectangular(
            grid.fields[field],
            settings.width,
            settings.height,
            boundary_width,
            boundary_height,
        ).astype(np.float32)

    fine_baseline = ocean_baseline_sst(static, settings)
    fine_start_mean = ocean_weighted_mean(
        grid.fields["sea_surface_temperature_c"],
        static,
        settings,
    )
    boundary_baseline = ocean_baseline_sst(boundary_static, boundary_settings)
    initial_fine_anomaly = (
        grid.fields["sea_surface_temperature_c"].astype(np.float64) - fine_baseline
    )
    initial_boundary_anomaly = _resample_equirectangular(
        initial_fine_anomaly,
        settings.width,
        settings.height,
        boundary_width,
        boundary_height,
    )
    boundary_sst = boundary_baseline + initial_boundary_anomaly
    boundary_ocean = np.asarray(boundary_static.is_ocean, dtype=np.bool_)
    boundary_grid.fields["sea_surface_temperature_c"] = boundary_sst.astype(np.float32)
    boundary_grid.fields["surface_temperature"] = np.where(
        boundary_ocean,
        boundary_sst,
        boundary_grid.fields["surface_temperature"],
    ).astype(np.float32)

    summary = advance_ocean_fast_forward(
        boundary_grid,
        boundary_static,
        boundary_settings,
        forcing,
        start_world_minutes=start_world_minutes,
        end_world_minutes=end_world_minutes,
        diagnostics=diagnostics,
    )
    for field in (
        "temperature",
        "water_vapor_specific_humidity",
        "cloud_condensate_specific_humidity",
        "circulation_pressure_hpa",
        "pressure_hpa",
        "wind_u",
        "wind_v",
        "cloud_cover",
    ):
        grid.fields[field] = _resample_equirectangular(
            boundary_grid.fields[field],
            boundary_width,
            boundary_height,
            settings.width,
            settings.height,
        ).astype(np.float32)
    # The skipped interval yields a climate precipitation integral, not a
    # precise event at the exact-spinup boundary.
    grid.fields["precipitation_rate"].fill(0.0)
    grid.fields["condensation_rate_kg_m2_s"].fill(0.0)
    grid.fields["latent_heating_rate_w_m2"].fill(0.0)
    final_boundary_anomaly = (
        boundary_grid.fields["sea_surface_temperature_c"].astype(np.float64)
        - boundary_baseline
    )
    upsampled_initial = _resample_equirectangular(
        initial_boundary_anomaly,
        boundary_width,
        boundary_height,
        settings.width,
        settings.height,
    )
    upsampled_final = _resample_equirectangular(
        final_boundary_anomaly,
        boundary_width,
        boundary_height,
        settings.width,
        settings.height,
    )
    duration_seconds = max(0.0, end_world_minutes - start_world_minutes) * 60.0
    deep_seconds = max(
        1.0,
        settings.value("ocean_deep_relaxation_days") * 86_400.0,
    )
    retained_residual = (
        initial_fine_anomaly - upsampled_initial
    ) * math.exp(-duration_seconds / deep_seconds)
    fine_ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    final_sst = fine_baseline + upsampled_final + retained_residual
    final_sst = np.clip(
        final_sst,
        settings.value("ocean_min_sst_c"),
        settings.value("ocean_max_sst_c"),
    )
    grid.fields["sea_surface_temperature_c"] = np.where(
        fine_ocean,
        final_sst,
        grid.fields["sea_surface_temperature_c"],
    ).astype(np.float32)
    grid.fields["surface_temperature"] = np.where(
        fine_ocean,
        final_sst,
        grid.fields["surface_temperature"],
    ).astype(np.float32)
    summary.update(
        {
            "boundary_grid_width": boundary_width,
            "boundary_grid_height": boundary_height,
            "start_mean_sst_c": fine_start_mean,
            "end_mean_sst_c": ocean_weighted_mean(final_sst, static, settings),
            "maximum_sst_anomaly_c": float(
                np.max((final_sst - fine_baseline)[fine_ocean])
            ),
            "boundary_atmosphere_updated": True,
        }
    )
    return summary


def advance_ocean_fast_forward(
    grid,
    static,
    settings,
    forcing,
    *,
    start_world_minutes,
    end_world_minutes,
    diagnostics=None,
):
    """Advance only the slow SST state with bounded vectorized macro steps."""
    ocean = np.asarray(static.is_ocean, dtype=np.bool_)
    baseline = ocean_baseline_sst(static, settings)
    sst = grid.fields["sea_surface_temperature_c"].astype(np.float64).copy()
    start_mean = ocean_weighted_mean(sst, static, settings)
    duration = max(0, int(end_world_minutes) - int(start_world_minutes))
    if duration == 0 or not np.any(ocean):
        return {
            "macro_steps": 0,
            "start_mean_sst_c": start_mean,
            "end_mean_sst_c": start_mean,
            "maximum_sst_anomaly_c": (
                None if not np.any(ocean) else float(np.max((sst - baseline)[ocean]))
            ),
            "maximum_evaporation_kg_m2_s": 0.0,
            "total_evaporated_water_kg": 0.0,
            "integrated_macro_precipitation_mass_kg": 0.0,
            "boundary_atmosphere_updated": False,
        }

    use_boundary_layer = (
        settings.value("fast_forward_ocean_boundary_layer_enabled") >= 0.5
    )
    boundary_width = min(
        settings.width,
        max(4, int(settings.value("fast_forward_boundary_grid_max_width"))),
    )
    boundary_height = min(
        settings.height,
        max(2, int(settings.value("fast_forward_boundary_grid_max_height"))),
    )
    if use_boundary_layer and (
        boundary_width < settings.width or boundary_height < settings.height
    ):
        return _advance_ocean_on_boundary_grid(
            grid,
            static,
            settings,
            forcing,
            start_world_minutes=start_world_minutes,
            end_world_minutes=end_world_minutes,
            boundary_width=boundary_width,
            boundary_height=boundary_height,
            diagnostics=diagnostics,
        )

    preferred = max(
        1.0,
        settings.value(
            "fast_forward_boundary_substep_minutes"
            if use_boundary_layer
            else "fast_forward_ocean_step_minutes"
        ),
    )
    maximum_steps = max(
        1,
        int(
            settings.value(
                "fast_forward_boundary_max_steps"
                if use_boundary_layer
                else "fast_forward_ocean_max_steps"
            )
        ),
    )
    steps = min(maximum_steps, max(1, math.ceil(duration / preferred)))
    minutes_per_step = duration / steps
    total_evaporated = 0.0
    total_precipitated = 0.0
    maximum_anomaly = -math.inf
    maximum_evaporation = 0.0
    areas = _ocean_area_weights(settings)
    geometry = geometry_for(settings)
    wind_iterations = max(
        0,
        int(settings.value("fast_forward_wind_spinup_iterations")),
    )
    wind_updates = max(
        1,
        int(settings.value("fast_forward_wind_updates_per_substep")),
    )
    macro_wind_grid = grid.clone() if use_boundary_layer or wind_iterations else None
    if use_boundary_layer:
        air_temperature = grid.fields["temperature"].astype(np.float64).copy()
        pressure = grid.fields["pressure_hpa"].astype(np.float64).copy()
        q_air = grid.fields["water_vapor_specific_humidity"].astype(np.float64).copy()
        q_cloud = grid.fields["cloud_condensate_specific_humidity"].astype(
            np.float64
        ).copy()
        wind_u = grid.fields["wind_u"].astype(np.float32).copy()
        wind_v = grid.fields["wind_v"].astype(np.float32).copy()
    for step in range(steps):
        midpoint = start_world_minutes + (step + 0.5) * minutes_per_step
        substep_end = start_world_minutes + (step + 1.0) * minutes_per_step
        if (
            use_boundary_layer
            and minutes_per_step <= settings.step_minutes
            and hasattr(forcing, "forcing_grid")
        ):
            exact_forcing = forcing.forcing_grid(geometry, substep_end)
            star = exact_forcing.stellar_flux_anomaly_w_m2
            ympha = exact_forcing.ympha_temperature_anomaly_c
            temperature_adjustment = exact_forcing.total_radiative_anomaly_c
        elif hasattr(forcing, "ocean_macro_forcing_grid"):
            macro_forcing = forcing.ocean_macro_forcing_grid(
                geometry,
                midpoint,
                minutes_per_step,
                ympha_samples=int(
                    settings.value(
                        "fast_forward_boundary_forcing_samples"
                        if use_boundary_layer
                        else "fast_forward_forcing_samples"
                    )
                ),
                legacy_rotation_mean=(
                    settings.value("fast_forward_legacy_rotation_mean") >= 0.5
                ),
            )
            star = macro_forcing.stellar_flux_anomaly_w_m2
            ympha = macro_forcing.ympha_temperature_anomaly_c
            temperature_adjustment = macro_forcing.air_temperature_anomaly_c
        else:
            star = np.zeros(grid.size, dtype=np.float64)
            ympha = np.zeros(grid.size, dtype=np.float64)
            temperature_adjustment = np.zeros(grid.size, dtype=np.float64)
        if use_boundary_layer:
            air_temperature = _advect_boundary_scalar(
                air_temperature,
                wind_u,
                wind_v,
                geometry,
                settings,
                minutes_per_step,
            )
            q_air = _advect_boundary_scalar(
                q_air,
                wind_u,
                wind_v,
                geometry,
                settings,
                minutes_per_step,
            )
            q_cloud = _advect_boundary_scalar(
                q_cloud,
                wind_u,
                wind_v,
                geometry,
                settings,
                minutes_per_step,
            )
            land = ~ocean
            land_target = np.asarray(static.mean_temperature, dtype=np.float64) + np.asarray(
                temperature_adjustment,
                dtype=np.float64,
            )
            step_scale = minutes_per_step / settings.step_minutes
            land_exchange = np.clip(
                settings.value("land_temperature_exchange"),
                0.0,
                1.0,
            )
            effective_land_exchange = 1.0 - (1.0 - land_exchange) ** step_scale
            air_temperature[land] += (
                land_target[land] - air_temperature[land]
            ) * effective_land_exchange
            macro_wind_grid.fields["temperature"] = air_temperature.astype(np.float32)
            pressure_updates = max(1, int(round(step_scale)))
            for update in range(pressure_updates):
                pressure = solve_pressure(
                    macro_wind_grid,
                    static,
                    settings,
                    max(
                        0,
                        int(substep_end // settings.step_minutes)
                        - pressure_updates
                        + update
                        + 1,
                    ),
                )
                macro_wind_grid.fields["pressure_hpa"] = pressure
            macro_wind_grid.fields["wind_u"] = wind_u
            macro_wind_grid.fields["wind_v"] = wind_v
            for _iteration in range(wind_updates):
                wind_u, wind_v = solve_wind(
                    macro_wind_grid,
                    static,
                    settings,
                    diagnostics=diagnostics,
                )
                macro_wind_grid.fields["wind_u"] = wind_u
                macro_wind_grid.fields["wind_v"] = wind_v
            wind = np.maximum(
                np.hypot(wind_u, wind_v),
                settings.value("fast_forward_minimum_effective_wind_m_s"),
            )
        else:
            air_temperature = (
                np.asarray(static.mean_temperature, dtype=np.float64)
                + np.asarray(temperature_adjustment, dtype=np.float64)
            )
            mean_sst = ocean_weighted_mean(sst, static, settings)
            mean_radiative_adjustment = ocean_weighted_mean(
                temperature_adjustment,
                static,
                settings,
            )
            mixed_air_temperature = (
                None
                if mean_sst is None or mean_radiative_adjustment is None
                else mean_sst + mean_radiative_adjustment
            )
            atmospheric_mixing = np.clip(
                settings.value("fast_forward_atmospheric_heat_mixing"),
                0.0,
                1.0,
            )
            if mixed_air_temperature is not None:
                air_temperature = np.where(
                    ocean,
                    (1.0 - atmospheric_mixing) * air_temperature
                    + atmospheric_mixing * mixed_air_temperature,
                    air_temperature,
                )
            air_temperature += np.where(
                ocean,
                settings.value("fast_forward_ocean_air_sst_coupling")
                * (sst - baseline),
                0.0,
            )
            pressure = grid.fields["pressure_hpa"].astype(np.float64).copy()
            initial_rh = np.where(
                ocean,
                settings.value("initial_ocean_humidity"),
                settings.value("initial_land_humidity"),
            )
            q_air = specific_humidity_from_relative_humidity(
                initial_rh,
                air_temperature,
                pressure,
                latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
                diagnostics=diagnostics,
            )
            if macro_wind_grid is not None:
                macro_wind_grid.fields["temperature"] = air_temperature.astype(np.float32)
                macro_wind_grid.fields["pressure_hpa"] = pressure.astype(np.float32)
                for _iteration in range(wind_iterations):
                    wind_u, wind_v = solve_wind(
                        macro_wind_grid,
                        static,
                        settings,
                        diagnostics=diagnostics,
                    )
                    macro_wind_grid.fields["wind_u"] = wind_u
                    macro_wind_grid.fields["wind_v"] = wind_v
                wind = np.maximum(
                    np.hypot(wind_u, wind_v),
                    settings.value("fast_forward_ocean_wind_m_s"),
                )
            else:
                wind = np.full(
                    grid.size,
                    settings.value("fast_forward_ocean_wind_m_s"),
                )
        fluxes = _ocean_flux_components(
            sst,
            baseline,
            air_temperature,
            pressure,
            q_air,
            wind,
            static,
            settings,
            stellar_flux_anomaly_w_m2=star,
            ympha_temperature_anomaly_c=ympha,
            diagnostics=diagnostics,
        )
        seconds = minutes_per_step * 60.0
        sst = _update_sst(
            sst,
            fluxes,
            static,
            settings,
            seconds,
            diagnostics=diagnostics,
            cap_step_scale=minutes_per_step / settings.step_minutes,
            analytic_deep_relaxation=(
                settings.value("fast_forward_analytic_deep_relaxation") >= 0.5
            ),
        )
        if use_boundary_layer:
            air_mass = air_column_mass_kg_m2(pressure, settings)
            step_scale = minutes_per_step / settings.step_minutes
            air_change = (
                fluxes["sensible"]
                * seconds
                / (settings.value("air_heat_capacity_j_kg_k") * air_mass)
            )
            maximum_air_change = (
                settings.value("air_max_sensible_change_per_step_c") * step_scale
            )
            air_temperature += np.where(
                ocean,
                np.clip(air_change, -maximum_air_change, maximum_air_change),
                0.0,
            )
            q_change = fluxes["evaporation"] * seconds / air_mass
            maximum_q_change = (
                settings.value("max_specific_humidity_change_per_step") * step_scale
            )
            q_air += np.where(ocean, np.minimum(q_change, maximum_q_change), 0.0)
            macro_wind_grid.fields["temperature"] = air_temperature.astype(np.float32)
            macro_wind_grid.fields["water_vapor_specific_humidity"] = q_air.astype(
                np.float32
            )
            macro_wind_grid.fields["cloud_condensate_specific_humidity"] = (
                q_cloud.astype(np.float32)
            )
            macro_wind_grid.fields["pressure_hpa"] = np.asarray(
                pressure, dtype=np.float32
            )
            macro_wind_grid.fields["wind_u"] = wind_u
            macro_wind_grid.fields["wind_v"] = wind_v
            apply_orographic_temperature_tendency(
                macro_wind_grid,
                static,
                settings,
                diagnostics=diagnostics,
            )
            adjusted = saturation_adjustment(
                macro_wind_grid.fields["temperature"],
                pressure,
                q_air,
                q_cloud,
                settings,
                diagnostics=diagnostics,
                air_mass_kg_m2_values=air_mass,
                cell_areas_m2=areas,
            )
            air_temperature = adjusted["temperature"]
            q_air = adjusted["q_v"]
            q_cloud = adjusted["q_c"]
            fallout = precipitation_fallout(
                q_cloud,
                pressure,
                air_temperature,
                settings,
                timestep_seconds=seconds,
                diagnostics=diagnostics,
                air_mass_kg_m2_values=air_mass,
                cell_areas_m2=areas,
                include_phase_partition=False,
            )
            q_cloud = fallout["q_c"]
            total_precipitated += float(
                np.sum(fallout["rate_kg_m2_s"] * areas * seconds)
            )
            macro_wind_grid.fields["temperature"] = air_temperature.astype(np.float32)
            macro_wind_grid.fields["water_vapor_specific_humidity"] = q_air.astype(
                np.float32
            )
            macro_wind_grid.fields["cloud_condensate_specific_humidity"] = (
                q_cloud.astype(np.float32)
            )
            macro_wind_grid.fields["cloud_cover"] = cloud_cover_from_condensate(
                q_cloud,
                pressure,
                settings,
            ).astype(np.float32)
            macro_wind_grid.fields["precipitation_rate"] = fallout[
                "rate_kg_m2_s"
            ].astype(np.float32)
            pressure = solve_pressure(
                macro_wind_grid,
                static,
                settings,
                max(0, int(substep_end // settings.step_minutes)),
                diagnostics=diagnostics,
            )
            macro_wind_grid.fields["pressure_hpa"] = pressure
        total_evaporated += float(
            np.sum(fluxes["evaporation"][ocean] * areas[ocean] * seconds)
        )
        maximum_evaporation = max(
            maximum_evaporation,
            float(np.max(fluxes["evaporation"][ocean])),
        )
        maximum_anomaly = max(maximum_anomaly, float(np.max((sst - baseline)[ocean])))

    grid.fields["sea_surface_temperature_c"] = sst.astype(np.float32)
    grid.fields["surface_temperature"] = np.where(
        ocean,
        sst,
        grid.fields["surface_temperature"],
    ).astype(np.float32)
    if use_boundary_layer:
        grid.fields["temperature"] = air_temperature.astype(np.float32)
        grid.fields["water_vapor_specific_humidity"] = q_air.astype(np.float32)
        grid.fields["cloud_condensate_specific_humidity"] = q_cloud.astype(np.float32)
        grid.fields["circulation_pressure_hpa"] = macro_wind_grid.fields[
            "circulation_pressure_hpa"
        ].astype(np.float32)
        grid.fields["pressure_hpa"] = np.asarray(pressure, dtype=np.float32)
        grid.fields["wind_u"] = wind_u.astype(np.float32)
        grid.fields["wind_v"] = wind_v.astype(np.float32)
        grid.fields["cloud_cover"] = cloud_cover_from_condensate(
            q_cloud,
            pressure,
            settings,
        ).astype(np.float32)
        grid.fields["precipitation_rate"].fill(0.0)
        grid.fields["condensation_rate_kg_m2_s"].fill(0.0)
        grid.fields["latent_heating_rate_w_m2"].fill(0.0)
    return {
        "macro_steps": steps,
        "start_mean_sst_c": start_mean,
        "end_mean_sst_c": ocean_weighted_mean(sst, static, settings),
        "maximum_sst_anomaly_c": maximum_anomaly,
        "maximum_evaporation_kg_m2_s": maximum_evaporation,
        "total_evaporated_water_kg": total_evaporated,
        "integrated_macro_precipitation_mass_kg": total_precipitated,
        "boundary_atmosphere_updated": use_boundary_layer,
    }


def cell_ocean_diagnostics(
    grid,
    static,
    settings,
    index,
    radiative_grid=None,
    *,
    point_sample=None,
):
    """Return diagnostics at a cell or at an already sampled Region point.

    Region weather uses bilinear interpolation for continuous fields.  When a
    point sample is supplied, diagnostics must use the exact same interpolation
    instead of silently comparing the WeatherState with one nearest cell.
    Surface and biome ownership remain nearest-cell by design.  Elevation is a
    continuous local field and surface pressure is hydrostatically re-derived
    at that same elevation by the point sampler.
    """

    from .circulation import circulation_diagnostics

    def continuous(field):
        if point_sample is not None:
            return float(point_sample.values[field])
        return float(grid.fields[field][index])

    def diagnostic_value(values):
        if point_sample is None:
            return float(values[index])
        x = point_sample.grid_x
        y = point_sample.grid_y
        x0 = int(np.floor(x))
        y0 = int(np.floor(y))
        x1 = (x0 + 1) % grid.width
        y1 = min(grid.height - 1, y0 + 1)
        tx = x - x0
        ty = y - y0
        top = values[grid.index(x0, y0)] * (1.0 - tx) + values[
            grid.index(x1, y0)
        ] * tx
        bottom = values[grid.index(x0, y1)] * (1.0 - tx) + values[
            grid.index(x1, y1)
        ] * tx
        return float(top * (1.0 - ty) + bottom * ty)

    temperature = continuous("temperature")
    pressure = continuous("pressure_hpa")
    circulation_pressure = continuous("circulation_pressure_hpa")
    q_v = continuous("water_vapor_specific_humidity")
    q_c = continuous("cloud_condensate_specific_humidity")
    q_sat = float(
        saturation_specific_humidity(
            temperature,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
    )
    vapor_pressure = float(vapor_pressure_from_specific_humidity(q_v, pressure))
    saturation_pressure = float(
        saturation_vapor_pressure_pa(
            temperature,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
    )
    wind_u = continuous("wind_u")
    wind_v = continuous("wind_v")
    wind_speed = float(np.hypot(wind_u, wind_v))
    rain_fraction, snow_fraction = rain_and_snow_fraction(temperature, settings)
    precipitation_flux = max(0.0, continuous("precipitation_rate"))
    circulation = circulation_diagnostics(grid, static, settings)
    nearest_elevation = float(static.elevation[index])
    elevation = (
        nearest_elevation
        if point_sample is None
        else float(point_sample.elevation_m)
    )
    is_ocean = (
        bool(static.is_ocean[index])
        if point_sample is None
        else bool(point_sample.is_ocean)
    )
    result = {
        "sampling_method": (
            "nearest_cell"
            if point_sample is None
            else "bilinear_primitives_hydrostatic_pressure"
        ),
        "sample_grid_x": None if point_sample is None else point_sample.grid_x,
        "sample_grid_y": None if point_sample is None else point_sample.grid_y,
        "nearest_cell_index": index,
        "local_elevation_m": elevation,
        "nearest_elevation_m": nearest_elevation,
        "interpolated_grid_surface_pressure_hpa": (
            pressure
            if point_sample is None
            else point_sample.interpolated_grid_surface_pressure_hpa
        ),
        "temperature_c": temperature,
        "surface_pressure_hpa": pressure,
        "circulation_pressure_hpa": circulation_pressure,
        "circulation_pressure_anomaly_hpa": (
            circulation_pressure
            - settings.value("circulation_reference_pressure_hpa")
        ),
        "wind_u_m_s": wind_u,
        "wind_v_m_s": wind_v,
        "wind_speed_m_s": wind_speed,
        "pressure_gradient_acceleration_m_s2": float(
            np.hypot(
                diagnostic_value(circulation["pressure_acceleration_u_m_s2"]),
                diagnostic_value(circulation["pressure_acceleration_v_m_s2"]),
            )
        ),
        "coriolis_parameter_s_1": diagnostic_value(
            circulation["coriolis_parameter_s_1"]
        ),
        "coriolis_acceleration_m_s2": float(
            np.hypot(
                diagnostic_value(circulation["coriolis_acceleration_u_m_s2"]),
                diagnostic_value(circulation["coriolis_acceleration_v_m_s2"]),
            )
        ),
        "surface_drag_acceleration_m_s2": float(
            np.hypot(
                diagnostic_value(circulation["surface_drag_acceleration_u_m_s2"]),
                diagnostic_value(circulation["surface_drag_acceleration_v_m_s2"]),
            )
        ),
        "divergence_s_1": diagnostic_value(circulation["divergence_s_1"]),
        "convergence_s_1": diagnostic_value(circulation["convergence_s_1"]),
        "relative_vorticity_s_1": diagnostic_value(
            circulation["relative_vorticity_s_1"]
        ),
        "absolute_vorticity_s_1": diagnostic_value(
            circulation["absolute_vorticity_s_1"]
        ),
        "w_orographic_m_s": diagnostic_value(circulation["w_orographic_m_s"]),
        "w_convergence_m_s": diagnostic_value(circulation["w_convergence_m_s"]),
        "vertical_motion_proxy_m_s": diagnostic_value(
            circulation["vertical_motion_proxy_m_s"]
        ),
        "terrain_slope": diagnostic_value(circulation["terrain_slope"]),
        "terrain_ruggedness": diagnostic_value(circulation["terrain_ruggedness"]),
        "specific_humidity_g_kg": q_v * 1000.0,
        "saturation_specific_humidity_g_kg": q_sat * 1000.0,
        "cloud_condensate_specific_humidity_g_kg": q_c * 1000.0,
        "cloud_water_path_kg_m2": float(
            cloud_water_path_kg_m2(q_c, pressure, settings)
        ),
        "relative_humidity_percent": float(
            relative_humidity_percent(
                q_v,
                temperature,
                pressure,
                latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
            )
        ),
        "vapor_pressure_pa": vapor_pressure,
        "saturation_vapor_pressure_pa": saturation_pressure,
        "precipitation_mass_flux_kg_m2_s": precipitation_flux,
        "precipitation_rate_mm_h": precipitation_flux * 3600.0,
        "precipitation_amount_mm_per_step": (
            precipitation_flux * settings.step_minutes * 60.0
        ),
        "rain_fraction": float(rain_fraction),
        "snow_fraction": float(snow_fraction),
        "cloud_cover_fraction": continuous("cloud_cover"),
        "fog_potential": float(
            fog_potential(
                q_v,
                q_c,
                temperature,
                pressure,
                wind_speed,
                elevation,
                settings,
            )
        ),
        "condensation_rate_kg_m2_s": continuous(
            "condensation_rate_kg_m2_s"
        ),
        "latent_heating_rate_w_m2": continuous("latent_heating_rate_w_m2"),
        "is_ocean": is_ocean,
        "baseline_sst_c": None,
        "current_sst_c": None,
        "sst_anomaly_c": None,
        "stellar_ocean_anomaly_w_m2": 0.0,
        "sensible_heat_w_m2": 0.0,
        "latent_heat_w_m2": 0.0,
        "evaporation_kg_m2_day": 0.0,
    }
    if not is_ocean:
        return result
    baseline = ocean_baseline_sst(static, settings)
    sst = grid.fields["sea_surface_temperature_c"].astype(np.float64)
    wind = np.hypot(grid.fields["wind_u"], grid.fields["wind_v"]).astype(np.float64)
    star = (
        np.zeros(grid.size)
        if radiative_grid is None
        else radiative_grid.stellar_flux_anomaly_w_m2
    )
    ympha = (
        np.zeros(grid.size)
        if radiative_grid is None
        else radiative_grid.ympha_temperature_anomaly_c
    )
    fluxes = _ocean_flux_components(
        sst,
        baseline,
        grid.fields["temperature"],
        grid.fields["pressure_hpa"],
        grid.fields["water_vapor_specific_humidity"],
        wind,
        static,
        settings,
        stellar_flux_anomaly_w_m2=star,
        ympha_temperature_anomaly_c=ympha,
    )
    result.update(
        {
            "baseline_sst_c": diagnostic_value(baseline),
            "current_sst_c": continuous("sea_surface_temperature_c"),
            "sst_anomaly_c": (
                continuous("sea_surface_temperature_c")
                - diagnostic_value(baseline)
            ),
            "stellar_ocean_anomaly_w_m2": diagnostic_value(fluxes["star"]),
            "sensible_heat_w_m2": diagnostic_value(fluxes["sensible"]),
            "latent_heat_w_m2": diagnostic_value(fluxes["latent"]),
            "evaporation_kg_m2_day": float(
                diagnostic_value(fluxes["evaporation"]) * 86_400.0
            ),
        }
    )
    return result
