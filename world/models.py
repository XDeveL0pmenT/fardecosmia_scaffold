import math

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from world.atmosphere_defaults import (
    ATMOSPHERIC_DEFAULT_HEIGHT,
    ATMOSPHERIC_DEFAULT_STEP_MINUTES,
    ATMOSPHERIC_DEFAULT_WIDTH,
    ATMOSPHERIC_FORMAT_VERSION,
    default_atmospheric_parameters,
)
from world.biomes import Biome as RegionBiome


class Region(models.Model):
    # Preserve the established Region.Biome public API while keeping the
    # canonical catalogue in one reusable module.
    Biome = RegionBiome

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="regions",
    )
    name = models.CharField(max_length=200)
    biome = models.CharField(max_length=30, choices=Biome.choices)
    base_temperature = models.FloatField(default=10)
    seasonal_amplitude = models.FloatField(
        default=15,
        validators=[MinValueValidator(0)],
    )
    humidity = models.FloatField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    elevation = models.FloatField(default=0)
    weather_volatility = models.FloatField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
    )
    light_cycle_temperature_amplitude = models.FloatField(
        default=6,
        validators=[MinValueValidator(0)],
        help_text="Настраиваемая сила влияния длинного светового цикла, °C.",
    )
    ympha_temperature_influence = models.FloatField(
        default=3,
        help_text="Настраиваемое влияние видимой Ympha ночью, °C.",
    )
    season_light_temperature_influence = models.FloatField(
        default=5,
        validators=[MinValueValidator(0)],
        help_text=(
            "Сила влияния Светлого или Тёмного сезона на температуру, °C. "
            "Значение остаётся настройкой региона, пока канон не задаёт точную величину."
        ),
    )
    elevation_temperature_per_1000m = models.FloatField(
        default=-6.5,
        help_text="Настраиваемая поправка температуры на 1000 единиц высоты, °C.",
    )
    weather_update_interval_minutes = models.PositiveIntegerField(
        default=360,
        validators=[MinValueValidator(1)],
        help_text="Минимальный интервал между новыми состояниями погоды.",
    )
    weather_persistence = models.FloatField(
        default=0.72,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Инерция погоды: 0 — быстрая смена, 1 — максимальная устойчивость.",
    )
    precipitation_bias = models.FloatField(
        default=0,
        validators=[MinValueValidator(-1), MaxValueValidator(1)],
        help_text=(
            "Локальная поправка к вероятности осадков: отрицательная для сухих "
            "земель, положительная для влажных."
        ),
    )
    map_longitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        help_text="Центр региона по долготе на мировой карте.",
    )
    map_latitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        help_text="Центр региона по широте на мировой карте.",
    )
    map_polygon = models.JSONField(
        default=list,
        blank=True,
        help_text="Контур региона как нормализованные точки карты [[x, y], ...].",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "name"],
                name="unique_region_name_per_campaign",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        from world.services.map_geometry import validate_map_polygon

        validate_map_polygon(self.map_polygon, require_polygon=False)


