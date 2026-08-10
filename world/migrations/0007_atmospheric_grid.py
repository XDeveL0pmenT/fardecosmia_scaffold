import django.core.validators
import django.db.models.deletion
import world.atmosphere_defaults
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0005_campaign_dark_season_max_red_turns_and_more"),
        ("world", "0006_expand_biome_catalogue"),
    ]

    operations = [
        migrations.CreateModel(
            name="AtmosphericConfig",
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
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Пока выключено, кампания продолжает использовать weather-v2.",
                    ),
                ),
                (
                    "grid_width",
                    models.PositiveSmallIntegerField(
                        default=180,
                        validators=[
                            django.core.validators.MinValueValidator(4),
                            django.core.validators.MaxValueValidator(720),
                        ],
                    ),
                ),
                (
                    "grid_height",
                    models.PositiveSmallIntegerField(
                        default=90,
                        validators=[
                            django.core.validators.MinValueValidator(2),
                            django.core.validators.MaxValueValidator(360),
                        ],
                    ),
                ),
                (
                    "step_minutes",
                    models.PositiveIntegerField(
                        default=360,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                ("world_seed", models.BigIntegerField(default=0)),
                (
                    "ocean_temperature_c",
                    models.FloatField(
                        blank=True,
                        help_text="Настраиваемая температура горячего океана. Точное каноническое значение пока неизвестно, поэтому автоматического default нет.",
                        null=True,
                    ),
                ),
                (
                    "parameters",
                    models.JSONField(
                        default=world.atmosphere_defaults.default_atmospheric_parameters,
                        help_text="Численные коэффициенты прототипа; все значения настраиваемы и не являются каноном.",
                    ),
                ),
                (
                    "campaign",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="atmospheric_config",
                        to="campaigns.campaign",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AtmosphericSnapshot",
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
                ("world_minutes", models.BigIntegerField()),
                ("grid_width", models.PositiveSmallIntegerField()),
                ("grid_height", models.PositiveSmallIntegerField()),
                ("format_version", models.PositiveSmallIntegerField(default=1)),
                ("payload", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="atmospheric_snapshots",
                        to="campaigns.campaign",
                    ),
                ),
            ],
            options={"ordering": ["-world_minutes"]},
        ),
        migrations.AddConstraint(
            model_name="atmosphericsnapshot",
            constraint=models.UniqueConstraint(
                fields=("campaign", "world_minutes"),
                name="unique_atmospheric_snapshot_per_campaign_time",
            ),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="cloud_cover",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(1),
                ],
            ),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="pressure_hpa",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="source",
            field=models.CharField(
                choices=[
                    ("legacy_v2", "Региональная weather-v2"),
                    ("atmospheric_grid_v1", "Глобальная атмосферная сетка v1"),
                ],
                default="legacy_v2",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="weatherstate",
            name="wind_direction_degrees",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
