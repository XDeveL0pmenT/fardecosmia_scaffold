from array import array
from dataclasses import dataclass
from functools import lru_cache

from world.models import GlobalWorldMapLayer
from world.services.world_data import SurfaceType, WorldData


@dataclass
class StaticWorldGrid:
    width: int
    height: int
    is_ocean: array
    elevation: array
    mean_temperature: array
    biome: tuple

    @property
    def size(self):
        return self.width * self.height

    def index(self, x, y):
        return y * self.width + (x % self.width)

    def neighbor_index(self, x, y):
        return self.index(x, max(0, min(self.height - 1, y)))

    def latitude_at_row(self, y):
        return 90.0 - (y + 0.5) * 180.0 / self.height

    def longitude_at_column(self, x):
        return -180.0 + (x + 0.5) * 360.0 / self.width


def build_static_world_grid(settings, *, world_data=None):
    world_data = world_data or WorldData()
    ocean = array("b")
    elevation = array("f")
    mean_temperature = array("f")
    biomes = []
    for y in range(settings.height):
        for x in range(settings.width):
            surface, value, temperature, biome = world_data.static_cell_for_grid(
                x,
                y,
                width=settings.width,
                height=settings.height,
            )
            ocean.append(1 if surface == SurfaceType.OCEAN else 0)
            elevation.append(0.0 if value is None else float(value))
            mean_temperature.append(temperature)
            biomes.append(biome)
    return StaticWorldGrid(
        width=settings.width,
        height=settings.height,
        is_ocean=ocean,
        elevation=elevation,
        mean_temperature=mean_temperature,
        biome=tuple(biomes),
    )


class _GridShape:
    def __init__(self, width, height):
        self.width = width
        self.height = height


@lru_cache(maxsize=8)
def _cached_static_world_grid(width, height, layer_pk, layer_revision):
    del layer_revision  # It exists solely to invalidate the cache key.
    layer = None
    if layer_pk is not None:
        layer = GlobalWorldMapLayer.objects.get(pk=layer_pk)
    return build_static_world_grid(
        _GridShape(width, height),
        world_data=WorldData(layer=layer),
    )


def cached_static_world_grid(settings):
    """Cache immutable geography until the shared atlas changes."""
    layer = (
        GlobalWorldMapLayer.objects.filter(slug=GlobalWorldMapLayer.FARDECOSMIA_SLUG)
        .only("pk", "updated_at")
        .first()
    )
    revision = None if layer is None else layer.updated_at.isoformat()
    return _cached_static_world_grid(
        settings.width,
        settings.height,
        None if layer is None else layer.pk,
        revision,
    )
