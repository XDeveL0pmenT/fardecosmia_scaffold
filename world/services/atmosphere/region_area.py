"""Deterministic Region-contour weather aggregation for R1.

Point weather remains a separate concept.  This module intersects the
manually authored normalized contour with atmospheric cells, applies true
spherical cell-area weights, and aggregates only already-computed grid fields.
It never advances or modifies atmospheric physics.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np

from world.atmosphere_defaults import (
    ATMOSPHERIC_SOLVER_VERSION,
    default_atmospheric_parameters,
)
from world.models import RegionAreaWeatherState, WeatherState

from .coordinate_sampling import sample_environment_at
from .grid import wind_speed_and_direction
from .microphysics import fog_potential, rain_and_snow_fraction
from .thermodynamics import relative_humidity_percent


MASK_SUBDIVISIONS = 4
TINY_REGION_CELL_EQUIVALENT = 0.25


@dataclass(frozen=True)
class RegionContourMask:
    indices: np.ndarray
    coverage_fractions: np.ndarray
    area_weights_m2: np.ndarray
    sampling_mode: str
    covered_area_m2: float


@dataclass(frozen=True)
class RegionAreaWeatherSummary:
    headline: str
    description: str
    temperature: str
    precipitation: str
    cloudiness: str
    wind: str
    hazards: tuple[str, ...]
    is_point_fallback: bool


def _unwrap_polygon_x(polygon):
    """Follow authored edges while choosing the nearest periodic image.

    A direct 0.97 -> 0.03 edge is therefore a short seam crossing, while a
    large contour remains large when its author supplied intermediate vertices
    whose consecutive longitude spans stay below half the map.
    """

    unwrapped = [float(polygon[0][0])]
    for point in polygon[1:]:
        value = float(point[0])
        previous = unwrapped[-1]
        value += round(previous - value)
        unwrapped.append(value)
    return np.asarray(unwrapped, dtype=np.float64)


def _unwrap_x(values, reference):
    values = np.asarray(values, dtype=np.float64)
    return reference + ((values - reference + 0.5) % 1.0 - 0.5)


def _points_in_polygon(x, y, polygon_x, polygon_y):
    """Vectorized even/odd test for deterministic sub-cell sample points."""

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    inside = np.zeros(x.shape, dtype=np.bool_)
    previous = len(polygon_x) - 1
    for current in range(len(polygon_x)):
        x_current = polygon_x[current]
        y_current = polygon_y[current]
        x_previous = polygon_x[previous]
        y_previous = polygon_y[previous]
        crosses_y = (y_current > y) != (y_previous > y)
        denominator = y_previous - y_current
        if abs(denominator) < 1e-15:
            previous = current
            continue
        crossing_x = (
            (x_previous - x_current) * (y - y_current) / denominator
            + x_current
        )
        inside ^= crosses_y & (x < crossing_x)
        previous = current
    return inside


def _spherical_cell_area_rows(width, height, circumference_km):
    radius_m = float(circumference_km) * 1000.0 / (2.0 * math.pi)
    longitude_step = 2.0 * math.pi / int(width)
    north = np.radians(90.0 - np.arange(height, dtype=np.float64) * 180.0 / height)
    south = np.radians(
        90.0 - (np.arange(height, dtype=np.float64) + 1.0) * 180.0 / height
    )
    return radius_m**2 * longitude_step * (np.sin(north) - np.sin(south))


@lru_cache(maxsize=512)
def _cached_contour_mask(
    region_id,
    revision,
    polygon_key,
    width,
    height,
    circumference_km,
    subdivisions,
):
    del region_id, revision  # Explicit cache identity/provenance keys.
    polygon = [list(point) for point in polygon_key]
    if len(polygon) < 3:
        empty = np.asarray([], dtype=np.float64)
        return RegionContourMask(
            indices=np.asarray([], dtype=np.int64),
            coverage_fractions=empty,
            area_weights_m2=empty,
            sampling_mode=RegionAreaWeatherState.SamplingMode.POINT_FALLBACK,
            covered_area_m2=0.0,
        )

    polygon_x = _unwrap_polygon_x(polygon)
    reference = float(np.mean(polygon_x))
    polygon_y = np.asarray([point[1] for point in polygon], dtype=np.float64)
    x_centres = _unwrap_x(
        (np.arange(width, dtype=np.float64) + 0.5) / width,
        reference,
    )
    y_centres = (np.arange(height, dtype=np.float64) + 0.5) / height
    x_margin = 0.5 / width
    y_margin = 0.5 / height
    columns = np.flatnonzero(
        (x_centres >= float(np.min(polygon_x)) - x_margin)
        & (x_centres <= float(np.max(polygon_x)) + x_margin)
    )
    rows = np.flatnonzero(
        (y_centres >= float(np.min(polygon_y)) - y_margin)
        & (y_centres <= float(np.max(polygon_y)) + y_margin)
    )
    if not columns.size or not rows.size:
        empty = np.asarray([], dtype=np.float64)
        return RegionContourMask(
            indices=np.asarray([], dtype=np.int64),
            coverage_fractions=empty,
            area_weights_m2=empty,
            sampling_mode=RegionAreaWeatherState.SamplingMode.POINT_FALLBACK,
            covered_area_m2=0.0,
        )

    candidate_x, candidate_y = np.meshgrid(columns, rows)
    candidate_x = candidate_x.reshape(-1)
    candidate_y = candidate_y.reshape(-1)
    hits = np.zeros(candidate_x.size, dtype=np.int16)
    subdivisions = max(1, int(subdivisions))
    for sub_y in range(subdivisions):
        sample_y = (
            candidate_y + (sub_y + 0.5) / subdivisions
        ) / height
        for sub_x in range(subdivisions):
            sample_x = _unwrap_x(
                (candidate_x + (sub_x + 0.5) / subdivisions) / width,
                reference,
            )
            hits += _points_in_polygon(
                sample_x,
                sample_y,
                polygon_x,
                polygon_y,
            ).astype(np.int16)

    covered = hits > 0
    indices = candidate_y[covered] * width + candidate_x[covered]
    coverage = hits[covered].astype(np.float64) / subdivisions**2
    cell_area_rows = _spherical_cell_area_rows(width, height, circumference_km)
    weights = coverage * cell_area_rows[candidate_y[covered]]
    covered_area = float(np.sum(weights))
    cell_equivalent = float(np.sum(coverage))
    mode = (
        RegionAreaWeatherState.SamplingMode.POINT_FALLBACK
        if cell_equivalent < TINY_REGION_CELL_EQUIVALENT
        else RegionAreaWeatherState.SamplingMode.AREA
    )
    for values in (indices, coverage, weights):
        values.flags.writeable = False
    return RegionContourMask(
        indices=indices.astype(np.int64, copy=False),
        coverage_fractions=coverage,
        area_weights_m2=weights,
        sampling_mode=mode,
        covered_area_m2=covered_area,
    )


def region_contour_mask(region, settings, *, subdivisions=MASK_SUBDIVISIONS):
    polygon_key = tuple(
        (round(float(point[0]), 6), round(float(point[1]), 6))
        for point in (region.map_polygon or [])
    )
    return _cached_contour_mask(
        region.pk,
        region.weather_geometry_revision,
        polygon_key,
        settings.width,
        settings.height,
        round(float(settings.world_circumference_km), 6),
        subdivisions,
    )


def clear_region_contour_mask_cache():
    _cached_contour_mask.cache_clear()


def _weighted_mean(values, weights):
    return float(np.average(np.asarray(values, dtype=np.float64), weights=weights))


def _weighted_quantile(values, weights, quantile):
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    threshold = min(1.0, max(0.0, float(quantile))) * cumulative[-1]
    return float(sorted_values[min(np.searchsorted(cumulative, threshold), len(order) - 1)])


def _weighted_fraction(mask, weights):
    return float(np.sum(weights * np.asarray(mask, dtype=np.float64)) / np.sum(weights))


def _area_arrays(region, grid, static, settings, mask):
    if mask.sampling_mode == RegionAreaWeatherState.SamplingMode.POINT_FALLBACK:
        point = sample_environment_at(
            grid,
            static,
            settings,
            region.map_latitude,
            region.map_longitude,
            local_elevation_m=region.elevation,
        )
        values = point.values
        return {
            "weights": np.ones(1, dtype=np.float64),
            "temperature": np.asarray([values["temperature"]]),
            "q_v": np.asarray([values["water_vapor_specific_humidity"]]),
            "q_c": np.asarray([values["cloud_condensate_specific_humidity"]]),
            "pressure": np.asarray([values["pressure_hpa"]]),
            "wind_u": np.asarray([values["wind_u"]]),
            "wind_v": np.asarray([values["wind_v"]]),
            "cloud": np.asarray([values["cloud_cover"]]),
            "precipitation": np.asarray([max(0.0, values["precipitation_rate"]) * 3600.0]),
            "elevation": np.asarray([point.elevation_m]),
            "covered_cell_count": 1,
        }

    indices = mask.indices
    return {
        "weights": mask.area_weights_m2,
        "temperature": grid.fields["temperature"][indices].astype(np.float64),
        "q_v": grid.fields["water_vapor_specific_humidity"][indices].astype(np.float64),
        "q_c": grid.fields["cloud_condensate_specific_humidity"][indices].astype(np.float64),
        "pressure": grid.fields["pressure_hpa"][indices].astype(np.float64),
        "wind_u": grid.fields["wind_u"][indices].astype(np.float64),
        "wind_v": grid.fields["wind_v"][indices].astype(np.float64),
        "cloud": grid.fields["cloud_cover"][indices].astype(np.float64),
        "precipitation": np.maximum(
            0.0,
            grid.fields["precipitation_rate"][indices].astype(np.float64) * 3600.0,
        ),
        "elevation": static.elevation[indices].astype(np.float64),
        "covered_cell_count": int(indices.size),
    }


def area_weather_from_grid_at_time(
    region,
    world_minutes,
    grid,
    *,
    settings,
    static,
    parameters=None,
    solver_version=ATMOSPHERIC_SOLVER_VERSION,
    atmosphere_fingerprint=None,
):
    if region.map_latitude is None or region.map_longitude is None:
        raise ValueError("Регион нужно расположить на карте перед агрегацией контура.")
    mask = region_contour_mask(region, settings)
    data = _area_arrays(region, grid, static, settings, mask)
    weights = data["weights"]
    temperature = data["temperature"]
    pressure = data["pressure"]
    humidity = np.clip(
        relative_humidity_percent(
            data["q_v"],
            temperature,
            pressure,
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        ),
        0.0,
        200.0,
    )
    wind_speed = np.hypot(data["wind_u"], data["wind_v"])
    precipitation = data["precipitation"]
    rain_fraction, snow_fraction = rain_and_snow_fraction(temperature, settings)
    thresholds = default_atmospheric_parameters()
    thresholds.update(parameters or {})
    precipitating = precipitation >= thresholds[
        "condition_precipitation_rate_mm_h"
    ]
    cloudy = data["cloud"] >= thresholds["condition_cloud_cover_threshold"]
    heavy_cloud = data["cloud"] >= float(
        thresholds.get("region_area_heavy_cloud_cover_threshold", 0.8)
    )
    strong_wind = wind_speed >= thresholds["condition_storm_wind_threshold"]
    fog_probability = fog_potential(
        data["q_v"],
        data["q_c"],
        temperature,
        pressure,
        wind_speed,
        data["elevation"],
        settings,
    )
    fog = fog_probability >= thresholds["condition_fog_potential_threshold"]
    dangerous_heat = temperature >= float(
        thresholds.get("region_area_dangerous_heat_temperature_c", 45.0)
    )
    dangerous_cold = temperature <= float(
        thresholds.get("region_area_dangerous_cold_temperature_c", -25.0)
    )
    mean_u = _weighted_mean(data["wind_u"], weights)
    mean_v = _weighted_mean(data["wind_v"], weights)
    _mean_vector_speed, direction = wind_speed_and_direction(mean_u, mean_v)
    wet_weight = weights * precipitating.astype(np.float64)
    wet_weight_total = float(np.sum(wet_weight))

    return RegionAreaWeatherState(
        region=region,
        world_minutes=world_minutes,
        region_weather_revision=region.weather_geometry_revision,
        sampling_mode=mask.sampling_mode,
        grid_width=grid.width,
        grid_height=grid.height,
        covered_cell_count=data["covered_cell_count"],
        covered_area_m2=mask.covered_area_m2,
        temperature_mean_c=round(_weighted_mean(temperature, weights), 3),
        temperature_min_c=round(float(np.min(temperature)), 3),
        temperature_max_c=round(float(np.max(temperature)), 3),
        temperature_p10_c=round(_weighted_quantile(temperature, weights, 0.10), 3),
        temperature_p90_c=round(_weighted_quantile(temperature, weights, 0.90), 3),
        humidity_mean_percent=round(_weighted_mean(humidity, weights), 3),
        humidity_p10_percent=round(_weighted_quantile(humidity, weights, 0.10), 3),
        humidity_p90_percent=round(_weighted_quantile(humidity, weights, 0.90), 3),
        surface_pressure_mean_hpa=round(_weighted_mean(pressure, weights), 3),
        cloud_cover_mean=round(_weighted_mean(data["cloud"], weights), 6),
        cloudy_area_fraction=round(_weighted_fraction(cloudy, weights), 6),
        heavy_cloud_area_fraction=round(_weighted_fraction(heavy_cloud, weights), 6),
        precipitating_area_fraction=round(
            _weighted_fraction(precipitating, weights), 6
        ),
        rain_area_fraction=round(
            float(np.sum(weights * precipitating * rain_fraction) / np.sum(weights)),
            6,
        ),
        snow_area_fraction=round(
            float(np.sum(weights * precipitating * snow_fraction) / np.sum(weights)),
            6,
        ),
        area_mean_precipitation_rate_mm_h=round(
            _weighted_mean(precipitation, weights), 6
        ),
        wet_area_mean_precipitation_rate_mm_h=round(
            0.0
            if wet_weight_total <= 0.0
            else float(np.sum(precipitation * wet_weight) / wet_weight_total),
            6,
        ),
        max_precipitation_rate_mm_h=round(float(np.max(precipitation)), 6),
        wind_mean_u_m_s=round(mean_u, 4),
        wind_mean_v_m_s=round(mean_v, 4),
        prevailing_wind_direction_degrees=(
            None if direction is None else round(float(direction), 3)
        ),
        wind_speed_mean_m_s=round(_weighted_mean(wind_speed, weights), 4),
        wind_speed_p90_m_s=round(_weighted_quantile(wind_speed, weights, 0.90), 4),
        wind_speed_max_m_s=round(float(np.max(wind_speed)), 4),
        strong_wind_area_fraction=round(_weighted_fraction(strong_wind, weights), 6),
        fog_area_fraction=round(_weighted_fraction(fog, weights), 6),
        dangerous_heat_area_fraction=round(
            _weighted_fraction(dangerous_heat, weights), 6
        ),
        dangerous_cold_area_fraction=round(
            _weighted_fraction(dangerous_cold, weights), 6
        ),
        source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        solver_version=solver_version,
        atmosphere_fingerprint=atmosphere_fingerprint,
    )


class AtmosphericRegionAreaSampler:
    """Collect contour aggregates in memory and persist them in one bulk write."""

    def __init__(
        self,
        regions,
        start_time,
        end_time,
        *,
        parameters=None,
        settings,
        static,
        solver_version=ATMOSPHERIC_SOLVER_VERSION,
        atmosphere_fingerprint=None,
    ):
        self.regions = [
            region
            for region in regions
            if region.map_latitude is not None and region.map_longitude is not None
        ]
        self.parameters = parameters
        self.settings = settings
        self.static = static
        self.solver_version = solver_version
        self.atmosphere_fingerprint = atmosphere_fingerprint
        self.generated = []
        region_ids = [region.pk for region in self.regions]
        self.existing = set()
        if region_ids:
            for row in RegionAreaWeatherState.objects.filter(
                region_id__in=region_ids,
                world_minutes__gte=start_time,
                world_minutes__lte=end_time,
            ).values_list("region_id", "region_weather_revision", "world_minutes"):
                self.existing.add(row)

    def sample(self, world_minutes, grid):
        for region in self.regions:
            key = (region.pk, region.weather_geometry_revision, world_minutes)
            if key in self.existing:
                continue
            self.generated.append(
                area_weather_from_grid_at_time(
                    region,
                    world_minutes,
                    grid,
                    settings=self.settings,
                    static=self.static,
                    parameters=self.parameters,
                    solver_version=self.solver_version,
                    atmosphere_fingerprint=self.atmosphere_fingerprint,
                )
            )
            self.existing.add(key)

    def save(self):
        RegionAreaWeatherState.objects.bulk_create(self.generated, batch_size=500)
        return self.generated


def _coverage_phrase(fraction):
    percentage = round(max(0.0, min(1.0, float(fraction))) * 100)
    if fraction < 0.05:
        scope = "единичные участки"
    elif fraction < 0.20:
        scope = "местами"
    elif fraction < 0.50:
        scope = "на части территории"
    elif fraction < 0.80:
        scope = "на большей части территории"
    else:
        scope = "почти повсеместно"
    return scope, percentage


def _direction_label(degrees):
    if degrees is None:
        return "переменного направления"
    labels = (
        "северный",
        "северо-восточный",
        "восточный",
        "юго-восточный",
        "южный",
        "юго-западный",
        "западный",
        "северо-западный",
    )
    return labels[round(float(degrees) / 45.0) % 8]


def build_region_area_weather_summary(state):
    if state is None:
        return None
    scope, percentage = _coverage_phrase(state.precipitating_area_fraction)
    if state.precipitating_area_fraction < 0.05:
        precipitation = "Существенных осадков по контуру почти нет."
    else:
        rain = state.rain_area_fraction
        snow = state.snow_area_fraction
        if rain > 0.01 and snow > 0.01:
            kind = "дождь и снег"
        elif snow > rain:
            kind = "снег"
        else:
            kind = "дождь"
        precipitation = (
            f"{kind.capitalize()} наблюдается {scope} ({percentage}%); "
            f"средняя интенсивность на влажных участках "
            f"{state.wet_area_mean_precipitation_rate_mm_h:.1f} мм/ч, "
            f"максимум {state.max_precipitation_rate_mm_h:.1f} мм/ч."
        )
    cloud_scope, cloud_percentage = _coverage_phrase(state.cloudy_area_fraction)
    cloudiness = (
        f"Облачность занимает {cloud_scope} ({cloud_percentage}% контура); "
        f"среднее покрытие {state.cloud_cover_mean * 100:.0f}%."
    )
    wind = (
        f"Преобладает {_direction_label(state.prevailing_wind_direction_degrees)} "
        f"ветер: средняя скорость {state.wind_speed_mean_m_s:.1f} м/с, "
        f"p90 {state.wind_speed_p90_m_s:.1f} м/с."
    )
    hazards = []
    for label, fraction in (
        ("туман", state.fog_area_fraction),
        ("опасная жара", state.dangerous_heat_area_fraction),
        ("опасный холод", state.dangerous_cold_area_fraction),
        ("сильный ветер", state.strong_wind_area_fraction),
    ):
        if fraction >= 0.05:
            hazard_scope, hazard_percentage = _coverage_phrase(fraction)
            hazards.append(f"{label.capitalize()} — {hazard_scope} ({hazard_percentage}%).")
    temperature = (
        f"Средняя температура {state.temperature_mean_c:.1f}°C; "
        f"основной диапазон {state.temperature_p10_c:.1f}…"
        f"{state.temperature_p90_c:.1f}°C, экстремумы "
        f"{state.temperature_min_c:.1f}…{state.temperature_max_c:.1f}°C."
    )
    description = " ".join((temperature, precipitation, cloudiness, wind))
    return RegionAreaWeatherSummary(
        headline="Погода в регионе",
        description=description,
        temperature=temperature,
        precipitation=precipitation,
        cloudiness=cloudiness,
        wind=wind,
        hazards=tuple(hazards),
        is_point_fallback=(
            state.sampling_mode
            == RegionAreaWeatherState.SamplingMode.POINT_FALLBACK
        ),
    )
