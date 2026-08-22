from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0006_time_advance_reports"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    fast_forward_spinup_turns__lte=models.F(
                        "exact_simulation_max_turns"
                    )
                ),
                name="fast_forward_spinup_not_above_exact_limit",
            ),
        ),
    ]
