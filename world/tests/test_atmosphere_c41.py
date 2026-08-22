from array import array
import math

import numpy as np
from django.test import SimpleTestCase, TestCase

from campaigns.models import Campaign
from world.models import Region, WeatherState
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.coordinate_sampling import sample_environment_at
from world.services.atmosphere.circulation import vertical_motion_fields
from world.services.atmosphere.forcing import CampaignSkyForcing, ZeroRadiativeForcing
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.pressure import surface_pressure_from_circulation
from world.services.atmosphere.sampling import _weather_from_grid_at_time
from world.services.atmosphere.simulation import initialize_atmosphere, simulate_step
from world.services.atmosphere.static_grid import StaticWorldGrid, build_static_world_grid
from world.services.atmosphere.thermodynamics import saturation_specific_humidity
from world.services.environment_summary import build_environment_summary
from world.services.orbital_climate import CANONICAL_YEAR_MINUTES
from world.services.weather_display import build_weather_summary


def settings(width=36, height=2, **parameters):
    defaults = {
        "initial_temperature_noise_c": 0.0,
        "initial_circulation_pressure_perturbation_hpa": 0.0,
        "pressure_gradient_acceleration_scale": 0.0,
        "rotation_period_days": 1e12,
        "land_drag_timescale_hours": 1e12,
        "ocean_drag_timescale_hours": 1e12,
        "terrain_upslope_drag_rate_per_slope_s": 0.0,
        "terrain_ruggedness_drag_rate_per_slope_s": 0.0,
        "land_temperature_exchange": 0.0,
    }
    defaults.update(parameters)
    return AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=360,
        world_seed=401,
        ocean_temperature_c=40.0,
        parameters=defaults,
    )


def static_grid(width, height, elevations, ocean_columns):
    ocean_columns = set(ocean_columns)
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=array(
            "b",
            (
                1 if index % width in ocean_columns else 0
                for index in range(width * height)
            ),
        ),
        elevation=array("f", elevations * height),
        mean_temperature=array("f", [20.0] * width * height),
        biome=tuple(None for _ in range(width * height)),
    )


class HydrologicalSanityScenarioTests(SimpleTestCase):
    def test_physical_orographic_velocity_is_not_scaled_as_convergence_proxy(self):
        width, height = 8, 2
        config = settings(width, height, vertical_motion_coupling=0.12)
        elevations = [float(x * 1000) for x in range(width)]
        static = static_grid(width, height, elevations, ())
        grid = AtmosphericGrid.empty(width, height)
        grid.fields["wind_u"].fill(10.0)
        grid.fields["wind_v"].fill(0.0)

        vertical = vertical_motion_fields(grid, static, config)
        index = grid.index(3, 0)

        self.assertGreater(vertical["w_orographic_m_s"][index], 0.0)
        self.assertAlmostEqual(vertical["w_convergence_m_s"][index], 0.0)
        self.assertAlmostEqual(
            vertical["vertical_motion_proxy_m_s"][index],
            vertical["w_orographic_m_s"][index],
        )

    def test_hot_ocean_moist_flow_precipitates_windward_more_than_lee(self):
        width, height = 36, 2
        config = settings(width, height)
        elevations = [0.0] * width
        elevations[15] = 1500.0
        elevations[16] = 3000.0
        elevations[17] = 1500.0
        static = static_grid(width, height, elevations, range(0, 12))
        grid, _ = initialize_atmosphere(
            config,
            static=static,
            world_minutes=0,
            forcing=ZeroRadiativeForcing(),
        )
        grid.fields["temperature"].fill(20.0)
        grid.fields["circulation_pressure_hpa"].fill(1000.0)
        grid.fields["wind_u"].fill(60.0)
        grid.fields["wind_v"].fill(0.0)
        dry_q = float(saturation_specific_humidity(20.0, 1000.0)) * 0.995
        moist_q = float(saturation_specific_humidity(20.0, 1000.0)) * 0.999
        grid.fields["water_vapor_specific_humidity"].fill(dry_q)
        for y in range(height):
            for x in range(12):
                grid.fields["water_vapor_specific_humidity"][grid.index(x, y)] = moist_q
        grid.fields["cloud_condensate_specific_humidity"].fill(0.0)
        grid.fields["pressure_hpa"] = surface_pressure_from_circulation(
            grid.fields["circulation_pressure_hpa"],
            grid.fields["temperature"],
            grid.fields["water_vapor_specific_humidity"],
            static.elevation,
            config,
        ).astype(np.float32)

        initial_downwind_q = float(
            grid.fields["water_vapor_specific_humidity"][grid.index(14, 0)]
        )
        diagnostics = {}
        integrated = np.zeros(grid.size, dtype=np.float64)
        maximum_q_c = 0.0
        for step in range(1, 29):
            grid = simulate_step(
                grid,
                static,
                config,
                step_index=step,
                world_minutes=step * config.step_minutes,
                forcing=ZeroRadiativeForcing(),
                diagnostics=diagnostics,
            )
            integrated += (
                grid.fields["precipitation_rate"].astype(np.float64)
                * config.step_minutes
                * 60.0
            )
            maximum_q_c = max(
                maximum_q_c,
                float(np.max(grid.fields["cloud_condensate_specific_humidity"])),
            )

        windward = sum(
            integrated[grid.index(x, y)]
            for y in range(height)
            for x in (15, 16)
        )
        lee = sum(
            integrated[grid.index(x, y)]
            for y in range(height)
            for x in (18, 19)
        )
        self.assertGreater(diagnostics.get("total_evaporated_water_kg", 0.0), 0.0)
        self.assertGreater(
            float(grid.fields["water_vapor_specific_humidity"][grid.index(14, 0)]),
            initial_downwind_q,
        )
        self.assertGreater(
            diagnostics.get("condensation_mass_kg", 0.0),
            0.0,
            diagnostics,
        )
        self.assertGreater(maximum_q_c, 0.0)
        self.assertGreater(diagnostics.get("total_precipitated_mass_kg", 0.0), 0.0)
        self.assertGreater(windward, lee)


