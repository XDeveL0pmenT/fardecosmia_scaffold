"""Configurable technical defaults for the prototype atmospheric solver.

These values are numerical stability controls, not statements about canon.
Campaigns may override every coefficient through ``AtmosphericConfig.parameters``.
"""


ATMOSPHERIC_FORMAT_VERSION = 1
ATMOSPHERIC_DEFAULT_WIDTH = 180
ATMOSPHERIC_DEFAULT_HEIGHT = 90
ATMOSPHERIC_DEFAULT_STEP_MINUTES = 360


def default_atmospheric_parameters():
    return {
        "reference_pressure_hpa": 1000.0,
        "pressure_scale_height_m": 8500.0,
        "pressure_temperature_factor": 0.7,
        "pressure_relaxation": 0.25,
        "pressure_neighbor_smoothing": 0.15,
        "pressure_noise_hpa": 0.18,
        "minimum_pressure_hpa": 50.0,
        "maximum_pressure_hpa": 2000.0,
        "wind_pressure_factor": 0.18,
        "wind_thermal_factor": 0.02,
        "coriolis_factor": 0.08,
        "land_wind_retention": 0.70,
        "ocean_wind_retention": 0.88,
        "terrain_blocking_per_1000m": 0.18,
        "minimum_terrain_wind_fraction": 0.10,
        "minimum_polar_cell_cosine": 0.05,
        "initial_land_humidity": 50.0,
        "initial_ocean_humidity": 78.0,
        "initial_temperature_noise_c": 0.4,
        "ocean_moisture_exchange": 0.12,
        "ocean_heat_exchange": 0.10,
        "land_temperature_exchange": 0.08,
        "cloud_threshold_humidity": 65.0,
        "cloud_response": 0.55,
        "precipitation_humidity_threshold": 78.0,
        "base_condensation_rate": 0.12,
        "precipitation_rate_scale": 10.0,
        "condensation_humidity_loss": 20.0,
        "orographic_lift_per_1000m": 0.18,
        "rain_shadow_drying_per_1000m": 6.0,
        "max_wind_speed_m_s": 80.0,
        "condition_precipitation_threshold": 0.15,
        "condition_storm_precipitation_threshold": 1.5,
        "condition_storm_wind_threshold": 18.0,
        "condition_fog_humidity_threshold": 92.0,
        "condition_fog_wind_max": 3.0,
        "condition_cloud_cover_threshold": 0.45,
        # Hooks for the established local-sky service. Zero means that the
        # prototype does not assert an unknown canonical heat contribution.
        "star_heating_c": 0.0,
        "ympha_heating_c": 0.0,
    }
