# Generated manually for Fardecosmia Phase C3.5.

from django.db import migrations, models


def preserve_existing_region_climate(apps, schema_editor):
    Region = apps.get_model("world", "Region")
    # Provenance of old numeric values is unknown.  Preserve them as explicit
    # legacy/manual data instead of silently claiming they came from World Data.
    Region.objects.update(use_manual_climate_overrides=True)


class Migration(migrations.Migration):

    dependencies = [
        ("world", "0012_phase_c3_cloud_microphysics"),
    ]

    operations = [
        migrations.AddField(
            model_name="region",
            name="use_manual_climate_overrides",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "GM явно переопределяет климатические значения карты. "
                    "По умолчанию регион получает их из World Data."
                ),
            ),
        ),
        migrations.RunPython(
            preserve_existing_region_climate,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="region",
            name="biome",
            field=models.CharField(
                blank=True,
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
                default="",
                help_text="Пустое значение означает, что биом в World Data ещё не задан.",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="region",
            name="elevation",
            field=models.FloatField(
                blank=True,
                default=0,
                help_text=(
                    "Высота из World Data; null означает неизвестное значение карты."
                ),
                null=True,
            ),
        ),
    ]
