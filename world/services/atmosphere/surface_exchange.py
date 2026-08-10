from .forcing import ZeroRadiativeForcing


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def apply_surface_exchange(
    grid,
    static,
    settings,
    *,
    world_minutes,
    forcing=None,
):
    forcing = forcing or ZeroRadiativeForcing()
    ocean_temperature = None
    if any(static.is_ocean):
        ocean_temperature = settings.require_ocean_temperature()
    for y in range(grid.height):
        latitude = static.latitude_at_row(y)
        for x in range(grid.width):
            index = grid.index(x, y)
            longitude = static.longitude_at_column(x)
            if static.is_ocean[index]:
                target = ocean_temperature
                exchange = settings.value("ocean_heat_exchange")
                humidity_exchange = settings.value("ocean_moisture_exchange")
                grid.fields["relative_humidity"][index] += (
                    100.0 - grid.fields["relative_humidity"][index]
                ) * humidity_exchange
            else:
                target = static.mean_temperature[index] + forcing.temperature_adjustment(
                    latitude,
                    longitude,
                    world_minutes,
                )
                exchange = settings.value("land_temperature_exchange")
            grid.fields["surface_temperature"][index] = target
            grid.fields["temperature"][index] += (
                target - grid.fields["temperature"][index]
            ) * exchange
            grid.fields["relative_humidity"][index] = clamp(
                grid.fields["relative_humidity"][index],
                0.0,
                100.0,
            )
            grid.fields["water_content"][index] = max(
                0.0,
                grid.fields["relative_humidity"][index] / 100.0,
            )

