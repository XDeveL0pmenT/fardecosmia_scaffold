"""Read-only access to Fardecosmia's objective spatial data.

Static rasters and the shared ``GlobalWorldMapLayer`` are the spatial source of
truth. ``Region`` climate fields remain weather-v2 snapshots/overrides; this API
never reads them. New global simulations should consume this module directly.
"""

import json
import math
from enum import Enum
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from world.models import GlobalWorldMapLayer


MAP_GRID_WIDTH = 360
MAP_GRID_HEIGHT = 180
MAX_MAP_CELLS = MAP_GRID_WIDTH * MAP_GRID_HEIGHT
DATA_DIRECTORY = Path(settings.BASE_DIR) / "static" / "data"
TEMPERATURE_DATA_PATH = DATA_DIRECTORY / "fardecosmia-average-temperature-grid.json"
ELEVATION_DATA_PATH = DATA_DIRECTORY / "fardecosmia-elevation-grid.json"
LAND_MASK_PATH = DATA_DIRECTORY / "fardecosmia-land-mask.json"


class SurfaceType(str, Enum):
    LAND = "land"
    OCEAN = "ocean"


class WorldDataUnavailable(LookupError):
    """A requested future spatial field has not been configured yet."""


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} должна быть числом.")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} должна быть конечным числом.")
    return value


def normalize_longitude(longitude):
    """Wrap longitude to the half-open interval [-180, 180)."""
    longitude = _finite_number(longitude, "Долгота")
    return (longitude + 180.0) % 360.0 - 180.0


def clamp_latitude(latitude):
    """Clamp a finite latitude to the map's north/south bounds."""
    latitude = _finite_number(latitude, "Широта")
    return max(-90.0, min(90.0, latitude))


def coordinates_to_grid(
    latitude,
    longitude,
    *,
    width=MAP_GRID_WIDTH,
    height=MAP_GRID_HEIGHT,
):
    """Map latitude/longitude to an equirectangular grid cell.

    Longitude wraps across the dateline. Latitude clamps at the poles because
    the current atlas is a complete equirectangular map rather than a partial
    regional projection.
    """
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("Ширина сетки должна быть положительным целым числом.")
    if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
        raise ValueError("Высота сетки должна быть положительным целым числом.")

    longitude = normalize_longitude(longitude)
    latitude = clamp_latitude(latitude)
    x = min(width - 1, int(((longitude + 180.0) / 360.0) * width))
    y = min(height - 1, int(((90.0 - latitude) / 180.0) * height))
    return x, y, y * width + x


def _load_grid(path, label):
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if (
        payload.get("width") != MAP_GRID_WIDTH
        or payload.get("height") != MAP_GRID_HEIGHT
        or len(payload.get("values", ())) != MAX_MAP_CELLS
    ):
        raise ValueError(f"Некорректная сетка {label} мира.")
    return payload


@lru_cache(maxsize=1)
def load_average_temperature_grid():
    return _load_grid(TEMPERATURE_DATA_PATH, "средней температуры")


@lru_cache(maxsize=1)
def load_elevation_grid():
    return _load_grid(ELEVATION_DATA_PATH, "высоты")


@lru_cache(maxsize=1)
def load_land_mask():
    return _load_grid(LAND_MASK_PATH, "маски суши")


