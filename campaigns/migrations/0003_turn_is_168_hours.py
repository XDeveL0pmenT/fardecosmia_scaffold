import django.core.validators
from django.db import migrations, models


def convert_day_hours_to_turn_hours(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    for campaign in Campaign.objects.all().iterator():
        campaign.calendar_hours_per_turn *= 7
        campaign.save(update_fields=["calendar_hours_per_turn"])


def convert_turn_hours_to_day_hours(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    for campaign in Campaign.objects.all().iterator():
        campaign.calendar_hours_per_turn //= 7
        campaign.save(update_fields=["calendar_hours_per_turn"])


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0002_campaign_calendar_epoch_year_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="campaign",
            old_name="calendar_hours_per_day",
            new_name="calendar_hours_per_turn",
        ),
        migrations.RunPython(
            convert_day_hours_to_turn_hours,
            convert_turn_hours_to_day_hours,
        ),
        migrations.AlterField(
            model_name="campaign",
            name="calendar_hours_per_turn",
            field=models.PositiveSmallIntegerField(
                default=168,
                help_text="Каноническая длительность одного Витка — дня мира, в часах.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
