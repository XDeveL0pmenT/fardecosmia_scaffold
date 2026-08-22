import math

import numpy as np
from django.test import SimpleTestCase

from campaigns.models import Campaign
from world.services.astronomy import calculate_local_sky
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.simulation import initialize_atmosphere, simulate_step
from world.services.atmosphere.static_grid import StaticWorldGrid
from world.services.calendar import PHASES_PER_TURN
from world.services.orbital_climate import (
    CANONICAL_YEAR_MINUTES,
    MEAN_ANOMALY_AT_EPOCH_RAD,
    SEASON_CODES,
    STAR_ORBIT_APOCENTER_AU,
    STAR_ORBIT_PERICENTER_AU,
    astronomical_milestones_between,
    canonical_season_durations,
    orbital_climate_state,
)


def _settings(**parameters):
    return AtmosphericSettings(
        width=4,
        height=2,
        ocean_temperature_c=45,
        parameters=parameters,
    )


def _static_grid():
    size = 8
    return StaticWorldGrid(
        width=4,
        height=2,
        is_ocean=np.zeros(size, dtype=np.bool_),
        elevation=np.zeros(size, dtype=np.float32),
        mean_temperature=np.full(size, 10.0, dtype=np.float32),
        biome=tuple(None for _ in range(size)),
    )


class OrbitalMechanicsTests(SimpleTestCase):
    def test_state_wraps_after_exactly_364_days(self):
        first = orbital_climate_state(123_456)
        wrapped = orbital_climate_state(123_456 + CANONICAL_YEAR_MINUTES)

        self.assertAlmostEqual(first.star_distance_au, wrapped.star_distance_au, places=10)
        self.assertAlmostEqual(first.true_anomaly_rad, wrapped.true_anomaly_rad, places=10)
        self.assertEqual(first.global_season, wrapped.global_season)
        self.assertAlmostEqual(first.season_progress, wrapped.season_progress, places=10)

    def test_pericenter_is_temporal_middle_of_summer_and_flux_maximum(self):
        peri_time = round(
            -MEAN_ANOMALY_AT_EPOCH_RAD / (2.0 * math.pi)
            * CANONICAL_YEAR_MINUTES
        )
        state = orbital_climate_state(peri_time)

        self.assertEqual(state.global_season, "summer")
        self.assertAlmostEqual(state.season_progress, 0.5, places=4)
        self.assertAlmostEqual(state.star_distance_au, STAR_ORBIT_PERICENTER_AU, places=4)
        self.assertLess(
            min(state.true_anomaly_degrees, 360.0 - state.true_anomaly_degrees),
            0.001,
        )
        self.assertAlmostEqual(state.stellar_flux_earth_ratio, 2.7105, places=4)

    def test_apocenter_is_temporal_middle_of_winter_and_flux_minimum(self):
        apo_time = round(
            (math.pi - MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi)
            * CANONICAL_YEAR_MINUTES
        )
        state = orbital_climate_state(apo_time)

        self.assertEqual(state.global_season, "winter")
        self.assertAlmostEqual(state.season_progress, 0.5, places=4)
        self.assertAlmostEqual(state.star_distance_au, STAR_ORBIT_APOCENTER_AU, places=4)
        self.assertAlmostEqual(state.true_anomaly_degrees, 180.0, places=3)
        self.assertAlmostEqual(state.stellar_flux_earth_ratio, 1.3985, places=4)

    def test_flux_ratio_and_time_mean_reference(self):
        peri = orbital_climate_state(
            round(-MEAN_ANOMALY_AT_EPOCH_RAD / (2.0 * math.pi) * CANONICAL_YEAR_MINUTES)
        )
        apo = orbital_climate_state(
            round((math.pi - MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi) * CANONICAL_YEAR_MINUTES)
        )

        self.assertAlmostEqual(
            peri.stellar_flux_w_m2 / apo.stellar_flux_w_m2,
            1.9381,
            places=4,
        )
        self.assertAlmostEqual(peri.annual_mean_flux_w_m2, 2614.0, delta=1.0)

    def test_true_anomaly_moves_faster_near_pericenter(self):
        peri_time = -MEAN_ANOMALY_AT_EPOCH_RAD / (2.0 * math.pi) * CANONICAL_YEAR_MINUTES
        apo_time = peri_time + CANONICAL_YEAR_MINUTES / 2.0
        interval = 10 * 24 * 60

        peri_delta = (
            orbital_climate_state(peri_time + interval).true_anomaly_rad
            - orbital_climate_state(peri_time).true_anomaly_rad
        ) % (2.0 * math.pi)
        apo_delta = (
            orbital_climate_state(apo_time + interval).true_anomaly_rad
            - orbital_climate_state(apo_time).true_anomaly_rad
        ) % (2.0 * math.pi)

        self.assertGreater(peri_delta, apo_delta)

    def test_season_lengths_emerge_from_geometry(self):
        days = {
            code: duration / 1440.0
            for code, duration in canonical_season_durations().items()
        }

        self.assertEqual(tuple(days), SEASON_CODES)
        self.assertAlmostEqual(days["summer"], 66.36, delta=0.02)
        self.assertAlmostEqual(days["autumn"], 88.65, delta=0.02)
        self.assertAlmostEqual(days["winter"], 120.33, delta=0.02)
        self.assertAlmostEqual(days["spring"], 88.65, delta=0.02)
        self.assertAlmostEqual(sum(days.values()), 364.0, places=8)

    def test_milestones_are_deterministic_inside_fast_forward_interval(self):
        events = astronomical_milestones_between(0, CANONICAL_YEAR_MINUTES)

        self.assertEqual(
            [event["kind"] for event in events].count("season_transition"),
            4,
        )
        self.assertEqual([event["kind"] for event in events].count("periapsis"), 1)
        self.assertEqual([event["kind"] for event in events].count("apoapsis"), 1)


