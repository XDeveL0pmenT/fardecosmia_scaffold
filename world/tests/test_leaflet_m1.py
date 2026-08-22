from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from world.forms import MAX_REGION_CONTOUR_JSON_BYTES, RegionPlacementForm
from world.models import AtmosphericConfig, Region, WeatherState
from world.services.atlas import build_atlas_config, load_atlas_manifest
from world.services.map_geometry import normalized_ring_to_latlon
from world.services.time import advance_world
from world.services.world_data import load_elevation_grid, load_land_mask


class LeafletAtlasContractTests(SimpleTestCase):
    def test_manifest_exposes_complete_versioned_layers(self):
        manifest = load_atlas_manifest()

        self.assertTrue(manifest["available"])
        self.assertEqual(manifest["world_pixel_size_zoom_zero"], [512, 256])
        self.assertEqual(set(manifest["layers"]), {"base", "temperature", "elevation", "biome"})
        self.assertEqual(manifest["layers"]["base"]["native_zoom"], 4)
        self.assertEqual(manifest["layers"]["temperature"]["source_world_crop"], [0, 0, 1774, 887])
        for layer in manifest["layers"].values():
            self.assertEqual(layer["canvas_width"], layer["canvas_height"] * 2)
            self.assertGreater(layer["tile_count"], 0)

    def test_leaflet_urls_keep_literal_tile_placeholders(self):
        config = build_atlas_config(inspect_url="/inspect/")

        self.assertEqual(config["view"]["max_zoom"], 10)
        self.assertEqual(config["crs"]["wrap_longitude"], [-180.0, 180.0])
        self.assertIsNone(config["crs"]["wrap_latitude"])
        self.assertIn("/{z}/{x}/{y}.", config["layers"]["base"]["url"])
        self.assertNotIn("%7B", config["layers"]["base"]["url"])

    def test_server_converts_legacy_region_storage_at_renderer_boundary(self):
        ring = [[0.99, 0.45], [0.01, 0.45], [0.01, 0.55], [0.99, 0.55]]
        config = build_atlas_config(
            region_shapes=[{"id": 1, "name": "Seam", "polygon": ring}],
        )

        self.assertEqual(config["regions"][0]["ring"], normalized_ring_to_latlon(ring))
        self.assertEqual(config["regions"][0]["polygon"], ring)

    def test_oversized_contour_is_rejected_before_json_parsing(self):
        oversized = " " * (MAX_REGION_CONTOUR_JSON_BYTES + 1)
        form = RegionPlacementForm(
            data={"region_id": 1, "map_polygon": oversized},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("map_polygon", form.errors)


class LeafletPointInspectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="m1-gm",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="M1 atlas")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.user,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(self.user)

    def test_global_point_get_is_read_only_and_returns_static_world_data(self):
        before = {
            "world_minutes": self.campaign.world_minutes,
            "regions": Region.objects.count(),
            "weather": WeatherState.objects.count(),
        }

        response = self.client.get(
            reverse("world:global_point_inspection"),
            {"latitude": 0, "longitude": 0},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latitude"], 0)
        self.assertEqual(payload["longitude"], 0)
        self.assertIn(payload["static"]["surface_type"], {"land", "ocean"})
        self.assertIn("base_temperature", payload["static"])
        self.assertIn("elevation", payload["static"])
        self.assertFalse(payload["weather_available"])
        self.campaign.refresh_from_db()
        self.assertEqual(
            before,
            {
                "world_minutes": self.campaign.world_minutes,
                "regions": Region.objects.count(),
                "weather": WeatherState.objects.count(),
            },
        )

    def test_point_inspector_handles_land_ocean_and_high_mountain_cells(self):
        mask = load_land_mask()["values"]
        elevation = load_elevation_grid()["values"]
        ocean_index = next(index for index, is_land in enumerate(mask) if not is_land)
        land_index = next(index for index, is_land in enumerate(mask) if is_land)
        mountain_index = max(
            (index for index, is_land in enumerate(mask) if is_land and elevation[index] is not None),
            key=lambda index: elevation[index],
        )
        endpoint = reverse("world:global_point_inspection")

        def sample(index):
            y, x = divmod(index, 360)
            return self.client.get(
                endpoint,
                {
                    "latitude": 90 - (y + 0.5),
                    "longitude": -180 + (x + 0.5),
                },
            ).json()["static"]

        self.assertEqual(sample(ocean_index)["surface_type"], "ocean")
        self.assertEqual(sample(land_index)["surface_type"], "land")
        mountain = sample(mountain_index)
        self.assertEqual(mountain["surface_type"], "land")
        self.assertGreater(mountain["elevation"], 1000)

    def test_campaign_point_get_without_atmosphere_returns_static_only(self):
        response = self.client.get(
            reverse(
                "world:campaign_point_inspection",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {"latitude": 42.5, "longitude": -73.25},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latitude"], 42.5)
        self.assertEqual(payload["longitude"], -73.25)
        self.assertFalse(payload["weather_available"])

    def test_campaign_point_returns_current_atmosphere_when_compatible_snapshot_exists(self):
        AtmosphericConfig.objects.create(
            campaign=self.campaign,
            enabled=True,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            world_seed=17,
            parameters={
                "initial_temperature_noise_c": 0.2,
                "pressure_noise_hpa": 0.1,
            },
        )
        advance_world(self.campaign.pk, 360)

        response = self.client.get(
            reverse(
                "world:campaign_point_inspection",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {"latitude": 12.5, "longitude": 21.25},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["weather_available"])
        self.assertEqual(payload["weather"]["snapshot_world_minutes"], 360)
        self.assertIn("surface_pressure_hpa", payload["weather"])
        self.assertIn("precipitation_rate_mm_h", payload["weather"])

    def test_point_inspection_wraps_longitude_but_rejects_polar_overflow(self):
        endpoint = reverse("world:global_point_inspection")
        east = self.client.get(endpoint, {"latitude": 0, "longitude": 180})
        west = self.client.get(endpoint, {"latitude": 0, "longitude": -180})
        invalid = self.client.get(endpoint, {"latitude": 90.01, "longitude": 0})

        self.assertEqual(east.status_code, 200)
        self.assertEqual(east.json()["longitude"], -180)
        self.assertEqual(east.json()["static"], west.json()["static"])
        self.assertEqual(invalid.status_code, 400)

    def test_player_cannot_use_campaign_point_inspection(self):
        player = get_user_model().objects.create_user(
            username="m1-player",
            password="test-password",
        )
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.client.force_login(player)

        response = self.client.get(
            reverse(
                "world:campaign_point_inspection",
                kwargs={"campaign_id": self.campaign.pk},
            ),
            {"latitude": 0, "longitude": 0},
        )

        self.assertEqual(response.status_code, 403)

    def test_atlas_page_contains_one_map_container_and_one_json_contract(self):
        response = self.client.get(
            reverse("world:world_map", kwargs={"campaign_id": self.campaign.pk})
        )
        content = response.content.decode()

        self.assertEqual(content.count("data-leaflet-map"), 1)
        self.assertEqual(content.count('id="fardecosmia-atlas-config"'), 1)
        config_start = content.index('id="fardecosmia-atlas-config"')
        self.assertIn("/static/atlas/tiles/", content[config_start:])
        self.assertIn("{z}/{x}/{y}", content[config_start:])

    def test_viewing_existing_irregular_seam_and_polar_regions_is_non_mutating(self):
        contours = (
            [[0.2, 0.3], [0.27, 0.32], [0.25, 0.4], [0.19, 0.36]],
            [[0.99, 0.48], [0.01, 0.48], [0.01, 0.53], [0.99, 0.53]],
            [[0.4, 0.0], [0.45, 0.0], [0.43, 0.03]],
        )
        regions = [
            Region.objects.create(
                campaign=self.campaign,
                name=f"M1 region {index}",
                map_polygon=polygon,
                map_latitude=0,
                map_longitude=0,
            )
            for index, polygon in enumerate(contours)
        ]
        before_weather = WeatherState.objects.count()

        response = self.client.get(
            reverse("world:world_map", kwargs={"campaign_id": self.campaign.pk})
        )

        self.assertEqual(response.status_code, 200)
        for region, polygon in zip(regions, contours, strict=True):
            region.refresh_from_db()
            self.assertEqual(region.map_polygon, polygon)
            self.assertEqual(region.weather_geometry_revision, 0)
            self.assertContains(response, region.name)
        self.assertEqual(WeatherState.objects.count(), before_weather)
