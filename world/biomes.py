from django.db import models


class Biome(models.TextChoices):
    """Stable biome identifiers used by the objective world atlas."""

    MEADOW = "meadow", "Луга"
    FOREST = "forest", "Лес"
    JUNGLE = "jungle", "Джунгли"
    SAHARA = "sahara", "Сахара"
    SWAMP = "swamp", "Болото"
    DESERT = "desert", "Пустыня"
    TUNDRA = "tundra", "Тундра"
    MOUNTAINS = "mountains", "Горы"
    BOILING_CRYSTAL_LAGOONS = (
        "boiling_crystal_lagoons",
        "Кипящие хрустальные лагуны",
    )
    GEYSER_WASTELAND = "geyser_wasteland", "Гейзерная пустошь"
    LUMENVEIN_THICKETS = "lumenvein_thickets", "Светожильные чащобы"
    MYCELIAL_GROVES = "mycelial_groves", "Мицелиевые Рощи"
    AZURE_PILLARS = "azure_pillars", "Лазурные Столпы"
    MISTY_MARSHES = "misty_marshes", "Туманные Топи"
    RED_PLATEAUS = "red_plateaus", "Красные Плато"
    HELLSCAPE = "hellscape", "Адская местность"

    # Kept deliberately: the old value cannot be mapped to one of the sixteen
    # objective biomes without inventing world data.
    LEGACY_COAST = "coast", "Побережье (legacy — требует уточнения)"


CANONICAL_BIOME_KEYS = tuple(
    value for value, _label in Biome.choices if value != Biome.LEGACY_COAST
)


BIOME_PALETTE = {
    Biome.MEADOW: "#95A843",
    Biome.FOREST: "#446D3C",
    Biome.JUNGLE: "#115D39",
    Biome.SAHARA: "#E8C370",
    Biome.SWAMP: "#859A7B",
    Biome.DESERT: "#D0AA75",
    Biome.TUNDRA: "#92B5C4",
    Biome.MOUNTAINS: "#82817C",
    Biome.BOILING_CRYSTAL_LAGOONS: "#25BFBC",
    Biome.GEYSER_WASTELAND: "#E3A06A",
    Biome.LUMENVEIN_THICKETS: "#0E6958",
    Biome.MYCELIAL_GROVES: "#786A8D",
    Biome.AZURE_PILLARS: "#26BCBA",
    Biome.MISTY_MARSHES: "#7598A4",
    Biome.RED_PLATEAUS: "#BE5D39",
    Biome.HELLSCAPE: "#000000",
    # Compatibility colour only. It is intentionally excluded from the
    # canonical sixteen and remains visible until a GM resolves the old cell.
    Biome.LEGACY_COAST: "#47A4B8",
}
