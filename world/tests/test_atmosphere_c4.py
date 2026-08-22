import math
from array import array

import numpy as np
from django.test import SimpleTestCase, TestCase

from campaigns.models import Campaign
from world.models import AtmosphericConfig, Region
from world.services.atmosphere.circulation import (
    apply_coriolis_rotation,
    circulation_diagnostics,
    pressure_gradient_acceleration,
    spherical_divergence,
    spherical_relative_vorticity,
)
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.coordinate_sampling import sample_environment_at
from world.services.atmosphere.geometry import geometry_for
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.pressure import (
    solve_pressure,
    surface_pressure_from_circulation,
)
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint
from world.services.atmosphere.persistence import (
    sample_campaign_environment_at,
    save_snapshot,
)
from world.services.atmosphere.simulation import initialize_atmosphere
from world.services.atmosphere.static_grid import StaticWorldGrid
from world.services.atmosphere.wind import solve_wind


def settings(width=12, height=6, **parameters):
    world_circumference_km = parameters.pop("world_circumference_km", 72_500)
    step_minutes = parameters.pop("step_minutes", 360)
    defaults = {
        "initial_circulation_pressure_perturbation_hpa": 0.0,
        "pressure_gradient_acceleration_scale": 1.0,
        "land_drag_timescale_hours": 1e12,
        "ocean_drag_timescale_hours": 1e12,
        "terrain_upslope_drag_rate_per_slope_s": 0.0,
        "terrain_ruggedness_drag_rate_per_slope_s": 0.0,
    }
    defaults.update(parameters)
    return AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=step_minutes,
        world_circumference_km=world_circumference_km,
        ocean_temperature_c=40,
        parameters=defaults,
    )


def static_grid(width=12, height=6, elevations=None, ocean_indices=()):
    size = width * height
    elevations = elevations if elevations is not None else [0.0] * size
    ocean_indices = set(ocean_indices)
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=array(
            "b", (1 if index in ocean_indices else 0 for index in range(size))
        ),
        elevation=array("f", elevations),
        mean_temperature=array("f", [10.0] * size),
        biome=tuple(None for _ in range(size)),
    )


def neutral_grid(config):
    grid = AtmosphericGrid.empty(config.width, config.height)
    grid.fields["temperature"].fill(10.0)
    grid.fields["circulation_pressure_hpa"].fill(1000.0)
    grid.fields["pressure_hpa"].fill(1000.0)
    return grid


class SphericalGeometryTests(SimpleTestCase):
    def test_radius_and_metrics_derive_from_fardecosmia_circumference(self):
        geometry = geometry_for(settings())
        self.assertAlmostEqual(
            geometry.planet_radius_m,
            72_500_000 / (2 * math.pi),
            delta=0.001,
        )
        equator = geometry.east_west_cell_m[2]
        near_pole = geometry.east_west_cell_m[0]
        self.assertLess(near_pole, equator)
        self.assertAlmostEqual(
            near_pole / equator,
            math.cos(math.radians(75)) / math.cos(math.radians(15)),
            places=10,
        )

    def test_longitude_wrap_and_polar_diagnostics_are_finite(self):
        config = settings()
        grid = neutral_grid(config)
        geometry = geometry_for(config)
        grid.fields["wind_u"] = np.sin(geometry.longitude_radians).astype(np.float32)
        grid.fields["wind_v"] = np.cos(geometry.latitude_radians).astype(np.float32)
        divergence = spherical_divergence(
            grid.fields["wind_u"], grid.fields["wind_v"], config
        )
        vorticity = spherical_relative_vorticity(
            grid.fields["wind_u"], grid.fields["wind_v"], config
        )
        self.assertEqual(grid.neighbor_index(-1, 2), grid.index(config.width - 1, 2))
        self.assertTrue(np.isfinite(divergence).all())
        self.assertTrue(np.isfinite(vorticity).all())


