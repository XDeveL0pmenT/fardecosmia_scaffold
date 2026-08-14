import numpy as np

from .advection import advect_heat_and_moisture
from .climatology import initial_relative_humidity_percent
from .deterministic import deterministic_signed_array
from .forcing import ZeroRadiativeForcing
from .grid import AtmosphericGrid
from .geometry import geometry_for
from .ocean import (
    air_column_mass_kg_m2,
    apply_ocean_surface_exchange,
    ocean_baseline_sst,
)
from .microphysics import (
    cloud_cover_from_condensate,
    precipitation_fallout,
    saturation_adjustment,
)
from .orography import apply_orographic_temperature_tendency
from .pressure import (
    initialize_pressure_fields,
    solve_pressure,
    surface_pressure_from_circulation,
)
from .static_grid import build_static_world_grid
from .surface_exchange import apply_surface_exchange, surface_temperature_target
from .thermodynamics import (
    relative_humidity_percent,
    saturation_specific_humidity,
    specific_humidity_from_relative_humidity,
)
from .wind import solve_wind


def apply_external_tendencies(grid, settings, tendencies=None):
    """Apply optional in-memory tendencies from a future orchestration layer.

    C4 itself never reads WorldEvent or catastrophe tables.  The small explicit
    boundary lets a later service contribute SI-rate arrays without coupling
    the solver core to database entities.
    """

    if tendencies is None:
        return
    seconds = settings.step_minutes * 60.0
    mapping = {
        "temperature_c_s": "temperature",
        "circulation_pressure_hpa_s": "circulation_pressure_hpa",
        "wind_u_m_s2": "wind_u",
        "wind_v_m_s2": "wind_v",
        "specific_humidity_s_1": "water_vapor_specific_humidity",
    }
    for tendency_name, field_name in mapping.items():
        values = tendencies.get(tendency_name)
        if values is None:
            continue
        field = grid.fields[field_name].astype(np.float64)
        tendency = np.asarray(values, dtype=np.float64)
        if tendency.size not in {1, grid.size}:
            raise ValueError(f"Неверный размер внешней тенденции {tendency_name}.")
        grid.fields[field_name] = (field + tendency * seconds).astype(np.float32)


