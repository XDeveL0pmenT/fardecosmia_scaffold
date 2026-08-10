from django.db import migrations, models


def _rename_cells(cells, source, target):
    if not isinstance(cells, dict):
        return cells, False
    changed = False
    migrated = {}
    for index, value in cells.items():
        if value == source:
            value = target
            changed = True
        migrated[index] = value
    return migrated, changed


def _migrate_biomes(apps, source, target):
    Region = apps.get_model("world", "Region")
    LegacyLayer = apps.get_model("world", "WorldMapLayer")
    GlobalLayer = apps.get_model("world", "GlobalWorldMapLayer")

    Region.objects.filter(biome=source).update(biome=target)
    for Layer in (LegacyLayer, GlobalLayer):
        for layer in Layer.objects.all().iterator():
            cells, changed = _rename_cells(layer.biome_cells, source, target)
            if changed:
                layer.biome_cells = cells
                layer.save(update_fields=["biome_cells"])


def forwards(apps, schema_editor):
    _migrate_biomes(apps, "plains", "meadow")


def backwards(apps, schema_editor):
    _migrate_biomes(apps, "meadow", "plains")


class Migration(migrations.Migration):
    dependencies = [("world", "0005_globalworldmaplayer")]

    operations = [
        migrations.AlterField(
            model_name="region",
            name="biome",
            field=models.CharField(
                choices=[
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
                    ("coast", "Побережье (legacy — требует уточнения)"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
