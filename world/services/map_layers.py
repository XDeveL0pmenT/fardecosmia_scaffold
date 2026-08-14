import math

from django.core.exceptions import ValidationError

from world.models import CampaignWorldMapOverride, GlobalWorldMapLayer, Region
from world.services.world_data import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    MAX_MAP_CELLS,
    WorldData,
    coordinates_to_grid,
    load_average_temperature_grid,
    load_elevation_grid,
    load_land_mask,
)


def get_global_map_layer(*, create=False):
    lookup = {"slug": GlobalWorldMapLayer.FARDECOSMIA_SLUG}
    if create:
        layer, _ = GlobalWorldMapLayer.objects.get_or_create(**lookup)
        return layer
    return GlobalWorldMapLayer.objects.filter(**lookup).first()


def get_campaign_map_override(campaign, *, create=False):
    if create:
        layer, _ = CampaignWorldMapOverride.objects.get_or_create(campaign=campaign)
        return layer
    return CampaignWorldMapOverride.objects.filter(campaign=campaign).first()


def effective_biome_cells(global_cells, campaign_cells):
    """Merge sparse biome maps without mutating either source."""
    merged = dict(global_cells or {})
    merged.update(campaign_cells or {})
    return merged


def land_only_biome_cells(cells):
    land_values = load_land_mask()["values"]
    return {
        str(index): biome
        for raw_index, biome in (cells or {}).items()
        if 0 <= (index := int(raw_index)) < len(land_values) and land_values[index]
    }


def coordinates_to_cell(longitude, latitude, width=MAP_GRID_WIDTH, height=MAP_GRID_HEIGHT):
    """Compatibility adapter; new code uses latitude-first World Data API."""
    return coordinates_to_grid(latitude, longitude, width=width, height=height)


def sample_average_temperature(longitude, latitude):
    return WorldData().mean_temperature_at(latitude, longitude)


def sample_reference_elevation(longitude, latitude):
    return WorldData(layer=get_global_map_layer()).elevation_at(latitude, longitude)


def sample_authored_layers(layer_state, longitude, latitude):
    if layer_state is None:
        return {"biome": None, "elevation": None}
    _, _, index = coordinates_to_cell(
        longitude,
        latitude,
        layer_state.grid_width,
        layer_state.grid_height,
    )
    key = str(index)
    return {
        "biome": layer_state.biome_cells.get(key),
        "elevation": layer_state.elevation_cells.get(key),
    }


def map_defaults_at(campaign, longitude, latitude):
    from world.services.region_climate import region_climate_at

    return region_climate_at(campaign, latitude, longitude)


def validate_layer_cells(cells, layer_type, *, width=MAP_GRID_WIDTH, height=MAP_GRID_HEIGHT):
    if not isinstance(cells, dict):
        raise ValidationError("Слой карты должен быть JSON-объектом.")
    if len(cells) > width * height:
        raise ValidationError("Слой содержит больше ячеек, чем сетка карты.")

    biome_codes = {value for value, _ in Region.Biome.choices}
    land_values = load_land_mask()["values"] if layer_type == "biome" else None
    normalized = {}
    for raw_index, raw_value in cells.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as error:
            raise ValidationError("Индекс ячейки слоя должен быть целым числом.") from error
        if str(index) != str(raw_index) or not 0 <= index < width * height:
            raise ValidationError("Индекс ячейки находится за пределами карты.")

        if layer_type == "biome":
            if not land_values[index]:
                raise ValidationError("Биом нельзя рисовать за пределами суши.")
            if raw_value not in biome_codes:
                raise ValidationError("Слой содержит неизвестный код биома.")
            normalized[str(index)] = raw_value
        elif layer_type == "elevation":
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValidationError("Высота ячейки должна быть числом.")
            if not math.isfinite(raw_value) or not -100_000 <= raw_value <= 100_000:
                raise ValidationError("Высота ячейки вышла за безопасный диапазон.")
            normalized[str(index)] = round(float(raw_value), 1)
        else:
            raise ValidationError("Неизвестный тип слоя карты.")
    return normalized
