import uuid

from django.conf import settings
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
        ]

    @property
    def calendar_minutes_per_turn(self):
        return self.calendar_hours_per_turn * self.calendar_minutes_per_hour

    @property
    def calendar_minutes_per_phase(self):
        return self.calendar_minutes_per_turn // 7

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
