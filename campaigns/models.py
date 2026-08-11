import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def default_season_weather_modifiers():
    """Technical defaults; GM can replace them when canon becomes more exact."""
    return {
        "summer": {"humidity": -5, "precipitation": -0.06},
        "autumn": {"humidity": 9, "precipitation": 0.12},
        "winter": {"humidity": 5, "precipitation": 0.18},
        "spring": {"humidity": 11, "precipitation": 0.14},
    }


class Campaign(models.Model):
    class LightDirection(models.IntegerChoices):
        EASTWARD = 1, "К востоку"
        WESTWARD = -1, "К западу"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    world_minutes = models.BigIntegerField(default=0)
    exact_simulation_max_turns = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1)],
        help_text=(
            "Технический порог: продвижение не длиннее этого числа Витков "
            "симулируется полностью. Это настройка производительности, не канон."
        ),
    )
    fast_forward_spinup_turns = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text=(
            "Число финальных Витков подробной симуляции после fast-forward. "
            "Промежуточная погода до spin-up не придумывается."
        ),
    )
    calendar_epoch_year = models.IntegerField(
        default=0,
        help_text="Год, соответствующий нулевой игровой минуте.",
    )
    calendar_hours_per_turn = models.PositiveSmallIntegerField(
        default=168,
        validators=[MinValueValidator(1)],
        help_text="Каноническая длительность одного Витка — дня мира, в часах.",
    )
    calendar_minutes_per_hour = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(1)],
        help_text="Техническое деление часа на игровые минуты.",
    )
    red_turn_visibility_threshold = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text=(
            "Технический порог видимости Ympha (0–1), после которого Виток "
            "считается Красным."
        ),
    )
    light_season_min_red_turns = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(13)],
        help_text=(
            "Минимальное число Красных Витков из 13, при котором локальный сезон "
            "называется Светлым. Технический порог настраивается GM."
        ),
    )
    dark_season_max_red_turns = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(12)],
        help_text=(
            "Максимальное число Красных Витков из 13, при котором локальный сезон "
            "называется Тёмным. Между порогами сезон считается Смешанным."
        ),
    )
    season_weather_modifiers = models.JSONField(
        default=default_season_weather_modifiers,
        help_text=(
            "Настраиваемые технические поправки влажности и вероятности осадков "
            "для summer/autumn/winter/spring; это не неизменный канон."
        ),
    )
    world_circumference_km = models.FloatField(
        default=72_200,
        validators=[MinValueValidator(1)],
        help_text="Полная длина мира по экватору, км.",
    )
    star_reference_longitude = models.FloatField(
        default=0,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        help_text=(
            "Долгота нулевого меридиана светового цикла Звезды. "
            "Начальное значение техническое и настраивается GM."
        ),
    )
    star_motion_direction = models.SmallIntegerField(
        choices=LightDirection.choices,
        default=LightDirection.EASTWARD,
        help_text="Направление обхода света Звезды по карте.",
    )
    ympha_peak_longitude_at_epoch = models.FloatField(
        default=0,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        help_text=(
            "Долгота максимальной ночной видимости Ympha в нулевую минуту. "
            "Начальное значение техническое и настраивается GM."
        ),
    )
    ympha_motion_direction = models.SmallIntegerField(
        choices=LightDirection.choices,
        default=LightDirection.EASTWARD,
        help_text="Направление обхода света Ympha по карте.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    dark_season_max_red_turns__lt=models.F(
                        "light_season_min_red_turns",
                    ),
                ),
                name="dark_season_threshold_below_light",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    fast_forward_spinup_turns__lte=models.F(
                        "exact_simulation_max_turns"
                    ),
                ),
                name="fast_forward_spinup_not_above_exact_limit",
            ),
        ]

    def clean(self):
        super().clean()
        if self.fast_forward_spinup_turns > self.exact_simulation_max_turns:
            raise ValidationError(
                {
                    "fast_forward_spinup_turns": (
                        "Финальный spin-up не должен быть длиннее exact-порога."
                    )
                }
            )

    @property
    def calendar_minutes_per_turn(self):
        return self.calendar_hours_per_turn * self.calendar_minutes_per_hour

    @property
    def calendar_minutes_per_phase(self):
        return self.calendar_minutes_per_turn // 7

    @property
    def light_season_min_red_fraction(self):
        """C1 proportional meaning of the backward-compatible 8/13 field."""
        return self.light_season_min_red_turns / 13.0

    @property
    def dark_season_max_red_fraction(self):
        """C1 proportional meaning of the backward-compatible 5/13 field."""
        return self.dark_season_max_red_turns / 13.0

    def __str__(self):
        return self.name


class CampaignMembership(models.Model):
    class Role(models.TextChoices):
        PLAYER = "player", "Игрок"
        GM = "gm", "Мастер"

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaign_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PLAYER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "user"],
                name="unique_campaign_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.campaign} ({self.role})"


class TimeAdvanceReport(models.Model):
    class SimulationMode(models.TextChoices):
        EXACT = "exact", "Точная симуляция"
        FAST_FORWARD = "fast_forward", "Быстрая прокрутка"

    class RequestedUnit(models.TextChoices):
        MINUTES = "minutes", "Минуты"
        HOURS = "hours", "Часы"
        PHASES = "phases", "Фазы Витка"
        TURNS = "turns", "Витки"
        SEASONS = "seasons", "Сезоны"
        YEARS = "years", "Годы"

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="time_advance_reports",
    )
    gm = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="time_advance_reports",
    )
    start_world_minutes = models.BigIntegerField()
    end_world_minutes = models.BigIntegerField()
    requested_amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    requested_unit = models.CharField(max_length=20, choices=RequestedUnit.choices)
    simulation_mode = models.CharField(max_length=20, choices=SimulationMode.choices)
    coverage = models.JSONField(default=list)
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_world_minutes__gt=models.F("start_world_minutes")),
                name="time_advance_report_end_after_start",
            )
        ]

    def __str__(self):
        return (
            f"{self.campaign}: {self.start_world_minutes}–{self.end_world_minutes} "
            f"({self.get_simulation_mode_display()})"
        )
