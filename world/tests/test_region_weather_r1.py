import json

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership, TimeAdvanceReport
from world.biomes import Biome
from world.models import (
    AtmosphericConfig,
    Region,
    RegionAreaWeatherState,
    WeatherState,
)
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.region_area import (
    _spherical_cell_area_rows,
    area_weather_from_grid_at_time,
    build_region_area_weather_summary,
    clear_region_contour_mask_cache,
    region_contour_mask,
)
from world.services.atmosphere.sampling import (
    AtmosphericRegionSampler,
    _weather_from_grid_at_time,
)
from world.services.atmosphere.static_grid import StaticWorldGrid
from world.services.region_weather import (
    initialize_region_weather,
    latest_current_point_weather,
)
from world.services.time import advance_world
from world.services.time_reports import build_time_advance_summary


def atmospheric_grid(width, height, *, temperature=10.0):
    grid = AtmosphericGrid.empty(width, height)
    grid.fields["temperature"].fill(temperature)
    grid.fields["surface_temperature"].fill(temperature)
    grid.fields["sea_surface_temperature_c"].fill(temperature)
    grid.fields["water_vapor_specific_humidity"].fill(0.004)
    grid.fields["circulation_pressure_hpa"].fill(1000.0)
    grid.fields["pressure_hpa"].fill(1000.0)
    return grid


def static_grid(width, height):
    size = width * height
    return StaticWorldGrid(
        width=width,
        height=height,
        is_ocean=np.zeros(size, dtype=np.bool_),
        elevation=np.zeros(size, dtype=np.float32),
        mean_temperature=np.full(size, 10.0, dtype=np.float32),
        biome=tuple(Biome.MEADOW for _ in range(size)),
    )


