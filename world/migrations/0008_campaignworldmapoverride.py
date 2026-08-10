from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0005_campaign_dark_season_max_red_turns_and_more"),
        ("world", "0007_atmospheric_grid"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignWorldMapOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("grid_width", models.PositiveSmallIntegerField(default=360, editable=False)),
                ("grid_height", models.PositiveSmallIntegerField(default=180, editable=False)),
                (
                    "biome_cells",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Разреженные замены биомов только для этой кампании: "
                            "индекс ячейки -> код биома. Отсутствующая ячейка наследует общий атлас."
                        ),
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="world_map_override",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={
                "verbose_name": "локальные замены биомов кампании",
                "verbose_name_plural": "локальные замены биомов кампаний",
            },
        ),
    ]
