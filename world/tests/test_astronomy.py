from django.test import SimpleTestCase

from campaigns.models import Campaign
from world.services.astronomy import (
    build_light_bands,
    calculate_local_sky,
    celestial_positions,
)


class RegionalAstronomyTests(SimpleTestCase):
    def setUp(self):
        self.campaign = Campaign()

    def test_longitude_changes_local_turn_time(self):
        reference = calculate_local_sky(self.campaign, 0, 0)
        east = calculate_local_sky(self.campaign, 0, 90)

        self.assertEqual(reference.local_moment.turn_clock, "000:00")
        self.assertEqual(reference.timezone_offset_minutes, 0)
        self.assertEqual(east.timezone_offset_minutes, -(42 * 60))
        self.assertNotEqual(reference.star_phase, east.star_phase)

    def test_equatorial_distance_uses_confirmed_circumference(self):
        sky = calculate_local_sky(self.campaign, 0, 90)

        self.assertEqual(sky.equatorial_offset_km, 18_050)

    def test_star_wraps_in_one_turn_and_ympha_in_sixteen(self):
        at_epoch = celestial_positions(self.campaign, 0)
        after_one_turn = celestial_positions(
            self.campaign,
            self.campaign.calendar_minutes_per_turn,
        )
        after_sixteen_turns = celestial_positions(
            self.campaign,
            self.campaign.calendar_minutes_per_turn * 16,
        )

        self.assertAlmostEqual(
            at_epoch["star_longitude"],
            after_one_turn["star_longitude"],
        )
        self.assertNotAlmostEqual(
            at_epoch["ympha_longitude"],
            after_one_turn["ympha_longitude"],
        )
        self.assertAlmostEqual(
            at_epoch["ympha_longitude"],
            after_sixteen_turns["ympha_longitude"],
        )

    def test_ympha_phase_is_local_to_longitude(self):
        at_peak = calculate_local_sky(self.campaign, 0, 0)
        opposite = calculate_local_sky(self.campaign, 0, 180)

        self.assertEqual(at_peak.ympha_visibility_percent, 100)
        self.assertEqual(opposite.ympha_visibility_percent, 0)
        self.assertNotEqual(at_peak.face_phase, opposite.face_phase)

    def test_svg_coordinates_are_not_localized_with_decimal_commas(self):
        positions = celestial_positions(self.campaign, 1234)
        bands = build_light_bands(self.campaign, 1234, steps=4)

        self.assertNotIn(",", positions["star_x"])
        self.assertNotIn(",", positions["ympha_x"])
        self.assertEqual(bands[1]["x"], "250.0000")

    def test_light_and_dark_seasons_are_local(self):
        first = calculate_local_sky(self.campaign, 0, 0)
        opposite = calculate_local_sky(self.campaign, 0, 180)

        self.assertNotEqual(first.season_light_code, opposite.season_light_code)
        self.assertIn(first.season_light_code, {"light", "dark", "mixed"})
        self.assertTrue(first.season_label.endswith("Лето"))
        self.assertGreater(first.season_turns, 9)
        self.assertLessEqual(first.season_turns, 11)
        self.assertGreaterEqual(first.season_red_fraction, 0)
        self.assertLessEqual(first.season_red_fraction, 1)
