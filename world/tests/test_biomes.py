from django.test import SimpleTestCase

from world.biomes import BIOME_PALETTE, CANONICAL_BIOME_KEYS, Biome


class BiomeCatalogueTests(SimpleTestCase):
    expected = [
        ("meadow", "Луга"),
        ("forest", "Лес"),
        ("jungle", "Джунгли"),
        ("sahara", "Сахара"),
        ("swamp", "Болото"),
        ("desert", "Пустыня"),
        ("tundra", "Тундра"),
        ("mountains", "Горы"),
        ("boiling_crystal_lagoons", "Кипящие хрустальные лагуны"),
        ("geyser_wasteland", "Гейзерная пустошь"),
        ("lumenvein_thickets", "Светожильные чащобы"),
        ("mycelial_groves", "Мицелиевые Рощи"),
        ("azure_pillars", "Лазурные Столпы"),
        ("misty_marshes", "Туманные Топи"),
        ("red_plateaus", "Красные Плато"),
        ("hellscape", "Адская местность"),
    ]

    def test_catalogue_contains_all_sixteen_canonical_keys_and_labels(self):
        self.assertEqual(len(CANONICAL_BIOME_KEYS), 16)
        self.assertEqual(
            [(key, Biome(key).label) for key in CANONICAL_BIOME_KEYS],
            self.expected,
        )

    def test_legacy_coast_is_retained_but_not_canonical(self):
        self.assertEqual(Biome.LEGACY_COAST, "coast")
        self.assertNotIn(Biome.LEGACY_COAST, CANONICAL_BIOME_KEYS)
        self.assertIn("требует уточнения", Biome.LEGACY_COAST.label)

    def test_palette_uses_exact_stable_colours(self):
        self.assertEqual(BIOME_PALETTE[Biome.BOILING_CRYSTAL_LAGOONS], "#25BFBC")
        self.assertEqual(BIOME_PALETTE[Biome.AZURE_PILLARS], "#26BCBA")
        self.assertEqual(BIOME_PALETTE[Biome.HELLSCAPE], "#000000")

