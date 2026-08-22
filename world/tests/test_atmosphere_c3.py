import math
from array import array

import numpy as np
from django.test import SimpleTestCase

from world.services.atmosphere.advection import advect_scalar
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.microphysics import (
    air_column_mass_kg_m2,
    cloud_cover_from_condensate,
    precipitation_fallout,
    rain_and_snow_fraction,
    saturation_adjustment,
)
from world.services.atmosphere.orography import apply_orographic_temperature_tendency
from world.services.atmosphere.sampling import condition_from_cell
from world.services.atmosphere.static_grid import StaticWorldGrid
from world.services.atmosphere.thermodynamics import (
    relative_humidity_percent,
    saturation_specific_humidity,
)


def settings(width=4, height=2, **overrides):
    return AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=360,
        world_seed=31,
        parameters={
            "initial_temperature_noise_c": 0.0,
            "pressure_noise_hpa": 0.0,
            **overrides,
        },
    )


def static_grid(width, height, *, elevations=None, ocean_indices=()):
    size = width * height
    ocean_indices = set(ocean_indices)
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=array(
            "b",
            [1 if index in ocean_indices else 0 for index in range(size)],
        ),
        elevation=array("f", elevations or [0.0] * size),
        mean_temperature=array("f", [20.0] * size),
        biome=tuple(None for _ in range(size)),
    )


class CondensationTests(SimpleTestCase):
    def test_supersaturation_condenses_warms_and_conserves_enthalpy_and_water(self):
        config = settings()
        temperature = np.full(8, 20.0)
        pressure = np.full(8, 1000.0)
        q_v = np.full(8, 0.03)
        q_c = np.zeros(8)
        cp = config.value("air_heat_capacity_j_kg_k")
        latent = config.value("latent_heat_vaporization_j_kg")
        enthalpy_before = cp * temperature + latent * q_v
        water_before = q_v + q_c

        result = saturation_adjustment(
            temperature,
            pressure,
            q_v,
            q_c,
            config,
        )

        self.assertTrue(np.all(result["q_v"] < q_v))
        self.assertTrue(np.all(result["q_c"] > q_c))
        self.assertTrue(np.all(result["temperature"] > temperature))
        np.testing.assert_allclose(result["q_v"] + result["q_c"], water_before, atol=1e-12)
        np.testing.assert_allclose(
            cp * result["temperature"] + latent * result["q_v"],
            enthalpy_before,
            rtol=1e-12,
            atol=1e-7,
        )
        rh = relative_humidity_percent(
            result["q_v"],
            result["temperature"],
            pressure,
        )
        np.testing.assert_allclose(rh, 100.0, atol=0.01)
        self.assertTrue(np.isfinite(result["temperature"]).all())

    def test_dry_air_evaporates_cloud_cools_and_conserves_water(self):
        config = settings()
        temperature = np.full(8, 20.0)
        pressure = np.full(8, 1000.0)
        q_v = np.full(8, 0.002)
        q_c = np.full(8, 0.004)
        water_before = q_v + q_c

        result = saturation_adjustment(
            temperature,
            pressure,
            q_v,
            q_c,
            config,
        )

        self.assertTrue(np.all(result["q_c"] < q_c))
        self.assertTrue(np.all(result["q_v"] > q_v))
        self.assertTrue(np.all(result["temperature"] < temperature))
        np.testing.assert_allclose(result["q_v"] + result["q_c"], water_before, atol=1e-12)

    def test_saturation_solver_is_bounded_across_extreme_model_domain(self):
        config = settings(width=40, height=10)
        temperature = np.linspace(-110.0, 200.0, config.width * config.height)
        pressure = np.linspace(500.0, 1100.0, config.width * config.height)
        q_sat = saturation_specific_humidity(temperature, pressure)
        q_v = np.minimum(0.5, q_sat * 1.5 + 0.001)

        result = saturation_adjustment(
            temperature,
            pressure,
            q_v,
            np.zeros_like(q_v),
            config,
        )

        rh = relative_humidity_percent(
            result["q_v"],
            result["temperature"],
            pressure,
        )
        self.assertLessEqual(float(np.max(rh)), 100.01)
        np.testing.assert_allclose(result["q_v"] + result["q_c"], q_v, atol=1e-12)
        self.assertTrue(np.isfinite(result["temperature"]).all())


