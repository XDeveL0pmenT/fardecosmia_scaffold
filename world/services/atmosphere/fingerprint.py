import hashlib
import json
from functools import lru_cache

from world.atmosphere_defaults import (
    ATMOSPHERIC_FORMAT_VERSION,
    ATMOSPHERIC_SOLVER_VERSION,
)
from world.models import GlobalWorldMapLayer
from world.services.world_data import (
    ELEVATION_DATA_PATH,
    LAND_MASK_PATH,
    TEMPERATURE_DATA_PATH,
)
from world.services.orbital_climate import canonical_orbital_fingerprint_data

from .config import AtmosphericSettings
from .circulation import CIRCULATION_MODEL_VERSION
from .ocean import OCEAN_MODEL_VERSION
from .microphysics import MICROPHYSICS_VERSION
from .thermodynamics import SATURATION_FORMULA_VERSION


@lru_cache(maxsize=16)
def _file_digest(path_string, modified_ns, size):
    del modified_ns, size
    digest = hashlib.sha256()
    with open(path_string, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def static_maps_version():
    versions = {}
    for path in (TEMPERATURE_DATA_PATH, ELEVATION_DATA_PATH, LAND_MASK_PATH):
        stat = path.stat()
        versions[path.name] = _file_digest(
            str(path),
            stat.st_mtime_ns,
            stat.st_size,
        )
    return versions


def atmospheric_input_fingerprint(campaign, config):
    """Hash every persisted/static input that can affect one solver step."""
    settings = AtmosphericSettings.from_model(config, campaign)
    layer = GlobalWorldMapLayer.objects.filter(
        slug=GlobalWorldMapLayer.FARDECOSMIA_SLUG,
    ).first()
    layer_state = None
    if layer is not None:
        layer_state = {
            "slug": layer.slug,
            "grid_width": layer.grid_width,
            "grid_height": layer.grid_height,
            "biome_cells": layer.biome_cells,
            "elevation_cells": layer.elevation_cells,
            "updated_at": layer.updated_at.isoformat(),
        }
    campaign_state = {
        "calendar_epoch_year": campaign.calendar_epoch_year,
        "calendar_hours_per_turn": campaign.calendar_hours_per_turn,
        "calendar_minutes_per_hour": campaign.calendar_minutes_per_hour,
        "red_turn_visibility_threshold": campaign.red_turn_visibility_threshold,
        "light_season_min_red_turns": campaign.light_season_min_red_turns,
        "dark_season_max_red_turns": campaign.dark_season_max_red_turns,
        "world_circumference_km": campaign.world_circumference_km,
        "star_reference_longitude": campaign.star_reference_longitude,
        "star_motion_direction": campaign.star_motion_direction,
        "ympha_peak_longitude_at_epoch": campaign.ympha_peak_longitude_at_epoch,
        "ympha_motion_direction": campaign.ympha_motion_direction,
    }
    payload = {
        "format_version": ATMOSPHERIC_FORMAT_VERSION,
        "solver_version": ATMOSPHERIC_SOLVER_VERSION,
        "settings": {
            "width": settings.width,
            "height": settings.height,
            "step_minutes": settings.step_minutes,
            "world_seed": settings.world_seed,
            "world_circumference_km": settings.world_circumference_km,
            "ocean_temperature_c": settings.ocean_temperature_c,
            "parameters": settings.parameters,
        },
        "campaign": campaign_state,
        "orbital_climate": canonical_orbital_fingerprint_data(),
        "ocean_model_version": OCEAN_MODEL_VERSION,
        "saturation_formula_version": SATURATION_FORMULA_VERSION,
        "microphysics_version": MICROPHYSICS_VERSION,
        "circulation_model_version": CIRCULATION_MODEL_VERSION,
        "static_maps": static_maps_version(),
        "global_layer": layer_state,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
