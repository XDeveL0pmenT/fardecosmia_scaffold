import numpy as np

from .forcing import ZeroRadiativeForcing
from .geometry import geometry_for


def surface_temperature_target(
    static,
    settings,
    *,
    world_minutes,
    forcing=None,
    radiative_grid=None,
):
    forcing = forcing or ZeroRadiativeForcing()
    geometry = geometry_for(settings)
    baseline = np.asarray(static.mean_temperature, dtype=np.float64).copy()
    adjustment = (
        radiative_grid.total_radiative_anomaly_c
        if radiative_grid is not None
        else forcing.temperature_adjustment_grid(geometry, world_minutes)
    )
    adjustment = np.asarray(adjustment, dtype=np.float64).reshape(-1)
    if adjustment.size != baseline.size:
        raise ValueError("Размер radiative forcing не совпадает с атмосферной сеткой.")
    return baseline + adjustment

def apply_surface_exchange(
    grid,
    static,
    settings,
    *,
    world_minutes,
    forcing=None,
    radiative_grid=None,
):
    forcing = forcing or ZeroRadiativeForcing()
    ocean_mask = np.asarray(static.is_ocean, dtype=np.bool_)

    target = surface_temperature_target(
        static,
        settings,
        world_minutes=world_minutes,
        forcing=forcing,
        radiative_grid=radiative_grid,
    )
    temperature = grid.fields["temperature"].astype(np.float64)
    land = ~ocean_mask
    temperature[land] += (
        target[land] - temperature[land]
    ) * settings.value("land_temperature_exchange")

    surface = grid.fields["surface_temperature"].astype(np.float64)
    surface[land] = target[land]
    grid.fields["surface_temperature"] = surface.astype(np.float32)
    grid.fields["temperature"] = temperature.astype(np.float32)
