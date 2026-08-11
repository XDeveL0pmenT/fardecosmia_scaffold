import base64
import json
import math
from array import array
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from world.services.atmosphere.advection import advect_scalar
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.orography import apply_orography_and_precipitation
from world.services.atmosphere.simulation import initialize_atmosphere, simulate_step
from world.services.atmosphere.static_grid import StaticWorldGrid
from world.services.atmosphere.ocean import apply_ocean_surface_exchange
from world.services.atmosphere.wind import solve_wind


def static_grid(width=8, height=4, *, ocean_indices=(), elevations=None, temperatures=None):
    size = width * height
    elevations = elevations or [0.0] * size
    temperatures = temperatures or [10.0] * size
    ocean_indices = set(ocean_indices)
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=array("b", [1 if index in ocean_indices else 0 for index in range(size)]),
        elevation=array("f", elevations),
        mean_temperature=array("f", temperatures),
        biome=tuple(None for _ in range(size)),
    )


def settings(width=8, height=4, **overrides):
    parameters = {
        "initial_temperature_noise_c": 0.0,
        "pressure_noise_hpa": 0.0,
        "stellar_response_c": 0.0,
        "ympha_response_c": 0.0,
    }
    parameters.update(overrides.pop("parameters", {}))
    return AtmosphericSettings(
        width=width,
        height=height,
        ocean_temperature_c=overrides.pop("ocean_temperature_c", 40.0),
        **overrides,
        parameters=parameters,
    )