class LocalRadiativeForcingTests(SimpleTestCase):
    def setUp(self):
        self.campaign = Campaign()

    def test_equator_noon_exceeds_dawn_and_deep_night_is_zero(self):
        forcing = CampaignSkyForcing(self.campaign, _settings())
        turn = self.campaign.calendar_minutes_per_turn
        dawn = forcing.diagnostics(0, 0, 0)
        noon = forcing.diagnostics(0, 0, round(2 / PHASES_PER_TURN * turn))
        night_time = round(5.5 / PHASES_PER_TURN * turn)
        night = forcing.diagnostics(0, 0, night_time)

        self.assertGreater(noon["stellar_direct_w_m2"], dawn["stellar_direct_w_m2"])
        self.assertEqual(night["stellar_direct_w_m2"], 0.0)
        self.assertEqual(calculate_local_sky(self.campaign, night_time, 0).star_phase, "Глубокая ночь")

    def test_longitude_moves_local_noon_without_changing_star_distance(self):
        forcing = CampaignSkyForcing(self.campaign, _settings())
        time = round(2 / PHASES_PER_TURN * self.campaign.calendar_minutes_per_turn)
        zero = forcing.diagnostics(0, 0, time)
        east = forcing.diagnostics(0, 90, time)

        self.assertGreater(zero["stellar_direct_w_m2"], east["stellar_direct_w_m2"])
        self.assertEqual(
            zero["orbital_state"].star_distance_au,
            east["orbital_state"].star_distance_au,
        )

    def test_hemispheres_respond_oppositely_and_zero_tilt_restores_symmetry(self):
        turn = self.campaign.calendar_minutes_per_turn
        local_noon_offset = round(2 / PHASES_PER_TURN * turn)
        apo_time = round(
            (math.pi - MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi)
            * CANONICAL_YEAR_MINUTES
        )
        time = apo_time - apo_time % turn + local_noon_offset
        tilted = CampaignSkyForcing(self.campaign, _settings())
        north = tilted.diagnostics(35, 0, time)["stellar_direct_w_m2"]
        south = tilted.diagnostics(-35, 0, time)["stellar_direct_w_m2"]
        self.assertNotEqual(north, south)

        untilted = CampaignSkyForcing(self.campaign, _settings(axial_tilt_deg=0.0))
        north_zero = untilted.diagnostics(35, 0, time)["stellar_direct_w_m2"]
        south_zero = untilted.diagnostics(-35, 0, time)["stellar_direct_w_m2"]
        self.assertAlmostEqual(north_zero, south_zero, places=8)

    def test_ympha_is_separate_visible_and_distance_dependent(self):
        visible = CampaignSkyForcing(self.campaign, _settings(ympha_response_c=2.0))
        hidden = visible.diagnostics(0, 180, 0)
        light_night_time = round(
            5 / PHASES_PER_TURN * self.campaign.calendar_minutes_per_turn
        )
        light_night = visible.diagnostics(0, 0, light_night_time)
        farther = visible.diagnostics(0, 0, 7_308)

        self.assertAlmostEqual(hidden["ympha_forcing_factor"], 0.0, places=8)
        self.assertGreater(light_night["ympha_forcing_factor"], 0.0)
        self.assertGreater(
            visible.diagnostics(0, 0, 0)["ympha_distance_factor"],
            farther["ympha_distance_factor"],
        )

        no_ympha = CampaignSkyForcing(self.campaign, _settings(ympha_response_c=0.0))
        self.assertEqual(
            visible.diagnostics(0, 0, light_night_time)["stellar_direct_w_m2"],
            no_ympha.diagnostics(0, 0, light_night_time)["stellar_direct_w_m2"],
        )

    def test_atmosphere_receives_forcing_and_remains_finite(self):
        config = _settings(
            initial_temperature_noise_c=0.0,
            pressure_noise_hpa=0.0,
        )
        forcing = CampaignSkyForcing(self.campaign, config)
        static = _static_grid()
        summer, _ = initialize_atmosphere(
            config,
            static=static,
            world_minutes=0,
            forcing=forcing,
        )
        winter_time = CANONICAL_YEAR_MINUTES // 2
        winter, _ = initialize_atmosphere(
            config,
            static=static,
            world_minutes=winter_time,
            forcing=forcing,
        )

        self.assertFalse(
            np.array_equal(
                summer.fields["surface_temperature"],
                winter.fields["surface_temperature"],
            )
        )
        evolved = simulate_step(
            summer,
            static,
            config,
            step_index=1,
            world_minutes=360,
            forcing=forcing,
        )
        for values in evolved.fields.values():
            self.assertTrue(np.isfinite(values).all())
