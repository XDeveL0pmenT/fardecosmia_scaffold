"""Server-side configuration for the Leaflet planetary atlas.

The map consumes one compact JSON contract.  Physics and Region persistence
remain in their existing services; this module only describes renderer inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

from world.services.map_geometry import (
    FARDECOSMIA_CIRCUMFERENCE_KM,
    normalized_ring_to_latlon,
)


ATLAS_MANIFEST_PATH = Path(settings.BASE_DIR) / "static" / "atlas" / "manifest.json"
ATLAS_MAX_ZOOM = 10
ATLAS_INITIAL_ZOOM = 1


def load_atlas_manifest():
    if not ATLAS_MANIFEST_PATH.exists():
        return {
            "format": 1,
            "available": False,
            "error": "Tile pyramid is not built.",
            "layers": {},
        }
    try:
        with ATLAS_MANIFEST_PATH.open(encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, ValueError):
        return {
            "format": 1,
            "available": False,
            "error": "Tile manifest is unreadable.",
            "layers": {},
        }
    if payload.get("format") != 1 or not isinstance(payload.get("layers"), dict):
        return {
            "format": 1,
            "available": False,
            "error": "Tile manifest has an unsupported format.",
            "layers": {},
        }
    return {**payload, "available": True}


def _tile_layers(manifest):
    layers = {}
    for name in ("base", "temperature", "elevation", "biome"):
        layer = manifest.get("layers", {}).get(name)
        if not layer:
            layers[name] = {"available": False}
            continue
        extension = layer.get("extension", "webp")
        # ``django.templatetags.static.static`` URI-escapes braces, while
        # Leaflet needs literal ``{z}/{x}/{y}`` placeholders.  Resolve only
        # the stable directory prefix through Django and append the template.
        tile_directory = static(
            f"atlas/tiles/{layer['version']}/{name}/"
        )
        layers[name] = {
            "available": True,
            "url": f"{tile_directory}{{z}}/{{x}}/{{y}}.{extension}",
            "native_zoom": int(layer["native_zoom"]),
            "source_width": int(layer["source_width"]),
            "source_height": int(layer["source_height"]),
            "canvas_width": int(layer["canvas_width"]),
            "canvas_height": int(layer["canvas_height"]),
            "version": layer["version"],
        }
    return layers


def build_atlas_config(
    *,
    campaign=None,
    inspect_url=None,
    region_shapes=(),
    global_biome_cells=None,
    campaign_biome_cells=None,
    biome_palette=(),
    light_bands=(),
    celestial=None,
    active_layer=None,
):
    manifest = load_atlas_manifest()
    circumference = (
        float(campaign.world_circumference_km)
        if campaign is not None
        else FARDECOSMIA_CIRCUMFERENCE_KM
    )
    regions = []
    for shape in region_shapes:
        regions.append(
            {
                **shape,
                "ring": normalized_ring_to_latlon(shape["polygon"]),
            }
        )
    normalized_bands = [
        {
            "x": float(band["x"]) / 1000.0,
            "width": float(band["width"]) / 1000.0,
            "star_opacity": float(band["star_opacity"]),
            "darkness_opacity": float(band["darkness_opacity"]),
            "ympha_opacity": float(band["ympha_opacity"]),
        }
        for band in light_bands
    ]
    celestial_payload = None
    if celestial:
        celestial_payload = {
            "star_longitude": float(celestial["star_x"]) / 1000.0 * 360.0 - 180.0,
            "ympha_longitude": float(celestial["ympha_x"]) / 1000.0 * 360.0 - 180.0,
        }
    return {
        "format": 1,
        "crs": {
            "projection": "equirectangular_lonlat",
            "world_bounds": [[-90.0, -180.0], [90.0, 180.0]],
            "world_pixel_size_zoom_zero": [512, 256],
            "wrap_longitude": [-180.0, 180.0],
            "wrap_latitude": None,
            "circumference_km": circumference,
            "radius_km": circumference / (2.0 * 3.141592653589793),
        },
        "view": {
            "center": [0.0, 0.0],
            "initial_zoom": ATLAS_INITIAL_ZOOM,
            "min_zoom": 0,
            "max_zoom": ATLAS_MAX_ZOOM,
        },
        "manifest": {
            "available": bool(manifest.get("available")),
            "error": manifest.get("error"),
            "version": manifest.get("version"),
        },
        "layers": _tile_layers(manifest),
        "static_data": {
            "temperature_url": static(
                "data/fardecosmia-average-temperature-grid.json"
            ),
            "elevation_url": static("data/fardecosmia-elevation-grid.json"),
            "land_mask_url": static("data/fardecosmia-land-mask.json"),
        },
        "campaign": (
            None
            if campaign is None
            else {
                "id": str(campaign.pk),
                "world_minutes": int(campaign.world_minutes),
            }
        ),
        "permissions": {
            "can_edit_regions": campaign is not None,
            "can_edit_biomes": campaign is not None,
            "can_inspect": bool(inspect_url),
        },
        "inspect_url": inspect_url,
        "regions": regions,
        "biomes": {
            "grid_width": 360,
            "grid_height": 180,
            "global_cells": global_biome_cells or {},
            "campaign_cells": campaign_biome_cells or {},
            "palette": list(biome_palette),
        },
        "light": {
            "bands": normalized_bands,
            "celestial": celestial_payload,
        },
        "active_layer": active_layer or ("light" if campaign is not None else "base"),
    }
