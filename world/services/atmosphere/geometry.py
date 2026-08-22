import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class GridGeometry:
    width: int
    height: int
    x: np.ndarray
    y: np.ndarray
    flat_x: np.ndarray
    flat_y: np.ndarray
    west: np.ndarray
    east: np.ndarray
    north: np.ndarray
    south: np.ndarray
    latitude_rows: np.ndarray
    longitude_columns: np.ndarray
    latitude_radians_rows: np.ndarray
    longitude_radians_columns: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    latitude_radians: np.ndarray
    longitude_radians: np.ndarray
    sin_latitude: np.ndarray
    cos_latitude: np.ndarray
    cos_latitude_rows: np.ndarray
    planet_radius_m: float
    longitude_step_radians: float
    latitude_step_radians: float
    east_west_cell_m: np.ndarray
    east_west_cell_m_flat: np.ndarray
    north_south_cell_m: float
    inverse_east_west_cell_m: np.ndarray
    inverse_north_south_cell_m: float
    cell_areas_m2: np.ndarray
    angular_velocity_rad_s: float
    coriolis_parameter_s: np.ndarray


@lru_cache(maxsize=16)
def grid_geometry(
    width,
    height,
    world_circumference_km,
    minimum_polar_cosine,
    rotation_period_days,
    rotation_direction_sign,
):
    """Return immutable geometry shared by every step of a grid configuration."""
    width = int(width)
    height = int(height)
    circumference = float(world_circumference_km)
    minimum_cosine = float(minimum_polar_cosine)
    rotation_period_seconds = max(1.0, float(rotation_period_days) * 86_400.0)
    rotation_sign = 1.0 if float(rotation_direction_sign) >= 0.0 else -1.0
    planet_radius_m = circumference * 1000.0 / (2.0 * math.pi)
    angular_velocity = rotation_sign * 2.0 * math.pi / rotation_period_seconds

    x, y = np.meshgrid(
        np.arange(width, dtype=np.int32),
        np.arange(height, dtype=np.int32),
    )
    flat_x = x.reshape(-1)
    flat_y = y.reshape(-1)
    west = flat_y * width + (flat_x - 1) % width
    east = flat_y * width + (flat_x + 1) % width
    north = np.maximum(0, flat_y - 1) * width + flat_x
    south = np.minimum(height - 1, flat_y + 1) * width + flat_x

    latitude_rows = 90.0 - (np.arange(height, dtype=np.float64) + 0.5) * 180.0 / height
    longitude_columns = -180.0 + (
        np.arange(width, dtype=np.float64) + 0.5
    ) * 360.0 / width
    latitude = np.repeat(latitude_rows, width)
    longitude = np.tile(longitude_columns, height)
    latitude_radians_rows = np.radians(latitude_rows)
    longitude_radians_columns = np.radians(longitude_columns)
    latitude_radians = np.repeat(latitude_radians_rows, width)
    longitude_radians = np.tile(longitude_radians_columns, height)
    sin_latitude = np.repeat(np.sin(latitude_radians_rows), width)
    cos_latitude_rows = np.maximum(
        minimum_cosine,
        np.abs(np.cos(latitude_radians_rows)),
    )
    cos_latitude = np.repeat(cos_latitude_rows, width)
    east_west_cell_m = circumference * 1000.0 * cos_latitude / width
    east_west_cell_m_rows = circumference * 1000.0 * cos_latitude_rows / width
    north_south_cell_m = circumference * 1000.0 / (2.0 * height)
    cell_areas_m2 = east_west_cell_m * north_south_cell_m
    inverse_east_west_cell_m = 1.0 / east_west_cell_m
    inverse_north_south_cell_m = 1.0 / north_south_cell_m
    coriolis_parameter = 2.0 * angular_velocity * sin_latitude

    for values in (
        x,
        y,
        flat_x,
        flat_y,
        west,
        east,
        north,
        south,
        latitude_rows,
        longitude_columns,
        latitude_radians_rows,
        longitude_radians_columns,
        latitude,
        longitude,
        latitude_radians,
        longitude_radians,
        sin_latitude,
        cos_latitude,
        cos_latitude_rows,
        east_west_cell_m,
        east_west_cell_m_rows,
        inverse_east_west_cell_m,
        cell_areas_m2,
        coriolis_parameter,
    ):
        values.flags.writeable = False
    return GridGeometry(
        width=width,
        height=height,
        x=x,
        y=y,
        flat_x=flat_x,
        flat_y=flat_y,
        west=west,
        east=east,
        north=north,
        south=south,
        latitude_rows=latitude_rows,
        longitude_columns=longitude_columns,
        latitude_radians_rows=latitude_radians_rows,
        longitude_radians_columns=longitude_radians_columns,
        latitude=latitude,
        longitude=longitude,
        latitude_radians=latitude_radians,
        longitude_radians=longitude_radians,
        sin_latitude=sin_latitude,
        cos_latitude=cos_latitude,
        cos_latitude_rows=cos_latitude_rows,
        planet_radius_m=planet_radius_m,
        longitude_step_radians=2.0 * math.pi / width,
        latitude_step_radians=math.pi / height,
        east_west_cell_m=east_west_cell_m_rows,
        east_west_cell_m_flat=east_west_cell_m,
        north_south_cell_m=north_south_cell_m,
        inverse_east_west_cell_m=inverse_east_west_cell_m,
        inverse_north_south_cell_m=inverse_north_south_cell_m,
        cell_areas_m2=cell_areas_m2,
        angular_velocity_rad_s=angular_velocity,
        coriolis_parameter_s=coriolis_parameter,
    )


def geometry_for(settings):
    return grid_geometry(
        settings.width,
        settings.height,
        settings.world_circumference_km,
        settings.value("minimum_polar_cell_cosine"),
        settings.value("rotation_period_days"),
        settings.value("rotation_direction_sign"),
    )
