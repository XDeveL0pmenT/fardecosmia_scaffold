import numpy as np

from .geometry import geometry_for


def solve_wind(grid, static, settings):
    pressure = grid.fields["pressure_hpa"].astype(np.float64)
    temperature = grid.fields["temperature"].astype(np.float64)
    previous_u = grid.fields["wind_u"].astype(np.float64)
    previous_v = grid.fields["wind_v"].astype(np.float64)
    geometry = geometry_for(settings)
    pressure_factor = settings.value("wind_pressure_factor")
    thermal_factor = settings.value("wind_thermal_factor")
    coriolis_factor = settings.value("coriolis_factor")
    blocking_factor = max(0.0, settings.value("terrain_blocking_per_1000m"))
    maximum = max(0.1, settings.value("max_wind_speed_m_s"))

    pressure_dx = (pressure[geometry.east] - pressure[geometry.west]) / 2.0
    pressure_dy_south = (
        pressure[geometry.south] - pressure[geometry.north]
    ) / 2.0
    temperature_dx = (
        temperature[geometry.east] - temperature[geometry.west]
    ) / 2.0
    temperature_dy_south = (
        temperature[geometry.south] - temperature[geometry.north]
    ) / 2.0

    retention = np.where(
        static.is_ocean,
        settings.value("ocean_wind_retention"),
        settings.value("land_wind_retention"),
    )
    u = previous_u * retention - pressure_dx * pressure_factor
    v = previous_v * retention + pressure_dy_south * pressure_factor
    u += temperature_dx * thermal_factor
    v -= temperature_dy_south * thermal_factor

    coriolis = coriolis_factor * geometry.sin_latitude
    rotated_u = u - coriolis * v
    rotated_v = v + coriolis * u
    u, v = rotated_u, rotated_v

    target_x = (geometry.flat_x + np.sign(u).astype(np.int32)) % grid.width
    target_y = np.clip(
        geometry.flat_y - np.sign(v).astype(np.int32),
        0,
        grid.height - 1,
    )
    target = target_y * grid.width + target_x
    elevation = np.asarray(static.elevation, dtype=np.float64)
    climb = np.maximum(0.0, elevation[target] - elevation)
    blocking = np.maximum(
        settings.value("minimum_terrain_wind_fraction"),
        1.0 - blocking_factor * climb / 1000.0,
    )
    u *= blocking
    v *= blocking

    speed = np.hypot(u, v)
    scale = np.ones_like(speed)
    too_fast = speed > maximum
    scale[too_fast] = maximum / speed[too_fast]
    return (u * scale).astype(np.float32), (v * scale).astype(np.float32)
