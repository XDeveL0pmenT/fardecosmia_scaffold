from django.test import TestCase

from campaigns.models import Campaign
from world.models import Region, WeatherState
from world.services.time import advance_world
from world.services.weather import generate_weather


class WeatherSimulationTests(TestCase):
    def setUp(self):
        self.campaign = Campaign.objects.create(name="Погодная кампания")
        self.region = Region.objects.create(
            campaign=self.campaign,
            name="Тестовый регион",
            biome=Region.Biome.MEADOW,
            weather_update_interval_minutes=360,
        )

    def test_short_advance_does_not_recalculate_existing_weather(self):
        initial = generate_weather(self.region, 0)

        advance_world(self.campaign.pk, 10)

        self.assertEqual(self.region.weather_history.count(), 1)
        self.assertEqual(self.region.weather_history.first().pk, initial.pk)

    def test_weather_is_generated_at_crossed_intervals(self):
        generate_weather(self.region, 0)

        advance_world(self.campaign.pk, 750)

        self.assertEqual(
            list(
                self.region.weather_history.order_by("world_minutes").values_list(
                    "world_minutes", flat=True
                )
            ),
            [0, 360, 720],
        )

    def test_temperature_uses_region_base_temperature(self):
        warm_region = Region.objects.create(
            campaign=self.campaign,
            name="Тёплый регион",
            biome=Region.Biome.LEGACY_COAST,
            base_temperature=30,
            seasonal_amplitude=0,
            light_cycle_temperature_amplitude=0,
            ympha_temperature_influence=0,
            weather_volatility=0,
            weather_persistence=0,
        )
        cold_region = Region.objects.create(
            campaign=self.campaign,
            name="Холодный регион",
            biome=Region.Biome.TUNDRA,
            base_temperature=-10,
            seasonal_amplitude=0,
            light_cycle_temperature_amplitude=0,
            ympha_temperature_influence=0,
            weather_volatility=0,
            weather_persistence=0,
        )

        warm = generate_weather(warm_region, 0)
        cold = generate_weather(cold_region, 0)

        self.assertEqual(warm.temperature - cold.temperature, 40)

    def test_summer_is_warmer_than_winter_for_same_region(self):
        self.region.seasonal_amplitude = 20
        self.region.light_cycle_temperature_amplitude = 0
        self.region.ympha_temperature_influence = 0
        self.region.weather_volatility = 0
        self.region.weather_persistence = 0
        self.region.save()
        minutes_per_phase = self.campaign.calendar_minutes_per_phase

        summer = generate_weather(self.region, 45 * minutes_per_phase)
        winter = generate_weather(self.region, (45 + 182) * minutes_per_phase)

        self.assertGreater(summer.temperature, winter.temperature)

    def test_snow_cannot_be_generated_above_freezing(self):
        self.region.base_temperature = 40
        self.region.seasonal_amplitude = 0
        self.region.light_cycle_temperature_amplitude = 0
        self.region.ympha_temperature_influence = 0
        self.region.weather_volatility = 0
        self.region.humidity = 100
        self.region.save()

        weather = generate_weather(self.region, 0)

        self.assertNotEqual(weather.condition, WeatherState.Condition.SNOW)

    def test_region_longitude_changes_light_temperature(self):
        self.region.base_temperature = 0
        self.region.seasonal_amplitude = 0
        self.region.light_cycle_temperature_amplitude = 20
        self.region.ympha_temperature_influence = 0
        self.region.weather_volatility = 0
        self.region.weather_persistence = 0
        self.region.map_longitude = 0
        self.region.map_latitude = 0
        self.region.save()
        bright_region = Region.objects.create(
            campaign=self.campaign,
            name="Регион яркого света",
            biome=Region.Biome.MEADOW,
            base_temperature=0,
            seasonal_amplitude=0,
            light_cycle_temperature_amplitude=20,
            ympha_temperature_influence=0,
            weather_volatility=0,
            weather_persistence=0,
            map_longitude=-(360 * 2 / 7),
            map_latitude=0,
        )

        reference_weather = generate_weather(self.region, 0)
        bright_weather = generate_weather(bright_region, 0)

        self.assertGreater(bright_weather.temperature, reference_weather.temperature)

    def test_light_season_changes_temperature_at_same_calendar_season(self):
        common = {
            "campaign": self.campaign,
            "biome": Region.Biome.MEADOW,
            "base_temperature": 0,
            "seasonal_amplitude": 0,
            "light_cycle_temperature_amplitude": 0,
            "ympha_temperature_influence": 0,
            "season_light_temperature_influence": 10,
            "weather_volatility": 0,
            "weather_persistence": 0,
            "map_latitude": 0,
        }
        dark_season = Region.objects.create(
            name="Тёмный сезон",
            map_longitude=0,
            **common,
        )
        light_season = Region.objects.create(
            name="Светлый сезон",
            map_longitude=180,
            **common,
        )

        dark_weather = generate_weather(dark_season, 0)
        light_weather = generate_weather(light_season, 0)

        self.assertGreater(light_weather.temperature, dark_weather.temperature)

    def test_cold_humid_winter_can_generate_snow(self):
        self.region.base_temperature = -30
        self.region.seasonal_amplitude = 0
        self.region.light_cycle_temperature_amplitude = 0
        self.region.ympha_temperature_influence = 0
        self.region.season_light_temperature_influence = 0
        self.region.weather_volatility = 0
        self.region.weather_persistence = 0
        self.region.humidity = 100
        self.region.save()
        winter_start = 26 * self.campaign.calendar_minutes_per_turn

        conditions = {
            generate_weather(self.region, winter_start + index * 360).condition
            for index in range(12)
        }

        self.assertIn(WeatherState.Condition.SNOW, conditions)
