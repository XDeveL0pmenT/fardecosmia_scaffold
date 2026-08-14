import numpy as np

from .geometry import geometry_for


def advect_array(
    values,
    wind_u,
    wind_v,
    settings,
    *,
    minutes=None,
    geometry=None,
):
    """Vectorized semi-Lagrangian backtrace on the equirectangular sphere.

    Scalar and vector-component fields share this transport operator.  The
    latter is a documented single-layer approximation: components stay in the
    local east/north basis while longitude wraps periodically.
    """

    geometry = geometry or geometry_for(settings)
    seconds = (settings.step_minutes if minutes is None else float(minutes)) * 60.0
    wind_u = np.asarray(wind_u, dtype=np.float64).reshape(
        settings.height,
        settings.width,
    )
    wind_v = np.asarray(wind_v, dtype=np.float64).reshape(
        settings.height,
        settings.width,
    )
    source_x = (
        geometry.x
        - wind_u * seconds / geometry.east_west_cell_m[:, np.newaxis]
    ) % settings.width
    source_y = np.clip(
        geometry.y + wind_v * seconds / geometry.north_south_cell_m,
        0.0,
        settings.height - 1.0,
    )

    x0 = np.floor(source_x).astype(np.int32)
    y0 = np.floor(source_y).astype(np.int32)
    x1 = (x0 + 1) % settings.width
    y1 = np.minimum(settings.height - 1, y0 + 1)
    tx = source_x - x0
    ty = source_y - y0
    source = np.asarray(values, dtype=np.float64).reshape(
        settings.height,
        settings.width,
    )
    top = source[y0, x0] * (1.0 - tx) + source[y0, x1] * tx
    bottom = source[y1, x0] * (1.0 - tx) + source[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).astype(np.float32).reshape(-1)


def advect_scalar(grid, field, settings):
    """Stable semi-Lagrangian backtrace with wrapped longitude."""
    return advect_array(
        grid.fields[field],
        grid.fields["wind_u"],
        grid.fields["wind_v"],
        settings,
    )


def advect_heat_and_moisture(grid, settings):
    return {
        name: advect_scalar(grid, name, settings)
        for name in (
            "temperature",
            "water_vapor_specific_humidity",
            "cloud_condensate_specific_humidity",
        )
    }


def advect_momentum(grid, settings):
    """Advect prognostic eastward/northward momentum components together."""
    return (
        advect_scalar(grid, "wind_u", settings),
        advect_scalar(grid, "wind_v", settings),
    )
