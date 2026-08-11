import math

from django.test import SimpleTestCase

from campaigns.models import Campaign
from world.services.calendar import TURNS_PER_YEAR, describe_time, minutes_for_time_step
from world.services.orbital_climate import orbital_climate_state


class CalendarServiceTests(SimpleTestCase):
    minutes_per_hour = 60
    hours_per_turn = 168
    minutes_per_turn = hours_per_turn * minutes_per_hour

    def at_turn(self, turn):
        return describe_time(turn * self.minutes_per_turn)

    def test_epoch_starts_in_year_zero_and_first_light_phase(self):
        moment = self.at_turn(0)

        self.assertEqual(moment.year, 0)
        self.assertEqual(moment.season, "Лето")
        self.assertEqual(moment.turn_of_year, 1)
        self.assertEqual(moment.phase_of_turn, 1)
        self.assertEqual(moment.light_phase, "Рассвет")
        self.assertEqual(moment.face_phase, "Рассветание")
        self.assertEqual(moment.turn_clock, "000:00")

    def test_one_turn_is_a_168_hour_world_day(self):
        last_minute = describe_time(self.minutes_per_turn - 1)
        next_turn = describe_time(self.minutes_per_turn)

        self.assertEqual(last_minute.turn_of_year, 1)
        self.assertEqual(last_minute.phase_of_turn, 7)
        self.assertEqual(last_minute.turn_clock, "167:59")
        self.assertEqual(next_turn.turn_of_year, 2)
        self.assertEqual(next_turn.phase_of_turn, 1)
        self.assertEqual(next_turn.turn_clock, "000:00")

    def test_season_and_year_boundaries_follow_confirmed_calendar(self):
        autumn_start = orbital_climate_state(0).season_end_world_minutes
        autumn = describe_time(math.ceil(autumn_start))
        next_year = self.at_turn(TURNS_PER_YEAR)

        self.assertEqual(autumn.season, "Осень")
        self.assertEqual(autumn.turn_of_season, 1)
        self.assertEqual(next_year.year, 1)
        self.assertEqual(next_year.turn_of_year, 1)
        self.assertEqual(next_year.season, "Лето")

    def test_face_circle_switches_from_blossoming_to_fading(self):
        blossoming_peak = self.at_turn(7)
        fading_start = self.at_turn(8)

        self.assertEqual(blossoming_peak.face_circle_turn, 8)
        self.assertEqual(blossoming_peak.face_phase_name, "Пик Рассветания")
        self.assertEqual(fading_start.face_circle_turn, 9)
        self.assertEqual(fading_start.face_phase, "Угасание")
        self.assertEqual(fading_start.face_phase_name, "Начало Угасания")

    def test_face_phase_shifts_four_turns_each_year(self):
        starts = [
            self.at_turn(year * TURNS_PER_YEAR).face_circle_turn
            for year in range(5)
        ]

        self.assertEqual(starts, [1, 5, 9, 13, 1])

    def test_epoch_year_and_hour_subdivision_are_configurable(self):
        moment = describe_time(
            10 * 40 + 5,
            epoch_year=-3,
            hours_per_turn=70,
            minutes_per_hour=40,
        )

        self.assertEqual(moment.year, -3)
        self.assertEqual(moment.phase_of_turn, 2)
        self.assertEqual(moment.turn_clock, "010:05")

    def test_season_time_step_preserves_progress_across_unequal_seasons(self):
        campaign = Campaign(world_minutes=30 * 24 * 60)
        before = orbital_climate_state(campaign.world_minutes)
        minutes = minutes_for_time_step(campaign, 1, "seasons")
        after = orbital_climate_state(campaign.world_minutes + minutes)

        self.assertNotEqual(before.global_season, after.global_season)
        self.assertAlmostEqual(before.season_progress, after.season_progress, places=5)
