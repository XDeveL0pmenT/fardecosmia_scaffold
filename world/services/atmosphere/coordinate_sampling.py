"""Read-only atmosphere sampling at arbitrary world coordinates.

This module deliberately has no Django model imports.  Region weather, future
map cursors and route sampling all consume the same renderer-independent API.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from world.services.world_data import clamp_latitude, normalize_longitude

from .grid import wind_speed_and_direction
from .pressure import surface_pressure_from_circulation


CONTINUOUS_FIELDS = (
    "temperature",
    "water_vapor_specific_humidity",
    "cloud_condensate_specific_humidity",
    "circulation_pressure_hpa",
    "wind_u",
    "wind_v",
    "cloud_cover",
    "precipitation_rate",
    "condensation_rate_kg_m2_s",
    "latent_heating_rate_w_m2",
    "surface_temperature",
    "sea_surface_temperature_c",
    "evaporation_flux_kg_m2_s",
)


@dataclass(frozen=True)
class AtmosphericPointSample:
    latitude: float
    longitude: float
    grid_x: float
    grid_y: float
    nearest_index: int
    values: dict[str, float]
    is_ocean: bool
    elevation_m: float
    mean_temperature_c: float
    biome: str | None
    wind_speed_m_s: float
    wind_direction_degrees: float | None
    interpolated_grid_surface_pressure_hpa: float


def coordinates_to_interpolation_point(latitude, longitude, *, width, height):
    """Map lat/lon to fractional grid-centre coordinates.

    Longitude is periodic.  Latitude is clamped to the centre of the polar
    rows because the current single-layer grid does not contain pole vertices.
    """

    latitude = clamp_latitude(latitude)
    longitude = normalize_longitude(longitude)
    x = ((longitude + 180.0) / 360.0) * width - 0.5
    y = ((90.0 - latitude) / 180.0) * height - 0.5
    return x % width, max(0.0, min(height - 1.0, y))


def _bilinear_array_sample(grid, values, x, y):
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
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


def sample_environment_at(
    grid,
    static,
    settings,
    latitude,
    longitude,
    *,
    local_elevation_m=None,
):
    """Sample a physically coherent atmosphere at arbitrary coordinates.

    The operation performs no ORM query, simulation step or mutation.  Every
    prognostic continuous field uses bilinear interpolation.  Local surface
    pressure is then derived from interpolated circulation pressure, T/q and
    the local continuous elevation; interpolating the already height-adjusted
    pressure would mix unrelated vertical levels near steep terrain.

    Surface type and biome remain discrete nearest-cell fields.  Callers with
    access to the full-resolution World Data elevation should pass it through
    ``local_elevation_m``.  The no-ORM fallback bilinearly samples the static
    atmospheric elevation grid (or uses sea level for a nearest ocean cell).
    """

    if (grid.width, grid.height) != (settings.width, settings.height):
        raise ValueError("Размер атмосферы не совпадает с конфигурацией выборки.")
    if (static.width, static.height) != (grid.width, grid.height):
        raise ValueError("Размер статической сетки не совпадает с атмосферой.")
    x, y = coordinates_to_interpolation_point(
        latitude,
        longitude,
        width=grid.width,
        height=grid.height,
    )
    nearest_x = int(math.floor(x + 0.5)) % grid.width
    nearest_y = max(0, min(grid.height - 1, int(math.floor(y + 0.5))))
    nearest_index = grid.index(nearest_x, nearest_y)
    values = {
        field: float(grid.bilinear_sample(field, x, y))
        for field in CONTINUOUS_FIELDS
    }
    interpolated_grid_pressure = float(grid.bilinear_sample("pressure_hpa", x, y))
    is_ocean = bool(static.is_ocean[nearest_index])
    if local_elevation_m is None:
        elevation_m = (
            0.0
            if is_ocean
            else _bilinear_array_sample(grid, static.elevation, x, y)
        )
    else:
        elevation_m = float(local_elevation_m)
        if not math.isfinite(elevation_m):
            raise ValueError("Локальная высота должна быть конечным числом.")
    values["pressure_hpa"] = float(
        surface_pressure_from_circulation(
            values["circulation_pressure_hpa"],
            values["temperature"],
            values["water_vapor_specific_humidity"],
            elevation_m,
            settings,
        )
    )
    wind_speed, wind_direction = wind_speed_and_direction(
        values["wind_u"],
        values["wind_v"],
    )
    return AtmosphericPointSample(
        latitude=clamp_latitude(latitude),
        longitude=normalize_longitude(longitude),
        grid_x=x,
        grid_y=y,
        nearest_index=nearest_index,
        values=values,
        is_ocean=is_ocean,
        elevation_m=elevation_m,
        mean_temperature_c=float(static.mean_temperature[nearest_index]),
        biome=static.biome[nearest_index],
        wind_speed_m_s=float(wind_speed),
        wind_direction_degrees=wind_direction,
        interpolated_grid_surface_pressure_hpa=interpolated_grid_pressure,
    )