def initialize_atmosphere(
    settings,
    *,
    static=None,
    world_data=None,
    world_minutes=0,
    forcing=None,
    sea_surface_temperature=None,
    fast_forward_moisture=False,
    restart_grid=None,
):
    static = static or build_static_world_grid(settings, world_data=world_data)
    if restart_grid is not None:
        if (restart_grid.width, restart_grid.height) != (settings.width, settings.height):
            raise ValueError("Размер restart grid не совпадает с конфигурацией атмосферы.")
        return restart_grid.clone(), static
    grid = AtmosphericGrid.empty(settings.width, settings.height)
    initial_step = world_minutes // settings.step_minutes
    indices = np.arange(grid.size, dtype=np.uint64)
    noise = deterministic_signed_array(
        settings.world_seed,
        initial_step,
        indices,
        0,
    ) * settings.value("initial_temperature_noise_c")
    mean_temperature = np.asarray(static.mean_temperature, dtype=np.float64)
    forcing = forcing or ZeroRadiativeForcing()
    ocean_mask = np.asarray(static.is_ocean, dtype=np.bool_)
    humidity = initial_relative_humidity_percent(ocean_mask, settings)
    radiative_grid = (
        forcing.forcing_grid(geometry_for(settings), world_minutes)
        if hasattr(forcing, "forcing_grid")
        else None
    )
    surface_temperature = surface_temperature_target(
        static,
        settings,
        world_minutes=world_minutes,
        forcing=forcing,
        radiative_grid=radiative_grid,
    )
    surface_baseline = mean_temperature.copy()
    radiative_adjustment = surface_temperature - surface_baseline
    temperature = mean_temperature + radiative_adjustment + noise
    provisional_circulation, pressure = initialize_pressure_fields(
        temperature,
        mean_temperature,
        np.zeros(grid.size, dtype=np.float64),
        static.elevation,
        settings,
    )
    baseline_sst = ocean_baseline_sst(static, settings)
    if sea_surface_temperature is None:
        sst = baseline_sst
    else:
        sst = np.asarray(sea_surface_temperature, dtype=np.float64).reshape(-1)
        if sst.size != grid.size:
            raise ValueError("Размер переданного SST state не совпадает с атмосферной сеткой.")
        sst = np.where(ocean_mask, sst, baseline_sst)
    surface_temperature = np.where(ocean_mask, sst, surface_temperature)
    q_v = specific_humidity_from_relative_humidity(
        humidity,
        temperature,
        pressure,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
    )
    if fast_forward_moisture and np.any(ocean_mask):
        q_surface = saturation_specific_humidity(
            sst,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
        blend = np.clip(settings.value("fast_forward_ocean_humidity_blend"), 0.0, 1.0)
        q_v += np.where(ocean_mask, np.maximum(0.0, q_surface - q_v) * blend, 0.0)
    q_v = np.clip(q_v, 0.0, settings.value("maximum_specific_humidity"))
    adjusted = saturation_adjustment(
        temperature,
        pressure,
        q_v,
        np.zeros(grid.size, dtype=np.float64),
        settings,
    )
    temperature = adjusted["temperature"]
    q_v = adjusted["q_v"]
    q_c = adjusted["q_c"]
    circulation_pressure, pressure = initialize_pressure_fields(
        temperature,
        mean_temperature,
        q_v,
        static.elevation,
        settings,
    )
    grid.fields["temperature"] = temperature.astype(np.float32)
    grid.fields["water_vapor_specific_humidity"] = q_v.astype(np.float32)
    grid.fields["cloud_condensate_specific_humidity"] = q_c.astype(np.float32)
    grid.fields["circulation_pressure_hpa"] = circulation_pressure
    grid.fields["pressure_hpa"] = pressure
    grid.fields["wind_u"].fill(0.0)
    grid.fields["wind_v"].fill(0.0)
    grid.fields["cloud_cover"] = cloud_cover_from_condensate(
        q_c,
        pressure,
        settings,
    ).astype(np.float32)
    grid.fields["precipitation_rate"].fill(0.0)
    grid.fields["condensation_rate_kg_m2_s"].fill(0.0)
    grid.fields["latent_heating_rate_w_m2"].fill(0.0)
    grid.fields["surface_temperature"] = surface_temperature.astype(np.float32)
    grid.fields["sea_surface_temperature_c"] = sst.astype(np.float32)
    grid.fields["evaporation_flux_kg_m2_s"].fill(0.0)
    return grid, static


def derive_relative_humidity_and_apply_safety(grid, settings, diagnostics=None):
    temperature = grid.fields["temperature"].astype(np.float64)
    pressure = grid.fields["pressure_hpa"].astype(np.float64)
    q_v = grid.fields["water_vapor_specific_humidity"].astype(np.float64)
    q_sat = saturation_specific_humidity(
        temperature,
        pressure,
        latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        diagnostics=diagnostics,
    )
    q_limit = np.minimum(
        settings.value("maximum_specific_humidity"),
        settings.value("supersaturation_emergency_ratio") * q_sat,
    )
    excess = np.maximum(0.0, q_v - q_limit)
    capped = excess > 0.0
    if diagnostics is not None and np.any(capped):
        diagnostics["supersaturation_emergency_clamp_hits"] = diagnostics.get(
            "supersaturation_emergency_clamp_hits", 0
        ) + int(np.count_nonzero(capped))
        air_mass = air_column_mass_kg_m2(pressure, settings)
        diagnostics["removed_excess_vapor_kg_m2"] = diagnostics.get(
            "removed_excess_vapor_kg_m2", 0.0
        ) + float(np.sum(excess[capped] * air_mass[capped]))
    q_v = np.clip(np.minimum(q_v, q_limit), 0.0, settings.value("maximum_specific_humidity"))
    grid.fields["water_vapor_specific_humidity"] = q_v.astype(np.float32)
    return np.clip(
        relative_humidity_percent(
            q_v,
            temperature,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        ),
        0.0,
        settings.value("supersaturation_emergency_ratio") * 100.0,
    )


def simulate_step(
    previous,
    static,
    settings,
    *,
    step_index,
    world_minutes,
    forcing=None,
    diagnostics=None,
    external_tendencies=None,
):
    if (previous.width, previous.height) != (settings.width, settings.height):
        raise ValueError("Размер снимка не совпадает с конфигурацией атмосферы.")
    if (static.width, static.height) != (settings.width, settings.height):
        raise ValueError("Размер статической сетки не совпадает с атмосферой.")

    result = previous.clone()
    advected = advect_heat_and_moisture(previous, settings)
    for name, values in advected.items():
        result.fields[name] = values
    apply_external_tendencies(result, settings, external_tendencies)
    result.fields["precipitation_rate"] = np.zeros(result.size, dtype=np.float32)

    forcing = forcing or ZeroRadiativeForcing()
    radiative_grid = (
        forcing.forcing_grid(geometry_for(settings), world_minutes)
        if hasattr(forcing, "forcing_grid")
        else None
    )

    apply_surface_exchange(
        result,
        static,
        settings,
        world_minutes=world_minutes,
        forcing=forcing,
        radiative_grid=radiative_grid,
    )
    apply_ocean_surface_exchange(
        result,
        static,
        settings,
        radiative_grid=radiative_grid,
        diagnostics=diagnostics,
    )
    result.fields["pressure_hpa"] = solve_pressure(
        result,
        static,
        settings,
        step_index,
        diagnostics=diagnostics,
    )
    wind_u, wind_v = solve_wind(result, static, settings, diagnostics=diagnostics)
    result.fields["wind_u"] = wind_u
    result.fields["wind_v"] = wind_v
    apply_orographic_temperature_tendency(
        result,
        static,
        settings,
        diagnostics=diagnostics,
    )
    air_mass_column = air_column_mass_kg_m2(
        result.fields["pressure_hpa"],
        settings,
    )
    adjusted = saturation_adjustment(
        result.fields["temperature"],
        result.fields["pressure_hpa"],
        result.fields["water_vapor_specific_humidity"],
        result.fields["cloud_condensate_specific_humidity"],
        settings,
        diagnostics=diagnostics,
        air_mass_kg_m2_values=air_mass_column,
        cell_areas_m2=geometry_for(settings).cell_areas_m2,
    )
    air_mass = air_mass_column
    seconds = settings.step_minutes * 60.0
    condensation_rate = adjusted["condensation_delta_q"] * air_mass / seconds
    cloud_evaporation_rate = adjusted["cloud_evaporation_delta_q"] * air_mass / seconds
    result.fields["condensation_rate_kg_m2_s"] = condensation_rate.astype(np.float32)
    result.fields["latent_heating_rate_w_m2"] = (
        settings.value("latent_heat_vaporization_j_kg")
        * (condensation_rate - cloud_evaporation_rate)
    ).astype(np.float32)
    result.fields["temperature"] = adjusted["temperature"].astype(np.float32)
    result.fields["water_vapor_specific_humidity"] = adjusted["q_v"].astype(np.float32)
    result.fields["cloud_condensate_specific_humidity"] = adjusted["q_c"].astype(np.float32)
    # Surface pressure is diagnostic.  Refresh it after latent heating so the
    # persisted field matches the final T/q state without advancing the
    # prognostic circulation pressure a second time.
    result.fields["pressure_hpa"] = surface_pressure_from_circulation(
        result.fields["circulation_pressure_hpa"],
        result.fields["temperature"],
        result.fields["water_vapor_specific_humidity"],
        static.elevation,
        settings,
    ).astype(np.float32)
    fallout_air_mass = air_column_mass_kg_m2(
        result.fields["pressure_hpa"],
        settings,
    )

    fallout = precipitation_fallout(
        result.fields["cloud_condensate_specific_humidity"],
        result.fields["pressure_hpa"],
        result.fields["temperature"],
        settings,
        diagnostics=diagnostics,
        air_mass_kg_m2_values=fallout_air_mass,
        cell_areas_m2=geometry_for(settings).cell_areas_m2,
        include_phase_partition=False,
    )
    result.fields["cloud_condensate_specific_humidity"] = fallout["q_c"].astype(np.float32)
    result.fields["precipitation_rate"] = fallout["rate_kg_m2_s"].astype(np.float32)
    result.fields["cloud_cover"] = cloud_cover_from_condensate(
        fallout["q_c"],
        result.fields["pressure_hpa"],
        settings,
    ).astype(np.float32)
    derive_relative_humidity_and_apply_safety(result, settings, diagnostics=diagnostics)

    for name, values in result.fields.items():
        if not np.isfinite(values).all():
            raise ValueError(f"Поле атмосферы {name} содержит неконечное значение.")
    return result
