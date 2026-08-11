from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from campaigns.models import Campaign
from world.biomes import Biome
from world.models import AtmosphericConfig, AtmosphericSnapshot, Region, WeatherState
from world.services.time import advance_world
from world.services.atmosphere import persistence
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint
from world.services.atmosphere.ocean import ocean_weighted_mean
from world.services.atmosphere.static_grid import cached_static_world_grid


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
        self.assertEqual(weather.source, WeatherState.Source.ATMOSPHERIC_GRID_V2)
        self.assertIsNotNone(weather.pressure_hpa)
        self.assertIsNotNone(weather.cloud_cover)
        self.assertIsNotNone(weather.precipitation_rate_mm_h)
        self.assertIsNotNone(weather.precipitation_amount_mm)

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

    def test_steps_and_region_sampling_stay_in_memory(self):
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
            "world.services.atmosphere.persistence.grid_from_snapshot",
            wraps=persistence.grid_from_snapshot,
        ) as deserialize:
            advance_world(campaign.pk, 360)

        self.assertEqual(deserialize.call_count, 0)
        self.assertEqual(WeatherState.objects.filter(region__campaign=campaign).count(), 6)

        with patch(
            "world.services.atmosphere.persistence.grid_from_snapshot",
            wraps=persistence.grid_from_snapshot,
        ) as deserialize:
            advance_world(campaign.pk, 1440)

        self.assertEqual(deserialize.call_count, 1)
        self.assertEqual(
            WeatherState.objects.filter(region__campaign=campaign).count(),
            18,
        )

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
        ) as static_grid, patch(
            "world.services.atmosphere.persistence.grid_from_snapshot"
        ) as deserialize, patch(
            "world.services.atmosphere.persistence.simulate_step"
        ) as simulate, patch(
            "world.services.atmosphere.persistence.atmospheric_input_fingerprint"
        ) as fingerprint:
            advance_world(campaign.pk, 10)

        static_grid.assert_not_called()
        deserialize.assert_not_called()
        simulate.assert_not_called()
        fingerprint.assert_not_called()
        self.assertEqual(campaign.atmospheric_snapshots.count(), snapshot_count)

    def test_one_vitok_keeps_only_turn_checkpoints_and_latest(self):
        campaign = self.create_campaign("Checkpoint Витка")

        advance_world(campaign.pk, campaign.calendar_minutes_per_turn)

        snapshots = list(
            campaign.atmospheric_snapshots.order_by("world_minutes").values_list(
                "world_minutes",
                "is_checkpoint",
            )
        )
        self.assertEqual(
            snapshots,
            [(0, True), (campaign.calendar_minutes_per_turn, True)],
        )

    def test_checkpoint_retention_does_not_remove_regional_history(self):
        campaign = self.create_campaign("Retention")
        config = campaign.atmospheric_config
        config.checkpoint_interval_minutes = 720
        config.checkpoint_retention_count = 2
        config.save(
            update_fields=[
                "checkpoint_interval_minutes",
                "checkpoint_retention_count",
            ]
        )
        region = Region.objects.create(
            campaign=campaign,
            name="Регион истории",
            biome=Biome.MEADOW,
            map_latitude=10,
            map_longitude=20,
        )

        advance_world(campaign.pk, 2160)

        self.assertEqual(
            list(
                campaign.atmospheric_snapshots.order_by("world_minutes").values_list(
                    "world_minutes",
                    flat=True,
                )
            ),
            [1440, 2160],
        )
        self.assertEqual(region.weather_history.count(), 7)

    def test_changed_input_fingerprint_starts_separate_history(self):
        campaign = self.create_campaign("Fingerprint")
        advance_world(campaign.pk, 360)
        old_fingerprint = (
            campaign.atmospheric_snapshots.exclude(input_fingerprint="")
            .values_list("input_fingerprint", flat=True)
            .first()
        )
        config = campaign.atmospheric_config
        config.ocean_temperature_c = 46
        config.save(update_fields=["ocean_temperature_c"])

        advance_world(campaign.pk, 360)

        fingerprints = set(
            campaign.atmospheric_snapshots.exclude(input_fingerprint="").values_list(
                "input_fingerprint",
                flat=True,
            )
        )
        self.assertIn(old_fingerprint, fingerprints)
        self.assertEqual(len(fingerprints), 2)

    def test_presentation_only_oxygen_fraction_does_not_invalidate_physics(self):
        campaign = self.create_campaign("Oxygen presentation")
        config = campaign.atmospheric_config
        before = atmospheric_input_fingerprint(campaign, config)

        config.oxygen_fraction = 0.19
        config.save(update_fields=["oxygen_fraction"])

        self.assertEqual(before, atmospheric_input_fingerprint(campaign, config))

    def test_legacy_snapshot_is_retained_but_not_silently_adopted(self):
        campaign = self.create_campaign("Legacy snapshot")
        legacy_grid = AtmosphericGrid.empty(8, 4)
        AtmosphericSnapshot.objects.create(
            campaign=campaign,
            world_minutes=0,
            grid_width=8,
            grid_height=4,
            format_version=1,
            solver_version=1,
            input_fingerprint="",
            payload=legacy_grid.serialize(),
        )

        with patch(
            "world.services.atmosphere.persistence.grid_from_snapshot",
            wraps=persistence.grid_from_snapshot,
        ) as deserialize:
            advance_world(campaign.pk, 360)

        deserialize.assert_not_called()
        self.assertTrue(
            campaign.atmospheric_snapshots.filter(input_fingerprint="").exists()
        )
        self.assertTrue(
            campaign.atmospheric_snapshots.exclude(input_fingerprint="").exists()
        )

    def test_snapshot_payload_with_wrong_solver_version_is_rejected(self):
        campaign = self.create_campaign("Wrong solver")
        grid = AtmosphericGrid.empty(8, 4)
        snapshot = AtmosphericSnapshot(
            campaign=campaign,
            world_minutes=0,
            grid_width=8,
            grid_height=4,
            format_version=2,
            solver_version=3,
            input_fingerprint="a" * 64,
            payload=grid.serialize(),
        )

        with self.assertRaises(ValueError):
            persistence.grid_from_snapshot(snapshot)

    def test_checkpoint_interval_must_align_to_physics_step(self):
        campaign = self.create_campaign("Checkpoint validation")
        config = campaign.atmospheric_config
        config.checkpoint_interval_minutes = 500

        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_legacy_prune_command_is_dry_run_and_protects_tip(self):
        campaign = self.create_campaign("Legacy pruning")
        grid = AtmosphericGrid.empty(8, 4)
        for world_minutes in (0, 360, 720):
            AtmosphericSnapshot.objects.create(
                campaign=campaign,
                world_minutes=world_minutes,
                grid_width=8,
                grid_height=4,
                format_version=1,
                solver_version=1,
                input_fingerprint="",
                payload=grid.serialize(),
            )
        versioned = AtmosphericSnapshot.objects.create(
            campaign=campaign,
            world_minutes=720,
            grid_width=8,
            grid_height=4,
            format_version=1,
            solver_version=2,
            input_fingerprint="a" * 64,
            payload=grid.serialize(),
        )

        call_command(
            "prune_legacy_atmosphere",
            str(campaign.pk),
            keep=1,
            stdout=StringIO(),
        )
        self.assertEqual(
            campaign.atmospheric_snapshots.filter(input_fingerprint="").count(),
            3,
        )

        call_command(
            "prune_legacy_atmosphere",
            str(campaign.pk),
            keep=1,
            confirm=True,
            stdout=StringIO(),
        )
        self.assertEqual(
            list(
                campaign.atmospheric_snapshots.filter(input_fingerprint="")
                .values_list("world_minutes", flat=True)
            ),
            [720],
        )
        self.assertTrue(AtmosphericSnapshot.objects.filter(pk=versioned.pk).exists())

    def test_incompatible_legacy_adoption_is_rejected_and_non_destructive(self):
        campaign = self.create_campaign("Legacy adoption")
        grid = AtmosphericGrid.empty(8, 4)
        legacy = AtmosphericSnapshot.objects.create(
            campaign=campaign,
            world_minutes=0,
            grid_width=8,
            grid_height=4,
            format_version=1,
            solver_version=1,
            input_fingerprint="",
            payload=grid.serialize(),
        )

        with self.assertRaises(CommandError):
            call_command(
                "adopt_legacy_atmosphere",
                str(campaign.pk),
                confirm=True,
                stdout=StringIO(),
            )
        self.assertTrue(AtmosphericSnapshot.objects.filter(pk=legacy.pk).exists())
        self.assertEqual(campaign.atmospheric_snapshots.count(), 1)

    def test_one_day_advance_matches_four_sequential_six_hour_advances(self):
        one_call = self.create_campaign("Один вызов")
        four_calls = self.create_campaign("Четыре вызова")

        advance_world(one_call.pk, 1440)
        for _ in range(4):
            advance_world(four_calls.pk, 360)

        one_payload = one_call.atmospheric_snapshots.get(world_minutes=1440).payload
        four_payload = four_calls.atmospheric_snapshots.get(world_minutes=1440).payload
        self.assertEqual(bytes(one_payload), bytes(four_payload))

    def test_fast_forward_simulates_only_final_spinup_turn(self):
        campaign = self.create_campaign("Atmospheric fast-forward")
        campaign.exact_simulation_max_turns = 1
        campaign.fast_forward_spinup_turns = 1
        campaign.save(
            update_fields=["exact_simulation_max_turns", "fast_forward_spinup_turns"]
        )
        Region.objects.create(
            campaign=campaign,
            name="Регион spin-up",
            biome=Biome.MEADOW,
            map_latitude=10,
            map_longitude=20,
        )

        with (
            patch(
                "world.services.atmosphere.persistence.initialize_atmosphere",
                wraps=persistence.initialize_atmosphere,
            ) as initialize,
            patch(
                "world.services.atmosphere.persistence.simulate_step",
                wraps=persistence.simulate_step,
            ) as simulate,
        ):
            advance_world(campaign.pk, 3 * campaign.calendar_minutes_per_turn)

        self.assertEqual(simulate.call_count, 28)
        spinup_start = 2 * campaign.calendar_minutes_per_turn
        self.assertEqual(initialize.call_args.kwargs["world_minutes"], spinup_start)
        self.assertIn("forcing", initialize.call_args.kwargs)
        self.assertFalse(
            WeatherState.objects.filter(
                region__campaign=campaign,
                world_minutes__gt=0,
                world_minutes__lt=spinup_start,
            ).exists()
        )
        self.assertTrue(
            WeatherState.objects.filter(
                region__campaign=campaign,
                world_minutes__gte=spinup_start,
            ).exists()
        )

    def test_fast_forward_advances_inherited_sst_instead_of_resetting_it(self):
        campaign = self.create_campaign("SST slow state")
        advance_world(campaign.pk, 360)
        campaign.refresh_from_db()
        config = campaign.atmospheric_config
        settings = AtmosphericSettings.from_model(config, campaign)
        static = cached_static_world_grid(settings)
        snapshot = campaign.atmospheric_snapshots.get(world_minutes=360)
        inherited = persistence.grid_from_snapshot(snapshot)
        inherited.fields["sea_surface_temperature_c"][static.is_ocean] += 4.0
        inherited_start_mean = ocean_weighted_mean(
            inherited.fields["sea_surface_temperature_c"],
            static,
            settings,
        )
        snapshot.payload = inherited.serialize()
        snapshot.save(update_fields=["payload"])

        turn = campaign.calendar_minutes_per_turn
        result = persistence.advance_atmosphere_for_period(
            campaign,
            config,
            2 * turn,
            3 * turn,
            force_initialize=True,
            fast_forward_start=360,
        )

        self.assertEqual(result.ocean_summary["mode"], "fast_forward")
        self.assertGreater(result.ocean_summary["macro_steps"], 0)
        self.assertAlmostEqual(
            result.ocean_summary["start_mean_sst_c"],
            inherited_start_mean,
            places=4,
        )
        self.assertIn(
            "total_atmospheric_vapor_mass_proxy_kg",
            result.numerical_diagnostics,
        )

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
