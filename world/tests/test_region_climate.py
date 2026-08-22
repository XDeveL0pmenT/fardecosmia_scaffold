import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from world.models import (
    AtmosphericConfig,
    CampaignWorldMapOverride,
    GlobalWorldMapLayer,
    Region,
    WeatherState,
)
from world.services.region_climate import (
    climatological_humidity_at,
    region_climate_at,
)
from world.services.time import advance_world
from world.services.world_data import (
    MAP_GRID_HEIGHT,
    MAP_GRID_WIDTH,
    load_average_temperature_grid,
    load_elevation_grid,
    load_land_mask,
)


def coordinates_for_index(index):
    x = index % MAP_GRID_WIDTH
    y = index // MAP_GRID_WIDTH
    longitude = -180.0 + (x + 0.5) * 360.0 / MAP_GRID_WIDTH
    latitude = 90.0 - (y + 0.5) * 180.0 / MAP_GRID_HEIGHT
    return latitude, longitude


def polygon_for_coordinates(latitude, longitude):
    x = (longitude + 180.0) / 360.0
    y = (90.0 - latitude) / 180.0
    delta = 0.0005
    return [
        [x - delta, y - delta],
        [x + delta, y - delta],
        [x, y + delta],
    ]


class RegionClimateAutoconfigurationTests(TestCase):
    def setUp(self):
        mask = load_land_mask()["values"]
        elevations = load_elevation_grid()["values"]
        temperatures = load_average_temperature_grid()["values"]
        candidates = [
            index
            for index, is_land in enumerate(mask)
            if is_land
            and elevations[index] is not None
            and 1 < index % MAP_GRID_WIDTH < MAP_GRID_WIDTH - 2
        ]
        self.first_index = candidates[0]
        self.second_index = next(
            index
            for index in candidates[1:]
            if temperatures[index] != temperatures[self.first_index]
            and elevations[index] != elevations[self.first_index]
        )
        self.first_coordinates = coordinates_for_index(self.first_index)
        self.second_coordinates = coordinates_for_index(self.second_index)
        self.first_polygon = polygon_for_coordinates(*self.first_coordinates)
        self.second_polygon = polygon_for_coordinates(*self.second_coordinates)

        self.user = get_user_model().objects.create_user(
            username="climate-gm",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="Автоклимат")
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
        self.preview_url = reverse(
            "world:region_climate_preview",
            kwargs={"campaign_id": self.campaign.pk},
        )

    def create_global_layer(self, cells=None):
        return GlobalWorldMapLayer.objects.create(
            biome_cells=cells or {str(self.first_index): Region.Biome.FOREST},
        )

    def test_biome_temperature_elevation_and_humidity_come_from_world_data(self):
        self.create_global_layer()
        latitude, longitude = self.first_coordinates
        climate = region_climate_at(self.campaign, latitude, longitude)

        self.assertEqual(climate["biome"], Region.Biome.FOREST)
        self.assertEqual(
            climate["base_temperature"],
            load_average_temperature_grid()["values"][self.first_index],
        )
        self.assertEqual(
            climate["elevation"],
            load_elevation_grid()["values"][self.first_index],
        )
        self.assertEqual(climate["humidity"], 50.0)

    def test_climatological_humidity_reuses_configured_grid_baseline(self):
        AtmosphericConfig.objects.create(
            campaign=self.campaign,
            parameters={"initial_land_humidity": 63.5},
        )
        latitude, longitude = self.first_coordinates

        self.assertEqual(
            climatological_humidity_at(
                latitude,
                longitude,
                campaign=self.campaign,
            ),
            63.5,
        )
        self.assertEqual(
            region_climate_at(self.campaign, latitude, longitude)["humidity"],
            63.5,
        )

    def test_campaign_biome_override_is_used_and_identified(self):
        self.create_global_layer()
        CampaignWorldMapOverride.objects.create(
            campaign=self.campaign,
            biome_cells={str(self.first_index): Region.Biome.RED_PLATEAUS},
        )
        climate = region_climate_at(self.campaign, *self.first_coordinates)

        self.assertEqual(climate["biome"], Region.Biome.RED_PLATEAUS)
        self.assertEqual(climate["biome_source"], "campaign_override")

    def test_post_without_manual_climate_fields_autopopulates(self):
        self.create_global_layer()
        response = self.client.post(
            self.map_url,
            {
                "action": "create",
                "create-name": "Автоматический регион",
                "create-map_polygon": json.dumps(self.first_polygon),
            },
        )

        self.assertEqual(response.status_code, 302)
        region = Region.objects.get(name="Автоматический регион")
        climate = region_climate_at(self.campaign, *self.first_coordinates)
        self.assertFalse(region.use_manual_climate_overrides)
        self.assertEqual(region.biome, climate["biome"])
        self.assertEqual(region.base_temperature, climate["base_temperature"])
        self.assertEqual(region.humidity, climate["humidity"])
        self.assertEqual(region.elevation, climate["elevation"])

    def test_preview_values_equal_server_saved_values_and_do_not_run_solver(self):
        self.create_global_layer()
        with patch(
            "world.services.atmosphere.simulation.initialize_atmosphere"
        ) as initialize:
            preview_response = self.client.get(
                self.preview_url,
                {"polygon": json.dumps(self.first_polygon)},
            )
        initialize.assert_not_called()
        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.json()

        self.client.post(
            self.map_url,
            {
                "action": "create",
                "create-name": "Preview parity",
                "create-map_polygon": json.dumps(self.first_polygon),
            },
        )
        region = Region.objects.get(name="Preview parity")
        self.assertEqual(region.biome, preview["biome"])
        self.assertEqual(region.base_temperature, preview["base_temperature"])
        self.assertEqual(region.humidity, preview["humidity"])
        self.assertEqual(region.elevation, preview["elevation"])

    def test_coordinate_change_recomputes_auto_fields_without_changing_name(self):
        self.create_global_layer(
            {
                str(self.first_index): Region.Biome.FOREST,
                str(self.second_index): Region.Biome.TUNDRA,
            }
        )
        self.client.post(
            self.map_url,
            {
                "action": "create",
                "create-name": "Постоянное имя",
                "create-map_polygon": json.dumps(self.first_polygon),
            },
        )
        region = Region.objects.get(name="Постоянное имя")
        original_temperature = region.base_temperature

        self.client.post(
            self.map_url,
            {
                "action": "place",
                "placement-region_id": str(region.pk),
                "placement-map_polygon": json.dumps(self.second_polygon),
            },
        )
        region.refresh_from_db()
        # Continuous elevation is sampled at the persisted polygon centroid,
        # which is intentionally not forced onto the source raster cell centre.
        expected = region_climate_at(
            self.campaign,
            region.map_latitude,
            region.map_longitude,
        )
        self.assertEqual(region.name, "Постоянное имя")
        self.assertNotEqual(region.base_temperature, original_temperature)
        self.assertEqual(region.biome, expected["biome"])
        self.assertEqual(region.base_temperature, expected["base_temperature"])
        self.assertEqual(region.elevation, expected["elevation"])

    def test_explicit_manual_override_survives_coordinate_change_and_refresh(self):
        self.create_global_layer()
        self.client.post(
            self.map_url,
            {
                "action": "create",
                "create-name": "Ручной регион",
                "create-use_manual_climate_overrides": "on",
                "create-biome": Region.Biome.MEADOW,
                "create-base_temperature": "12.5",
                "create-seasonal_amplitude": "9",
                "create-humidity": "61",
                "create-elevation": "345",
                "create-weather_volatility": "1.5",
                "create-precipitation_bias": "0.2",
                "create-map_polygon": json.dumps(self.first_polygon),
            },
        )
        region = Region.objects.get(name="Ручной регион")
        self.client.post(
            self.map_url,
            {
                "action": "place",
                "placement-region_id": str(region.pk),
                "placement-map_polygon": json.dumps(self.second_polygon),
            },
        )
        self.client.post(
            reverse(
                "world:region_detail",
                kwargs={
                    "campaign_id": self.campaign.pk,
                    "region_id": region.pk,
                },
            ),
            {"action": "refresh-climate"},
        )
        region.refresh_from_db()
        self.assertTrue(region.use_manual_climate_overrides)
        self.assertEqual(region.biome, Region.Biome.MEADOW)
        self.assertEqual(region.base_temperature, 12.5)
        self.assertEqual(region.humidity, 61.0)
        self.assertEqual(region.elevation, 345.0)
        self.assertEqual(region.precipitation_bias, 0.2)

    def test_red_plateau_has_no_biome_humidity_or_precipitation_hardcode(self):
        self.create_global_layer(
            {
                str(self.first_index): Region.Biome.RED_PLATEAUS,
                str(self.second_index): Region.Biome.MEADOW,
            }
        )
        red = region_climate_at(self.campaign, *self.first_coordinates)
        meadow = region_climate_at(self.campaign, *self.second_coordinates)
        self.assertEqual(red["humidity"], meadow["humidity"])

    def test_atmospheric_grid_ignores_all_legacy_region_climate_controls(self):
        self.create_global_layer()
        AtmosphericConfig.objects.create(
            campaign=self.campaign,
            enabled=True,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            parameters={
                "initial_temperature_noise_c": 0.0,
                "pressure_noise_hpa": 0.0,
            },
        )
        latitude, longitude = self.first_coordinates
        first = Region.objects.create(
            campaign=self.campaign,
            name="Legacy low",
            biome=Region.Biome.RED_PLATEAUS,
            base_temperature=-100,
            seasonal_amplitude=0,
            humidity=1,
            elevation=100,
            weather_volatility=0,
            precipitation_bias=-1,
            map_latitude=latitude,
            map_longitude=longitude,
            use_manual_climate_overrides=True,
        )
        second = Region.objects.create(
            campaign=self.campaign,
            name="Legacy high",
            biome=Region.Biome.MEADOW,
            base_temperature=100,
            seasonal_amplitude=80,
            humidity=99,
            elevation=100,
            weather_volatility=3,
            precipitation_bias=1,
            map_latitude=latitude,
            map_longitude=longitude,
            use_manual_climate_overrides=True,
        )

        advance_world(self.campaign.pk, 360)
        first_weather = first.weather_history.get(world_minutes=360)
        second_weather = second.weather_history.get(world_minutes=360)
        self.assertEqual(first_weather.source, WeatherState.Source.ATMOSPHERIC_GRID_V3)
        for field_name in (
            "temperature",
            "humidity",
            "pressure_hpa",
            "wind_speed",
            "cloud_cover",
            "precipitation_rate_mm_h",
        ):
            self.assertEqual(
                getattr(first_weather, field_name),
                getattr(second_weather, field_name),
            )
