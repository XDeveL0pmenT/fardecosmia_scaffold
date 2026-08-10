"""Build the browser image and sampled data from the GM temperature raster.

This is an offline asset tool.  The source raster and its own legend remain the
authority; the script does not synthesize temperatures for missing source data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


GRID_WIDTH = 360
GRID_HEIGHT = 180
MAP_ASPECT_RATIO = 2
LEGEND_MIN_C = -97.2
LEGEND_MAX_C = 74.6
PALETTE_SAMPLES = 512
LUMINANCE_WEIGHT = 0.12


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
        (116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])),
        axis=-1,
    )


def _temperature_features(colors: np.ndarray) -> np.ndarray:
    """Use chroma as the primary signal and lighting only as a weak tiebreaker.

    The supplied map keeps relief and surface texture beneath its temperature
    tint.  Full Lab distance therefore mistakes a bright mountain for a hotter
    colour.  Down-weighting L preserves the legend hue/chroma while remaining
    stable around the least saturated section of the gradient.
    """
    lab = _srgb_to_lab(colors)
    features = lab.copy()
    features[..., 0] *= LUMINANCE_WEIGHT
    return features


def _match_palette(sampled: Image.Image, palette: np.ndarray) -> np.ndarray:
    palette_image = Image.fromarray(palette.reshape(1, len(palette), 3), "RGB")
    palette = np.asarray(
        palette_image.resize((PALETTE_SAMPLES, 1), Image.Resampling.LANCZOS)
    )[0]
    palette_features = _temperature_features(palette)
    sampled_features = _temperature_features(np.asarray(sampled)).reshape(-1, 3)

    nearest_chunks = []
    # Chunking avoids a several-hundred-megabyte temporary array on large maps.
    for start in range(0, len(sampled_features), 4096):
        chunk = sampled_features[start : start + 4096]
        distances = np.sum(
            (chunk[:, None, :] - palette_features[None, :, :]) ** 2,
            axis=2,
        )
        nearest_chunks.append(np.argmin(distances, axis=1))
    nearest = np.concatenate(nearest_chunks).reshape(GRID_HEIGHT, GRID_WIDTH)

    # Temperature is a broad field; a 3x3 median removes isolated relief/grid
    # artefacts without inventing values or blurring coastlines across large areas.
    padded = np.pad(nearest, 1, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3))
    return np.median(windows, axis=(-2, -1)).astype(np.int32)


def build(source: Path, image_target: Path, data_target: Path) -> None:
    source_image = Image.open(source).convert("RGB")
    map_height = source_image.width // MAP_ASPECT_RATIO
    if source_image.height <= map_height:
        raise ValueError("The source image has no room for the temperature legend.")

    map_image = source_image.crop((0, 0, source_image.width, map_height))
    image_target.parent.mkdir(parents=True, exist_ok=True)
    map_image.save(image_target, "WEBP", quality=90, method=6)

    # These normalized bounds point at the uninterrupted gradient in the
    # supplied legend.  Sampling a vertical median ignores its subtle texture.
    legend_left = round(source_image.width * 0.038)
    legend_right = round(source_image.width * 0.720)
    legend_top = round(source_image.height * 0.849)
    legend_bottom = round(source_image.height * 0.905)
    legend = np.asarray(source_image)[legend_top:legend_bottom, legend_left:legend_right]
    palette = np.median(legend, axis=0).astype(np.uint8)
    palette_temperatures = np.linspace(
        LEGEND_MIN_C,
        LEGEND_MAX_C,
        PALETTE_SAMPLES,
    )

    # Box reduction followed by a tiny median removes map grid lines while
    # preserving the geography already painted into the supplied raster.
    sampled = map_image.resize((GRID_WIDTH, GRID_HEIGHT), Image.Resampling.BOX)
    sampled = sampled.filter(ImageFilter.GaussianBlur(radius=1.15))
    nearest = _match_palette(sampled, palette)
    temperatures = palette_temperatures[nearest]

    payload = {
        "source": source.name,
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
        "minimum_c": LEGEND_MIN_C,
        "maximum_c": LEGEND_MAX_C,
        "sampling_method": "legend-lab-chroma-v2",
        "luminance_weight": LUMINANCE_WEIGHT,
        "values": [round(float(value), 1) for value in temperatures.reshape(-1)],
    }
    data_target.parent.mkdir(parents=True, exist_ok=True)
    data_target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("image_target", type=Path)
    parser.add_argument("data_target", type=Path)
    args = parser.parse_args()
    build(args.source, args.image_target, args.data_target)


if __name__ == "__main__":
    main()
