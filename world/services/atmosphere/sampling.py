from world.models import WeatherState
from world.atmosphere_defaults import default_atmospheric_parameters
from world.services.world_data import coordinates_to_grid

from .grid import wind_speed_and_direction
from .persistence import grid_from_snapshot


def condition_from_cell(
    temperature,
    humidity,
    wind_speed,
    cloud_cover,
    precipitation,
    *,
    parameters=None,
):
    thresholds = default_atmospheric_parameters()
    thresholds.update(parameters or {})
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


def _weather_from_grid(region, snapshot, grid, *, parameters=None):
    if region.map_latitude is None or region.map_longitude is None:
        raise ValueError("Регион нужно расположить на карте перед выборкой атмосферы.")
    _, _, index = coordinates_to_grid(
        region.map_latitude,
        region.map_longitude,
        width=grid.width,
        height=grid.height,
    )
    temperature = float(grid.fields["temperature"][index])
    humidity = float(grid.fields["relative_humidity"][index])
    wind_speed, direction = wind_speed_and_direction(
        grid.fields["wind_u"][index],
        grid.fields["wind_v"][index],
    )
    cloud_cover = float(grid.fields["cloud_cover"][index])
    precipitation = float(grid.fields["precipitation_rate"][index])
    return WeatherState(
        region=region,
        world_minutes=snapshot.world_minutes,
        temperature=round(temperature, 1),
        humidity=round(humidity, 1),
        pressure_hpa=round(float(grid.fields["pressure_hpa"][index]), 1),
        wind_speed=round(wind_speed, 1),
        wind_direction_degrees=(None if direction is None else round(direction, 1)),
        cloud_cover=round(cloud_cover, 3),
        precipitation=round(precipitation, 2),
        condition=condition_from_cell(
            temperature,
            humidity,
            wind_speed,
            cloud_cover,
            precipitation,
            parameters=parameters,
        ),
        source=WeatherState.Source.ATMOSPHERIC_GRID_V1,
    )


def weather_from_snapshot(region, snapshot, *, parameters=None):
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
    regions = list(regions)
    snapshots = list(snapshots)
    if not regions or not snapshots:
        return []
    region_ids = [region.pk for region in regions]
    world_minutes = [snapshot.world_minutes for snapshot in snapshots]
    existing = set(
        WeatherState.objects.filter(
            region_id__in=region_ids,
            world_minutes__in=world_minutes,
        ).values_list("region_id", "world_minutes")
    )
    generated = []
    for snapshot in snapshots:
        grid = grid_from_snapshot(snapshot)
        for region in regions:
            key = (region.pk, snapshot.world_minutes)
            if key in existing:
                continue
            generated.append(
                _weather_from_grid(
                    region,
                    snapshot,
                    grid,
                    parameters=parameters,
                )
            )
            existing.add(key)
    WeatherState.objects.bulk_create(generated, batch_size=500)
    return generated
