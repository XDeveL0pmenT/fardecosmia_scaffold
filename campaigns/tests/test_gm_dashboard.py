from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from world.models import AtmosphericConfig, Region


class GmDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gm",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="Фардекосмия")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.user,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(self.user)
        self.dashboard_url = reverse(
            "campaigns:gm_dashboard",
            kwargs={"campaign_id": self.campaign.pk},
        )
        self.advance_url = reverse(
            "campaigns:advance_time",
            kwargs={"campaign_id": self.campaign.pk},
        )
        self.atmosphere_url = reverse(
            "campaigns:configure_atmosphere",
            kwargs={"campaign_id": self.campaign.pk},
        )

    def test_dashboard_contains_calendar_and_dynamic_time_units(self):
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Календарь Фардекосмии")
        self.assertContains(response, "Год 0")
        self.assertContains(response, 'value="turns"')
        self.assertContains(response, "1 Виток = 168 часов")
        self.assertContains(response, 'type="range"')
        self.assertContains(response, "Глобальная атмосфера")
        self.assertContains(response, "Выключена")

    def test_gm_can_enable_atmosphere_from_campaign_dashboard(self):
        response = self.client.post(
            self.atmosphere_url,
            {
                "enabled": "on",
                "ocean_temperature_c": "45",
                "grid_width": "180",
                "grid_height": "90",
                "step_minutes": "360",
                "world_seed": "314",
            },
        )

        self.assertRedirects(response, self.dashboard_url)
        config = AtmosphericConfig.objects.get(campaign=self.campaign)
        self.assertTrue(config.enabled)
        self.assertEqual(config.ocean_temperature_c, 45)
        self.assertEqual(config.world_seed, 314)

    def test_atmosphere_cannot_be_enabled_without_ocean_temperature(self):
        response = self.client.post(
            self.atmosphere_url,
            {
                "enabled": "on",
                "ocean_temperature_c": "",
                "grid_width": "180",
                "grid_height": "90",
                "step_minutes": "360",
                "world_seed": "0",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Задайте температуру океана перед включением сетки",
            status_code=400,
        )
        self.assertFalse(AtmosphericConfig.objects.exists())

    def test_advance_accepts_calendar_units(self):
        response = self.client.post(
            self.advance_url,
            {"amount": "1", "unit": "turns"},
        )

        self.assertRedirects(response, self.dashboard_url)
        self.campaign.refresh_from_db()
        self.assertEqual(
            self.campaign.world_minutes,
            self.campaign.calendar_minutes_per_turn,
        )

    def test_advance_accepts_reported_thirty_seven_hour_scenario(self):
        response = self.client.post(
            self.advance_url,
            {"amount": "37", "unit": "hours"},
        )

        self.assertRedirects(response, self.dashboard_url)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.world_minutes, 37 * 60)

    def test_advance_rejects_values_outside_unit_limit(self):
        response = self.client.post(
            self.advance_url,
            {"amount": "999", "unit": "years"},
        )

        self.assertEqual(response.status_code, 400)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.world_minutes, 0)

    def test_advance_can_return_to_the_current_campaign_page(self):
        map_url = reverse(
            "world:world_map",
            kwargs={"campaign_id": self.campaign.pk},
        )

        response = self.client.post(
            self.advance_url,
            {"amount": "10", "unit": "minutes", "next": map_url},
        )

        self.assertRedirects(response, map_url)

    @patch("campaigns.views.advance_world")
    def test_database_lock_returns_clear_service_response(self, advance_mock):
        advance_mock.side_effect = OperationalError("database is locked")

        response = self.client.post(
            self.advance_url,
            {"amount": "37", "unit": "hours"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "SQLite занят другим процессом", status_code=503)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.world_minutes, 0)

    def test_dashboard_region_row_uses_local_time_and_face(self):
        Region.objects.create(
            campaign=self.campaign,
            name="Восточный регион",
            biome=Region.Biome.LEGACY_COAST,
            map_longitude=90,
            map_latitude=0,
        )

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, "126:00")
        self.assertContains(response, "Рассветание")
        self.assertContains(response, "видимость Ympha")
