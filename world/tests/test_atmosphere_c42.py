import numpy as np
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from world.models import AtmosphericConfig, Region, WeatherState
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.coordinate_sampling import sample_environment_at
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint
from world.services.atmosphere.forcing import CampaignSkyForcing
from world.services.atmosphere.geometry import geometry_for
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.microphysics import precipitation_fallout
from world.services.atmosphere.pressure import surface_pressure_from_circulation
from world.services.atmosphere.persistence import (
    grid_from_snapshot,
    latest_atmospheric_cell_diagnostics,
    save_snapshot,
)
from world.services.atmosphere.sampling import _weather_from_grid_at_time
from world.services.atmosphere.simulation import initialize_atmosphere, simulate_step
from world.services.atmosphere.static_grid import build_static_world_grid
from world.services.environment_summary import build_environment_summary
from world.services.weather_display import build_weather_summary


def exact_reference(campaign, config):
    settings = AtmosphericSettings.from_model(config, campaign)
    static = build_static_world_grid(settings)
    forcing = CampaignSkyForcing(campaign, settings)
    grid, _ = initialize_atmosphere(
        settings,
        static=static,
        world_minutes=0,
        forcing=forcing,
    )
    for step in range(1, 29):
        grid = simulate_step(
            grid,
            static,
            settings,
            step_index=step,
            world_minutes=step * settings.step_minutes,
            forcing=forcing,
        )
    return grid, static, settings


class FalloutLifecycleTests(SimpleTestCase):
    def setUp(self):
        self.settings = AtmosphericSettings(
            width=4,
            height=2,
            step_minutes=360,
            parameters={"precipitation_condensate_threshold": 0.00005},
        )

    def test_positive_condensate_falls_out_but_rate_survives_in_current_grid(self):
        condensate = np.full(8, 0.0002, dtype=np.float64)
        fallout = precipitation_fallout(
            condensate,
            np.full(8, 1000.0),
            np.full(8, 12.0),
            self.settings,
        )

        self.assertTrue(np.all(fallout["q_c"] > 0.0))
        self.assertTrue(np.all(fallout["q_c"] < condensate))
        self.assertTrue(np.all(fallout["rate_mm_h"] > 0.0))
        self.assertTrue(np.all(fallout["amount_mm_per_step"] > 0.0))

        grid = AtmosphericGrid.empty(4, 2)
        grid.fields["cloud_condensate_specific_humidity"] = fallout["q_c"].astype(
            np.float32
        )
        grid.fields["precipitation_rate"] = fallout["rate_kg_m2_s"].astype(
            np.float32
        )
        restored = AtmosphericGrid.deserialize(4, 2, grid.serialize())
        self.assertGreater(float(restored.fields["precipitation_rate"][0]), 0.0)

    def test_zero_condensate_still_cannot_generate_precipitation(self):
        fallout = precipitation_fallout(
            np.zeros(8),
            np.full(8, 1000.0),
            np.full(8, 12.0),
            self.settings,
        )

        np.testing.assert_array_equal(fallout["rate_mm_h"], 0.0)
        np.testing.assert_array_equal(fallout["amount_mm_per_step"], 0.0)


