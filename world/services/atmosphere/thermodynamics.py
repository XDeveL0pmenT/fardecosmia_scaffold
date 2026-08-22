"""Vectorized Phase C2 water-vapor thermodynamics.

Specific humidity (kg water / kg moist air) is the prognostic moisture field.
Relative humidity is always derived from q, temperature and pressure.
"""

from __future__ import annotations

import numpy as np


SATURATION_FORMULA_VERSION = 1
REFERENCE_TEMPERATURE_K = 273.15
REFERENCE_VAPOR_PRESSURE_PA = 611.2
WATER_VAPOR_GAS_CONSTANT_J_KG_K = 461.5
DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG = 2_500_000.0
DRY_TO_VAPOR_MASS_RATIO = 0.622
MAX_VAPOR_PRESSURE_FRACTION = 0.98


def _record(diagnostics, key, count):
    if diagnostics is not None and count:
        diagnostics[key] = diagnostics.get(key, 0) + int(count)


def saturation_vapor_pressure_pa(
    temperature_c,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
):
    temperature_k = np.asarray(temperature_c, dtype=np.float64) + 273.15
    # These are numerical-domain safeguards, not a climate range.
    temperature_k = np.clip(temperature_k, 120.0, 500.0)
    exponent = (
        float(latent_heat_j_kg)
        / WATER_VAPOR_GAS_CONSTANT_J_KG_K
        * (1.0 / REFERENCE_TEMPERATURE_K - 1.0 / temperature_k)
    )
    return REFERENCE_VAPOR_PRESSURE_PA * np.exp(np.clip(exponent, -80.0, 80.0))


def saturation_specific_humidity(
    temperature_c,
    pressure_hpa,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
    diagnostics=None,
):
    pressure_pa = np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0)
    vapor_pressure = saturation_vapor_pressure_pa(
        temperature_c,
        latent_heat_j_kg=latent_heat_j_kg,
    )
    maximum = pressure_pa * MAX_VAPOR_PRESSURE_FRACTION
    unsafe = vapor_pressure >= maximum
    _record(diagnostics, "saturation_pressure_cap_cells", np.count_nonzero(unsafe))
    vapor_pressure = np.minimum(vapor_pressure, maximum)
    denominator = pressure_pa - (1.0 - DRY_TO_VAPOR_MASS_RATIO) * vapor_pressure
    denominator = np.maximum(1e-9, denominator)
    return DRY_TO_VAPOR_MASS_RATIO * vapor_pressure / denominator


def saturation_specific_humidity_temperature_derivative(
    temperature_c,
    pressure_hpa,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
):
    """Analytic d(q_sat)/dT for the uncapped Clausius-Clapeyron branch."""

    temperature_k = np.clip(
        np.asarray(temperature_c, dtype=np.float64) + 273.15,
        120.0,
        500.0,
    )
    pressure_pa = np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0)
    vapor_pressure = saturation_vapor_pressure_pa(
        temperature_c,
        latent_heat_j_kg=latent_heat_j_kg,
    )
    maximum = pressure_pa * MAX_VAPOR_PRESSURE_FRACTION
    capped = vapor_pressure >= maximum
    vapor_pressure = np.minimum(vapor_pressure, maximum)
    denominator = np.maximum(
        1e-9,
        pressure_pa - (1.0 - DRY_TO_VAPOR_MASS_RATIO) * vapor_pressure,
    )
    de_dt = (
        vapor_pressure
        * float(latent_heat_j_kg)
        / (WATER_VAPOR_GAS_CONSTANT_J_KG_K * temperature_k**2)
    )
    dq_de = DRY_TO_VAPOR_MASS_RATIO * pressure_pa / denominator**2
    return np.where(capped, 0.0, dq_de * de_dt)


def saturation_specific_humidity_with_temperature_derivative(
    temperature_c,
    pressure_hpa,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
    diagnostics=None,
):
    """Return q_sat and d(q_sat)/dT with one vapor-pressure evaluation."""

    temperature_k = np.clip(
        np.asarray(temperature_c, dtype=np.float64) + 273.15,
        120.0,
        500.0,
    )
    pressure_pa = np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0)
    vapor_pressure = saturation_vapor_pressure_pa(
        temperature_c,
        latent_heat_j_kg=latent_heat_j_kg,
    )
    maximum = pressure_pa * MAX_VAPOR_PRESSURE_FRACTION
    capped = vapor_pressure >= maximum
    _record(diagnostics, "saturation_pressure_cap_cells", np.count_nonzero(capped))
    vapor_pressure = np.minimum(vapor_pressure, maximum)
    denominator = np.maximum(
        1e-9,
        pressure_pa - (1.0 - DRY_TO_VAPOR_MASS_RATIO) * vapor_pressure,
    )
    q_sat = DRY_TO_VAPOR_MASS_RATIO * vapor_pressure / denominator
    de_dt = (
        vapor_pressure
        * float(latent_heat_j_kg)
        / (WATER_VAPOR_GAS_CONSTANT_J_KG_K * temperature_k**2)
    )
    dq_de = DRY_TO_VAPOR_MASS_RATIO * pressure_pa / denominator**2
    derivative = np.where(capped, 0.0, dq_de * de_dt)
    return q_sat, derivative


def vapor_pressure_from_specific_humidity(specific_humidity, pressure_hpa):
    q_v = np.maximum(0.0, np.asarray(specific_humidity, dtype=np.float64))
    pressure_pa = np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0)
    denominator = DRY_TO_VAPOR_MASS_RATIO + (
        1.0 - DRY_TO_VAPOR_MASS_RATIO
    ) * q_v
    return q_v * pressure_pa / np.maximum(1e-9, denominator)


def relative_humidity_percent(
    specific_humidity,
    temperature_c,
    pressure_hpa,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
):
    actual = vapor_pressure_from_specific_humidity(specific_humidity, pressure_hpa)
    saturation = saturation_vapor_pressure_pa(
        temperature_c,
        latent_heat_j_kg=latent_heat_j_kg,
    )
    return 100.0 * actual / np.maximum(1e-9, saturation)


def specific_humidity_from_relative_humidity(
    relative_humidity_percent_value,
    temperature_c,
    pressure_hpa,
    *,
    latent_heat_j_kg=DEFAULT_LATENT_HEAT_VAPORIZATION_J_KG,
    diagnostics=None,
):
    fraction = np.maximum(
        0.0,
        np.asarray(relative_humidity_percent_value, dtype=np.float64) / 100.0,
    )
    pressure_pa = np.maximum(1.0, np.asarray(pressure_hpa, dtype=np.float64) * 100.0)
    vapor_pressure = fraction * saturation_vapor_pressure_pa(
        temperature_c,
        latent_heat_j_kg=latent_heat_j_kg,
    )
    maximum = pressure_pa * MAX_VAPOR_PRESSURE_FRACTION
    unsafe = vapor_pressure >= maximum
    _record(diagnostics, "relative_humidity_pressure_cap_cells", np.count_nonzero(unsafe))
    vapor_pressure = np.minimum(vapor_pressure, maximum)
    denominator = pressure_pa - (
        1.0 - DRY_TO_VAPOR_MASS_RATIO
    ) * vapor_pressure
    return (
        DRY_TO_VAPOR_MASS_RATIO
        * vapor_pressure
        / np.maximum(1e-9, denominator)
    )
