import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BiomeMigrationTests(TransactionTestCase):
    migrate_from = [("campaigns", "0005_campaign_dark_season_max_red_turns_and_more"), ("world", "0005_globalworldmaplayer")]
    migrate_to = [("campaigns", "0005_campaign_dark_season_max_red_turns_and_more"), ("world", "0006_expand_biome_catalogue")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Campaign = old_apps.get_model("campaigns", "Campaign")
        Region = old_apps.get_model("world", "Region")
        LegacyLayer = old_apps.get_model("world", "WorldMapLayer")
        GlobalLayer = old_apps.get_model("world", "GlobalWorldMapLayer")
        campaign = Campaign.objects.create(name="Проверка миграции биомов")
        old_values = [
            "plains",
            "forest",
            "desert",
            "mountains",
            "tundra",
            "swamp",
            "coast",
        ]
        for index, biome in enumerate(old_values):
            Region.objects.create(
                campaign=campaign,
                name=f"Старый биом {index}",
                biome=biome,
            )
        cells = {str(index): biome for index, biome in enumerate(old_values)}
        LegacyLayer.objects.create(campaign=campaign, biome_cells=cells)
        GlobalLayer.objects.create(biome_cells=cells)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_old_values_are_preserved_and_plains_is_renamed(self):
        Region = self.apps.get_model("world", "Region")
        LegacyLayer = self.apps.get_model("world", "WorldMapLayer")
        GlobalLayer = self.apps.get_model("world", "GlobalWorldMapLayer")
        expected = [
            "meadow",
            "forest",
            "desert",
            "mountains",
            "tundra",
            "swamp",
            "coast",
        ]

        self.assertCountEqual(
            Region.objects.values_list("biome", flat=True),
            expected,
        )
        self.assertEqual(
            list(LegacyLayer.objects.get().biome_cells.values()),
            expected,
        )
        self.assertEqual(
            list(GlobalLayer.objects.get().biome_cells.values()),
            expected,
        )

        # The data operation is safe if a deploy or recovery process invokes it
        # again: it neither duplicates nor changes already-migrated values.
        migration = importlib.import_module("world.migrations.0006_expand_biome_catalogue")
        migration.forwards(self.apps, None)
        self.assertCountEqual(
            Region.objects.values_list("biome", flat=True),
            expected,
        )