class PrecipitationTests(SimpleTestCase):
    def test_fallout_uses_condensate_removes_mass_and_converts_to_mm_h(self):
        config = settings()
        q_c = np.full(8, 0.001)
        result = precipitation_fallout(
            q_c,
            np.full(8, 1000.0),
            np.full(8, 20.0),
            config,
        )

        self.assertTrue(np.all(result["rate_kg_m2_s"] > 0.0))
        self.assertTrue(np.all(result["q_c"] < q_c))
        self.assertTrue(np.all(result["q_c"] >= 0.0))
        np.testing.assert_allclose(
            result["rate_mm_h"],
            result["rate_kg_m2_s"] * 3600.0,
        )
        removed = q_c - result["q_c"]
        self.assertTrue(np.all(removed <= q_c))
        column_mass = air_column_mass_kg_m2(np.full(8, 1000.0), config)
        np.testing.assert_allclose(
            removed * column_mass,
            result["rate_kg_m2_s"] * config.step_minutes * 60.0,
        )

        dry = precipitation_fallout(
            np.zeros(8),
            np.full(8, 1000.0),
            np.full(8, 20.0),
            config,
        )
        self.assertTrue(np.all(dry["rate_kg_m2_s"] == 0.0))

    def test_rain_snow_partition_is_smooth(self):
        config = settings()
        rain, snow = rain_and_snow_fraction(np.array([-3.0, 0.0, 3.0]), config)
        np.testing.assert_allclose(snow, [1.0, 0.5, 0.0])
        np.testing.assert_allclose(rain + snow, 1.0)

    def test_cloud_cover_comes_from_condensate_not_rh(self):
        config = settings()
        pressure = np.full(8, 1000.0)
        covers = [
            cloud_cover_from_condensate(np.full(8, value), pressure, config)[0]
            for value in (0.0, 0.00005, 0.0005)
        ]
        self.assertAlmostEqual(float(covers[0]), 0.0)
        self.assertLess(covers[0], covers[1])
        self.assertLess(covers[1], covers[2])
        self.assertTrue(all(0.0 <= value <= 1.0 for value in covers))

    def test_condensate_is_advected_as_a_prognostic_scalar(self):
        config = settings(width=8, height=2)
        grid = AtmosphericGrid.empty(8, 2)
        latitude = 45.0
        cell_m = (
            config.world_circumference_km
            * 1000.0
            * math.cos(math.radians(latitude))
            / config.width
        )
        grid.fields["wind_u"].fill(cell_m / (config.step_minutes * 60.0))
        for y in range(config.height):
            grid.fields["cloud_condensate_specific_humidity"][grid.index(2, y)] = 0.002

        moved = advect_scalar(
            grid,
            "cloud_condensate_specific_humidity",
            config,
        )

        self.assertAlmostEqual(float(moved[grid.index(3, 0)]), 0.002, delta=1e-6)
        self.assertLess(float(moved[grid.index(2, 0)]), 1e-6)

    def test_conditions_are_diagnostics_and_rh_alone_does_not_make_cloud_or_fog(self):
        self.assertEqual(
            condition_from_cell(
                20.0,
                99.9,
                1.0,
                0.0,
                0.0,
                precipitation_rate_mm_h=0.0,
                snow_fraction=0.0,
                fog_probability=0.0,
            ),
            "clear",
        )
        self.assertEqual(
            condition_from_cell(
                20.0,
                99.9,
                1.0,
                0.2,
                0.0,
                precipitation_rate_mm_h=0.0,
                snow_fraction=0.0,
                fog_probability=1.0,
            ),
            "fog",
        )


class OrographicRainShadowTests(SimpleTestCase):
    def test_moist_flow_precipitates_on_mountain_and_drains_before_lee(self):
        width, height = 8, 2
        config = settings(width, height)
        elevations = [0, 0, 0, 1500, 0, 0, 0, 0] * height
        static = static_grid(
            width,
            height,
            elevations=elevations,
            ocean_indices={2, 10},
        )
        grid = AtmosphericGrid.empty(width, height)
        grid.fields["temperature"].fill(20.0)
        grid.fields["pressure_hpa"].fill(1000.0)
        saturated = float(saturation_specific_humidity(20.0, 1000.0))
        grid.fields["water_vapor_specific_humidity"].fill(saturated * 0.4)
        for y in range(height):
            grid.fields["water_vapor_specific_humidity"][grid.index(2, y)] = saturated * 0.99
        # One longitudinal cell per six-hour step on both ±45° rows.
        cell_m = config.world_circumference_km * 1000.0 * math.cos(math.radians(45)) / width
        grid.fields["wind_u"].fill(cell_m / (config.step_minutes * 60.0))
        grid.fields["wind_v"].fill(0.0)

        mountain_precipitation = 0.0
        lee_precipitation = 0.0
        for _step in range(2):
            for field in (
                "temperature",
                "water_vapor_specific_humidity",
                "cloud_condensate_specific_humidity",
            ):
                grid.fields[field] = advect_scalar(grid, field, config)
            apply_orographic_temperature_tendency(grid, static, config)
            adjusted = saturation_adjustment(
                grid.fields["temperature"],
                grid.fields["pressure_hpa"],
                grid.fields["water_vapor_specific_humidity"],
                grid.fields["cloud_condensate_specific_humidity"],
                config,
            )
            grid.fields["temperature"] = adjusted["temperature"].astype(np.float32)
            grid.fields["water_vapor_specific_humidity"] = adjusted["q_v"].astype(np.float32)
            fallout = precipitation_fallout(
                adjusted["q_c"],
                grid.fields["pressure_hpa"],
                grid.fields["temperature"],
                config,
            )
            grid.fields["cloud_condensate_specific_humidity"] = fallout["q_c"].astype(np.float32)
            mountain_precipitation += float(fallout["rate_mm_h"][grid.index(3, 0)])
            lee_precipitation += float(fallout["rate_mm_h"][grid.index(4, 0)])

        self.assertGreater(mountain_precipitation, lee_precipitation)
        self.assertLess(
            float(grid.fields["water_vapor_specific_humidity"][grid.index(4, 0)]),
            saturated * 0.99,
        )
