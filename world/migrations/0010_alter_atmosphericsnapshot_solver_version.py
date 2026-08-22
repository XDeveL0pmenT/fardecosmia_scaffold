from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("world", "0009_atmospheric_checkpointing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atmosphericsnapshot",
            name="solver_version",
            field=models.PositiveSmallIntegerField(default=3),
        ),
    ]

