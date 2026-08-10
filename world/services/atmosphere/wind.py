import math
from array import array


def solve_wind(grid, static, settings):
    pressure = grid.fields["pressure_hpa"]
    temperature = grid.fields["temperature"]
    previous_u = grid.fields["wind_u"]
    previous_v = grid.fields["wind_v"]
    result_u = array("f", [0.0]) * grid.size
    result_v = array("f", [0.0]) * grid.size
    pressure_factor = settings.value("wind_pressure_factor")
    thermal_factor = settings.value("wind_thermal_factor")
    coriolis_factor = settings.value("coriolis_factor")
    blocking_factor = max(0.0, settings.value("terrain_blocking_per_1000m"))
    maximum = max(0.1, settings.value("max_wind_speed_m_s"))

    for y in range(grid.height):
        latitude = static.latitude_at_row(y)
        coriolis = coriolis_factor * math.sin(math.radians(latitude))
        for x in range(grid.width):
            index = grid.index(x, y)
            west = grid.neighbor_index(x - 1, y)
            east = grid.neighbor_index(x + 1, y)
            north = grid.neighbor_index(x, y - 1)
            south = grid.neighbor_index(x, y + 1)
            pressure_dx = (pressure[east] - pressure[west]) / 2.0
            pressure_dy_south = (pressure[south] - pressure[north]) / 2.0
            temperature_dx = (temperature[east] - temperature[west]) / 2.0
            temperature_dy_south = (temperature[south] - temperature[north]) / 2.0

            retention = settings.value(
                "ocean_wind_retention" if static.is_ocean[index] else "land_wind_retention"
            )
            u = previous_u[index] * retention - pressure_dx * pressure_factor
            v = previous_v[index] * retention + pressure_dy_south * pressure_factor
            u += temperature_dx * thermal_factor
            v -= temperature_dy_south * thermal_factor

            rotated_u = u - coriolis * v
            rotated_v = v + coriolis * u
            u, v = rotated_u, rotated_v

            current_elevation = static.elevation[index]
            target_x = x + (1 if u > 0 else -1 if u < 0 else 0)
            target_y = y - (1 if v > 0 else -1 if v < 0 else 0)
            target = static.neighbor_index(target_x, target_y)
            climb = max(0.0, static.elevation[target] - current_elevation)
            blocking = max(
                settings.value("minimum_terrain_wind_fraction"),
                1.0 - blocking_factor * climb / 1000.0,
            )
            u *= blocking
            v *= blocking

            speed = math.hypot(u, v)
            if speed > maximum:
                u *= maximum / speed
                v *= maximum / speed
            result_u[index] = u
            result_v[index] = v
    return result_u, result_v
