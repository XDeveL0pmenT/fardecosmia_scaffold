import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership, TimeAdvanceReport
from world.models import (
    CampaignWorldMapOverride,
    GlobalWorldMapLayer,
    Region,
    WeatherState,
    WorldEvent,
)
from world.services.map_layers import load_land_mask


class WorldMapViewTests(TestCase):
    polygon = [[0.49, 0.49], [0.52, 0.49], [0.51, 0.53]]

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cartographer",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="Карта Фардекосмии")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.user,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(self.user)
        self.map_url = reverse(
            "world:world_map",
            kwargs={"campaign_id": self.campaign.pk},
        )

    def test_map_renders_canonical_image_and_drawing_ui(self):
        response = self.client.get(self.map_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fardecosmia-world-map.webp")
        self.assertContains(response, "Новый контур")
        self.assertContains(response, "Звезда · пик света")
        self.assertContains(response, "fardecosmia-temperature-map.webp")
        self.assertContains(response, "На весь экран")
        self.assertContains(response, "Средняя температура")
        self.assertContains(response, "fardecosmia-elevation-map.webp")
        self.assertContains(response, "data-map-tooltip")

    def test_map_get_does_not_generate_weather(self):
        Region.objects.create(
            campaign=self.campaign,
            name="Без погоды",
            biome=Region.Biome.FOREST,
        )

        self.client.get(self.map_url)

        self.assertEqual(WeatherState.objects.count(), 0)

    def test_gm_can_draw_and_create_region(self):
        response = self.client.post(
            self.map_url,
            {
                "action": "create",
                "create-name": "Нарисованный регион",
                "create-biome": Region.Biome.MEADOW,
                "create-base_temperature": "12",
                "create-seasonal_amplitude": "15",
                "create-humidity": "60",
                "create-elevation": "100",
                "create-weather_volatility": "1",
                "create-map_polygon": json.dumps(self.polygon),
            },
        )

        region = Region.objects.get(name="Нарисованный регион")
        self.assertRedirects(
            response,
            reverse(
                "world:region_detail",
                kwargs={
                    "campaign_id": self.campaign.pk,
                    "region_id": region.pk,
                },
            ),
        )
        self.assertIsNotNone(region.map_longitude)
        self.assertIsNotNone(region.map_latitude)
        self.assertEqual(region.map_polygon, self.polygon)

    def test_gm_can_place_existing_region(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Существующий регион",
            biome=Region.Biome.TUNDRA,
        )

        response = self.client.post(
            self.map_url,
            {
                "action": "place",
                "placement-region_id": str(region.pk),
                "placement-map_polygon": json.dumps(self.polygon),
            },
        )

        self.assertEqual(response.status_code, 302)
        region.refresh_from_db()
        self.assertEqual(region.map_polygon, self.polygon)
        self.assertIsNotNone(region.map_longitude)

    def test_gm_can_save_sparse_biome_layer(self):
        land_index = load_land_mask()["values"].index(1)
        response = self.client.post(
            self.map_url,
            {
                "action": "save-layer",
                "layer-layer_type": "biome",
                "layer-layer_cells": json.dumps({str(land_index): Region.Biome.TUNDRA}),
            },
        )

        self.assertEqual(response.status_code, 302)
        layer = CampaignWorldMapOverride.objects.get(campaign=self.campaign)
        self.assertEqual(layer.biome_cells, {str(land_index): Region.Biome.TUNDRA})
        self.assertFalse(GlobalWorldMapLayer.objects.exists())

    def test_campaign_biome_override_does_not_change_global_atlas(self):
        land_index = load_land_mask()["values"].index(1)
        global_layer = GlobalWorldMapLayer.objects.create(
            biome_cells={str(land_index): Region.Biome.FOREST},
        )

        self.client.post(
            self.map_url,
            {
                "action": "save-layer",
                "layer-layer_type": "biome",
                "layer-layer_cells": json.dumps({str(land_index): Region.Biome.TUNDRA}),
            },
        )

        global_layer.refresh_from_db()
        response = self.client.get(self.map_url)
        self.assertEqual(global_layer.biome_cells[str(land_index)], Region.Biome.FOREST)
        self.assertEqual(
            response.context["biome_cells"][str(land_index)],
            Region.Biome.TUNDRA,
        )
        self.assertEqual(
            response.context["global_biome_cells"][str(land_index)],
            Region.Biome.FOREST,
        )

    def test_biome_layer_rejects_water_cells(self):
        water_index = load_land_mask()["values"].index(0)
        response = self.client.post(
            self.map_url,
            {
                "action": "save-layer",
                "layer-layer_type": "biome",
                "layer-layer_cells": json.dumps({str(water_index): Region.Biome.LEGACY_COAST}),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Биом нельзя рисовать за пределами суши")
        self.assertFalse(CampaignWorldMapOverride.objects.exists())

    def test_global_atlas_is_independent_from_campaign_route(self):
        response = self.client.get(reverse("world:global_world_map"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Общий атлас Фардекосмии")
        self.assertContains(response, "fardecosmia-temperature-map.webp")
        self.assertContains(response, "fardecosmia-elevation-map.webp")

    def test_global_atlas_is_not_exposed_to_player(self):
        player = get_user_model().objects.create_user(
            username="atlas-player",
            password="test-password",
        )
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.client.force_login(player)

        response = self.client.get(reverse("world:global_world_map"))

        self.assertEqual(response.status_code, 403)

    def test_region_page_has_local_sky_and_does_not_mutate_weather_on_get(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Местное небо",
            biome=Region.Biome.LEGACY_COAST,
            map_longitude=90,
            map_latitude=30,
            map_polygon=self.polygon,
        )
        url = reverse(
            "world:region_detail",
            kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Местное время Витка")
        self.assertContains(response, "Видимость Ympha ночью")
        self.assertContains(response, "region-atmosphere--")
        self.assertEqual(WeatherState.objects.count(), 0)

    def test_time_advance_report_is_displayed_after_return_to_region(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Регион со сводкой",
            biome=Region.Biome.MEADOW,
            map_longitude=20,
            map_latitude=10,
            map_polygon=self.polygon,
        )
        region_url = reverse(
            "world:region_detail",
            kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
        )

        response = self.client.post(
            reverse(
                "campaigns:advance_time",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {"amount": "10", "unit": "minutes", "next": region_url},
            follow=True,
        )

        report = TimeAdvanceReport.objects.get(campaign=self.campaign)
        self.assertRedirects(
            response,
            f"{region_url}?advance_report={report.pk}",
        )
        self.assertEqual(response.context["time_advance_report"], report)
        self.assertContains(response, "Сводка продвижения времени")

        report.summary["regional_weather"][0]["integrated_precipitation"] = {
            "integrated_amount_mm": 2.4,
            "rain_amount_mm": 2.4,
            "snow_water_equivalent_mm": 0.0,
            "maximum_rate_mm_h": 0.4,
            "sampled_steps": 1,
            "wet_steps": 1,
        }
        report.summary["extremes"]["precipitation_maximum"] = {
            "region_name": region.name,
            "value": 2.4,
        }
        report.save(update_fields=["summary"])

        response = self.client.get(f"{region_url}?advance_report={report.pk}")
        self.assertContains(response, "2,40 мм")
        self.assertContains(response, "Осадки за подробно рассчитанную часть периода")

    def test_region_page_explains_weather_units(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Понятная погода",
            biome=Region.Biome.MEADOW,
            map_longitude=20,
            map_latitude=10,
            map_polygon=self.polygon,
        )
        WeatherState.objects.create(
            region=region,
            world_minutes=0,
            temperature=18,
            humidity=72,
            wind_speed=12.7,
            wind_direction_degrees=225,
            pressure_hpa=1002.4,
            cloud_cover=0.72,
            precipitation=0.8,
            condition=WeatherState.Condition.RAIN,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V1,
        )

        response = self.client.get(
            reverse(
                "world:region_detail",
                kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
            )
        )

        self.assertContains(response, "м/с")
        self.assertContains(response, "км/ч")
        self.assertContains(response, "откуда")
        self.assertContains(response, "относительная величина модели")

    def test_region_page_shows_c3_traveller_summary_and_physical_precipitation(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Регион C3",
            biome=Region.Biome.MEADOW,
            map_longitude=20,
            map_latitude=10,
            map_polygon=self.polygon,
        )
        WeatherState.objects.create(
            region=region,
            world_minutes=0,
            temperature=38,
            humidity=85,
            wind_speed=6,
            wind_direction_degrees=315,
            pressure_hpa=970,
            cloud_cover=0.9,
            precipitation=0,
            precipitation_rate_mm_h=8.0,
            precipitation_amount_mm=48.0,
            rain_fraction=1.0,
            snow_fraction=0.0,
            condition=WeatherState.Condition.RAIN,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )

        response = self.client.get(
            reverse(
                "world:region_detail",
                kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
            )
        )

        self.assertContains(response, "Условия для путника")
        self.assertContains(response, "Влажный термометр")
        self.assertContains(response, "8.00 мм/ч")
        self.assertContains(response, "Осадки сейчас")
        self.assertContains(response, "Сумма осадков за прокрутку времени")
        self.assertContains(response, "1 кг/м² = 1 мм")
        self.assertNotContains(response, "не хватает кислорода")

    def test_gm_can_confirm_and_delete_region(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Удаляемый регион",
            biome=Region.Biome.MEADOW,
        )
        weather = WeatherState.objects.create(
            region=region,
            world_minutes=0,
            temperature=10,
            humidity=50,
            condition=WeatherState.Condition.CLEAR,
        )
        event = WorldEvent.objects.create(
            campaign=self.campaign,
            region=region,
            title="Событие региона",
            trigger_at=120,
        )
        delete_url = reverse(
            "world:region_delete",
            kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
        )

        confirmation = self.client.get(delete_url)

        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "Удалить регион «Удаляемый регион»?")
        self.assertContains(confirmation, "Состояний погоды: 1")
        self.assertTrue(Region.objects.filter(pk=region.pk).exists())

        response = self.client.post(delete_url, follow=True)

        self.assertRedirects(response, self.map_url)
        self.assertFalse(Region.objects.filter(pk=region.pk).exists())
        self.assertFalse(WeatherState.objects.filter(pk=weather.pk).exists())
        event.refresh_from_db()
        self.assertIsNone(event.region_id)
        self.assertContains(response, "Регион «Удаляемый регион» удалён.")

    def test_player_cannot_delete_region(self):
        region = Region.objects.create(
            campaign=self.campaign,
            name="Защищённый регион",
            biome=Region.Biome.FOREST,
        )
        player = get_user_model().objects.create_user(
            username="region-delete-player",
            password="test-password",
        )
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.client.force_login(player)

        response = self.client.post(
            reverse(
                "world:region_delete",
                kwargs={"campaign_id": self.campaign.pk, "region_id": region.pk},
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Region.objects.filter(pk=region.pk).exists())

    def test_player_cannot_open_objective_world_map(self):
        player = get_user_model().objects.create_user(
            username="player",
            password="test-password",
        )
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.client.force_login(player)

        response = self.client.get(self.map_url)

        self.assertEqual(response.status_code, 403)