class CoriolisTests(SimpleTestCase):
    def test_rotation_period_equator_magnitude_and_hemisphere_sign(self):
        config = settings(height=18)
        geometry = geometry_for(config)
        expected_omega = 2 * math.pi / (7.52 * 86_400)
        self.assertAlmostEqual(geometry.angular_velocity_rad_s, expected_omega)
        northern = geometry.coriolis_parameter_s[config.width]
        southern = geometry.coriolis_parameter_s[(config.height - 2) * config.width]
        equatorial_pair = (
            abs(geometry.coriolis_parameter_s[(config.height // 2 - 1) * config.width]),
            abs(geometry.coriolis_parameter_s[(config.height // 2) * config.width]),
        )
        self.assertGreater(abs(northern), max(equatorial_pair))
        self.assertAlmostEqual(northern, -southern, places=14)

    def test_exact_coriolis_preserves_speed_and_rotation_sign_flips_deflection(self):
        positive = settings(height=18)
        negative = settings(height=18, rotation_direction_sign=-1.0)
        u = np.full(positive.width * positive.height, 12.0)
        v = np.full_like(u, 3.0)
        u_after, v_after = apply_coriolis_rotation(u, v, positive)
        _u_reverse, v_reverse = apply_coriolis_rotation(u, v, negative)
        np.testing.assert_allclose(np.hypot(u_after, v_after), np.hypot(u, v))
        index = positive.width
        self.assertLess(v_after[index] - v[index], 0.0)
        self.assertGreater(v_reverse[index] - v[index], 0.0)


class PressureAndWindTests(SimpleTestCase):
    def test_uniform_reduced_pressure_has_no_acceleration(self):
        config = settings()
        acceleration = pressure_gradient_acceleration(
            np.full(config.width * config.height, 1000.0),
            np.full(config.width * config.height, 10.0),
            np.zeros(config.width * config.height),
            config,
        )
        np.testing.assert_array_equal(acceleration[0], 0.0)
        np.testing.assert_array_equal(acceleration[1], 0.0)

    def test_high_west_low_east_accelerates_eastward(self):
        config = settings(rotation_period_days=1e12)
        grid = neutral_grid(config)
        static = static_grid()
        index = grid.index(5, 3)
        grid.fields["circulation_pressure_hpa"][grid.index(4, 3)] = 1010.0
        grid.fields["circulation_pressure_hpa"][grid.index(6, 3)] = 990.0
        u, _v = solve_wind(grid, static, config)
        self.assertGreater(u[index], 0.0)

    def test_elevation_only_changes_surface_not_circulation_pressure(self):
        config = settings()
        circulation = np.full(config.width * config.height, 1000.0)
        elevation = np.zeros_like(circulation)
        elevation[3] = 3000.0
        surface = surface_pressure_from_circulation(
            circulation,
            np.full_like(circulation, 10.0),
            np.zeros_like(circulation),
            elevation,
            config,
        )
        self.assertEqual(circulation[2], circulation[3])
        self.assertLess(surface[3], surface[2])

    def test_reduced_pressure_is_prognostic_and_moves_downwind(self):
        config = settings(
            width=8,
            height=2,
            world_circumference_km=80,
            rotation_period_days=1e12,
            circulation_pressure_relaxation_hours=1e12,
            circulation_pressure_diffusion_fraction=0.0,
        )
        grid = neutral_grid(config)
        static = static_grid(8, 2)
        grid.fields["circulation_pressure_hpa"][grid.index(2, 0)] = 1010.0
        cell_m = geometry_for(config).east_west_cell_m[0]
        grid.fields["wind_u"].fill(cell_m / (config.step_minutes * 60.0))
        solve_pressure(grid, static, config)
        self.assertAlmostEqual(
            grid.fields["circulation_pressure_hpa"][grid.index(3, 0)],
            1010.0,
            delta=0.01,
        )

    def test_drag_damps_persistent_wind(self):
        config = settings(
            rotation_period_days=1e12,
            pressure_gradient_acceleration_scale=0.0,
            land_drag_timescale_hours=6.0,
        )
        grid = neutral_grid(config)
        grid.fields["wind_u"].fill(20.0)
        u, v = solve_wind(grid, static_grid(), config)
        self.assertLess(float(np.hypot(u, v).max()), 20.0)
        self.assertGreater(float(np.hypot(u, v).max()), 0.0)


class FlowAndTerrainTests(SimpleTestCase):
    def test_translation_has_zero_divergence_and_vorticity(self):
        config = settings()
        u = np.full(config.width * config.height, 8.0)
        v = np.zeros_like(u)
        np.testing.assert_allclose(spherical_divergence(u, v, config), 0.0)
        np.testing.assert_allclose(
            spherical_relative_vorticity(np.zeros_like(u), v, config), 0.0
        )

    def test_controlled_convergence_and_rotation_have_expected_signs(self):
        config = settings(width=12, height=6)
        geometry = geometry_for(config)
        centre_x = 6
        u = -(geometry.flat_x - centre_x).astype(np.float64)
        v = np.zeros_like(u)
        divergence = spherical_divergence(u, v, config)
        self.assertLess(divergence[3 * config.width + centre_x], 0.0)
        rotational_v = (geometry.flat_x - centre_x).astype(np.float64)
        vorticity = spherical_relative_vorticity(np.zeros_like(u), rotational_v, config)
        self.assertGreater(vorticity[3 * config.width + centre_x], 0.0)

    def test_flat_terrain_has_no_orographic_motion_and_ramp_changes_sign(self):
        config = settings(width=8, height=2)
        grid = neutral_grid(config)
        grid.fields["wind_u"].fill(10.0)
        flat = circulation_diagnostics(grid, static_grid(8, 2), config)
        np.testing.assert_array_equal(flat["w_orographic_m_s"], 0.0)

        ramp = [float(x * 1000) for _y in range(2) for x in range(8)]
        diagnostics = circulation_diagnostics(
            grid,
            static_grid(8, 2, elevations=ramp),
            config,
        )
        self.assertGreater(diagnostics["w_orographic_m_s"][grid.index(3, 0)], 0.0)
        grid.fields["wind_u"].fill(-10.0)
        reverse = circulation_diagnostics(
            grid,
            static_grid(8, 2, elevations=ramp),
            config,
        )
        self.assertLess(reverse["w_orographic_m_s"][grid.index(3, 0)], 0.0)
        self.assertTrue(np.isfinite(diagnostics["terrain_slope"]).all())


class CoordinateSamplingTests(SimpleTestCase):
    def test_arbitrary_bilinear_sample_is_deterministic_and_read_only(self):
        config = settings(width=4, height=2)
        static = static_grid(4, 2, elevations=[0, 100, 200, 300] * 2)
        grid = neutral_grid(config)
        grid.fields["temperature"] = np.arange(8, dtype=np.float32)
        before = grid.serialize()
        first = sample_environment_at(grid, static, config, 0.0, 0.0)
        second = sample_environment_at(grid, static, config, 0.0, 0.0)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first.values["temperature"], 3.5)
        self.assertEqual(grid.serialize(), before)

    def test_longitude_seam_interpolates_without_region(self):
        config = settings(width=4, height=2)
        static = static_grid(4, 2)
        grid = neutral_grid(config)
        grid.fields["temperature"] = np.array([0, 10, 20, 30] * 2, dtype=np.float32)
        west = sample_environment_at(grid, static, config, 0.0, -180.0)
        east = sample_environment_at(grid, static, config, 0.0, 180.0)
        self.assertEqual(west, east)
        self.assertAlmostEqual(west.values["temperature"], 15.0)

    def test_steep_relief_rederives_pressure_at_local_continuous_elevation(self):
        config = settings(width=4, height=2)
        elevations = np.array(
            [0.0, 0.0, 6000.0, 0.0, 0.0, 0.0, 6000.0, 0.0],
            dtype=np.float64,
        )
        static = static_grid(4, 2, elevations=elevations)
        grid = neutral_grid(config)
        grid.fields["temperature"].fill(20.0)
        grid.fields["water_vapor_specific_humidity"].fill(0.01)
        grid.fields["circulation_pressure_hpa"].fill(1000.0)
        grid.fields["pressure_hpa"] = surface_pressure_from_circulation(
            grid.fields["circulation_pressure_hpa"],
            grid.fields["temperature"],
            grid.fields["water_vapor_specific_humidity"],
            elevations,
            config,
        ).astype(np.float32)

        point = sample_environment_at(
            grid,
            static,
            config,
            0.0,
            0.0,
            local_elevation_m=-15.0,
        )
        expected = float(
            surface_pressure_from_circulation(
                1000.0,
                20.0,
                0.01,
                -15.0,
                config,
            )
        )

        self.assertEqual(point.elevation_m, -15.0)
        self.assertAlmostEqual(point.values["pressure_hpa"], expected)
        self.assertLess(point.interpolated_grid_surface_pressure_hpa, 800.0)
        self.assertGreater(point.values["pressure_hpa"], 1000.0)

    def test_static_fallback_interpolates_elevation_before_pressure(self):
        config = settings(width=4, height=2)
        elevations = np.array(
            [0.0, 0.0, 6000.0, 0.0, 0.0, 0.0, 6000.0, 0.0],
            dtype=np.float64,
        )
        static = static_grid(4, 2, elevations=elevations)
        grid = neutral_grid(config)
        grid.fields["temperature"].fill(20.0)
        grid.fields["water_vapor_specific_humidity"].fill(0.01)
        grid.fields["circulation_pressure_hpa"].fill(1000.0)
        grid.fields["pressure_hpa"] = surface_pressure_from_circulation(
            grid.fields["circulation_pressure_hpa"],
            grid.fields["temperature"],
            grid.fields["water_vapor_specific_humidity"],
            elevations,
            config,
        ).astype(np.float32)

        point = sample_environment_at(grid, static, config, 0.0, 0.0)
        expected = float(
            surface_pressure_from_circulation(
                1000.0,
                20.0,
                0.01,
                3000.0,
                config,
            )
        )

        self.assertAlmostEqual(point.elevation_m, 3000.0)
        self.assertAlmostEqual(point.values["pressure_hpa"], expected)


class CampaignCoordinateSamplingTests(TestCase):
    def test_campaign_sampler_needs_no_region_and_does_not_advance_time(self):
        campaign = Campaign.objects.create(name="C4 coordinate sampling")
        config = AtmosphericConfig.objects.create(
            campaign=campaign,
            enabled=True,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            ocean_temperature_c=40.0,
        )
        config_settings = AtmosphericSettings.from_model(config, campaign)
        grid, _static = initialize_atmosphere(config_settings, world_minutes=0)
        save_snapshot(
            campaign,
            0,
            grid,
            input_fingerprint=atmospheric_input_fingerprint(campaign, config),
        )
        before_time = campaign.world_minutes
        before_regions = Region.objects.count()

        first = sample_campaign_environment_at(campaign, 12.5, -33.25)
        second = sample_campaign_environment_at(campaign, 12.5, -33.25)

        campaign.refresh_from_db()
        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertEqual(Region.objects.count(), before_regions)
        self.assertEqual(before_regions, 0)
        self.assertEqual(campaign.world_minutes, before_time)
