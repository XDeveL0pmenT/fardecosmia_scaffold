from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("world", "0013_region_climate_autoconfiguration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atmosphericsnapshot",
            name="format_version",
            field=models.PositiveSmallIntegerField(default=4),
        ),
        migrations.AlterField(
            model_name="atmosphericsnapshot",
            name="solver_version",
            field=models.PositiveSmallIntegerField(default=6),
        ),
        migrations.AlterField(
            model_name="weatherstate",
            name="source",
            field=models.CharField(
                choices=[
                    ("legacy_v2", "Региональная weather-v2"),
                    ("atmospheric_grid_v1", "Глобальная атмосферная сетка v1"),
                    ("atmospheric_grid_v2", "Глобальная атмосферная сетка C3"),
                    ("atmospheric_grid_v3", "Глобальная атмосферная сетка C4"),
                ],
                default="legacy_v2",
                max_length=30,
            ),
        ),
    ]
