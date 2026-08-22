import math
from array import array
from types import SimpleNamespace

import numpy as np
from django.test import SimpleTestCase

from campaigns.models import Campaign
from world.services.atmosphere.advection import advect_scalar
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.geometry import geometry_for
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.ocean import (
    advance_ocean_fast_forward,
    air_column_mass_kg_m2,
    apply_ocean_surface_exchange,
    ocean_baseline_sst,
    ocean_heat_capacity_j_m2_k,
)
from world.services.atmosphere.simulation import (
    derive_relative_humidity_and_apply_safety,
    initialize_atmosphere,
)
from world.services.atmosphere.static_grid import StaticWorldGrid, build_static_world_grid
from world.services.atmosphere.surface_exchange import apply_surface_exchange
from world.services.atmosphere.thermodynamics import (
    relative_humidity_percent,
    saturation_specific_humidity,
    specific_humidity_from_relative_humidity,
)


def make_static(
    width=4,
    height=2,
    *,
    ocean_indices=(),
    temperatures=None,
    elevations=None,
):
    size = width * height
    ocean_indices = set(ocean_indices)
    temperatures = temperatures or [10.0] * size
    elevations = elevations or [0.0] * size
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=array(
            "b",
            [1 if index in ocean_indices else 0 for index in range(size)],
        ),
        elevation=array("f", elevations),
        mean_temperature=array("f", temperatures),
        biome=tuple(None for _ in range(size)),
    )


def make_settings(width=4, height=2, **parameter_overrides):
    parameters = {
        "initial_temperature_noise_c": 0.0,
        "pressure_noise_hpa": 0.0,
        "stellar_response_c": 0.0,
        "ympha_response_c": 0.0,
    }
    parameters.update(parameter_overrides)
    return AtmosphericSettings(
        width=width,
        height=height,
        step_minutes=360,
        world_seed=19,
        ocean_temperature_c=64.0,
        parameters=parameters,
    )


def radiative_grid(size, *, star_w_m2=0.0, temperature_anomaly_c=0.0):
    return SimpleNamespace(
        stellar_flux_anomaly_w_m2=np.full(size, star_w_m2, dtype=np.float64),
        ympha_temperature_anomaly_c=np.zeros(size, dtype=np.float64),
        total_radiative_anomaly_c=np.full(
            size,
            temperature_anomaly_c,
            dtype=np.float64,
        ),
    )


def initialized_ocean_case(
    *,
    baseline=20.0,
    sst=20.0,
    air_temperature=10.0,
    q_v=0.0,
    wind=1.0,
    **parameters,
):
    settings = make_settings(
        ocean_deep_relaxation_days=1e12,
        ocean_horizontal_mixing_w_m2_k=0.0,
        **parameters,
    )
    temperatures = [baseline] + [10.0] * 7
    static = make_static(ocean_indices={0}, temperatures=temperatures)
    grid, _ = initialize_atmosphere(settings, static=static)
    grid.fields["sea_surface_temperature_c"][0] = sst
    grid.fields["surface_temperature"][0] = sst
    grid.fields["temperature"][0] = air_temperature
    grid.fields["pressure_hpa"][0] = 1000.0
    grid.fields["water_vapor_specific_humidity"][0] = q_v
    grid.fields["wind_u"][0] = wind
    grid.fields["wind_v"][0] = 0.0
    return grid, static, settings


class WaterVaporThermodynamicsTests(SimpleTestCase):
    def test_relative_humidity_q_roundtrip(self):
        temperatures = np.array([-20.0, 10.0, 40.0])
        pressures = np.array([700.0, 1000.0, 1200.0])
        original_rh = np.array([35.0, 72.0, 95.0])

        q_v = specific_humidity_from_relative_humidity(
            original_rh,
            temperatures,
            pressures,
        )
        restored_rh = relative_humidity_percent(
            q_v,
            temperatures,
            pressures,
        )

        np.testing.assert_allclose(restored_rh, original_rh, rtol=1e-12, atol=1e-12)

    def test_rh_responds_to_temperature_moisture_and_pressure(self):
        q_v = 0.01
        self.assertGreater(
            float(relative_humidity_percent(q_v, 10.0, 1000.0)),
            float(relative_humidity_percent(q_v, 30.0, 1000.0)),
        )
        self.assertGreater(
            float(relative_humidity_percent(0.02, 20.0, 1000.0)),
            float(relative_humidity_percent(0.01, 20.0, 1000.0)),
        )
        self.assertGreater(
            float(saturation_specific_humidity(20.0, 800.0)),
            float(saturation_specific_humidity(20.0, 1100.0)),
        )

    def test_supersaturation_safety_changes_q_not_an_independent_rh_field(self):
        settings = make_settings(supersaturation_emergency_ratio=1.1)
        grid = AtmosphericGrid.empty(4, 2)
        grid.fields["temperature"].fill(20.0)
        grid.fields["pressure_hpa"].fill(1000.0)
        grid.fields["water_vapor_specific_humidity"].fill(0.5)
        diagnostics = {}

        relative_humidity = derive_relative_humidity_and_apply_safety(
            grid,
            settings,
            diagnostics,
        )

        self.assertLessEqual(float(relative_humidity.max()), 110.0001)
        self.assertGreater(diagnostics["supersaturation_emergency_clamp_hits"], 0)
        self.assertNotIn("relative_humidity", grid.fields)