class AnnualWorldHydrologyTests(TestCase):
    def test_reduced_real_world_annual_run_is_not_globally_dry(self):
        config = settings(width=12, height=6)
        static = build_static_world_grid(config)
        forcing = CampaignSkyForcing(Campaign(), config)
        grid, _ = initialize_atmosphere(
            config,
            static=static,
            world_minutes=0,
            forcing=forcing,
        )
        diagnostics = {}
        wet = np.zeros(grid.size, dtype=np.bool_)
        steps = CANONICAL_YEAR_MINUTES // config.step_minutes
        for step in range(1, steps + 1):
            grid = simulate_step(
                grid,
                static,
                config,
                step_index=step,
                world_minutes=step * config.step_minutes,
                forcing=forcing,
                diagnostics=diagnostics,
            )
            wet |= grid.fields["precipitation_rate"] > 0.0

        self.assertGreater(diagnostics.get("total_evaporated_water_kg", 0.0), 0.0)
        self.assertGreater(diagnostics.get("condensation_mass_kg", 0.0), 0.0)
        self.assertGreater(diagnostics.get("total_precipitated_mass_kg", 0.0), 0.0)
        self.assertGreater(int(np.count_nonzero(wet)), 0)


class WetCellEndToEndTests(TestCase):
    def test_raw_sampler_weather_state_and_human_summary_agree_on_rain(self):
        campaign = Campaign.objects.create(name="C4.1 wet sampling")
        region = Region.objects.create(
            campaign=campaign,
            name="Wet cell",
            map_latitude=45.0,
            map_longitude=-135.0,
        )
        config = settings(width=4, height=2)
        static = static_grid(4, 2, [0.0] * 4, ())
        grid = AtmosphericGrid.empty(4, 2)
        grid.fields["temperature"].fill(10.0)
        grid.fields["pressure_hpa"].fill(1000.0)
        grid.fields["circulation_pressure_hpa"].fill(1000.0)
        grid.fields["water_vapor_specific_humidity"].fill(
            float(saturation_specific_humidity(10.0, 1000.0))
        )
        grid.fields["cloud_condensate_specific_humidity"].fill(0.0001)
        grid.fields["cloud_cover"].fill(0.9)
        grid.fields["precipitation_rate"].fill(1.0 / 3600.0)

        raw_rate = float(grid.fields["precipitation_rate"][0] * 3600.0)
        point = sample_environment_at(grid, static, config, 45.0, -135.0)
        weather = _weather_from_grid_at_time(
            region,
            360,
            grid,
            settings=config,
            static=static,
        )
        weather.save()
        display = build_weather_summary(weather)
        environment = build_environment_summary(weather, elevation_m=0.0)

        self.assertAlmostEqual(point.values["precipitation_rate"] * 3600.0, raw_rate)
        self.assertEqual(weather.condition, WeatherState.Condition.RAIN)
        self.assertEqual(weather.precipitation_rate_mm_h, 1.0)
        self.assertEqual(weather.precipitation_amount_mm, 6.0)
        self.assertIn("дождь", display["precipitation"])
        self.assertNotEqual(environment.precipitation_label, "без осадков")
        self.assertEqual(
            region.weather_history.get(world_minutes=360).precipitation_rate_mm_h,
            1.0,
        )


class NoFakeRainRegressionTests(SimpleTestCase):
    def test_zero_condensate_cannot_produce_precipitation(self):
        from world.services.atmosphere.microphysics import precipitation_fallout

        config = settings(width=4, height=2)
        fallout = precipitation_fallout(
            np.zeros(8),
            np.full(8, 1000.0),
            np.full(8, 15.0),
            config,
        )
        np.testing.assert_array_equal(fallout["rate_mm_h"], 0.0)
