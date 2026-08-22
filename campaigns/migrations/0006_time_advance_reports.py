import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0005_campaign_dark_season_max_red_turns_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="exact_simulation_max_turns",
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text=(
                    "Технический порог: продвижение не длиннее этого числа Витков "
                    "симулируется полностью. Это настройка производительности, не канон."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="fast_forward_spinup_turns",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text=(
                    "Число финальных Витков подробной симуляции после fast-forward. "
                    "Промежуточная погода до spin-up не придумывается."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.CreateModel(
            name="TimeAdvanceReport",
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
                ("start_world_minutes", models.BigIntegerField()),
                ("end_world_minutes", models.BigIntegerField()),
                (
                    "requested_amount",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                (
                    "requested_unit",
                    models.CharField(
                        choices=[
                            ("minutes", "Минуты"),
                            ("hours", "Часы"),
                            ("phases", "Фазы Витка"),
                            ("turns", "Витки"),
                            ("seasons", "Сезоны"),
                            ("years", "Годы"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "simulation_mode",
                    models.CharField(
                        choices=[
                            ("exact", "Точная симуляция"),
                            ("fast_forward", "Быстрая прокрутка"),
                        ],
                        max_length=20,
                    ),
                ),
                ("coverage", models.JSONField(default=list)),
                ("summary", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_advance_reports",
                        to="campaigns.campaign",
                    ),
                ),
                (
                    "gm",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="time_advance_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-pk"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("end_world_minutes__gt", models.F("start_world_minutes"))
                        ),
                        name="time_advance_report_end_after_start",
                    )
                ],
            },
        ),
    ]