class ExactCurrentPrecipitationPipelineTests(TestCase):
    def setUp(self):
        self.gm = get_user_model().objects.create_user(
            username="c42-gm",
            password="test-password",
        )
        self.campaign = Campaign.objects.create(name="C4.2 lifecycle")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        parameters = AtmosphericConfig._meta.get_field("parameters").default()
        parameters.update(
            {
                "initial_temperature_noise_c": 0.0,
                "pressure_noise_hpa": 0.0,
            }
        )
        self.config = AtmosphericConfig.objects.create(
            campaign=self.campaign,
            enabled=True,
            grid_width=24,
            grid_height=12,
            step_minutes=360,
            world_seed=202,
            ocean_temperature_c=64.0,
            parameters=parameters,
        )

    def test_wettest_last_exact_cell_survives_snapshot_and_sampler_without_region(self):
        grid, static, settings = exact_reference(self.campaign, self.config)
        index = int(np.argmax(grid.fields["precipitation_rate"]))
        raw_rate = float(grid.fields["precipitation_rate"][index])
        self.assertGreater(raw_rate, 0.0)

        restored = AtmosphericGrid.deserialize(24, 12, grid.serialize())
        geometry = geometry_for(settings)
        point = sample_environment_at(
            restored,
            static,
            settings,
            float(geometry.latitude[index]),
            float(geometry.longitude[index]),
        )

        self.assertAlmostEqual(
            float(restored.fields["precipitation_rate"][index]),
            raw_rate,
        )
        self.assertAlmostEqual(point.values["precipitation_rate"], raw_rate)

    def test_gm_diagnostics_use_same_bilinear_continuous_fields_as_weather(self):
        # Fingerprints must use the same DB-normalized model values as the
        # request, rather than Python literals still held by create().
        self.campaign.refresh_from_db()
        self.config.refresh_from_db()
        settings = AtmosphericSettings.from_model(self.config, self.campaign)
        static = build_static_world_grid(settings)
        grid = AtmosphericGrid.empty(settings.width, settings.height)
        indices = np.arange(grid.size, dtype=np.float32)
        grid.fields["temperature"] = 10.0 + indices * 0.1
        grid.fields["water_vapor_specific_humidity"] = 0.005 + indices * 0.00001
        grid.fields["cloud_condensate_specific_humidity"].fill(0.0)
        grid.fields["circulation_pressure_hpa"] = 990.0 + indices * 0.05
        grid.fields["pressure_hpa"] = 800.0 + indices
        grid.fields["wind_u"] = indices * 0.01
        grid.fields["wind_v"] = indices * -0.005
        grid.fields["cloud_cover"] = indices / grid.size
        grid.fields["precipitation_rate"] = indices * 0.00000001
        grid.fields["surface_temperature"] = grid.fields["temperature"].copy()
        grid.fields["sea_surface_temperature_c"] = grid.fields["temperature"].copy()

        latitude = 0.0
        longitude = 0.0
        point = sample_environment_at(
            grid,
            static,
            settings,
            latitude,
            longitude,
            local_elevation_m=0.0,
        )
        nearest_pressure = float(grid.fields["pressure_hpa"][point.nearest_index])
        self.assertNotAlmostEqual(point.values["pressure_hpa"], nearest_pressure)
        expected_pressure = float(
            surface_pressure_from_circulation(
                point.values["circulation_pressure_hpa"],
                point.values["temperature"],
                point.values["water_vapor_specific_humidity"],
                0.0,
                settings,
            )
        )
        self.assertAlmostEqual(point.values["pressure_hpa"], expected_pressure)
        self.assertNotAlmostEqual(
            point.values["pressure_hpa"],
            point.interpolated_grid_surface_pressure_hpa,
        )
        fingerprint = atmospheric_input_fingerprint(self.campaign, self.config)
        save_snapshot(
            self.campaign,
            0,
            grid,
            input_fingerprint=fingerprint,
        )
        region = Region.objects.create(
            campaign=self.campaign,
            name="Fractional diagnostic point",
            map_latitude=latitude,
            map_longitude=longitude,
        )
        weather = _weather_from_grid_at_time(
            region,
            0,
            grid,
            parameters=self.config.parameters,
            settings=settings,
            static=static,
        )
        weather.save()
        diagnostics = latest_atmospheric_cell_diagnostics(
            self.campaign,
            self.config,
            latitude,
            longitude,
            world_minutes=0,
            local_elevation_m=region.elevation,
        )

        self.assertEqual(
            diagnostics["sampling_method"],
            "bilinear_primitives_hydrostatic_pressure",
        )
        self.assertAlmostEqual(
            diagnostics["temperature_c"],
            point.values["temperature"],
        )
        self.assertAlmostEqual(
            diagnostics["surface_pressure_hpa"],
            point.values["pressure_hpa"],
        )
        self.assertAlmostEqual(
            diagnostics["circulation_pressure_hpa"],
            point.values["circulation_pressure_hpa"],
        )
        self.assertAlmostEqual(diagnostics["wind_u_m_s"], point.values["wind_u"])
        self.assertAlmostEqual(diagnostics["wind_v_m_s"], point.values["wind_v"])
        self.assertAlmostEqual(
            diagnostics["wind_speed_m_s"],
            point.wind_speed_m_s,
        )
        self.assertAlmostEqual(
            diagnostics["cloud_cover_fraction"],
            point.values["cloud_cover"],
        )
        self.assertAlmostEqual(
            diagnostics["precipitation_rate_mm_h"],
            point.values["precipitation_rate"] * 3600.0,
        )
        self.assertAlmostEqual(
            diagnostics["temperature_c"], weather.temperature, delta=0.051
        )
        self.assertAlmostEqual(
            diagnostics["surface_pressure_hpa"], weather.pressure_hpa, delta=0.051
        )
        self.assertAlmostEqual(
            diagnostics["relative_humidity_percent"], weather.humidity, delta=0.051
        )
        self.assertAlmostEqual(
            diagnostics["wind_speed_m_s"], weather.wind_speed, delta=0.051
        )
        self.assertAlmostEqual(
            diagnostics["cloud_cover_fraction"], weather.cloud_cover, delta=0.00051
        )
        self.assertAlmostEqual(
            diagnostics["precipitation_rate_mm_h"],
            weather.precipitation_rate_mm_h,
            delta=0.000051,
        )

        client = Client()
        client.force_login(self.gm)
        response = client.get(
            reverse(
                "world:region_detail",
                kwargs={
                    "campaign_id": self.campaign.pk,
                    "region_id": region.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"{weather.temperature:.1f}".replace(".", ",") + "°C",
        )
        self.assertContains(
            response,
            f"{diagnostics['surface_pressure_hpa']:.2f}".replace(".", ",")
            + " гПа",
        )
        self.assertContains(
            response,
            f"{diagnostics['relative_humidity_percent']:.1f}".replace(".", ",")
            + "%",
        )

    def test_exact_rain_survives_snapshot_weatherstate_environment_and_region_html(self):
        grid, static, settings = exact_reference(self.campaign, self.config)
        index = int(np.argmax(grid.fields["precipitation_rate"]))
        raw_rate_mm_h = float(grid.fields["precipitation_rate"][index] * 3600.0)
        self.assertGreater(raw_rate_mm_h, 0.05)

        geometry = geometry_for(settings)
        latitude = float(geometry.latitude[index])
        longitude = float(geometry.longitude[index])
        world_minutes = 28 * settings.step_minutes
        self.campaign.world_minutes = world_minutes
        self.campaign.save(update_fields=["world_minutes"])
        fingerprint = atmospheric_input_fingerprint(self.campaign, self.config)
        snapshot, _ = save_snapshot(
            self.campaign,
            world_minutes,
            grid,
            input_fingerprint=fingerprint,
            is_checkpoint=True,
        )
        restored = grid_from_snapshot(snapshot)
        self.assertGreater(
            float(restored.fields["precipitation_rate"][index]),
            0.0,
        )

        point = sample_environment_at(
            restored,
            static,
            settings,
            latitude,
            longitude,
        )
        region = Region.objects.create(
            campaign=self.campaign,
            name="Exact wet cell",
            map_latitude=latitude,
            map_longitude=longitude,
            elevation=point.elevation_m,
        )
        weather = _weather_from_grid_at_time(
            region,
            world_minutes,
            restored,
            parameters=self.config.parameters,
            settings=settings,
            static=static,
        )
        weather.save()

        self.assertGreater(weather.precipitation_rate_mm_h, 0.0)
        self.assertGreater(weather.precipitation_amount_mm, 0.0)
        self.assertIn(
            weather.condition,
            {WeatherState.Condition.RAIN, WeatherState.Condition.SNOW},
        )
        self.assertNotEqual(
            build_environment_summary(
                weather,
                elevation_m=point.elevation_m,
                parameters=settings.parameters,
            ).precipitation_label,
            "без осадков",
        )
        display = build_weather_summary(weather)
        self.assertNotEqual(display["precipitation"], "нет")

        client = Client()
        client.force_login(self.gm)
        response = client.get(
            reverse(
                "world:region_detail",
                kwargs={
                    "campaign_id": self.campaign.pk,
                    "region_id": region.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Осадки сейчас")
        self.assertContains(
            response,
            f"{weather.precipitation_rate_mm_h:.2f} мм/ч",
        )
