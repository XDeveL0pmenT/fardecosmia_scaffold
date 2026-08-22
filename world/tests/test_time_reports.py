from django.contrib.auth import get_user_model
from django.test import TestCase

from campaigns.models import Campaign, CampaignMembership, TimeAdvanceReport
from world.biomes import Biome
from world.models import AtmosphericConfig, Region, WeatherState, WorldEvent
from world.services.time import advance_world
from world.services.time_reports import build_time_advance_summary
from world.services.orbital_climate import CANONICAL_YEAR_MINUTES


class TimeAdvanceReportTests(TestCase):
    def setUp(self):
        self.gm = get_user_model().objects.create_user(
            username="report-gm",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="Отчётная кампания")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        self.region = Region.objects.create(
            campaign=self.campaign,
            name="Долина",
            biome=Biome.MEADOW,
            weather_update_interval_minutes=360,
        )

    def weather(self, minute, condition, temperature, *, wind=4, precipitation=0):
        return WeatherState.objects.create(
            region=self.region,
            world_minutes=minute,
            condition=condition,
            temperature=temperature,
            humidity=70,
            wind_speed=wind,
            precipitation=precipitation,
        )

    def test_dominant_condition_and_rain_states_merge_into_one_episode(self):
        self.weather(0, WeatherState.Condition.CLEAR, 12)
        rain_one = self.weather(
            360,
            WeatherState.Condition.RAIN,
            10,
            precipitation=2,
        )
        storm = self.weather(
            720,
            WeatherState.Condition.STORM,
            8,
            wind=22,
            precipitation=12,
        )
        rain_two = self.weather(
            1080,
            WeatherState.Condition.RAIN,
            9,
            precipitation=3,
        )

        summary = build_time_advance_summary(
            self.campaign,
            [self.region],
            [rain_one, storm, rain_two],
            [],
            start=0,
            end=1440,
            amount=1,
            unit="phases",
            simulation_mode="exact",
            weather_coverage_start=0,
        )
        regional = summary["regional_weather"][0]

        self.assertEqual(regional["dominant_condition"], WeatherState.Condition.RAIN)
        shares = {
            item["condition"]: item["percent"]
            for item in regional["condition_shares"]
        }
        self.assertEqual(shares[WeatherState.Condition.RAIN], 50.0)
        self.assertTrue(regional["summary"].startswith("Преимущественно дождливо"))
        self.assertEqual(len(regional["periods"]["precipitation"]), 1)
        self.assertEqual(
            regional["periods"]["precipitation"][0]["duration_minutes"],
            1080,
        )
        self.assertEqual(len(regional["notable_episodes"]), 1)
        self.assertEqual(regional["notable_episodes"][0]["start"], 360)
        self.assertEqual(regional["notable_episodes"][0]["end"], 1440)
        self.assertEqual(regional["temperature"]["minimum"], 8)
        self.assertEqual(regional["maximum_wind_speed"], 22)
        self.assertTrue(summary["global_highlights"])
        self.assertEqual(summary["global_highlights"][0]["title"], "Грозовой эпизод")

    def test_exact_advance_persists_exact_coverage_report(self):
        result = advance_world(
            self.campaign.pk,
            720,
            advanced_by=self.gm,
            requested_amount=12,
            requested_unit="hours",
        )

        report = result.report
        self.assertIsNotNone(report)
        self.assertEqual(TimeAdvanceReport.objects.count(), 1)
        self.assertEqual(report.gm, self.gm)
        self.assertEqual(report.simulation_mode, TimeAdvanceReport.SimulationMode.EXACT)
        self.assertEqual(
            report.coverage,
            [{"kind": "exact", "start": 0, "end": 720}],
        )
        self.assertEqual(report.summary["weather_scope"], "exact")
        self.assertIn("world_events", report.summary)
        self.assertIn("astronomical_events", report.summary)

    def test_report_sums_step_amounts_separately_from_current_rate(self):
        self.weather(0, WeatherState.Condition.CLEAR, 12)
        wet = WeatherState.objects.create(
            region=self.region,
            world_minutes=360,
            condition=WeatherState.Condition.RAIN,
            temperature=10,
            humidity=98,
            wind_speed=4,
            precipitation=0,
            precipitation_rate_mm_h=0.4,
            precipitation_amount_mm=2.4,
            rain_fraction=1.0,
            snow_fraction=0.0,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )
        dry_now = WeatherState.objects.create(
            region=self.region,
            world_minutes=720,
            condition=WeatherState.Condition.CLEAR,
            temperature=12,
            humidity=60,
            wind_speed=2,
            precipitation=0,
            precipitation_rate_mm_h=0.0,
            precipitation_amount_mm=0.0,
            rain_fraction=1.0,
            snow_fraction=0.0,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )

        summary = build_time_advance_summary(
            self.campaign,
            [self.region],
            [wet, dry_now],
            [],
            start=0,
            end=720,
            amount=12,
            unit="hours",
            simulation_mode="exact",
            weather_coverage_start=0,
        )
        regional = summary["regional_weather"][0]

        self.assertEqual(dry_now.precipitation_rate_mm_h, 0.0)
        self.assertEqual(
            regional["integrated_precipitation"],
            {
                "integrated_amount_mm": 2.4,
                "rain_amount_mm": 2.4,
                "snow_water_equivalent_mm": 0.0,
                "maximum_rate_mm_h": 0.4,
                "sampled_steps": 2,
                "wet_steps": 1,
            },
        )
        self.assertIn("2.40 мм осадков", regional["summary"])
        self.assertEqual(summary["extremes"]["precipitation_maximum"]["value"], 2.4)

    def test_fast_forward_integrated_precipitation_ignores_unsimulated_interval(self):
        self.weather(0, WeatherState.Condition.CLEAR, 12)
        skipped = WeatherState.objects.create(
            region=self.region,
            world_minutes=360,
            condition=WeatherState.Condition.RAIN,
            temperature=10,
            humidity=98,
            wind_speed=4,
            precipitation=0,
            precipitation_rate_mm_h=4.0,
            precipitation_amount_mm=24.0,
            rain_fraction=1.0,
            snow_fraction=0.0,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )
        spinup = WeatherState.objects.create(
            region=self.region,
            world_minutes=1080,
            condition=WeatherState.Condition.SNOW,
            temperature=-5,
            humidity=99,
            wind_speed=3,
            precipitation=0,
            precipitation_rate_mm_h=0.5,
            precipitation_amount_mm=3.0,
            rain_fraction=0.0,
            snow_fraction=1.0,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )

        summary = build_time_advance_summary(
            self.campaign,
            [self.region],
            [skipped, spinup],
            [],
            start=0,
            end=1080,
            amount=1,
            unit="turns",
            simulation_mode="fast_forward",
            weather_coverage_start=720,
        )

        precipitation = summary["regional_weather"][0]["integrated_precipitation"]
        self.assertEqual(precipitation["integrated_amount_mm"], 3.0)
        self.assertEqual(precipitation["snow_water_equivalent_mm"], 3.0)
        self.assertEqual(precipitation["sampled_steps"], 1)

    def test_fast_forward_has_only_final_spinup_weather_and_real_events(self):
        self.campaign.exact_simulation_max_turns = 1
        self.campaign.fast_forward_spinup_turns = 1
        self.campaign.save(
            update_fields=["exact_simulation_max_turns", "fast_forward_spinup_turns"]
        )
        turn = self.campaign.calendar_minutes_per_turn
        event = WorldEvent.objects.create(
            campaign=self.campaign,
            title="Совет городов",
            trigger_at=turn,
        )

        result = advance_world(
            self.campaign.pk,
            3 * turn,
            advanced_by=self.gm,
            requested_amount=3,
            requested_unit="turns",
        )

        report = result.report
        spinup_start = 2 * turn
        self.assertEqual(
            report.simulation_mode,
            TimeAdvanceReport.SimulationMode.FAST_FORWARD,
        )
        self.assertEqual(
            report.coverage,
            [
                {"kind": "fast_forwarded", "start": 0, "end": spinup_start},
                {"kind": "spinup", "start": spinup_start, "end": 3 * turn},
            ],
        )
        self.assertEqual(report.summary["weather_scope"], "final_spinup")
        self.assertIn("climate_summary", report.summary)
        self.assertFalse(
            self.region.weather_history.filter(
                world_minutes__gt=0,
                world_minutes__lt=spinup_start,
            ).exists()
        )
        self.assertTrue(
            self.region.weather_history.filter(world_minutes__gte=spinup_start).exists()
        )
        for highlight in report.summary["global_highlights"]:
            if "start" in highlight:
                self.assertGreaterEqual(highlight["start"], spinup_start)
            if "world_minutes" in highlight:
                self.assertGreaterEqual(highlight["world_minutes"], spinup_start)
        self.assertEqual(report.summary["world_events"][0]["id"], event.pk)
        event.refresh_from_db()
        self.assertEqual(event.status, WorldEvent.Status.TRIGGERED)

    def test_fast_forward_reports_real_astronomical_milestones(self):
        self.campaign.exact_simulation_max_turns = 1
        self.campaign.fast_forward_spinup_turns = 1
        self.campaign.save(
            update_fields=["exact_simulation_max_turns", "fast_forward_spinup_turns"]
        )

        report = advance_world(
            self.campaign.pk,
            CANONICAL_YEAR_MINUTES,
            advanced_by=self.gm,
            requested_amount=1,
            requested_unit="years",
        ).report
        kinds = [event["kind"] for event in report.summary["astronomical_events"]]

        self.assertEqual(report.simulation_mode, TimeAdvanceReport.SimulationMode.FAST_FORWARD)
        self.assertEqual(kinds.count("season_transition"), 4)
        self.assertEqual(kinds.count("periapsis"), 1)
        self.assertEqual(kinds.count("apoapsis"), 1)

    def test_atmospheric_report_persists_compact_ocean_summary(self):
        self.region.map_latitude = 0
        self.region.map_longitude = 0
        self.region.save(update_fields=["map_latitude", "map_longitude"])
        AtmosphericConfig.objects.create(
            campaign=self.campaign,
            enabled=True,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            world_seed=73,
        )

        report = advance_world(
            self.campaign.pk,
            360,
            advanced_by=self.gm,
            requested_amount=6,
            requested_unit="hours",
        ).report

        ocean = report.summary["ocean_summary"]
        self.assertEqual(ocean["mode"], "exact")
        self.assertIn("end_mean_sst_c", ocean)
        self.assertIn("maximum_evaporation_kg_m2_day", ocean)
        self.assertIn("atmospheric_vapor_mass_proxy_change_percent", ocean)
        self.assertNotIn("weather_states", ocean)
