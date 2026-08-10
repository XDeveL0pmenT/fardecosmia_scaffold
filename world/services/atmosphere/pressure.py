import math
from array import array

from .deterministic import deterministic_signed


def pressure_for_cell(temperature, mean_temperature, elevation, settings):
    scale_height = max(1.0, settings.value("pressure_scale_height_m"))
    altitude_pressure = settings.value("reference_pressure_hpa") * math.exp(
        -float(elevation) / scale_height
    )
    anomaly = temperature - mean_temperature
    return altitude_pressure - anomaly * settings.value("pressure_temperature_factor")


def solve_pressure(grid, static, settings, step_index):
    previous = grid.fields["pressure_hpa"]
    temperature = grid.fields["temperature"]
    result = array("f", [0.0]) * grid.size
    relaxation = min(1.0, max(0.0, settings.value("pressure_relaxation")))
    smoothing = min(1.0, max(0.0, settings.value("pressure_neighbor_smoothing")))
    noise_size = max(0.0, settings.value("pressure_noise_hpa"))
    for y in range(grid.height):
        for x in range(grid.width):
            index = grid.index(x, y)
            diagnostic = pressure_for_cell(
                temperature[index],
                static.mean_temperature[index],
                static.elevation[index],
                settings,
            )
            neighbors = (
                previous[grid.neighbor_index(x - 1, y)]
                + previous[grid.neighbor_index(x + 1, y)]
                + previous[grid.neighbor_index(x, y - 1)]
                + previous[grid.neighbor_index(x, y + 1)]
            ) / 4.0
            soft_noise = (
                deterministic_signed(settings.world_seed, step_index, index, 1) * 0.5
                + deterministic_signed(settings.world_seed, step_index, index, 2) * 0.3
                + deterministic_signed(settings.world_seed, step_index, index, 3) * 0.2
            )
            value = previous[index] + relaxation * (diagnostic - previous[index])
            value += smoothing * (neighbors - previous[index])
            value += soft_noise * noise_size
            result[index] = max(
                settings.value("minimum_pressure_hpa"),
                min(settings.value("maximum_pressure_hpa"), value),
            )
    return result