class DynamicOceanTests(SimpleTestCase):
    def test_map_is_baseline_and_sst_survives_snapshot_roundtrip(self):
        settings = make_settings()
        static = make_static(
            ocean_indices={0, 1},
            temperatures=[37.0, -15.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        )
        grid, _ = initialize_atmosphere(settings, static=static)
        grid.fields["sea_surface_temperature_c"][0] += 2.25
        grid.fields["cloud_condensate_specific_humidity"][0] = 0.00125
        restored = AtmosphericGrid.deserialize(4, 2, grid.serialize())

        np.testing.assert_allclose(ocean_baseline_sst(static, settings)[:2], [37.0, -15.0])
        self.assertAlmostEqual(
            float(restored.fields["sea_surface_temperature_c"][0]),
            39.25,
        )
        self.assertNotEqual(float(restored.fields["sea_surface_temperature_c"][0]), 64.0)
        self.assertAlmostEqual(
            float(restored.fields["cloud_condensate_specific_humidity"][0]),
            0.00125,
        )

    def test_land_reacts_quickly_while_ocean_has_mixed_layer_inertia(self):
        settings = make_settings(
            ocean_evaporation_transfer_coefficient=0.0,
            ocean_sensible_transfer_coefficient=0.0,
            ocean_deep_relaxation_days=1e12,
            ocean_horizontal_mixing_w_m2_k=0.0,
        )
        static = make_static(ocean_indices={0})
        grid, _ = initialize_atmosphere(settings, static=static)
        before_land = float(grid.fields["temperature"][1])
        before_ocean = float(grid.fields["sea_surface_temperature_c"][0])
        forcing = radiative_grid(grid.size, star_w_m2=1000.0, temperature_anomaly_c=20.0)

        apply_surface_exchange(
            grid,
            static,
            settings,
            world_minutes=360,
            radiative_grid=forcing,
        )
        apply_ocean_surface_exchange(grid, static, settings, radiative_grid=forcing)

        land_change = float(grid.fields["temperature"][1]) - before_land
        ocean_change = float(grid.fields["sea_surface_temperature_c"][0]) - before_ocean
        self.assertGreater(land_change, 1.0)
        self.assertGreater(ocean_change, 0.0)
        self.assertGreater(land_change, ocean_change * 10.0)

        no_forcing = radiative_grid(grid.size)
        for step in range(10):
            apply_surface_exchange(
                grid,
                static,
                settings,
                world_minutes=720 + step * 360,
                radiative_grid=no_forcing,
            )
            apply_ocean_surface_exchange(
                grid,
                static,
                settings,
                radiative_grid=no_forcing,
            )
        land_remaining_fraction = (
            float(grid.fields["temperature"][1]) - before_land
        ) / land_change
        ocean_remaining_fraction = (
            float(grid.fields["sea_surface_temperature_c"][0]) - before_ocean
        ) / ocean_change
        self.assertGreater(ocean_remaining_fraction, land_remaining_fraction)

    def test_sensible_exchange_is_bidirectional_and_zero_at_equilibrium(self):
        hot_ocean, static, settings = initialized_ocean_case(
            baseline=20.0,
            sst=20.0,
            air_temperature=10.0,
            ocean_evaporation_transfer_coefficient=0.0,
        )
        before_sst = float(hot_ocean.fields["sea_surface_temperature_c"][0])
        before_air = float(hot_ocean.fields["temperature"][0])
        apply_ocean_surface_exchange(hot_ocean, static, settings)
        self.assertLess(float(hot_ocean.fields["sea_surface_temperature_c"][0]), before_sst)
        self.assertGreater(float(hot_ocean.fields["temperature"][0]), before_air)

        cold_ocean, static, settings = initialized_ocean_case(
            baseline=10.0,
            sst=10.0,
            air_temperature=20.0,
            ocean_evaporation_transfer_coefficient=0.0,
        )
        apply_ocean_surface_exchange(cold_ocean, static, settings)
        self.assertGreater(float(cold_ocean.fields["sea_surface_temperature_c"][0]), 10.0)
        self.assertLess(float(cold_ocean.fields["temperature"][0]), 20.0)

        equal, static, settings = initialized_ocean_case(
            baseline=15.0,
            sst=15.0,
            air_temperature=15.0,
            ocean_evaporation_transfer_coefficient=0.0,
        )
        apply_ocean_surface_exchange(equal, static, settings)
        self.assertAlmostEqual(float(equal.fields["temperature"][0]), 15.0, places=6)
        self.assertAlmostEqual(
            float(equal.fields["sea_surface_temperature_c"][0]),
            15.0,
            places=6,
        )

    def test_sensible_exchange_conserves_pair_energy_and_strengthens_with_wind(self):
        changes = []
        for wind in (1.0, 10.0):
            grid, static, settings = initialized_ocean_case(
                baseline=20.0,
                sst=20.0,
                air_temperature=10.0,
                wind=wind,
                ocean_evaporation_transfer_coefficient=0.0,
            )
            old_sst = float(grid.fields["sea_surface_temperature_c"][0])
            old_air = float(grid.fields["temperature"][0])
            air_mass = float(air_column_mass_kg_m2(1000.0, settings))
            apply_ocean_surface_exchange(grid, static, settings)
            ocean_loss = ocean_heat_capacity_j_m2_k(settings) * (
                old_sst - float(grid.fields["sea_surface_temperature_c"][0])
            )
            air_gain = (
                settings.value("air_heat_capacity_j_kg_k")
                * air_mass
                * (float(grid.fields["temperature"][0]) - old_air)
            )
            self.assertAlmostEqual(ocean_loss, air_gain, delta=max(2.0, ocean_loss * 0.01))
            changes.append(old_sst - float(grid.fields["sea_surface_temperature_c"][0]))
        self.assertGreater(changes[1], changes[0] * 5.0)

    def test_evaporation_dependencies_and_water_energy_effects(self):
        def run(*, sst, q_v, wind, ocean=True):
            grid, static, settings = initialized_ocean_case(
                baseline=sst,
                sst=sst,
                air_temperature=sst,
                q_v=q_v,
                wind=wind,
                ocean_sensible_transfer_coefficient=0.0,
            )
            if not ocean:
                static = make_static(temperatures=[sst] + [10.0] * 7)
            old_sst = float(grid.fields["sea_surface_temperature_c"][0])
            old_q = float(grid.fields["water_vapor_specific_humidity"][0])
            apply_ocean_surface_exchange(grid, static, settings)
            return (
                float(grid.fields["evaporation_flux_kg_m2_s"][0]),
                float(grid.fields["sea_surface_temperature_c"][0]) - old_sst,
                float(grid.fields["water_vapor_specific_humidity"][0]) - old_q,
            )

        cold = run(sst=5.0, q_v=0.0, wind=5.0)
        warm = run(sst=35.0, q_v=0.0, wind=5.0)
        humid_q = float(specific_humidity_from_relative_humidity(80.0, 35.0, 1000.0))
        humid = run(sst=35.0, q_v=humid_q, wind=5.0)
        weak_wind = run(sst=35.0, q_v=0.0, wind=1.0)
        strong_wind = run(sst=35.0, q_v=0.0, wind=10.0)
        saturated_q = float(saturation_specific_humidity(35.0, 1000.0))
        saturated = run(sst=35.0, q_v=saturated_q, wind=5.0)
        land = run(sst=35.0, q_v=0.0, wind=5.0, ocean=False)

        self.assertGreater(warm[0], cold[0])
        self.assertGreater(warm[0], humid[0])
        self.assertGreater(strong_wind[0], weak_wind[0])
        self.assertAlmostEqual(saturated[0], 0.0, places=10)
        self.assertEqual(land[0], 0.0)
        self.assertLess(warm[1], 0.0)
        self.assertGreater(warm[2], 0.0)

    def test_latent_energy_loss_matches_evaporated_water_energy(self):
        grid, static, settings = initialized_ocean_case(
            baseline=30.0,
            sst=30.0,
            air_temperature=30.0,
            q_v=0.0,
            wind=5.0,
            initial_ocean_humidity=100.0,
            ocean_sensible_transfer_coefficient=0.0,
        )
        old_sst = float(grid.fields["sea_surface_temperature_c"][0])
        apply_ocean_surface_exchange(grid, static, settings)
        evaporation = float(grid.fields["evaporation_flux_kg_m2_s"][0])
        measured_energy_loss = ocean_heat_capacity_j_m2_k(settings) * (
            old_sst - float(grid.fields["sea_surface_temperature_c"][0])
        )
        expected_energy_loss = (
            settings.value("latent_heat_vaporization_j_kg")
            * evaporation
            * settings.step_minutes
            * 60.0
        )
        self.assertAlmostEqual(
            measured_energy_loss,
            expected_energy_loss,
            delta=max(10.0, expected_energy_loss * 0.002),
        )

    def test_horizontal_ocean_mixing_does_not_cross_land(self):
        settings = make_settings(
            ocean_evaporation_transfer_coefficient=0.0,
            ocean_sensible_transfer_coefficient=0.0,
            ocean_deep_relaxation_days=1e12,
            ocean_horizontal_mixing_w_m2_k=100.0,
        )
        static = make_static(ocean_indices={0, 2})
        grid, _ = initialize_atmosphere(settings, static=static)
        grid.fields["sea_surface_temperature_c"][0] = 30.0
        before_isolated = float(grid.fields["sea_surface_temperature_c"][2])

        apply_ocean_surface_exchange(grid, static, settings)

        self.assertAlmostEqual(
            float(grid.fields["sea_surface_temperature_c"][2]),
            before_isolated,
            places=6,
        )

    def test_cold_high_latitude_ocean_remains_bounded_with_small_evaporation(self):
        grid, static, settings = initialized_ocean_case(
            baseline=-35.0,
            sst=-35.0,
            air_temperature=-35.0,
            q_v=0.0,
            wind=5.0,
            ocean_sensible_transfer_coefficient=0.0,
        )
        apply_ocean_surface_exchange(grid, static, settings)
        self.assertTrue(np.isfinite(grid.fields["sea_surface_temperature_c"]).all())
        self.assertGreaterEqual(float(grid.fields["sea_surface_temperature_c"][0]), -120.0)
        self.assertLess(float(grid.fields["evaporation_flux_kg_m2_s"][0]), 2e-6)


class MoistureTransportTests(SimpleTestCase):
    def test_specific_humidity_blob_advects_and_is_conserved_for_integer_shift(self):
        settings = AtmosphericSettings(
            width=8,
            height=2,
            step_minutes=60,
            world_circumference_km=80.0,
            parameters={
                "stellar_response_c": 0.0,
                "ympha_response_c": 0.0,
            },
        )
        grid = AtmosphericGrid.empty(8, 2)
        latitude = 45.0
        cell_km = 80.0 * math.cos(math.radians(latitude)) / 8.0
        grid.fields["wind_u"].fill(cell_km * 1000.0 / 3600.0)
        for y in range(2):
            grid.fields["water_vapor_specific_humidity"][grid.index(2, y)] = 0.02

        moved = advect_scalar(grid, "water_vapor_specific_humidity", settings)

        self.assertAlmostEqual(float(moved[grid.index(3, 0)]), 0.02, delta=1e-5)
        self.assertLess(float(moved[grid.index(2, 0)]), 1e-5)
        self.assertAlmostEqual(float(moved.sum()), 0.04, delta=1e-5)
        self.assertNotIn("relative_humidity", grid.fields)

    def test_ocean_moisture_reaches_downwind_land_only_through_transport(self):
        settings = make_settings(width=8, height=2)
        static = make_static(
            width=8,
            height=2,
            ocean_indices={1, 9},
            temperatures=[35.0] * 16,
        )
        grid, _ = initialize_atmosphere(settings, static=static)
        grid.fields["water_vapor_specific_humidity"].fill(0.0)
        grid.fields["temperature"].fill(35.0)
        grid.fields["sea_surface_temperature_c"].fill(35.0)
        grid.fields["wind_u"].fill(10.0)
        apply_ocean_surface_exchange(grid, static, settings)
        after_evaporation = grid.fields["water_vapor_specific_humidity"].copy()
        self.assertGreater(float(after_evaporation[grid.index(1, 0)]), 0.0)
        self.assertEqual(float(after_evaporation[grid.index(2, 0)]), 0.0)

        transported = advect_scalar(grid, "water_vapor_specific_humidity", settings)

        self.assertGreater(float(transported[grid.index(2, 0)]), 0.0)


class FastForwardBoundaryApproximationTests(SimpleTestCase):
    databases = {"default"}

    def test_subturn_macro_forcing_preserves_canonical_longitude(self):
        settings = make_settings()
        forcing = CampaignSkyForcing(Campaign(), settings)
        geometry = geometry_for(settings)

        canonical = forcing.ocean_macro_forcing_grid(
            geometry,
            world_minutes=12 * 60,
            interval_minutes=24 * 60,
            ympha_samples=1,
        )
        legacy = forcing.ocean_macro_forcing_grid(
            geometry,
            world_minutes=12 * 60,
            interval_minutes=24 * 60,
            ympha_samples=1,
            legacy_rotation_mean=True,
        )

        first_row = canonical.stellar_flux_anomaly_w_m2[: settings.width]
        legacy_row = legacy.stellar_flux_anomaly_w_m2[: settings.width]
        self.assertGreater(float(np.ptp(first_row)), 1.0)
        self.assertAlmostEqual(float(np.ptp(legacy_row)), 0.0, places=6)

    def test_new_boundary_controls_do_not_reinterpret_legacy_macro_settings(self):
        settings = AtmosphericSettings(
            width=4,
            height=2,
            parameters={
                "fast_forward_ocean_step_minutes": 10080.0,
                "fast_forward_ocean_max_steps": 512.0,
                "fast_forward_forcing_samples": 7.0,
            },
        )

        self.assertEqual(settings.value("fast_forward_ocean_step_minutes"), 10080.0)
        self.assertEqual(settings.value("fast_forward_boundary_substep_minutes"), 360.0)
        self.assertEqual(settings.value("fast_forward_boundary_max_steps"), 2000.0)
        self.assertEqual(settings.value("fast_forward_boundary_forcing_samples"), 1.0)

    def test_boundary_fast_forward_advances_q_c_and_integrates_only_macro_precipitation(self):
        settings = make_settings(
            precipitation_condensate_threshold=0.00005,
            precipitation_fallout_timescale_seconds=21600.0,
        )
        static = make_static(ocean_indices={0, 1, 4, 5})
        forcing = CampaignSkyForcing(Campaign(), settings)
        grid, _ = initialize_atmosphere(settings, static=static, forcing=forcing)
        grid.fields["cloud_condensate_specific_humidity"].fill(0.002)
        before = grid.fields["cloud_condensate_specific_humidity"].copy()

        summary = advance_ocean_fast_forward(
            grid,
            static,
            settings,
            forcing,
            start_world_minutes=0,
            end_world_minutes=720,
        )

        self.assertGreater(summary["integrated_macro_precipitation_mass_kg"], 0.0)
        self.assertFalse(
            np.array_equal(
                grid.fields["cloud_condensate_specific_humidity"],
                before,
            )
        )
        self.assertTrue(np.all(grid.fields["cloud_condensate_specific_humidity"] >= 0.0))
        # The skipped interval has a climate integral, not a fabricated exact
        # event at the final grid instant.
        self.assertTrue(np.all(grid.fields["precipitation_rate"] == 0.0))

    def test_large_grid_uses_deterministic_coarse_boundary_state(self):
        settings = AtmosphericSettings(
            width=48,
            height=24,
            step_minutes=360,
            parameters={
                "initial_temperature_noise_c": 0.0,
                "pressure_noise_hpa": 0.0,
            },
        )
        static = build_static_world_grid(settings)
        forcing = CampaignSkyForcing(Campaign(), settings)
        initial, _ = initialize_atmosphere(
            settings,
            static=static,
            forcing=forcing,
        )
        control = initial.clone()
        detail_index = int(np.flatnonzero(static.is_ocean)[0])
        initial.fields["sea_surface_temperature_c"][detail_index] += 4.0
        first = initial.clone()
        second = initial.clone()

        first_summary = advance_ocean_fast_forward(
            first,
            static,
            settings,
            forcing,
            start_world_minutes=0,
            end_world_minutes=720,
        )
        second_summary = advance_ocean_fast_forward(
            second,
            static,
            settings,
            forcing,
            start_world_minutes=0,
            end_world_minutes=720,
        )
        advance_ocean_fast_forward(
            control,
            static,
            settings,
            forcing,
            start_world_minutes=0,
            end_world_minutes=720,
        )

        self.assertEqual(first_summary["boundary_grid_width"], 24)
        self.assertEqual(first_summary["boundary_grid_height"], 12)
        self.assertEqual(first_summary["macro_steps"], 2)
        np.testing.assert_array_equal(
            first.fields["sea_surface_temperature_c"],
            second.fields["sea_surface_temperature_c"],
        )
        self.assertGreater(
            float(
                first.fields["sea_surface_temperature_c"][detail_index]
                - control.fields["sea_surface_temperature_c"][detail_index]
            ),
            3.0,
        )
        self.assertTrue(np.isfinite(first.fields["sea_surface_temperature_c"]).all())
