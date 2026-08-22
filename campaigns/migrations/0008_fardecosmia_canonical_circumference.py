from django.db import migrations, models
import django.core.validators


def update_legacy_default_circumference(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    Campaign.objects.filter(world_circumference_km=72_200).update(
        world_circumference_km=72_500
    )


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0007_campaign_time_simulation_constraint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="world_circumference_km",
            field=models.FloatField(
                default=72_500,
                help_text="Полная длина мира по экватору, км.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.RunPython(
            update_legacy_default_circumference,
            migrations.RunPython.noop,
        ),
    ]
