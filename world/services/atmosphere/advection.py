import numpy as np

from .geometry import geometry_for


def advect_scalar(grid, field, settings):
    """Stable semi-Lagrangian backtrace with wrapped longitude."""
    geometry = geometry_for(settings)
    seconds = settings.step_minutes * 60.0
    wind_u = grid.field_2d("wind_u").astype(np.float64)
    wind_v = grid.field_2d("wind_v").astype(np.float64)
    source_x = (
        geometry.x
        - wind_u * seconds / geometry.east_west_cell_m[:, np.newaxis]
    ) % grid.width
    source_y = np.clip(
        geometry.y + wind_v * seconds / geometry.north_south_cell_m,
        0.0,
        grid.height - 1.0,
    )

    x0 = np.floor(source_x).astype(np.int32)
    y0 = np.floor(source_y).astype(np.int32)
    x1 = (x0 + 1) % grid.width
    y1 = np.minimum(grid.height - 1, y0 + 1)
    tx = source_x - x0
    ty = source_y - y0
    values = grid.field_2d(field).astype(np.float64)
    top = values[y0, x0] * (1.0 - tx) + values[y0, x1] * tx
    bottom = values[y1, x0] * (1.0 - tx) + values[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).astype(np.float32).reshape(-1)


def advect_heat_and_moisture(grid, settings):
    return {
        name: advect_scalar(grid, name, settings)
        for name in (
            "temperature",
            "water_vapor_specific_humidity",
            "cloud_condensate_specific_humidity",
        )
    }