class AtmosphericGridTests(SimpleTestCase):
    def test_phase_b_payload_is_not_silently_read_as_solver_v4(self):
        fixture_path = (
            Path(__file__).with_name("fixtures")
            / "atmosphere_scalar_regression.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        encoded = next(iter(fixture["states"].values()))

        with self.assertRaises(ValueError):
            AtmosphericGrid.deserialize(
                fixture["width"],
                fixture["height"],
                base64.b64decode(encoded),
            )

    def test_disabled_heat_hooks_skip_expensive_local_sky_calculation(self):
        forcing = CampaignSkyForcing(object(), settings())

        with patch(
            "world.services.atmosphere.forcing._annual_reference_for_latitudes"
        ) as annual_reference:
            adjustment = forcing.temperature_adjustment(10, 20, 360)

        self.assertEqual(adjustment, 0.0)
        annual_reference.assert_not_called()

    def test_default_grid_storage_is_one_compact_float_blob(self):
        grid = AtmosphericGrid.empty(180, 90)
        payload = grid.serialize()
        restored = AtmosphericGrid.deserialize(180, 90, payload)

        self.assertEqual(grid.uncompressed_size_bytes, 842_400)
        self.assertLess(len(payload), grid.uncompressed_size_bytes)
        self.assertEqual(restored.serialize(), payload)

    def test_pressure_anomaly_persists_and_relaxes_instead_of_rerolling(self):
        config = settings(
            parameters={
                "pressure_relaxation": 0.2,
                "pressure_neighbor_smoothing": 0.0,
                "land_temperature_exchange": 0.0,
                "wind_pressure_factor": 0.0,
                "wind_thermal_factor": 0.0,
            }
        )
        static = static_grid()
        grid, _ = initialize_atmosphere(config, static=static)
        centre = grid.index(3, 2)
        equilibrium = grid.fields["pressure_hpa"][centre]
        grid.fields["pressure_hpa"][centre] = equilibrium + 20.0

        after_one = simulate_step(
            grid,
            static,
            config,
            step_index=1,
            world_minutes=360,
        )
        after_two = simulate_step(
            after_one,
            static,
            config,
            step_index=2,
            world_minutes=720,
        )

        self.assertGreater(after_one.fields["pressure_hpa"][centre], equilibrium)
        self.assertGreater(after_two.fields["pressure_hpa"][centre], equilibrium)
        self.assertLess(
            after_two.fields["pressure_hpa"][centre],
            after_one.fields["pressure_hpa"][centre],
        )

    def test_pressure_gradient_drives_air_from_high_to_low_pressure(self):
        config = settings(parameters={"coriolis_factor": 0.0, "wind_thermal_factor": 0.0})
        static = static_grid()
        grid = AtmosphericGrid.empty(8, 4)
        for index in range(grid.size):
            grid.fields["pressure_hpa"][index] = 1000.0
            grid.fields["temperature"][index] = 10.0
        index = grid.index(3, 2)
        grid.fields["pressure_hpa"][grid.index(2, 2)] = 1010.0
        grid.fields["pressure_hpa"][grid.index(4, 2)] = 990.0

        wind_u, _wind_v = solve_wind(grid, static, config)

        self.assertGreater(wind_u[index], 0.0)

    def test_heat_is_advected_downwind(self):
        config = settings(
            width=8,
            height=2,
            step_minutes=60,
            world_circumference_km=80,
        )
        grid = AtmosphericGrid.empty(8, 2)
        latitude = 45.0
        cell_km = 80 * math.cos(math.radians(latitude)) / 8
        one_cell_wind = cell_km * 1000 / (60 * 60)
        for y in range(2):
            grid.fields["temperature"][grid.index(2, y)] = 100.0
        for index in range(grid.size):
            grid.fields["wind_u"][index] = one_cell_wind

        moved = advect_scalar(grid, "temperature", config)

        self.assertAlmostEqual(moved[grid.index(3, 0)], 100.0, delta=0.01)
        self.assertLess(moved[grid.index(2, 0)], 1.0)

    def test_ocean_uses_map_baseline_instead_of_legacy_constant(self):
        config = settings(
            width=4,
            height=2,
            ocean_temperature_c=60,
            parameters={
                "ocean_sensible_transfer_coefficient": 0.0012,
                "ocean_evaporation_transfer_coefficient": 0.0012,
            },
        )
        static = static_grid(4, 2, ocean_indices={0})
        grid, _ = initialize_atmosphere(config, static=static)

        apply_ocean_surface_exchange(grid, static, config)

        self.assertAlmostEqual(grid.fields["sea_surface_temperature_c"][0], 10.0, delta=0.01)
        self.assertNotEqual(grid.fields["sea_surface_temperature_c"][0], 60.0)

    def test_orography_cools_windward_slope_without_directly_changing_water(self):
        width, height = 5, 2
        elevations = [0, 0, 1000, 0, 0] * height
        static = static_grid(width, height, elevations=elevations)
        config = settings(width=width, height=height)
        grid = AtmosphericGrid.empty(width, height)
        grid.fields["temperature"].fill(20.0)
        grid.fields["wind_u"].fill(10.0)
        q_before = grid.fields["water_vapor_specific_humidity"].copy()

        apply_orography_and_precipitation(
            grid,
            static,
            config,
            relative_humidity=np.full(grid.size, 90.0),
        )

        windward_plain = grid.index(1, 0)
        mountain = grid.index(2, 0)
        self.assertLess(
            grid.fields["temperature"][mountain],
            grid.fields["temperature"][windward_plain],
        )
        self.assertEqual(float(grid.fields["precipitation_rate"][mountain]), 0.0)
        np.testing.assert_array_equal(
            grid.fields["water_vapor_specific_humidity"],
            q_before,
        )

    def test_same_seed_and_state_are_bitwise_deterministic(self):
        config = settings(world_seed=917)
        static = static_grid()
        first, _ = initialize_atmosphere(config, static=static)
        second, _ = initialize_atmosphere(config, static=static)
        first = simulate_step(
            first,
            static,
            config,
            step_index=1,
            world_minutes=360,
        )
        second = simulate_step(
            second,
            static,
            config,
            step_index=1,
            world_minutes=360,
        )

        self.assertEqual(first.serialize(), second.serialize())
