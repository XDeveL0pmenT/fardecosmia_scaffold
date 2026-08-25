from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings as django_settings
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from characters.models import Character, CharacterLocationState
from world.models import (
    AtmosphericConfig,
    AtmosphericSnapshot,
    AuditLog,
    WeatherState,
)
from world.services.ambience import (
    build_ambient_presentation,
    build_character_ambience,
    build_region_ambience,
)
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.persistence import save_snapshot
from world.services.atmosphere.sampling import (
    AtmosphericPointWeather,
    interpret_point_weather,
)


def sky(
    *,
    light="day",
    star=0.8,
    ympha=0.0,
    darkness=0.1,
    turn="black",
    season="Лето",
):
    return SimpleNamespace(
        location_known=True,
        star_phase_code=light,
        star_intensity=star,
        ympha_visibility=ympha,
        darkness=darkness,
        turn_type_code=turn,
        season_light_code="mixed",
        local_moment=SimpleNamespace(season=season),
    )


def weather(
    *,
    temperature=20.0,
    cloud=0.1,
    rate=0.0,
    rain=1.0,
    snow=0.0,
    condition=WeatherState.Condition.CLEAR,
    amount=0.0,
):
    return AtmosphericPointWeather(
        temperature=temperature,
        humidity=55.0,
        pressure_hpa=1000.0,
        wind_speed=3.0,
        wind_direction_degrees=90.0,
        cloud_cover=cloud,
        precipitation=0.0,
        precipitation_rate_mm_h=rate,
        precipitation_amount_mm=amount,
        rain_fraction=rain,
        snow_fraction=snow,
        fog_probability=1.0 if condition == WeatherState.Condition.FOG else 0.0,
        condition=condition,
    )


def point(*, temperature=20.0, cloud=0.1, rate_mm_h=0.0):
    return SimpleNamespace(
        values={
            "temperature": temperature,
            "water_vapor_specific_humidity": 0.006,
            "cloud_condensate_specific_humidity": 0.0,
            "pressure_hpa": 1000.0,
            "wind_u": 2.0,
            "wind_v": 0.0,
            "cloud_cover": cloud,
            "precipitation_rate": rate_mm_h / 3600.0,
        },
        wind_speed_m_s=2.0,
        wind_direction_degrees=90.0,
        elevation_m=25.0,
        biome="forest",
    )


