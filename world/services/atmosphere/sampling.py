from world.models import WeatherState
from world.atmosphere_defaults import default_atmospheric_parameters
from world.services.world_data import coordinates_to_grid

from .grid import wind_speed_and_direction
from .config import AtmosphericSettings
from .microphysics import fog_potential, rain_and_snow_fraction
from .thermodynamics import relative_humidity_percent


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


def _weather_from_grid_at_time(
    region,
    world_minutes,
    grid,
    *,
    parameters=None,
    settings=None,
):
    if region.map_latitude is None or region.map_longitude is None:
        raise ValueError("Регион нужно расположить на карте перед выборкой атмосферы.")
    _, _, index = coordinates_to_grid(
        region.map_latitude,
        region.map_longitude,
        width=grid.width,
        height=grid.height,
    )
    temperature = float(grid.fields["temperature"][index])
    humidity = float(
        relative_humidity_percent(
            grid.fields["water_vapor_specific_humidity"][index],
            temperature,
            grid.fields["pressure_hpa"][index],
            latent_heat_j_kg=(parameters or {}).get(
                "latent_heat_vaporization_j_kg",
                default_atmospheric_parameters()["latent_heat_vaporization_j_kg"],
            ),
        )
    )
    humidity = max(0.0, min(200.0, humidity))
    wind_speed, direction = wind_speed_and_direction(
        grid.fields["wind_u"][index],
        grid.fields["wind_v"][index],
    )
    cloud_cover = float(grid.fields["cloud_cover"][index])
    physical_rate = max(0.0, float(grid.fields["precipitation_rate"][index]))
    precipitation_rate_mm_h = physical_rate * 3600.0
    settings = settings or AtmosphericSettings(
        width=grid.width,
        height=grid.height,
        parameters=parameters,
    )
    rain_fraction, snow_fraction = rain_and_snow_fraction(temperature, settings)
    q_c = float(grid.fields["cloud_condensate_specific_humidity"][index])
    fog_probability = float(
        fog_potential(
            grid.fields["water_vapor_specific_humidity"][index],
            q_c,
            temperature,
            grid.fields["pressure_hpa"][index],
            wind_speed,
            region.elevation,
            settings,
        )
    )
    return WeatherState(
        region=region,
        world_minutes=world_minutes,
        temperature=round(temperature, 1),
        humidity=round(humidity, 1),
        pressure_hpa=round(float(grid.fields["pressure_hpa"][index]), 1),
        wind_speed=round(wind_speed, 1),
        wind_direction_degrees=(None if direction is None else round(direction, 1)),
        cloud_cover=round(cloud_cover, 3),
        # This legacy index remains untouched for old rows.  C3 physical
        # precipitation is stored in explicitly unit-bearing fields below.
        precipitation=0.0,
        precipitation_rate_mm_h=round(precipitation_rate_mm_h, 4),
        precipitation_amount_mm=round(
            physical_rate * settings.step_minutes * 60.0,
            4,
        ),
        rain_fraction=round(float(rain_fraction), 4),
        snow_fraction=round(float(snow_fraction), 4),
        condition=condition_from_cell(
            temperature,
            humidity,
            wind_speed,
            cloud_cover,
            0.0,
            parameters=parameters,
            precipitation_rate_mm_h=precipitation_rate_mm_h,
            snow_fraction=float(snow_fraction),
            fog_probability=fog_probability,
        ),
        source=WeatherState.Source.ATMOSPHERIC_GRID_V2,
    )


def _weather_from_grid(region, snapshot, grid, *, parameters=None, settings=None):
    return _weather_from_grid_at_time(
        region,
        snapshot.world_minutes,
        grid,
        parameters=parameters,
        settings=settings,
    )


class AtmosphericRegionSampler:
    """Accumulate small regional rows while global grids stay only in memory."""

    def __init__(self, regions, start_time, end_time, *, parameters=None, settings=None):
        self.regions = list(regions)
        self.parameters = parameters
        self.settings = settings
        self.generated = []
        region_ids = [region.pk for region in self.regions]
        if region_ids:
            self.existing = set(
                WeatherState.objects.filter(
                    region_id__in=region_ids,
                    world_minutes__gte=start_time,
                    world_minutes__lte=end_time,
                ).values_list("region_id", "world_minutes")
            )
        else:
            self.existing = set()

    def sample(self, world_minutes, grid):
        for region in self.regions:
            key = (region.pk, world_minutes)
            if key in self.existing:
                continue
            self.generated.append(
                _weather_from_grid_at_time(
                    region,
                    world_minutes,
                    grid,
                    parameters=self.parameters,
                    settings=self.settings,
                )
            )
            self.existing.add(key)

    def save(self):
        WeatherState.objects.bulk_create(self.generated, batch_size=500)
        return self.generated


def weather_from_snapshot(region, snapshot, *, parameters=None):
    from .persistence import grid_from_snapshot

    existing = region.weather_history.filter(world_minutes=snapshot.world_minutes).first()
    if existing is not None:
        return existing, False
    weather = _weather_from_grid(
        region,
        snapshot,
        grid_from_snapshot(snapshot),
        parameters=parameters,
    )
    weather.save(force_insert=True)
    return weather, True


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
        sampler.sample(snapshot.world_minutes, grid)
    return sampler.save()
