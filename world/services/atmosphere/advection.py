from array import array


def advect_scalar(grid, field, settings):
    """Stable semi-Lagrangian backtrace with wrapped longitude."""
    result = array("f", [0.0]) * grid.size
    seconds = settings.step_minutes * 60.0
    north_south_cell_km = settings.world_circumference_km / (2.0 * grid.height)
    wind_u = grid.fields["wind_u"]
    wind_v = grid.fields["wind_v"]
    for y in range(grid.height):
        import math

        latitude = 90.0 - (y + 0.5) * 180.0 / grid.height
        east_west_cell_km = (
            settings.world_circumference_km
            * max(
                settings.value("minimum_polar_cell_cosine"),
                abs(math.cos(math.radians(latitude))),
            )
            / grid.width
        )
        for x in range(grid.width):
            index = grid.index(x, y)
            x_shift = wind_u[index] * seconds / (east_west_cell_km * 1000.0)
            y_shift = wind_v[index] * seconds / (north_south_cell_km * 1000.0)
            result[index] = grid.bilinear_sample(
                field,
                x - x_shift,
                y + y_shift,
            )
    return result


def advect_heat_and_moisture(grid, settings):
    return {
        name: advect_scalar(grid, name, settings)
        for name in ("temperature", "relative_humidity", "water_content")
    }
