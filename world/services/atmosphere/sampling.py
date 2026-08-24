from dataclasses import dataclass

from world.models import WeatherState
from world.atmosphere_defaults import (
    ATMOSPHERIC_SOLVER_VERSION,
    default_atmospheric_parameters,
)
from .config import AtmosphericSettings
from .coordinate_sampling import sample_environment_at
from .microphysics import fog_potential, rain_and_snow_fraction
from .thermodynamics import relative_humidity_percent


@dataclass(frozen=True, slots=True)
class AtmosphericPointWeather:
    """Current, read-only weather interpretation of one sampled point.

    This is deliberately not a model and carries no accumulated interval
    precipitation. Region persistence and Player ambience can therefore share
    one interpretation without making Character another weather source of
    truth.
    """

    temperature: float
    humidity: float
    pressure_hpa: float
    wind_speed: float
    wind_direction_degrees: float | None
    cloud_cover: float
    precipitation: float
    precipitation_rate_mm_h: float
    precipitation_amount_mm: float
    rain_fraction: float
    snow_fraction: float
    fog_probability: float
    condition: str


def condition_from_cell(
    temperature,
    humidity,
    wind_speed,
    cloud_cover,
    precipitation,
    *,
    parameters=None,
    precipitation_rate_mm_h=None,
    snow_fraction=None,
    fog_probability=None,
):
    thresholds = default_atmospheric_parameters()
    thresholds.update(parameters or {})
    if precipitation_rate_mm_h is not None:
        if precipitation_rate_mm_h >= thresholds["condition_precipitation_rate_mm_h"]:
            if snow_fraction is not None and snow_fraction >= 0.5:
                return WeatherState.Condition.SNOW
            if (
                precipitation_rate_mm_h
                >= thresholds["condition_storm_precipitation_rate_mm_h"]
                and cloud_cover >= thresholds["condition_storm_cloud_cover"]
            ) or wind_speed >= thresholds["condition_storm_wind_threshold"]:
                return WeatherState.Condition.STORM
            return WeatherState.Condition.RAIN
        if fog_probability is not None and fog_probability >= thresholds[
            "condition_fog_potential_threshold"
        ]:
            return WeatherState.Condition.FOG
        if cloud_cover >= thresholds["condition_cloud_cover_threshold"]:
            return WeatherState.Condition.CLOUDY
        return WeatherState.Condition.CLEAR

    if precipitation >= thresholds["condition_precipitation_threshold"]:
        if temperature <= 0:
            return WeatherState.Condition.SNOW
        if (
            precipitation >= thresholds["condition_storm_precipitation_threshold"]
            or wind_speed >= thresholds["condition_storm_wind_threshold"]
        ):
            return WeatherState.Condition.STORM
        return WeatherState.Condition.RAIN
    if (
        humidity >= thresholds["condition_fog_humidity_threshold"]
        and wind_speed < thresholds["condition_fog_wind_max"]
    ):
        return WeatherState.Condition.FOG
    if cloud_cover >= thresholds["condition_cloud_cover_threshold"]:
        return WeatherState.Condition.CLOUDY
    return WeatherState.Condition.CLEAR


