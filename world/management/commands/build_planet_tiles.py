from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageColor, ImageDraw

from world.biomes import BIOME_PALETTE
from world.models import GlobalWorldMapLayer
from world.services.map_layers import land_only_biome_cells


TILE_SIZE = 256
BUILDER_VERSION = 1
RASTER_LAYERS = {
    "base": {
        "source": "fardecosmia-world-map.webp",
        "extension": "webp",
    },
    "temperature": {
        # 0.webp is the current authored source.  Its lower 263 px are a UI
        # legend outside the 2:1 world extent, so the crop is explicit and is
        # recorded in the manifest rather than silently trimming geography.
        "source": "0.webp",
        "extension": "webp",
        "world_crop": "top_2_to_1",
    },
    "elevation": {
        "source": "fardecosmia-elevation-map.webp",
        "extension": "webp",
    },
}


def _native_zoom(width):
    return max(0, int(round(math.log2(max(1.0, width / 512.0)))))


def _digest(parts):
    checksum = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            checksum.update(part)
        else:
            checksum.update(str(part).encode("utf-8"))
    return checksum.hexdigest()[:16]


def _save_tile(tile, destination, extension):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if extension == "png":
        tile.save(destination, format="PNG", optimize=True)
    else:
        tile.save(
            destination,
            format="WEBP",
            quality=88,
            method=6,
            exact=True,
        )


def _write_pyramid(image, *, native_zoom, destination, extension):
    count = 0
    for zoom in range(native_zoom + 1):
        width = 512 * (2**zoom)
        height = 256 * (2**zoom)
        level = image if image.size == (width, height) else image.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )
        for y in range(height // TILE_SIZE):
            for x in range(width // TILE_SIZE):
                tile = level.crop(
                    (
                        x * TILE_SIZE,
                        y * TILE_SIZE,
                        (x + 1) * TILE_SIZE,
                        (y + 1) * TILE_SIZE,
                    )
                )
                _save_tile(
                    tile,
                    destination / str(zoom) / str(x) / f"{y}.{extension}",
                    extension,
                )
                count += 1
    return count


class Command(BaseCommand):
    help = "Build deterministic 2:1 Leaflet tile pyramids for the Fardecosmia atlas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--layers",
            nargs="+",
            choices=(*RASTER_LAYERS, "biome"),
            default=[*RASTER_LAYERS, "biome"],
        )

    def handle(self, *args, **options):
        started = perf_counter()
        image_root = Path(settings.BASE_DIR) / "static" / "images"
        atlas_root = Path(settings.BASE_DIR) / "static" / "atlas"
        tile_root = atlas_root / "tiles"
        manifest_path = atlas_root / "manifest.json"
        manifest = {"format": 1, "builder_version": BUILDER_VERSION, "layers": {}}

        if manifest_path.exists():
            try:
                with manifest_path.open(encoding="utf-8") as source:
                    previous = json.load(source)
                if previous.get("format") == 1:
                    manifest["layers"].update(previous.get("layers", {}))
            except (OSError, ValueError):
                pass

        for name in options["layers"]:
            layer_started = perf_counter()
            if name == "biome":
                metadata, image = self._biome_image()
            else:
                metadata, image = self._raster_image(name, image_root)

            version = metadata.pop("version")
            destination = tile_root / version / name
            tile_count = _write_pyramid(
                image,
                native_zoom=metadata["native_zoom"],
                destination=destination,
                extension=metadata["extension"],
            )
            disk_bytes = sum(
                path.stat().st_size for path in destination.rglob("*.*")
            )
            manifest["layers"][name] = {
                **metadata,
                "version": version,
                "tile_count": tile_count,
                "disk_bytes": disk_bytes,
            }
            self.stdout.write(
                f"{name}: {tile_count} tiles, {disk_bytes} bytes, "
                f"{perf_counter() - layer_started:.3f}s"
            )

        versions = sorted(
            (name, layer["version"])
            for name, layer in manifest["layers"].items()
        )
        manifest["version"] = _digest(
            [BUILDER_VERSION, json.dumps(versions, separators=(",", ":"))]
        )
        manifest["tile_size"] = TILE_SIZE
        manifest["world_pixel_size_zoom_zero"] = [512, 256]
        atlas_root.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Atlas manifest {manifest['version']} built in "
                f"{perf_counter() - started:.3f}s"
            )
        )

    def _raster_image(self, name, image_root):
        configuration = RASTER_LAYERS[name]
        source_path = image_root / configuration["source"]
        if not source_path.exists():
            raise CommandError(f"Missing atlas source: {source_path}")
        source_bytes = source_path.read_bytes()
        with Image.open(source_path) as opened:
            source_width, source_height = opened.size
            image = opened.convert("RGBA")

        crop = None
        if configuration.get("world_crop") == "top_2_to_1":
            world_height = source_width // 2
            if source_height < world_height:
                raise CommandError(
                    f"{source_path.name} is too short for a 2:1 world extent."
                )
            crop = [0, 0, source_width, world_height]
            image = image.crop(tuple(crop))
        world_width, world_height = image.size
        aspect = world_width / world_height
        if abs(aspect - 2.0) > 0.08:
            raise CommandError(
                f"{source_path.name} has incompatible world aspect {aspect:.5f}; "
                "expected approximately 2:1."
            )
        native_zoom = _native_zoom(world_width)
        canvas_size = (512 * (2**native_zoom), 256 * (2**native_zoom))
        image = image.resize(canvas_size, Image.Resampling.LANCZOS)
        version = _digest(
            [BUILDER_VERSION, name, source_bytes, crop, canvas_size, "webp-q88-m6"]
        )
        return (
            {
                "version": version,
                "source": f"static/images/{source_path.name}",
                "source_width": source_width,
                "source_height": source_height,
                "source_world_crop": crop,
                "canvas_width": canvas_size[0],
                "canvas_height": canvas_size[1],
                "native_zoom": native_zoom,
                "extension": configuration["extension"],
                "resampling": "lanczos",
            },
            image,
        )

    def _biome_image(self):
        layer = GlobalWorldMapLayer.objects.filter(
            slug=GlobalWorldMapLayer.FARDECOSMIA_SLUG,
        ).first()
        cells = land_only_biome_cells(layer.biome_cells) if layer else {}
        source_width, source_height = 360, 180
        source = Image.new("RGBA", (source_width, source_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        for raw_index, biome in sorted(cells.items(), key=lambda item: int(item[0])):
            index = int(raw_index)
            x = index % source_width
            y = index // source_width
            color = ImageColor.getrgb(BIOME_PALETTE[biome])
            draw.point((x, y), fill=(*color, 205))
        native_zoom = 0
        canvas_size = (512, 256)
        image = source.resize(canvas_size, Image.Resampling.NEAREST)
        serialized = json.dumps(cells, sort_keys=True, separators=(",", ":"))
        version = _digest(
            [BUILDER_VERSION, "biome", serialized, sorted(BIOME_PALETTE.items())]
        )
        return (
            {
                "version": version,
                "source": "GlobalWorldMapLayer.biome_cells",
                "source_width": source_width,
                "source_height": source_height,
                "source_world_crop": None,
                "canvas_width": canvas_size[0],
                "canvas_height": canvas_size[1],
                "native_zoom": native_zoom,
                "extension": "png",
                "resampling": "nearest",
            },
            image,
        )