class RegionWeatherLifecycleR1Tests(TestCase):
    polygon = [[0.45, 0.45], [0.55, 0.45], [0.55, 0.55], [0.45, 0.55]]

    def campaign_with_grid(self, name="R1", *, enabled=True):
        campaign = Campaign.objects.create(name=name)
        config = AtmosphericConfig.objects.create(
            campaign=campaign,
            enabled=enabled,
            grid_width=8,
            grid_height=4,
            step_minutes=360,
            world_seed=81,
            parameters={
                "initial_temperature_noise_c": 0.0,
                "pressure_noise_hpa": 0.0,
            },
        )
        return campaign, config

    def located_region(self, campaign, name="Регион"):
        return Region.objects.create(
            campaign=campaign,
            name=name,
            biome=Biome.MEADOW,
            map_latitude=0.0,
            map_longitude=0.0,
            map_polygon=self.polygon,
        )

    def test_enabled_grid_with_compatible_state_initializes_physical_not_legacy(self):
        campaign, _config = self.campaign_with_grid()
        advance_world(campaign.pk, 360)
        campaign.refresh_from_db()
        region = self.located_region(campaign)

        result = initialize_region_weather(region)

        self.assertEqual(result.mode, "physical")
        self.assertEqual(result.point_weather.source, WeatherState.Source.ATMOSPHERIC_GRID_V3)
        self.assertEqual(result.point_weather.world_minutes, 360)
        self.assertEqual(result.point_weather.region_weather_revision, 0)
        self.assertIsNotNone(result.point_weather.sample_latitude)
        self.assertIsNotNone(result.point_weather.solver_version)
        self.assertIsNotNone(result.point_weather.atmosphere_fingerprint)
        self.assertIsNotNone(result.area_weather)
        self.assertFalse(region.weather_history.filter(source=WeatherState.Source.LEGACY_V2).exists())

    def test_enabled_grid_without_snapshot_leaves_pending(self):
        campaign, _config = self.campaign_with_grid()
        region = self.located_region(campaign)

        result = initialize_region_weather(region)

        self.assertTrue(result.pending)
        self.assertFalse(region.weather_history.exists())

    def test_region_create_view_with_enabled_grid_does_not_seed_legacy(self):
        campaign, _config = self.campaign_with_grid("Create flow")
        gm = get_user_model().objects.create_user(username="create-gm", password="pw")
        CampaignMembership.objects.create(
            campaign=campaign,
            user=gm,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(gm)

        response = self.client.post(
            reverse("world:world_map", kwargs={"campaign_id": campaign.pk}),
            {
                "action": "create",
                "create-name": "Созданный через карту",
                "create-map_polygon": json.dumps(self.polygon),
            },
        )

        self.assertEqual(response.status_code, 302)
        region = Region.objects.get(name="Созданный через карту")
        self.assertFalse(region.weather_history.exists())
        self.assertFalse(region.area_weather_history.exists())

        gm = get_user_model().objects.create_user(username="r1-gm", password="pw")
        CampaignMembership.objects.create(
            campaign=campaign,
            user=gm,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(gm)
        response = self.client.get(
            reverse(
                "world:region_detail",
                kwargs={"campaign_id": campaign.pk, "region_id": region.pk},
            )
        )
        self.assertContains(response, "Физическая погода ожидает расчёта")
        self.assertFalse(region.weather_history.exists())

    def test_disabled_grid_uses_real_legacy_fallback(self):
        campaign, _config = self.campaign_with_grid(enabled=False)
        region = self.located_region(campaign)

        result = initialize_region_weather(region)

        self.assertEqual(result.mode, "legacy")
        self.assertEqual(result.point_weather.source, WeatherState.Source.LEGACY_V2)
        self.assertFalse(region.area_weather_history.exists())

    def test_geometry_revision_changes_only_for_sampling_geometry(self):
        campaign = Campaign.objects.create(name="Revision")
        region = self.located_region(campaign)

        region.name = "Новое имя"
        region.save(update_fields=["name"])
        self.assertEqual(region.weather_geometry_revision, 0)

        region.map_polygon = [[0.4, 0.4], [0.6, 0.4], [0.5, 0.6]]
        region.save(update_fields=["map_polygon"])
        self.assertEqual(region.weather_geometry_revision, 1)

        region.map_longitude = 12.0
        region.save(update_fields=["map_longitude"])
        self.assertEqual(region.weather_geometry_revision, 2)

        region.elevation = 250.0
        region.save(update_fields=["elevation"])
        self.assertEqual(region.weather_geometry_revision, 3)

    def test_old_history_survives_move_but_is_not_current(self):
        campaign = Campaign.objects.create(name="History")
        region = self.located_region(campaign)
        old = WeatherState.objects.create(
            region=region,
            world_minutes=0,
            region_weather_revision=0,
            temperature=5,
            humidity=50,
            condition=WeatherState.Condition.CLEAR,
        )

        region.map_latitude = 20.0
        region.save(update_fields=["map_latitude"])
        new = WeatherState.objects.create(
            region=region,
            world_minutes=0,
            region_weather_revision=region.weather_geometry_revision,
            temperature=25,
            humidity=50,
            condition=WeatherState.Condition.CLEAR,
        )

        self.assertTrue(WeatherState.objects.filter(pk=old.pk).exists())
        self.assertEqual(region.weather_history.count(), 2)
        self.assertEqual(latest_current_point_weather(region, 0), new)

    def test_legacy_at_same_minute_is_replaced_by_incoming_physical_state(self):
        campaign = Campaign.objects.create(name="Source precedence")
        region = self.located_region(campaign)
        legacy = WeatherState.objects.create(
            region=region,
            world_minutes=0,
            region_weather_revision=0,
            temperature=-90,
            humidity=1,
            condition=WeatherState.Condition.CLEAR,
            source=WeatherState.Source.LEGACY_V2,
        )
        settings = AtmosphericSettings(width=4, height=2)
        static = static_grid(4, 2)
        grid = atmospheric_grid(4, 2, temperature=22)
        sampler = AtmosphericRegionSampler(
            [region],
            0,
            0,
            settings=settings,
            static=static,
            atmosphere_fingerprint="f" * 64,
        )

        sampler.sample(0, grid)
        sampler.save()

        legacy.refresh_from_db()
        self.assertEqual(region.weather_history.count(), 1)
        self.assertEqual(legacy.source, WeatherState.Source.ATMOSPHERIC_GRID_V3)
        self.assertEqual(legacy.temperature, 22.0)
        self.assertEqual(legacy.atmosphere_fingerprint, "f" * 64)

    def test_existing_physical_state_is_never_arbitrarily_overwritten(self):
        campaign = Campaign.objects.create(name="Physical precedence")
        region = self.located_region(campaign)
        physical = WeatherState.objects.create(
            region=region,
            world_minutes=0,
            region_weather_revision=0,
            temperature=-33,
            humidity=30,
            condition=WeatherState.Condition.CLEAR,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )
        settings = AtmosphericSettings(width=4, height=2)
        sampler = AtmosphericRegionSampler(
            [region],
            0,
            0,
            settings=settings,
            static=static_grid(4, 2),
        )

        sampler.sample(0, atmospheric_grid(4, 2, temperature=22))
        sampler.save()

        physical.refresh_from_db()
        self.assertEqual(region.weather_history.count(), 1)
        self.assertEqual(physical.temperature, -33)

    def test_region_page_marks_point_weather_older_than_one_step_as_stale(self):
        campaign, _config = self.campaign_with_grid("Stale")
        campaign.world_minutes = 720
        campaign.save(update_fields=["world_minutes"])
        region = self.located_region(campaign)
        WeatherState.objects.create(
            region=region,
            world_minutes=0,
            region_weather_revision=0,
            temperature=10,
            humidity=50,
            condition=WeatherState.Condition.CLEAR,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )
        gm = get_user_model().objects.create_user(username="stale-gm", password="pw")
        CampaignMembership.objects.create(
            campaign=campaign,
            user=gm,
            role=CampaignMembership.Role.GM,
        )
        self.client.force_login(gm)

        response = self.client.get(
            reverse(
                "world:region_detail",
                kwargs={"campaign_id": campaign.pk, "region_id": region.pk},
            )
        )

        self.assertContains(response, "Атмосферное состояние устарело")
        self.assertContains(response, "12.0 ч.")

    def test_fast_forward_creates_area_only_for_final_exact_spinup(self):
        campaign, _config = self.campaign_with_grid("FF")
        campaign.exact_simulation_max_turns = 1
        campaign.fast_forward_spinup_turns = 1
        campaign.save(update_fields=["exact_simulation_max_turns", "fast_forward_spinup_turns"])
        region = self.located_region(campaign)
        turn = campaign.calendar_minutes_per_turn

        advance_world(campaign.pk, 3 * turn)

        spinup_start = 2 * turn
        times = list(
            region.area_weather_history.order_by("world_minutes").values_list(
                "world_minutes", flat=True
            )
        )
        self.assertTrue(times)
        self.assertEqual(times[0], spinup_start)
        self.assertEqual(times[-1], 3 * turn)
        self.assertFalse(any(0 < minute < spinup_start for minute in times))
        self.assertTrue(all(minute % 360 == 0 for minute in times))


class RegionContourGeometryR1Tests(TestCase):
    def setUp(self):
        clear_region_contour_mask_cache()
        self.campaign = Campaign.objects.create(name="Geometry")
        self.settings = AtmosphericSettings(width=12, height=6)

    def region(self, polygon, name):
        return Region.objects.create(
            campaign=self.campaign,
            name=name,
            map_latitude=0,
            map_longitude=0,
            map_polygon=polygon,
        )

    def test_rectangle_and_irregular_contours_produce_area_masks(self):
        rectangle = self.region(
            [[0.25, 0.25], [0.5, 0.25], [0.5, 0.75], [0.25, 0.75]],
            "Rectangle",
        )
        irregular = self.region(
            [[0.1, 0.2], [0.45, 0.25], [0.36, 0.48], [0.5, 0.8], [0.16, 0.66]],
            "Irregular",
        )

        rectangle_mask = region_contour_mask(rectangle, self.settings)
        irregular_mask = region_contour_mask(irregular, self.settings)

        self.assertEqual(rectangle_mask.sampling_mode, RegionAreaWeatherState.SamplingMode.AREA)
        self.assertGreater(rectangle_mask.indices.size, 0)
        self.assertEqual(irregular_mask.sampling_mode, RegionAreaWeatherState.SamplingMode.AREA)
        self.assertTrue(np.any(irregular_mask.coverage_fractions < 1.0))

    def test_huge_seam_crossing_and_polar_contours_are_supported(self):
        huge = self.region(
            [
                [0.05, 0.1], [0.35, 0.1], [0.65, 0.1], [0.95, 0.1],
                [0.95, 0.9], [0.65, 0.9], [0.35, 0.9], [0.05, 0.9],
            ],
            "Huge",
        )
        seam = self.region(
            [[0.97, 0.25], [0.03, 0.25], [0.03, 0.75], [0.97, 0.75]],
            "Seam",
        )
        polar = self.region(
            [[0.2, 0.0], [0.45, 0.0], [0.42, 0.12], [0.24, 0.15]],
            "Polar",
        )

        huge_mask = region_contour_mask(huge, self.settings)
        seam_mask = region_contour_mask(seam, self.settings)
        polar_mask = region_contour_mask(polar, self.settings)

        self.assertGreater(huge_mask.indices.size, self.settings.width)
        self.assertTrue({0, self.settings.width - 1}.issubset(set(seam_mask.indices % self.settings.width)))
        self.assertTrue(np.all(polar_mask.indices // self.settings.width <= 1))

    def test_tiny_contour_has_explicit_point_fallback(self):
        tiny = self.region(
            [[0.500, 0.500], [0.502, 0.500], [0.501, 0.502]],
            "Tiny",
        )
        mask = region_contour_mask(tiny, self.settings)
        self.assertEqual(mask.sampling_mode, RegionAreaWeatherState.SamplingMode.POINT_FALLBACK)

    def test_spherical_weights_are_deterministic_and_shrink_toward_poles(self):
        equator = self.region(
            [[0.25, 0.42], [0.5, 0.42], [0.5, 0.58], [0.25, 0.58]],
            "Equator",
        )
        first = region_contour_mask(equator, self.settings)
        second = region_contour_mask(equator, self.settings)
        self.assertTrue(np.array_equal(first.indices, second.indices))
        self.assertTrue(np.array_equal(first.area_weights_m2, second.area_weights_m2))

        rows = _spherical_cell_area_rows(
            self.settings.width,
            self.settings.height,
            self.settings.world_circumference_km,
        )
        self.assertGreater(rows[self.settings.height // 2], rows[0])


class RegionAreaAggregateR1Tests(TestCase):
    polygon = [
        [0.05, 0.05], [0.35, 0.05], [0.65, 0.05], [0.95, 0.05],
        [0.95, 0.95], [0.65, 0.95], [0.35, 0.95], [0.05, 0.95],
    ]

    def setUp(self):
        clear_region_contour_mask_cache()
        self.campaign = Campaign.objects.create(name="Aggregate")
        self.settings = AtmosphericSettings(width=4, height=2)
        self.static = static_grid(4, 2)
        self.region = Region.objects.create(
            campaign=self.campaign,
            name="Area",
            map_latitude=45.0,
            map_longitude=-135.0,
            map_polygon=self.polygon,
        )

    def test_area_metrics_use_weighted_temperature_and_precipitation_coverage(self):
        grid = atmospheric_grid(4, 2)
        grid.fields["temperature"][:] = np.arange(8, dtype=np.float32)
        grid.fields["precipitation_rate"][:4] = 0.001
        mask = region_contour_mask(self.region, self.settings)

        state = area_weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )
        expected_temperature = np.average(
            grid.fields["temperature"][mask.indices],
            weights=mask.area_weights_m2,
        )
        wet = grid.fields["precipitation_rate"][mask.indices] * 3600 >= self.settings.value(
            "condition_precipitation_rate_mm_h"
        )
        expected_coverage = np.average(wet, weights=mask.area_weights_m2)

        self.assertAlmostEqual(state.temperature_mean_c, expected_temperature, places=3)
        self.assertAlmostEqual(state.precipitating_area_fraction, expected_coverage, places=6)
        self.assertGreater(state.humidity_mean_percent, 0.0)
        self.assertEqual(state.surface_pressure_mean_hpa, 1000.0)
        self.assertEqual(state.cloud_cover_mean, 0.0)
        self.assertEqual(state.cloudy_area_fraction, 0.0)

    def test_rain_and_snow_can_coexist_in_one_region(self):
        grid = atmospheric_grid(4, 2)
        grid.fields["temperature"][:4] = -8.0
        grid.fields["temperature"][4:] = 8.0
        grid.fields["precipitation_rate"].fill(0.001)

        state = area_weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )

        self.assertGreater(state.rain_area_fraction, 0.0)
        self.assertGreater(state.snow_area_fraction, 0.0)
        self.assertAlmostEqual(
            state.rain_area_fraction + state.snow_area_fraction,
            state.precipitating_area_fraction,
            places=5,
        )

    def test_wind_uses_vector_mean_and_summary_is_metric_driven(self):
        grid = atmospheric_grid(4, 2)
        grid.fields["wind_u"][:6] = 4.0
        grid.fields["wind_u"][6:] = -4.0
        grid.fields["precipitation_rate"][:6] = 0.001
        grid.fields["cloud_cover"][:6] = 0.9

        state = area_weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )
        summary = build_region_area_weather_summary(state)

        self.assertAlmostEqual(state.wind_mean_u_m_s, 2.0, places=3)
        self.assertAlmostEqual(state.wind_mean_v_m_s, 0.0, places=3)
        self.assertAlmostEqual(state.prevailing_wind_direction_degrees, 270.0, places=2)
        self.assertIn("Средняя температура", summary.temperature)
        self.assertIn("Дождь", summary.precipitation)
        self.assertIn("большей части", summary.precipitation)

    def test_anchor_dry_can_coexist_with_majority_area_rain(self):
        grid = atmospheric_grid(4, 2)
        grid.fields["precipitation_rate"][:6] = 0.001
        grid.fields["precipitation_rate"][0] = 0.0
        point = _weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )
        area = area_weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )

        self.assertEqual(point.condition, WeatherState.Condition.CLEAR)
        self.assertGreater(area.precipitating_area_fraction, 0.5)
        self.assertIn("большей части", build_region_area_weather_summary(area).precipitation)

    def test_anchor_rain_can_coexist_with_mostly_dry_area(self):
        grid = atmospheric_grid(4, 2)
        grid.fields["precipitation_rate"][0] = 0.001
        point = _weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )
        area = area_weather_from_grid_at_time(
            self.region,
            0,
            grid,
            settings=self.settings,
            static=self.static,
        )

        self.assertEqual(point.condition, WeatherState.Condition.RAIN)
        self.assertLess(area.precipitating_area_fraction, 0.2)
        self.assertIn("местами", build_region_area_weather_summary(area).precipitation)

    def test_time_report_integrated_precipitation_does_not_read_area_current_rate(self):
        point = WeatherState.objects.create(
            region=self.region,
            world_minutes=360,
            region_weather_revision=0,
            temperature=10,
            humidity=50,
            wind_speed=1,
            precipitation=0,
            precipitation_rate_mm_h=0,
            precipitation_amount_mm=0,
            condition=WeatherState.Condition.CLEAR,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V3,
        )
        grid = atmospheric_grid(4, 2)
        grid.fields["precipitation_rate"].fill(0.001)
        area = area_weather_from_grid_at_time(
            self.region,
            360,
            grid,
            settings=self.settings,
            static=self.static,
        )
        area.save()

        summary = build_time_advance_summary(
            self.campaign,
            [self.region],
            [point],
            [],
            start=0,
            end=360,
            amount=360,
            unit=TimeAdvanceReport.RequestedUnit.MINUTES,
            simulation_mode=TimeAdvanceReport.SimulationMode.EXACT,
            weather_coverage_start=0,
        )

        regional = summary["regional_weather"][0]
        self.assertEqual(
            regional["integrated_precipitation"]["integrated_amount_mm"],
            0.0,
        )
        self.assertGreater(area.area_mean_precipitation_rate_mm_h, 0.0)
