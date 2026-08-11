import math

import numpy as np

from .deterministic import deterministic_signed_array
from .geometry import geometry_for


def pressure_for_cell(temperature, mean_temperature, elevation, settings):
    scale_height = max(1.0, settings.value("pressure_scale_height_m"))
    altitude_pressure = settings.value("reference_pressure_hpa") * math.exp(
        -float(elevation) / scale_height
    )
    anomaly = temperature - mean_temperature
    return altitude_pressure - anomaly * settings.value("pressure_temperature_factor")


def pressure_for_arrays(temperature, mean_temperature, elevation, settings):
    scale_height = max(1.0, settings.value("pressure_scale_height_m"))
    return (
        settings.value("reference_pressure_hpa")
        * np.exp(-np.asarray(elevation, dtype=np.float64) / scale_height)
        - (
            np.asarray(temperature, dtype=np.float64)
            - np.asarray(mean_temperature, dtype=np.float64)
        )
        * settings.value("pressure_temperature_factor")
    )


def solve_pressure(grid, static, settings, step_index):
    previous = grid.fields["pressure_hpa"].astype(np.float64)
    temperature = grid.fields["temperature"].astype(np.float64)
    geometry = geometry_for(settings)
    relaxation = min(1.0, max(0.0, settings.value("pressure_relaxation")))
    smoothing = min(1.0, max(0.0, settings.value("pressure_neighbor_smoothing")))
    noise_size = max(0.0, settings.value("pressure_noise_hpa"))
    diagnostic = pressure_for_arrays(
        temperature,
        static.mean_temperature,
        static.elevation,
        settings,
    )
    neighbors = (
        previous[geometry.west]
        + previous[geometry.east]
        + previous[geometry.north]
        + previous[geometry.south]
    ) / 4.0
    indices = np.arange(grid.size, dtype=np.uint64)
    soft_noise = (
        deterministic_signed_array(settings.world_seed, step_index, indices, 1) * 0.5
        + deterministic_signed_array(settings.world_seed, step_index, indices, 2) * 0.3
        + deterministic_signed_array(settings.world_seed, step_index, indices, 3) * 0.2
    )
    result = previous + relaxation * (diagnostic - previous)
    result += smoothing * (neighbors - previous)
    result += soft_noise * noise_size
    return np.clip(
        result,
        settings.value("minimum_pressure_hpa"),
        settings.value("maximum_pressure_hpa"),
    ).astype(np.float32)