class WorldData:
    """Reusable sampler that performs at most one global-layer query."""

    def __init__(self, *, layer=None):
        self._layer = layer
        self._layer_loaded = layer is not None

    def _global_layer(self):
        if not self._layer_loaded:
            self._layer = GlobalWorldMapLayer.objects.filter(
                slug=GlobalWorldMapLayer.FARDECOSMIA_SLUG,
            ).first()
            self._layer_loaded = True
        return self._layer

    def static_cell_for_grid(self, x, y, *, width, height):
        """Read all static fields for one target-grid cell in one pass."""
        if not 0 <= x < width or not 0 <= y < height:
            raise IndexError("Ячейка находится за пределами целевой сетки.")
        atlas_x = min(MAP_GRID_WIDTH - 1, int((x + 0.5) * MAP_GRID_WIDTH / width))
        atlas_y = min(MAP_GRID_HEIGHT - 1, int((y + 0.5) * MAP_GRID_HEIGHT / height))
        atlas_index = atlas_y * MAP_GRID_WIDTH + atlas_x
        is_land = bool(load_land_mask()["values"][atlas_index])
        elevation = load_elevation_grid()["values"][atlas_index]
        temperature = float(load_average_temperature_grid()["values"][atlas_index])
        biome = None

        layer = self._global_layer()
        if layer is not None:
            layer_x = min(layer.grid_width - 1, int((x + 0.5) * layer.grid_width / width))
            layer_y = min(layer.grid_height - 1, int((y + 0.5) * layer.grid_height / height))
            layer_index = layer_y * layer.grid_width + layer_x
            authored_elevation = layer.elevation_cells.get(str(layer_index))
            if authored_elevation is not None:
                elevation = float(authored_elevation)
            if is_land:
                biome = layer.biome_cells.get(str(layer_index))

        return (
            SurfaceType.LAND if is_land else SurfaceType.OCEAN,
            None if elevation is None else float(elevation),
            temperature,
            biome,
        )

    @staticmethod
    def grid_coordinates(latitude, longitude, *, width=MAP_GRID_WIDTH, height=MAP_GRID_HEIGHT):
        return coordinates_to_grid(
            latitude,
            longitude,
            width=width,
            height=height,
        )

    def surface_at(self, latitude, longitude):
        _, _, index = coordinates_to_grid(latitude, longitude)
        return (
            SurfaceType.LAND
            if load_land_mask()["values"][index]
            else SurfaceType.OCEAN
        )

    def elevation_at(self, latitude, longitude):
        layer = self._global_layer()
        if layer is not None:
            _, _, layer_index = coordinates_to_grid(
                latitude,
                longitude,
                width=layer.grid_width,
                height=layer.grid_height,
            )
            override = layer.elevation_cells.get(str(layer_index))
            if override is not None:
                return float(override)

        _, _, index = coordinates_to_grid(latitude, longitude)
        value = load_elevation_grid()["values"][index]
        return None if value is None else float(value)

    def mean_temperature_at(self, latitude, longitude):
        _, _, index = coordinates_to_grid(latitude, longitude)
        return float(load_average_temperature_grid()["values"][index])

    def biome_at(self, latitude, longitude):
        if self.surface_at(latitude, longitude) == SurfaceType.OCEAN:
            return None
        layer = self._global_layer()
        if layer is None:
            return None
        _, _, index = coordinates_to_grid(
            latitude,
            longitude,
            width=layer.grid_width,
            height=layer.grid_height,
        )
        return layer.biome_cells.get(str(index))

    def distance_to_ocean(self, latitude, longitude):
        coordinates_to_grid(latitude, longitude)
        raise WorldDataUnavailable(
            "Поле расстояния до океана ещё не добавлено в объективный атлас."
        )

    def ocean_temperature_at(self, latitude, longitude, *, configured_temperature=None):
        return self.ocean_baseline_temperature_at(
            latitude,
            longitude,
            configured_temperature=configured_temperature,
        )

    def ocean_baseline_temperature_at(
        self,
        latitude,
        longitude,
        *,
        configured_temperature=None,
    ):
        if self.surface_at(latitude, longitude) != SurfaceType.OCEAN:
            raise ValueError("Температура океана запрошена для ячейки суши.")
        value = self.mean_temperature_at(latitude, longitude)
        if math.isfinite(value):
            return value
        if configured_temperature is not None:
            return _finite_number(configured_temperature, "Температура океана")
        raise WorldDataUnavailable(
            "Карта средней температуры не содержит baseline океана; "
            "задайте fallback в конфигурации."
        )

    def albedo_at(
        self,
        latitude,
        longitude,
        *,
        surface_values=None,
        biome_values=None,
    ):
        surface = self.surface_at(latitude, longitude)
        biome = self.biome_at(latitude, longitude)
        if biome_values and biome in biome_values:
            return _finite_number(biome_values[biome], "Альбедо")
        if surface_values and surface.value in surface_values:
            return _finite_number(surface_values[surface.value], "Альбедо")
        raise WorldDataUnavailable(
            "Альбедо не задано каноном; передайте настраиваемую таблицу значений."
        )


def surface_at(latitude, longitude):
    return WorldData().surface_at(latitude, longitude)


def elevation_at(latitude, longitude):
    return WorldData().elevation_at(latitude, longitude)


def mean_temperature_at(latitude, longitude):
    return WorldData().mean_temperature_at(latitude, longitude)


def biome_at(latitude, longitude):
    return WorldData().biome_at(latitude, longitude)


def distance_to_ocean(latitude, longitude):
    return WorldData().distance_to_ocean(latitude, longitude)


def ocean_temperature_at(latitude, longitude, *, configured_temperature=None):
    return WorldData().ocean_temperature_at(
        latitude,
        longitude,
        configured_temperature=configured_temperature,
    )


def ocean_baseline_temperature_at(
    latitude,
    longitude,
    *,
    configured_temperature=None,
):
    return WorldData().ocean_baseline_temperature_at(
        latitude,
        longitude,
        configured_temperature=configured_temperature,
    )


def albedo_at(latitude, longitude, *, surface_values=None, biome_values=None):
    return WorldData().albedo_at(
        latitude,
        longitude,
        surface_values=surface_values,
        biome_values=biome_values,
    )
