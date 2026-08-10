import math

from .advection import advect_heat_and_moisture
from .deterministic import deterministic_signed
from .forcing import ZeroRadiativeForcing
from .grid import AtmosphericGrid
from .orography import apply_orography_and_precipitation
from .pressure import pressure_for_cell, solve_pressure
from .static_grid import build_static_world_grid
from .surface_exchange import apply_surface_exchange
from .wind import solve_wind


def initialize_atmosphere(settings, *, static=None, world_data=None, world_minutes=0):
    static = static or build_static_world_grid(settings, world_data=world_data)
    grid = AtmosphericGrid.empty(settings.width, settings.height)
    ocean_temperature = None
    if any(static.is_ocean):
        ocean_temperature = settings.require_ocean_temperature()
    initial_step = world_minutes // settings.step_minutes
    for index in range(grid.size):
        noise = deterministic_signed(
            settings.world_seed,
            initial_step,
            index,
            0,
        ) * settings.value("initial_temperature_noise_c")
        temperature = static.mean_temperature[index] + noise
        humidity = settings.value(
            "initial_ocean_humidity" if static.is_ocean[index] else "initial_land_humidity"
        )
        surface_temperature = (
            ocean_temperature if static.is_ocean[index] else static.mean_temperature[index]
        )
        grid.fields["temperature"][index] = temperature
        grid.fields["relative_humidity"][index] = humidity
        grid.fields["pressure_hpa"][index] = pressure_for_cell(
            temperature,
            static.mean_temperature[index],
            static.elevation[index],
            settings,
        )
        grid.fields["wind_u"][index] = 0.0
        grid.fields["wind_v"][index] = 0.0
        cloud_threshold = settings.value("cloud_threshold_humidity")
        grid.fields["cloud_cover"][index] = max(
            0.0,
            min(1.0, (humidity - cloud_threshold) / max(1.0, 100.0 - cloud_threshold)),
        )
        grid.fields["water_content"][index] = humidity / 100.0
        grid.fields["precipitation_rate"][index] = 0.0
        grid.fields["surface_temperature"][index] = surface_temperature
    return grid, static


def simulate_step(
    previous,
    static,
    settings,
    *,
    step_index,
    world_minutes,
    forcing=None,
):
    if (previous.width, previous.height) != (settings.width, settings.height):
        raise ValueError("Размер снимка не совпадает с конфигурацией атмосферы.")
    if (static.width, static.height) != (settings.width, settings.height):
        raise ValueError("Размер статической сетки не совпадает с атмосферой.")

    result = previous.clone()
    advected = advect_heat_and_moisture(previous, settings)
    for name, values in advected.items():
        result.fields[name] = values
    result.fields["precipitation_rate"] = type(result.fields["precipitation_rate"])(
        "f",
        [0.0],
    ) * result.size

    apply_surface_exchange(
        result,
        static,
        settings,
        world_minutes=world_minutes,
        forcing=forcing or ZeroRadiativeForcing(),
    )
    result.fields["pressure_hpa"] = solve_pressure(
        result,
        static,
        settings,
        step_index,
    )
    wind_u, wind_v = solve_wind(result, static, settings)
    result.fields["wind_u"] = wind_u
    result.fields["wind_v"] = wind_v
    apply_orography_and_precipitation(result, static, settings)

    for name in result.fields:
        for value in result.fields[name]:
            if not math.isfinite(value):
                raise ValueError(f"Поле атмосферы {name} содержит неконечное значение.")
    return result