def interpret_point_weather(point, settings, *, parameters=None):
    """Interpret an authoritative point sample using existing C4 semantics."""

    values = point.values
    parameters = settings.parameters if parameters is None else parameters
    temperature = float(values["temperature"])
    humidity = float(
        relative_humidity_percent(
            values["water_vapor_specific_humidity"],
            temperature,
            values["pressure_hpa"],
            latent_heat_j_kg=parameters.get(
                "latent_heat_vaporization_j_kg",
                default_atmospheric_parameters()["latent_heat_vaporization_j_kg"],
            ),
        )
    )
    humidity = max(0.0, min(200.0, humidity))
    physical_rate = max(0.0, float(values["precipitation_rate"]))
    precipitation_rate_mm_h = physical_rate * 3600.0
    rain_fraction, snow_fraction = rain_and_snow_fraction(temperature, settings)
    fog_probability = float(
        fog_potential(
            values["water_vapor_specific_humidity"],
            values["cloud_condensate_specific_humidity"],
            temperature,
            values["pressure_hpa"],
            point.wind_speed_m_s,
            point.elevation_m,
            settings,
        )
    )
    condition = condition_from_cell(
        temperature,
        humidity,
        point.wind_speed_m_s,
        values["cloud_cover"],
        0.0,
        parameters=parameters,
        precipitation_rate_mm_h=precipitation_rate_mm_h,
        snow_fraction=float(snow_fraction),
        fog_probability=fog_probability,
    )
    return AtmosphericPointWeather(
        temperature=temperature,
        humidity=humidity,
        pressure_hpa=float(values["pressure_hpa"]),
        wind_speed=float(point.wind_speed_m_s),
        wind_direction_degrees=point.wind_direction_degrees,
        cloud_cover=float(values["cloud_cover"]),
        precipitation=0.0,
        precipitation_rate_mm_h=precipitation_rate_mm_h,
        precipitation_amount_mm=physical_rate * settings.step_minutes * 60.0,
        rain_fraction=float(rain_fraction),
        snow_fraction=float(snow_fraction),
        fog_probability=fog_probability,
        condition=condition,
    )


def _weather_from_grid_at_time(
    region,
    world_minutes,
    grid,
    *,
    parameters=None,
    settings=None,
    static=None,
    solver_version=ATMOSPHERIC_SOLVER_VERSION,
    atmosphere_fingerprint=None,
):
    if region.map_latitude is None or region.map_longitude is None:
        raise ValueError("Регион нужно расположить на карте перед выборкой атмосферы.")
    settings = settings or AtmosphericSettings(
        width=grid.width,
        height=grid.height,
        parameters=parameters,
    )
    if static is None:
        from .static_grid import cached_static_world_grid

        static = cached_static_world_grid(settings)
    point = sample_environment_at(
        grid,
        static,
        settings,
        region.map_latitude,
        region.map_longitude,
        local_elevation_m=region.elevation,
    )
    reading = interpret_point_weather(
        point,
        settings,
        parameters=parameters,
    )
    return WeatherState(
        region=region,
        world_minutes=world_minutes,
        temperature=round(reading.temperature, 1),
        humidity=round(reading.humidity, 1),
        pressure_hpa=round(reading.pressure_hpa, 1),
        wind_speed=round(reading.wind_speed, 1),
        wind_direction_degrees=(
            None
            if reading.wind_direction_degrees is None
            else round(reading.wind_direction_degrees, 1)
        ),
        cloud_cover=round(reading.cloud_cover, 3),
        # This legacy index remains untouched for old rows.  C3 physical
        # precipitation is stored in explicitly unit-bearing fields below.
        precipitation=0.0,
        precipitation_rate_mm_h=round(reading.precipitation_rate_mm_h, 4),
        precipitation_amount_mm=round(reading.precipitation_amount_mm, 4),
        rain_fraction=round(reading.rain_fraction, 4),
        snow_fraction=round(reading.snow_fraction, 4),
        condition=reading.condition,
        source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        region_weather_revision=region.weather_geometry_revision,
        sample_latitude=point.latitude,
        sample_longitude=point.longitude,
        sample_elevation_m=point.elevation_m,
        solver_version=solver_version,
        atmosphere_fingerprint=atmosphere_fingerprint,
    )


def _weather_from_grid(region, snapshot, grid, *, parameters=None, settings=None, static=None):
    return _weather_from_grid_at_time(
        region,
        snapshot.world_minutes,
        grid,
        parameters=parameters,
        settings=settings,
        static=static,
        solver_version=snapshot.solver_version,
        atmosphere_fingerprint=snapshot.input_fingerprint,
    )


