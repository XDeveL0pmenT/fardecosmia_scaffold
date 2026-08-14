"""Prognostic reduced pressure and diagnostic local surface pressure."""

from __future__ import annotations

import math

import numpy as np

from .advection import advect_array
from .circulation import virtual_temperature_k
from .deterministic import deterministic_signed_array
from .geometry import geometry_for


def circulation_pressure_target(temperature, mean_temperature, q_v, settings):
    temperature = np.asarray(temperature, dtype=np.float64)
    baseline = np.asarray(mean_temperature, dtype=np.float64)
    q_v = np.asarray(q_v, dtype=np.float64)
    virtual_anomaly = virtual_temperature_k(temperature, q_v, settings) - (
        baseline + 273.15
    )
    return (
        settings.value("circulation_reference_pressure_hpa")
        - settings.value("circulation_pressure_temperature_factor_hpa_k")
        * virtual_anomaly
    )


def surface_pressure_from_circulation(
    circulation_pressure_hpa,
    temperature,
    q_v,
    elevation,
    settings,
):
    gravity = settings.value("fardecosmia_gravity_m_s2")
    gas_constant = max(1.0, settings.value("dry_air_gas_constant_j_kg_k"))
    virtual_temperature = virtual_temperature_k(temperature, q_v, settings)
    elevation = np.asarray(elevation, dtype=np.float64)
    exponent = np.clip(
        -gravity * elevation / (gas_constant * virtual_temperature),
        -20.0,
        20.0,
    )
    return np.asarray(circulation_pressure_hpa, dtype=np.float64) * np.exp(exponent)


def pressure_for_cell(temperature, mean_temperature, elevation, settings):
    circulation = float(
        circulation_pressure_target(temperature, mean_temperature, 0.0, settings)
    )
    return float(
        surface_pressure_from_circulation(
            circulation,
            temperature,
            0.0,
            elevation,
            settings,
        )
    )


def pressure_for_arrays(temperature, mean_temperature, elevation, settings):
    circulation = circulation_pressure_target(
        temperature,
        mean_temperature,
        np.zeros_like(np.asarray(temperature, dtype=np.float64)),
        settings,
    )
    return surface_pressure_from_circulation(
        circulation,
        temperature,
        0.0,
        elevation,
        settings,
    )


def initialize_pressure_fields(temperature, mean_temperature, q_v, elevation, settings):
    circulation = circulation_pressure_target(
        temperature,
        mean_temperature,
        q_v,
        settings,
    )
    perturbation_size = max(
        0.0,
        settings.value("initial_circulation_pressure_perturbation_hpa"),
    )
    if perturbation_size:
        indices = np.arange(np.size(circulation), dtype=np.uint64)
        circulation = circulation + perturbation_size * deterministic_signed_array(
            settings.world_seed,
            0,
            indices,
            41,
        )
    circulation = np.clip(
        circulation,
        settings.value("minimum_circulation_pressure_hpa"),
        settings.value("maximum_circulation_pressure_hpa"),
    )
    surface = surface_pressure_from_circulation(
        circulation,
        temperature,
        q_v,
        elevation,
        settings,
    )
    return circulation.astype(np.float32), surface.astype(np.float32)


def solve_pressure(grid, static, settings, step_index=None, *, diagnostics=None):
    """Advect/relax reduced pressure and return derived local pressure."""

    del step_index  # C4 noise is initialized once, never re-rolled each step.
    geometry = geometry_for(settings)
    previous = grid.fields["circulation_pressure_hpa"].astype(np.float64)
    advected = advect_array(
        previous,
        grid.fields["wind_u"],
        grid.fields["wind_v"],
        settings,
        geometry=geometry,
    ).astype(np.float64)
    target = circulation_pressure_target(
        grid.fields["temperature"],
        static.mean_temperature,
        grid.fields["water_vapor_specific_humidity"],
        settings,
    )
    seconds = settings.step_minutes * 60.0
    tau = max(
        1.0,
        settings.value("circulation_pressure_relaxation_hours") * 3600.0,
    )
    relaxation = 1.0 - math.exp(-seconds / tau)
    updated = advected + relaxation * (target - advected)
    diffusion = np.clip(
        settings.value("circulation_pressure_diffusion_fraction"),
        0.0,
        1.0,
    )
    neighbor_mean = (
        updated[geometry.west]
        + updated[geometry.east]
        + updated[geometry.north]
        + updated[geometry.south]
    ) * 0.25
    updated += diffusion * (neighbor_mean - updated)
    minimum = settings.value("minimum_circulation_pressure_hpa")
    maximum = settings.value("maximum_circulation_pressure_hpa")
    clamp_hits = int(np.count_nonzero((updated < minimum) | (updated > maximum)))
    updated = np.clip(updated, minimum, maximum)
    grid.fields["circulation_pressure_hpa"] = updated.astype(np.float32)
    if diagnostics is not None:
        diagnostics["pressure_cap_hits"] = diagnostics.get("pressure_cap_hits", 0) + clamp_hits
    return surface_pressure_from_circulation(
        updated,
        grid.fields["temperature"],
        grid.fields["water_vapor_specific_humidity"],
        static.elevation,
        settings,
    ).astype(np.float32)
