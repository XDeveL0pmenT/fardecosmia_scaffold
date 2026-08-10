from django.db import migrations, models


def copy_single_legacy_layer(apps, schema_editor):
    LegacyLayer = apps.get_model("world", "WorldMapLayer")
    GlobalLayer = apps.get_model("world", "GlobalWorldMapLayer")
    legacy_layers = list(LegacyLayer.objects.all().order_by("pk")[:2])
    if len(legacy_layers) != 1:
        return

    legacy = legacy_layers[0]
    target_width = 360
    target_height = 180

    def upscale(cells):
        scaled = {}
        for raw_index, value in (cells or {}).items():
            index = int(raw_index)
            source_x = index % legacy.grid_width
            source_y = index // legacy.grid_width
            x0 = source_x * target_width // legacy.grid_width
            x1 = (source_x + 1) * target_width // legacy.grid_width
            y0 = source_y * target_height // legacy.grid_height
            y1 = (source_y + 1) * target_height // legacy.grid_height
            for y in range(y0, max(y0 + 1, y1)):
                for x in range(x0, max(x0 + 1, x1)):
                    scaled[str(y * target_width + x)] = value
        return scaled

    GlobalLayer.objects.create(
        slug="fardecosmia",
        grid_width=target_width,
        grid_height=target_height,
        biome_cells=upscale(legacy.biome_cells),
        elevation_cells=upscale(legacy.elevation_cells),
    )


def remove_copied_global_layer(apps, schema_editor):
    GlobalLayer = apps.get_model("world", "GlobalWorldMapLayer")
    GlobalLayer.objects.filter(slug="fardecosmia").delete()


class Migration(migrations.Migration):
    dependencies = [("world", "0004_region_precipitation_bias_and_more")]

    operations = [
        migrations.CreateModel(
            name="GlobalWorldMapLayer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(default="fardecosmia", max_length=50, unique=True),
                ),
                ("grid_width", models.PositiveSmallIntegerField(default=360, editable=False)),
                ("grid_height", models.PositiveSmallIntegerField(default=180, editable=False)),
                (
                    "biome_cells",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Разреженная общая сетка биомов: индекс ячейки -> код биома.",
                    ),
                ),
                (
                    "elevation_cells",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Необязательные GM-поправки к растровой карте высот.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "общий слой карты мира",
                "verbose_name_plural": "общие слои карты мира",
            },
        ),
        migrations.RunPython(copy_single_legacy_layer, remove_copied_global_layer),
    ]
