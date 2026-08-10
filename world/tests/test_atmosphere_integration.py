from unittest.mock import patch

from django.test import TestCase

from campaigns.models import Campaign
from world.biomes import Biome
from world.models import AtmosphericConfig, AtmosphericSnapshot, Region, WeatherState
from world.services.time import advance_world
from world.services.atmosphere import sampling


class AtmosphericIntegrationTests(TestCase):
    def create_campaign(self, name):
        campaign = Campaign.objects.create(name=name)
        AtmosphericConfig.objects.create(
            campaign=campaign,
            enabled=True,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            world_seed=443,
            ocean_temperature_c=45,
            parameters={
                "initial_temperature_noise_c": 0.2,
                "pressure_noise_hpa": 0.1,
            },
        )
        return campaign

    def test_time_advance_saves_grid_and_region_weather_snapshot(self):
        campaign = self.create_campaign("Атмосферная кампания")
        region = Region.objects.create(
            campaign=campaign,
            name="Регион сетки",
            biome=Biome.MEADOW,
            map_latitude=10,
            map_longitude=20,
        )

        advance_world(campaign.pk, 360)

        self.assertEqual(
            list(
                AtmosphericSnapshot.objects.filter(campaign=campaign)
                .order_by("world_minutes")
                .values_list("world_minutes", flat=True)
            ),
            [0, 360],
        )
        weather = region.weather_history.order_by("-world_minutes").first()
        self.assertEqual(weather.source, WeatherState.Source.ATMOSPHERIC_GRID_V1)
        self.assertIsNotNone(weather.pressure_hpa)
        self.assertIsNotNone(weather.cloud_cover)

    def test_region_without_map_position_stays_on_legacy_weather(self):
        campaign = self.create_campaign("Смешанная кампания")
        region = Region.objects.create(
            campaign=campaign,
            name="Неразмещённый регион",
            biome=Biome.TUNDRA,
        )

        advance_world(campaign.pk, 360)

        self.assertEqual(
            region.weather_history.order_by("-world_minutes").first().source,
            WeatherState.Source.LEGACY_V2,
        )

    def test_each_snapshot_is_deserialized_once_for_all_regions(self):
        campaign = self.create_campaign("Пакетная выборка")
        for index in range(3):
            Region.objects.create(
                campaign=campaign,
                name=f"Регион {index}",
                biome=Biome.MEADOW,
                map_latitude=10 + index,
                map_longitude=20 + index,
            )

        with patch(
            "world.services.atmosphere.sampling.grid_from_snapshot",
            wraps=sampling.grid_from_snapshot,
        ) as deserialize:
            advance_world(campaign.pk, 360)

        self.assertEqual(deserialize.call_count, 2)
        self.assertEqual(WeatherState.objects.filter(region__campaign=campaign).count(), 6)

    def test_sub_step_advance_skips_static_grid_after_initial_snapshot(self):
        campaign = self.create_campaign("Короткая прокрутка")
        Region.objects.create(
            campaign=campaign,
            name="Регион",
            biome=Biome.MEADOW,
            map_latitude=10,
            map_longitude=20,
        )
        advance_world(campaign.pk, 360)
        snapshot_count = campaign.atmospheric_snapshots.count()

        with patch(
            "world.services.atmosphere.persistence.cached_static_world_grid"
        ) as static_grid:
            advance_world(campaign.pk, 10)

        static_grid.assert_not_called()
        self.assertEqual(campaign.atmospheric_snapshots.count(), snapshot_count)

    def test_one_day_advance_matches_four_sequential_six_hour_advances(self):
        one_call = self.create_campaign("Один вызов")
        four_calls = self.create_campaign("Четыре вызова")

        advance_world(one_call.pk, 1440)
        for _ in range(4):
            advance_world(four_calls.pk, 360)

        one_payload = one_call.atmospheric_snapshots.get(world_minutes=1440).payload
        four_payload = four_calls.atmospheric_snapshots.get(world_minutes=1440).payload
        self.assertEqual(bytes(one_payload), bytes(four_payload))

    def test_disabled_configuration_preserves_weather_v2(self):
        campaign = Campaign.objects.create(name="Прежняя погода")
        AtmosphericConfig.objects.create(campaign=campaign, enabled=False)
        region = Region.objects.create(
            campaign=campaign,
            name="Legacy",
            biome=Biome.FOREST,
        )

        advance_world(campaign.pk, 360)

        self.assertFalse(campaign.atmospheric_snapshots.exists())
        self.assertEqual(
            region.weather_history.order_by("-world_minutes").first().source,
            WeatherState.Source.LEGACY_V2,
        )