class WorldMapLayer(models.Model):
    """Legacy campaign layer kept so earlier drawings remain recoverable."""

    campaign = models.OneToOneField(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="world_map_layer",
    )
    grid_width = models.PositiveSmallIntegerField(default=180, editable=False)
    grid_height = models.PositiveSmallIntegerField(default=90, editable=False)
    biome_cells = models.JSONField(
        default=dict,
        blank=True,
        help_text="Разреженная сетка биомов: индекс ячейки -> код биома.",
    )
    elevation_cells = models.JSONField(
        default=dict,
        blank=True,
        help_text="Разреженная сетка высот: индекс ячейки -> высота.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Слои карты: {self.campaign}"


class GlobalWorldMapLayer(models.Model):
    """Shared objective cartographic layer for the planet, independent of campaigns."""

    FARDECOSMIA_SLUG = "fardecosmia"

    slug = models.SlugField(max_length=50, unique=True, default=FARDECOSMIA_SLUG)
    grid_width = models.PositiveSmallIntegerField(default=360, editable=False)
    grid_height = models.PositiveSmallIntegerField(default=180, editable=False)
    biome_cells = models.JSONField(
        default=dict,
        blank=True,
        help_text="Разреженная общая сетка биомов: индекс ячейки -> код биома.",
    )
    elevation_cells = models.JSONField(
        default=dict,
        blank=True,
        help_text="Необязательные GM-поправки к растровой карте высот.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "общий слой карты мира"
        verbose_name_plural = "общие слои карты мира"

    def __str__(self):
        return "Общий атлас Фардекосмии"


class CampaignWorldMapOverride(models.Model):
    """Sparse campaign-only biome changes layered over the objective atlas.

    An absent cell means "inherit the global atlas".  Keeping this separate
    from ``GlobalWorldMapLayer`` prevents a GM experiment in one campaign from
    silently rewriting the shared objective map.
    """

    campaign = models.OneToOneField(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="world_map_override",
    )
    grid_width = models.PositiveSmallIntegerField(default=360, editable=False)
    grid_height = models.PositiveSmallIntegerField(default=180, editable=False)
    biome_cells = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Разреженные замены биомов только для этой кампании: "
            "индекс ячейки -> код биома. Отсутствующая ячейка наследует общий атлас."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "локальные замены биомов кампании"
        verbose_name_plural = "локальные замены биомов кампаний"

    def __str__(self):
        return f"Локальные биомы: {self.campaign}"


class AtmosphericConfig(models.Model):
    """Opt-in technical configuration for a campaign's global atmosphere."""

    campaign = models.OneToOneField(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="atmospheric_config",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Пока выключено, кампания продолжает использовать weather-v2.",
    )
    grid_width = models.PositiveSmallIntegerField(
        default=ATMOSPHERIC_DEFAULT_WIDTH,
        validators=[MinValueValidator(4), MaxValueValidator(720)],
    )
    grid_height = models.PositiveSmallIntegerField(
        default=ATMOSPHERIC_DEFAULT_HEIGHT,
        validators=[MinValueValidator(2), MaxValueValidator(360)],
    )
    step_minutes = models.PositiveIntegerField(
        default=ATMOSPHERIC_DEFAULT_STEP_MINUTES,
        validators=[MinValueValidator(1)],
    )
    world_seed = models.BigIntegerField(default=0)
    ocean_temperature_c = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Настраиваемая температура горячего океана. Точное каноническое "
            "значение пока неизвестно, поэтому автоматического default нет."
        ),
    )
    parameters = models.JSONField(
        default=default_atmospheric_parameters,
        help_text="Численные коэффициенты прототипа; все значения настраиваемы и не являются каноном.",
    )

    def __str__(self):
        return f"Атмосфера: {self.campaign}"

    def clean(self):
        super().clean()
        if self.enabled and self.ocean_temperature_c is None:
            raise ValidationError(
                {"ocean_temperature_c": "Задайте температуру океана перед включением сетки."}
            )
        if not isinstance(self.parameters, dict):
            raise ValidationError({"parameters": "Параметры должны быть JSON-объектом."})
        invalid = [
            key
            for key, value in self.parameters.items()
            if isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ]
        if invalid:
            raise ValidationError(
                {"parameters": f"Параметры должны быть конечными числами: {', '.join(invalid)}."}
            )


class AtmosphericSnapshot(models.Model):
    """One compressed global grid snapshot, never one database row per cell."""

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="atmospheric_snapshots",
    )
    world_minutes = models.BigIntegerField()
    grid_width = models.PositiveSmallIntegerField()
    grid_height = models.PositiveSmallIntegerField()
    format_version = models.PositiveSmallIntegerField(default=ATMOSPHERIC_FORMAT_VERSION)
    payload = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-world_minutes"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "world_minutes"],
                name="unique_atmospheric_snapshot_per_campaign_time",
            )
        ]

    def __str__(self):
        return f"Атмосфера {self.campaign} @ {self.world_minutes}"


class WeatherState(models.Model):
    class Source(models.TextChoices):
        LEGACY_V2 = "legacy_v2", "Региональная weather-v2"
        ATMOSPHERIC_GRID_V1 = "atmospheric_grid_v1", "Глобальная атмосферная сетка v1"

    class Condition(models.TextChoices):
        CLEAR = "clear", "Ясно"
        CLOUDY = "cloudy", "Облачно"
        RAIN = "rain", "Дождь"
        STORM = "storm", "Гроза"
        SNOW = "snow", "Снег"
        FOG = "fog", "Туман"

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="weather_history",
    )
    world_minutes = models.BigIntegerField()
    temperature = models.FloatField()
    humidity = models.FloatField()
    wind_speed = models.FloatField(default=0)
    wind_direction_degrees = models.FloatField(null=True, blank=True)
    pressure_hpa = models.FloatField(null=True, blank=True)
    cloud_cover = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    precipitation = models.FloatField(default=0)
    condition = models.CharField(max_length=20, choices=Condition.choices)
    source = models.CharField(
        max_length=30,
        choices=Source.choices,
        default=Source.LEGACY_V2,
    )

    class Meta:
        ordering = ["-world_minutes"]
        constraints = [
            models.UniqueConstraint(
                fields=["region", "world_minutes"],
                name="unique_weather_state_per_region_time",
            )
        ]

    def __str__(self):
        return f"{self.region}: {self.temperature}°C, {self.condition}"


class WorldEvent(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        TRIGGERED = "triggered", "Произошло"
        CANCELLED = "cancelled", "Отменено"

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="events",
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_at = models.BigIntegerField(help_text="Игровая минута запуска")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    visible_to_players = models.BooleanField(default=False)
    triggered_at = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["trigger_at"]

    def __str__(self):
        return self.title