class AtmosphericRegionSampler:
    """Accumulate small regional rows while global grids stay only in memory."""

    PHYSICAL_UPDATE_FIELDS = (
        "temperature",
        "humidity",
        "wind_speed",
        "wind_direction_degrees",
        "pressure_hpa",
        "cloud_cover",
        "precipitation",
        "precipitation_rate_mm_h",
        "precipitation_amount_mm",
        "rain_fraction",
        "snow_fraction",
        "condition",
        "source",
        "region_weather_revision",
        "sample_latitude",
        "sample_longitude",
        "sample_elevation_m",
        "solver_version",
        "atmosphere_fingerprint",
    )

    def __init__(
        self,
        regions,
        start_time,
        end_time,
        *,
        parameters=None,
        settings=None,
        static=None,
        solver_version=ATMOSPHERIC_SOLVER_VERSION,
        atmosphere_fingerprint=None,
    ):
        self.regions = list(regions)
        self.parameters = parameters
        self.settings = settings
        self.static = static
        self.solver_version = solver_version
        self.atmosphere_fingerprint = atmosphere_fingerprint
        self.generated = []
        self.replaced_legacy = []
        region_ids = [region.pk for region in self.regions]
        if region_ids:
            revisions = {
                region.pk: region.weather_geometry_revision for region in self.regions
            }
            existing_rows = list(
                WeatherState.objects.filter(
                    region_id__in=region_ids,
                    world_minutes__gte=start_time,
                    world_minutes__lte=end_time,
                )
            )
            self.existing = {}
            for weather in existing_rows:
                effective_revision = (
                    0
                    if weather.region_weather_revision is None
                    else weather.region_weather_revision
                )
                if effective_revision != revisions[weather.region_id]:
                    continue
                self.existing[
                    (weather.region_id, effective_revision, weather.world_minutes)
                ] = weather
        else:
            self.existing = {}

    def sample(self, world_minutes, grid):
        for region in self.regions:
            key = (
                region.pk,
                region.weather_geometry_revision,
                world_minutes,
            )
            candidate = _weather_from_grid_at_time(
                region,
                world_minutes,
                grid,
                parameters=self.parameters,
                settings=self.settings,
                static=self.static,
                solver_version=self.solver_version,
                atmosphere_fingerprint=self.atmosphere_fingerprint,
            )
            existing = self.existing.get(key)
            if existing is not None:
                if existing.source != WeatherState.Source.LEGACY_V2:
                    continue
                for field_name in self.PHYSICAL_UPDATE_FIELDS:
                    setattr(existing, field_name, getattr(candidate, field_name))
                self.replaced_legacy.append(existing)
                self.existing[key] = existing
                continue
            self.generated.append(candidate)
            self.existing[key] = candidate

    def save(self):
        WeatherState.objects.bulk_create(self.generated, batch_size=500)
        if self.replaced_legacy:
            WeatherState.objects.bulk_update(
                self.replaced_legacy,
                self.PHYSICAL_UPDATE_FIELDS,
                batch_size=500,
            )
        return [*self.generated, *self.replaced_legacy]


def weather_from_snapshot(region, snapshot, *, parameters=None):
    from .persistence import grid_from_snapshot

    sampler = AtmosphericRegionSampler(
        [region],
        snapshot.world_minutes,
        snapshot.world_minutes,
        parameters=parameters,
        solver_version=snapshot.solver_version,
        atmosphere_fingerprint=snapshot.input_fingerprint,
    )
    sampler.sample(snapshot.world_minutes, grid_from_snapshot(snapshot))
    saved = sampler.save()
    if saved:
        return saved[0], True
    return (
        region.weather_history.filter(
            world_minutes=snapshot.world_minutes,
            region_weather_revision=region.weather_geometry_revision,
        ).first(),
        False,
    )


def weather_for_regions_from_snapshots(regions, snapshots, *, parameters=None):
    """Sample each compressed snapshot once, then save all regional rows in bulk."""
    from .persistence import grid_from_snapshot

    regions = list(regions)
    snapshots = list(snapshots)
    if not regions or not snapshots:
        return []
    sampler = AtmosphericRegionSampler(
        regions,
        min(snapshot.world_minutes for snapshot in snapshots),
        max(snapshot.world_minutes for snapshot in snapshots),
        parameters=parameters,
    )
    for snapshot in snapshots:
        grid = grid_from_snapshot(snapshot)
        sampler.solver_version = snapshot.solver_version
        sampler.atmosphere_fingerprint = snapshot.input_fingerprint
        sampler.sample(snapshot.world_minutes, grid)
    return sampler.save()
