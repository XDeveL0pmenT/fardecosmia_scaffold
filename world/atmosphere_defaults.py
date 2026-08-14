"""Configurable technical defaults for the prototype atmospheric solver.

These values are numerical stability controls, not statements about canon.
Campaigns may override every coefficient through ``AtmosphericConfig.parameters``.
"""


ATMOSPHERIC_FORMAT_VERSION = 4
ATMOSPHERIC_SOLVER_VERSION = 7
ATMOSPHERIC_DEFAULT_WIDTH = 180
ATMOSPHERIC_DEFAULT_HEIGHT = 90
ATMOSPHERIC_DEFAULT_STEP_MINUTES = 360

# NumPy evaluates the same prototype equations in a different grouping than
# the former scalar Python loops.  These bounds define the accepted numerical
# equivalence against the captured Phase B scalar regression fixture.
ATMOSPHERIC_NUMERICAL_ATOL = 1e-4
ATMOSPHERIC_NUMERICAL_RTOL = 1e-6


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
        # Phase C1 calibration controls.  Astronomical distances, luminosity,
        # axial tilt and periods live in orbital_climate.py as canon; response
        # coefficients and safeguards below remain explicit technical knobs.
        "stellar_response_c": 12.0,
        "ympha_response_c": 1.5,
        "axial_tilt_deg": 8.79,
        "axial_phase_deg": 109.0,
        "stellar_anomaly_min_c": -30.0,
        "stellar_anomaly_max_c": 40.0,
        "ympha_anomaly_max_c": 3.0,
        "total_radiative_anomaly_min_c": -30.0,
        "total_radiative_anomaly_max_c": 42.0,
        # Phase C2 ocean mixed layer and physical vapor.  These are explicit
        # technical calibration values, not additional world canon.
        "fardecosmia_gravity_m_s2": 9.98,
        "water_density_kg_m3": 1000.0,
        "water_heat_capacity_j_kg_k": 4180.0,
        "air_heat_capacity_j_kg_k": 1005.0,
        "air_density_kg_m3": 1.2,
        "latent_heat_vaporization_j_kg": 2500000.0,
        "ocean_mixed_layer_depth_m": 50.0,
        "ocean_absorptivity": 0.75,
        "ocean_deep_relaxation_days": 720.0,
        "ocean_sensible_transfer_coefficient": 0.0012,
        "ocean_sensible_min_wind_m_s": 0.5,
        "ocean_evaporation_transfer_coefficient": 0.0012,
        "ocean_evaporation_min_wind_m_s": 0.3,
        "ocean_climatological_evaporation_wind_m_s": 5.0,
        "ocean_horizontal_mixing_w_m2_k": 4.0,
        "ocean_min_sst_c": -120.0,
        "ocean_max_sst_c": 120.0,
        "ocean_max_sst_change_per_step_c": 1.0,
        "air_max_sensible_change_per_step_c": 3.0,
        "max_specific_humidity_change_per_step": 0.02,
        "max_supersaturation_ratio": 500.0,
        "maximum_specific_humidity": 0.6,
        "maximum_evaporation_kg_m2_s": 0.003,
        "fast_forward_ocean_step_minutes": 10080.0,
        "fast_forward_ocean_max_steps": 512.0,
        "fast_forward_forcing_samples": 7.0,
        "fast_forward_legacy_rotation_mean": 0.0,
        "fast_forward_boundary_grid_max_width": 24.0,
        "fast_forward_boundary_grid_max_height": 12.0,
        "fast_forward_boundary_substep_minutes": 360.0,
        "fast_forward_boundary_max_steps": 2000.0,
        "fast_forward_boundary_forcing_samples": 1.0,
        "fast_forward_ocean_wind_m_s": 5.0,
        "fast_forward_wind_spinup_iterations": 0.0,
        "fast_forward_ocean_boundary_layer_enabled": 1.0,
        "fast_forward_wind_updates_per_substep": 1.0,
        "fast_forward_minimum_effective_wind_m_s": 0.3,
        "fast_forward_analytic_deep_relaxation": 1.0,
        "fast_forward_atmospheric_heat_mixing": 1.0,
        "fast_forward_ocean_air_sst_coupling": 0.0,
        "fast_forward_ocean_humidity_blend": 0.15,
        # Phase C3 bulk-column cloud microphysics.  All values below are
        # technical calibration controls, not immutable world canon.
        "saturation_adjustment_tolerance": 1e-8,
        "saturation_adjustment_max_iterations": 6.0,
        "supersaturation_emergency_ratio": 1.01,
        "maximum_cloud_condensate_specific_humidity": 0.2,
        "cloud_ice_temperature_c": -2.0,
        "cloud_liquid_temperature_c": 2.0,
        "cloud_optical_coefficient_m2_kg": 0.22,
        "precipitation_condensate_threshold": 0.00005,
        "precipitation_fallout_timescale_seconds": 21600.0,
        "orographic_cooling_c_per_1000m": 4.5,
        "orographic_descent_warming_c_per_1000m": 2.5,
        "orographic_max_temperature_change_c": 8.0,
        "fog_rh_threshold_percent": 96.0,
        "fog_condensate_threshold": 0.000005,
        "fog_wind_max_m_s": 5.0,
        "fog_lowland_elevation_m": 600.0,
        "condition_precipitation_rate_mm_h": 0.05,
        "condition_storm_precipitation_rate_mm_h": 7.5,
        "condition_storm_cloud_cover": 0.8,
        "condition_fog_potential_threshold": 0.6,
        # Optional-composition/human-summary thresholds remain configurable.
        "human_reference_pressure_hpa": 1000.0,
        "heat_corruption_lowland_elevation_m": 500.0,
        # Phase C4 single-layer circulation.  The rotation period and gravity
        # are confirmed world inputs.  The rotation sign and all response/
        # damping coefficients remain explicit technical assumptions.
        "rotation_period_days": 7.52,
        "rotation_direction_sign": 1.0,
        "dry_air_gas_constant_j_kg_k": 287.05,
        "virtual_temperature_moisture_coefficient": 0.61,
        "circulation_reference_pressure_hpa": 1000.0,
        "circulation_pressure_temperature_factor_hpa_k": 0.55,
        "circulation_pressure_relaxation_hours": 72.0,
        "circulation_pressure_diffusion_fraction": 0.08,
        "initial_circulation_pressure_perturbation_hpa": 0.6,
        "minimum_circulation_pressure_hpa": 820.0,
        "maximum_circulation_pressure_hpa": 1180.0,
        "pressure_gradient_acceleration_scale": 0.22,
        "land_drag_timescale_hours": 18.0,
        "ocean_drag_timescale_hours": 36.0,
        "terrain_upslope_drag_rate_per_slope_s": 0.0010,
        "terrain_ruggedness_drag_rate_per_slope_s": 0.0004,
        "effective_mixing_depth_m": 1800.0,
        # Coupling applies only to the diagnosed convergence component.
        # Orographic u*grad(h) already is a physical vertical velocity.
        "vertical_motion_coupling": 0.12,
        "effective_adiabatic_lapse_rate_c_per_km": 4.5,
        "maximum_vertical_motion_proxy_m_s": 2.5,
        "maximum_vertical_temperature_change_c": 8.0,
        "circulation_pressure_emergency_margin_hpa": 0.01,
    }
