"""Build elevation and land-mask assets from GM-provided world rasters.

The supplied files remain the source of truth.  Elevation values are matched
to the discrete legend printed on ElevationMap.png.  Ocean cells and cells
covered by that legend are stored as ``null`` instead of inventing terrain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


GRID_WIDTH = 360
GRID_HEIGHT = 180
ELEVATION_LEVELS = (
    6365,
    5688,
    5049,
    4450,
    3889,
    3368,
    2884,
    2439,
    2032,
    1663,
    1331,
    1037,
    779,
    558,
    374,
    225,
    111,
    31,
    -15,
    -29,
)


def _srgb_to_lab(colors: np.ndarray) -> np.ndarray:
    rgb = colors.astype(np.float64) / 255.0
    rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    matrix = np.array(
        (
            (0.4124564, 0.3575761, 0.1804375),
            (0.2126729, 0.7151522, 0.0721750),
            (0.0193339, 0.1191920, 0.9503041),
        )
    )
    xyz = rgb @ matrix.T
    xyz /= np.array((0.95047, 1.0, 1.08883))
    epsilon = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > epsilon, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.stack(
        (
            116 * f[..., 1] - 16,
            500 * (f[..., 0] - f[..., 1]),
            200 * (f[..., 1] - f[..., 2]),
        ),
        axis=-1,
    )


def _legend_palette(source: np.ndarray) -> np.ndarray:
    height, width, _ = source.shape
    # The discrete legend occupies the right edge of the supplied raster.
    # Narrow left-side samples avoid its text labels and rounded border.
    x0 = round(width * 0.9580)
    x1 = round(width * 0.9630)
    first_center = height * (120 / 3459)
    row_step = height * (140 / 3459)
    half_band = max(4, round(height * (25 / 3459)))
    colors = []
    for row in range(len(ELEVATION_LEVELS)):
        center = round(first_center + row * row_step)
        band = source[center - half_band : center + half_band + 1, x0:x1]
        colors.append(np.median(band.reshape(-1, 3), axis=0))
    return np.asarray(colors, dtype=np.uint8)


def build(
    elevation_source: Path,
    land_source: Path,
    elevation_image_target: Path,
    elevation_data_target: Path,
    land_data_target: Path,
) -> None:
    elevation_image = Image.open(elevation_source).convert("RGB")
    land_image = Image.open(land_source).convert("L")
    if elevation_image.size != land_image.size:
        raise ValueError("ElevationMap.png and LandMap.png must use the same projection.")

    elevation_image_target.parent.mkdir(parents=True, exist_ok=True)
    elevation_image.save(elevation_image_target, "WEBP", quality=91, method=6)

    source = np.asarray(elevation_image)
    palette = _legend_palette(source)
    palette_lab = _srgb_to_lab(palette)
    sampled = elevation_image.resize((GRID_WIDTH, GRID_HEIGHT), Image.Resampling.BOX)
    sampled = sampled.filter(ImageFilter.MedianFilter(size=3))
    sampled_lab = _srgb_to_lab(np.asarray(sampled)).reshape(-1, 3)
    distances = np.sum((sampled_lab[:, None, :] - palette_lab[None, :, :]) ** 2, axis=2)
    nearest = np.argmin(distances, axis=1)
    values = np.asarray(ELEVATION_LEVELS, dtype=np.int32)[nearest]

    # The source legend hides the eastern edge.  Mark it unknown; wrapping or
    # extrapolating would create geography that the GM did not provide.
    legend_start_x = round(elevation_image.width * 0.954)
    unavailable_from = int(legend_start_x / elevation_image.width * GRID_WIDTH)
    elevation_values: list[int | None] = values.tolist()
    for y in range(GRID_HEIGHT):
        for x in range(unavailable_from, GRID_WIDTH):
            elevation_values[y * GRID_WIDTH + x] = None

    # BOX produces a land-coverage fraction per editor cell.  Requiring a
    # majority removes coordinate labels/grid lines while retaining coastlines.
    land_sample = np.asarray(
        land_image.resize((GRID_WIDTH, GRID_HEIGHT), Image.Resampling.BOX),
        dtype=np.uint8,
    )
    land_values = (land_sample >= 128).astype(np.uint8).reshape(-1).tolist()
    for index, is_land in enumerate(land_values):
        if not is_land:
            elevation_values[index] = None

    elevation_payload = {
        "source": elevation_source.name,
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
        "unit": "m",
        "minimum_m": min(ELEVATION_LEVELS),
        "maximum_m": max(ELEVATION_LEVELS),
        "unavailable_from_x": unavailable_from,
        "values": elevation_values,
    }
    elevation_data_target.parent.mkdir(parents=True, exist_ok=True)
    elevation_data_target.write_text(
        json.dumps(elevation_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    land_payload = {
        "source": land_source.name,
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
        "values": land_values,
    }
    land_data_target.parent.mkdir(parents=True, exist_ok=True)
    land_data_target.write_text(
        json.dumps(land_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("elevation_source", type=Path)
    parser.add_argument("land_source", type=Path)
    parser.add_argument("elevation_image_target", type=Path)
    parser.add_argument("elevation_data_target", type=Path)
    parser.add_argument("land_data_target", type=Path)
    args = parser.parse_args()
    build(
        args.elevation_source,
        args.land_source,
        args.elevation_image_target,
        args.elevation_data_target,
        args.land_data_target,
    )


if __name__ == "__main__":
    main()
