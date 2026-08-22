import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("world", "0008_campaignworldmapoverride"),
    ]

    operations = [
        migrations.AddField(
            model_name="atmosphericconfig",
            name="checkpoint_interval_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Интервал постоянных глобальных checkpoints. Пустое значение означает "
                    "один Виток текущего календаря кампании."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="atmosphericconfig",
            name="checkpoint_retention_count",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Максимальное число checkpoints текущей совместимой ветки. "
                    "Пустое значение хранит их без ограничения; latest всегда защищён."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="atmosphericsnapshot",
            name="input_fingerprint",
            field=models.CharField(db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="atmosphericsnapshot",
            name="is_checkpoint",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="atmosphericsnapshot",
            name="solver_version",
            field=models.PositiveSmallIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.RemoveConstraint(
            model_name="atmosphericsnapshot",
            name="unique_atmospheric_snapshot_per_campaign_time",
        ),
        migrations.AddConstraint(
            model_name="atmosphericsnapshot",
            constraint=models.UniqueConstraint(
                fields=("campaign", "world_minutes", "input_fingerprint"),
                name="unique_atmospheric_snapshot_per_campaign_time_and_input",
            ),
        ),
        migrations.AlterModelOptions(
            name="atmosphericsnapshot",
            options={"ordering": ["-world_minutes", "-created_at"]},
        ),
        migrations.AlterField(
            model_name="atmosphericsnapshot",
            name="solver_version",
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
