from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("world", "0014_phase_c4_snapshot_versions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atmosphericsnapshot",
            name="solver_version",
            field=models.PositiveSmallIntegerField(default=7),
        ),
    ]