class CharacterAmbiencePW2Tests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.gm = users.create_user(username="pw2-gm", password="pass")
        self.player = users.create_user(username="pw2-player", password="pass")
        self.other = users.create_user(username="pw2-other", password="pass")
        self.campaign = Campaign.objects.create(name="PW2 ambience")
        self.foreign_campaign = Campaign.objects.create(name="PW2 foreign")
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        self.membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.other_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.other,
            role=CampaignMembership.Role.PLAYER,
        )
        self.config = AtmosphericConfig.objects.create(
            campaign=self.campaign,
            enabled=True,
            grid_width=24,
            grid_height=12,
            step_minutes=360,
        )
        self.character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership,
            name="Иллара",
        )

    def place(self, character=None, *, latitude="12.345678", longitude="-45.123456"):
        return CharacterLocationState.objects.create(
            character=character or self.character,
            latitude=Decimal(latitude),
            longitude=Decimal(longitude),
        )

    def sampled(self, sampled_point=None):
        return SimpleNamespace(
            point=sampled_point or point(),
            snapshot_world_minutes=self.campaign.world_minutes,
            requested_world_minutes=self.campaign.world_minutes,
        )

    def workspace(self, *, query=""):
        self.client.force_login(self.player)
        return self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk]) + query
        )

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_unplaced_character_is_neutral_and_sampler_is_not_called(self, sampler):
        response = self.workspace()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["character_ambience"].has_environment)
        self.assertFalse(response.context["character_ambience"].location_available)
        self.assertContains(response, 'data-ambience="neutral"')
        sampler.assert_not_called()

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_effective_location_coordinates_are_sampled_exactly_once(self, sampler):
        self.place()
        sampler.return_value = self.sampled()

        response = self.workspace()

        self.assertEqual(response.status_code, 200)
        sampler.assert_called_once()
        args = sampler.call_args.args
        self.assertEqual(args[0], self.campaign)
        self.assertEqual(args[1], 12.345678)
        self.assertEqual(args[2], -45.123456)
        self.assertTrue(response.context["character_ambience"].has_environment)

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_player_query_coordinates_are_ignored_and_not_an_oracle(self, sampler):
        self.place(latitude="7.000001", longitude="8.000002")
        sampler.return_value = self.sampled()

        response = self.workspace(query="?latitude=89&longitude=179")

        self.assertEqual(response.status_code, 200)
        sampler.assert_called_once()
        self.assertEqual(sampler.call_args.args[1:3], (7.000001, 8.000002))

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_foreign_campaign_and_other_character_cannot_be_sampled(self, sampler):
        other_character = Character.objects.create(
            campaign=self.campaign,
            owner=self.other_membership,
            name="Чужой",
        )
        self.place(other_character, latitude="44", longitude="55")
        self.client.force_login(self.player)

        foreign = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.foreign_campaign.pk])
        )
        other_detail = self.client.get(
            reverse("characters:detail", args=[self.campaign.pk, other_character.pk])
        )

        self.assertEqual(foreign.status_code, 403)
        self.assertEqual(other_detail.status_code, 404)
        sampler.assert_not_called()

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_workspace_get_does_not_mutate_world_or_weather(self, sampler):
        self.place()
        sampler.return_value = self.sampled()
        before = {
            "world_minutes": self.campaign.world_minutes,
            "weather": WeatherState.objects.count(),
            "snapshots": AtmosphericSnapshot.objects.count(),
            "locations": CharacterLocationState.objects.count(),
            "audits": AuditLog.objects.count(),
        }

        response = self.workspace()
        self.campaign.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.campaign.world_minutes, before["world_minutes"])
        self.assertEqual(WeatherState.objects.count(), before["weather"])
        self.assertEqual(AtmosphericSnapshot.objects.count(), before["snapshots"])
        self.assertEqual(CharacterLocationState.objects.count(), before["locations"])
        self.assertEqual(AuditLog.objects.count(), before["audits"])

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_unavailable_environment_is_safe_neutral_with_location_preserved(self, sampler):
        self.place()
        sampler.return_value = None

        response = self.workspace()

        ambience = response.context["character_ambience"]
        self.assertFalse(ambience.has_environment)
        self.assertTrue(ambience.location_available)
        self.assertContains(response, "Точка пути различима.")
        self.assertContains(response, 'data-ambience="neutral"')

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_disabled_or_missing_atmosphere_does_not_trigger_sampling(self, sampler):
        self.place()
        self.config.delete()

        response = self.workspace()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["character_ambience"].has_environment)
        self.assertTrue(response.context["character_ambience"].location_available)
        sampler.assert_not_called()

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_player_html_contains_only_safe_tokens_not_coordinates_or_diagnostics(self, sampler):
        self.place(latitude="17.123456", longitude="-88.654321")
        sampler.return_value = self.sampled(point(temperature=31.0, cloud=0.8))

        response = self.workspace()

        self.assertContains(response, 'data-ambience="live"')
        self.assertContains(response, 'data-temperature-band="hot"')
        for hidden in (
            "17.123456",
            "-88.654321",
            "snapshot_world_minutes",
            "surface_pressure_hpa",
            "circulation_pressure_hpa",
            "grid_x",
            "nearest_index",
            "fardecosmia-atlas-config",
            "leaflet.js",
        ):
            self.assertNotContains(response, hidden)

    def test_shared_region_and_character_adapter_match_for_same_state(self):
        current = weather(
            temperature=-8.0,
            cloud=0.73,
            rate=1.5,
            rain=0.1,
            snow=0.9,
            condition=WeatherState.Condition.SNOW,
            amount=900.0,
        )
        local_sky = sky(light="deep-night", star=0.0, ympha=0.8, darkness=0.35, turn="red")
        region_weather = WeatherState(
            temperature=current.temperature,
            humidity=current.humidity,
            pressure_hpa=current.pressure_hpa,
            wind_speed=current.wind_speed,
            wind_direction_degrees=current.wind_direction_degrees,
            cloud_cover=current.cloud_cover,
            precipitation=0.0,
            precipitation_rate_mm_h=current.precipitation_rate_mm_h,
            precipitation_amount_mm=current.precipitation_amount_mm,
            rain_fraction=current.rain_fraction,
            snow_fraction=current.snow_fraction,
            condition=current.condition,
        )

        character_tokens = build_ambient_presentation(
            sky=local_sky,
            weather=current,
            biome="tundra",
        )
        region_tokens = build_region_ambience(
            region_weather,
            local_sky,
            biome="tundra",
        )

        for field in (
            "light_level",
            "is_dark",
            "ympha_light_strength",
            "cloud_fraction",
            "precipitation_kind",
            "precipitation_intensity",
            "rain_intensity",
            "snow_intensity",
            "temperature_band",
            "weather_code",
        ):
            self.assertEqual(getattr(character_tokens, field), getattr(region_tokens, field))

    def test_current_precipitation_rate_not_accumulated_amount_drives_ambience(self):
        local_sky = sky()
        dry = build_ambient_presentation(
            sky=local_sky,
            weather=weather(rate=0.0, amount=999.0),
        )
        wet = build_ambient_presentation(
            sky=local_sky,
            weather=weather(
                rate=4.0,
                amount=0.0,
                condition=WeatherState.Condition.RAIN,
            ),
        )

        self.assertEqual(dry.precipitation_kind, "none")
        self.assertEqual(dry.precipitation_intensity, 0.0)
        self.assertEqual(wet.precipitation_kind, "rain")
        self.assertGreater(wet.rain_intensity, 0.0)

    def test_visual_tokens_cover_sky_cloud_precipitation_fog_and_temperature(self):
        states = {
            "bright": build_ambient_presentation(sky=sky(light="bright", star=1.0), weather=weather()),
            "dark": build_ambient_presentation(sky=sky(light="deep-night", star=0.0, darkness=1.0), weather=weather()),
            "ympha": build_ambient_presentation(sky=sky(light="night", star=0.0, ympha=0.9, turn="red"), weather=weather()),
            "cloud": build_ambient_presentation(sky=sky(), weather=weather(cloud=0.95, condition=WeatherState.Condition.CLOUDY)),
            "rain": build_ambient_presentation(sky=sky(), weather=weather(rate=8.0, condition=WeatherState.Condition.RAIN)),
            "snow": build_ambient_presentation(sky=sky(), weather=weather(temperature=-5.0, rate=3.0, rain=0.0, snow=1.0, condition=WeatherState.Condition.SNOW)),
            "fog": build_ambient_presentation(sky=sky(), weather=weather(cloud=0.8, condition=WeatherState.Condition.FOG)),
            "hot": build_ambient_presentation(sky=sky(), weather=weather(temperature=39.0)),
            "cold": build_ambient_presentation(sky=sky(), weather=weather(temperature=-18.0)),
        }

        self.assertEqual(states["bright"].light_level, "bright")
        self.assertFalse(states["bright"].is_dark)
        self.assertTrue(states["dark"].is_dark)
        self.assertGreater(states["dark"].darkness_strength, 0.9)
        self.assertGreater(states["ympha"].ympha_tint_strength, 0.8)
        self.assertGreater(states["cloud"].cloud_fraction, 0.9)
        self.assertEqual(states["rain"].precipitation_kind, "rain")
        self.assertEqual(states["snow"].precipitation_kind, "snow")
        self.assertGreater(states["fog"].fog_or_haze_strength, 0.0)
        self.assertEqual(states["hot"].temperature_band, "hot")
        self.assertEqual(states["cold"].temperature_band, "cold")

    @patch("world.services.ambience.sample_campaign_environment_state_at")
    def test_active_character_switch_rebuilds_ambience_at_new_location(self, sampler):
        self.place(latitude="10", longitude="20")
        second = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership,
            name="Сайра",
        )
        self.place(second, latitude="-30", longitude="80")
        self.membership.active_character = self.character
        self.membership.save(update_fields=["active_character"])

        def sampled_for_location(_campaign, _latitude, longitude, **_kwargs):
            temperature = 40.0 if longitude == 20.0 else -20.0
            return self.sampled(point(temperature=temperature))

        sampler.side_effect = sampled_for_location
        self.client.force_login(self.player)
        first = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        switched = self.client.post(
            reverse("characters:switch_active", args=[self.campaign.pk]),
            {"character": second.pk},
            follow=True,
        )

        self.assertEqual(first.context["character_ambience"].temperature_band, "hot")
        self.assertEqual(switched.context["character_ambience"].temperature_band, "cold")
        self.assertEqual(sampler.call_args.args[1:3], (-30.0, 80.0))

    def test_authoritative_snapshot_integration_is_read_only(self):
        self.place(latitude="0", longitude="0")
        self.campaign.refresh_from_db()
        self.config.refresh_from_db()
        settings = AtmosphericSettings.from_model(self.config, self.campaign)
        grid = AtmosphericGrid.empty(settings.width, settings.height)
        grid.fields["temperature"].fill(24.0)
        grid.fields["water_vapor_specific_humidity"].fill(0.006)
        grid.fields["cloud_condensate_specific_humidity"].fill(0.0)
        grid.fields["circulation_pressure_hpa"].fill(1000.0)
        grid.fields["pressure_hpa"].fill(1000.0)
        grid.fields["wind_u"].fill(2.0)
        grid.fields["wind_v"].fill(0.0)
        grid.fields["cloud_cover"].fill(0.25)
        grid.fields["precipitation_rate"].fill(0.0)
        grid.fields["surface_temperature"].fill(24.0)
        grid.fields["sea_surface_temperature_c"].fill(24.0)
        fingerprint = atmospheric_input_fingerprint(self.campaign, self.config)
        save_snapshot(
            self.campaign,
            self.campaign.world_minutes,
            grid,
            input_fingerprint=fingerprint,
        )
        before_payload = AtmosphericSnapshot.objects.get().payload

        response = self.workspace()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["character_ambience"].has_environment)
        self.assertEqual(WeatherState.objects.count(), 0)
        self.assertEqual(AtmosphericSnapshot.objects.count(), 1)
        self.assertEqual(AtmosphericSnapshot.objects.get().payload, before_payload)

    def test_point_interpreter_and_character_model_add_no_ambience_persistence(self):
        settings = AtmosphericSettings.from_model(self.config, self.campaign)
        reading = interpret_point_weather(point(rate_mm_h=2.0), settings)

        self.assertGreater(reading.precipitation_rate_mm_h, 0.0)
        self.assertFalse(hasattr(self.character, "current_weather"))
        self.assertFalse(hasattr(self.character, "current_temperature"))
        self.assertFalse(hasattr(self.character, "is_raining"))

    def test_shared_css_motion_is_reducible_and_has_no_animated_weather_gifs(self):
        css = (Path(django_settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("ambient-rain-fall", css)
        self.assertIn("ambient-snow-fall", css)
        self.assertNotIn('url("../gifs/rain.gif")', css)
        self.assertNotIn('url("../gifs/placidplace-snow-16036.gif")', css)
