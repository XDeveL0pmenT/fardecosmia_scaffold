import math

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from world.atmosphere_defaults import (
    ATMOSPHERIC_DEFAULT_HEIGHT,
    ATMOSPHERIC_DEFAULT_STEP_MINUTES,
    ATMOSPHERIC_DEFAULT_WIDTH,
    ATMOSPHERIC_FORMAT_VERSION,
    ATMOSPHERIC_SOLVER_VERSION,
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
    biome = models.CharField(
        max_length=30,
        choices=Biome.choices,
        blank=True,
        default="",
        help_text="Пустое значение означает, что биом в World Data ещё не задан.",
    )
    base_temperature = models.FloatField(default=10)
    seasonal_amplitude = models.FloatField(
        default=15,
        validators=[MinValueValidator(0)],
    )
    humidity = models.FloatField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    elevation = models.FloatField(
        null=True,
        blank=True,
        default=0,
        help_text="Высота из World Data; null означает неизвестное значение карты.",
    )
    use_manual_climate_overrides = models.BooleanField(
        default=False,
        help_text=(
            "GM явно переопределяет климатические значения карты. "
            "По умолчанию регион получает их из World Data."
        ),
    )
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
    weather_geometry_revision = models.PositiveIntegerField(
        default=0,
        editable=False,
        help_text=(
            "Ревизия контура и опорной точки, для которых рассчитывается "
            "текущая погода региона."
        ),
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

    def save(self, *args, **kwargs):
        """Advance weather provenance only when sampling geometry changes."""

        if self.pk:
            geometry_fields = {
                "map_polygon",
                "map_latitude",
                "map_longitude",
                "elevation",
            }
            update_fields = kwargs.get("update_fields")
            compared_fields = (
                geometry_fields
                if update_fields is None
                else geometry_fields.intersection(update_fields)
            )
            if compared_fields:
                previous = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values(*compared_fields, "weather_geometry_revision")
                    .first()
                )
                if previous is not None and any(
                    previous[field_name] != getattr(self, field_name)
                    for field_name in compared_fields
                ):
                    self.weather_geometry_revision = (
                        int(previous["weather_geometry_revision"]) + 1
                    )
                    if update_fields is not None:
                        kwargs["update_fields"] = set(update_fields) | {
                            "weather_geometry_revision"
                        }
        super().save(*args, **kwargs)

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
    checkpoint_interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=(
            "Интервал постоянных глобальных checkpoints. Пустое значение означает "
            "один Виток текущего календаря кампании."
        ),
    )
    checkpoint_retention_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=(
            "Максимальное число checkpoints текущей совместимой ветки. "
            "Пустое значение хранит их без ограничения; latest всегда защищён."
        ),
    )
    ocean_temperature_c = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Fallback температуры океана только для пикселей без значения на "
            "карте средней температуры. Не заменяет динамическую SST."
        ),
    )
    oxygen_fraction = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text=(
            "Необязательная доля кислорода 0..1 для будущей оценки парциального давления. "
            "Пустое значение означает, что состав атмосферы канонически неизвестен."
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
        if (
            self.checkpoint_interval_minutes is not None
            and self.step_minutes
            and self.checkpoint_interval_minutes % self.step_minutes != 0
        ):
            raise ValidationError(
                {
                    "checkpoint_interval_minutes": (
                        "Интервал checkpoint должен быть кратен атмосферному шагу."
                    )
                }
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
    solver_version = models.PositiveSmallIntegerField(default=ATMOSPHERIC_SOLVER_VERSION)
    input_fingerprint = models.CharField(max_length=64, default="", db_index=True)
    is_checkpoint = models.BooleanField(default=True)
    payload = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-world_minutes", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "world_minutes", "input_fingerprint"],
                name="unique_atmospheric_snapshot_per_campaign_time_and_input",
            )
        ]

    def __str__(self):
        return f"Атмосфера {self.campaign} @ {self.world_minutes}"


class WeatherState(models.Model):
    class Source(models.TextChoices):
        LEGACY_V2 = "legacy_v2", "Региональная weather-v2"
        ATMOSPHERIC_GRID_V1 = "atmospheric_grid_v1", "Глобальная атмосферная сетка v1"
        ATMOSPHERIC_GRID_V2 = "atmospheric_grid_v2", "Глобальная атмосферная сетка C3"
        ATMOSPHERIC_GRID_V3 = "atmospheric_grid_v3", "Глобальная атмосферная сетка C4"

    class Condition(models.TextChoices):
        CLEAR = "clear", "Ясно"
        CLOUDY = "cloudy", "Облачно"
        RAIN = "rain", "Дождь"
        STORM = "storm", "Шторм"
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
    precipitation_rate_mm_h = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Физическая интенсивность осадков C3, мм водного эквивалента в час.",
    )
    precipitation_amount_mm = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Осадки за атмосферный timestep C3, мм водного эквивалента.",
    )
    rain_fraction = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    snow_fraction = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    condition = models.CharField(max_length=20, choices=Condition.choices)
    source = models.CharField(
        max_length=30,
        choices=Source.choices,
        default=Source.LEGACY_V2,
    )
    region_weather_revision = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    sample_latitude = models.FloatField(null=True, blank=True)
    sample_longitude = models.FloatField(null=True, blank=True)
    sample_elevation_m = models.FloatField(null=True, blank=True)
    solver_version = models.PositiveSmallIntegerField(null=True, blank=True)
    atmosphere_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-world_minutes"]
        constraints = [
            models.UniqueConstraint(
                fields=["region", "world_minutes", "region_weather_revision"],
                name="unique_weather_state_per_region_time_revision",
            )
        ]
        indexes = [
            models.Index(
                fields=["region", "region_weather_revision", "-world_minutes"],
                name="world_ws_current_idx",
            )
        ]

    def __str__(self):
        return f"{self.region}: {self.temperature}°C, {self.condition}"


class RegionAreaWeatherState(models.Model):
    """Physical weather aggregated over a manually authored Region contour."""

    class SamplingMode(models.TextChoices):
        AREA = "area", "Контур области"
        POINT_FALLBACK = "point_fallback", "Точечная оценка"

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="area_weather_history",
    )
    world_minutes = models.BigIntegerField()
    region_weather_revision = models.PositiveIntegerField(db_index=True)
    sampling_mode = models.CharField(
        max_length=20,
        choices=SamplingMode.choices,
        default=SamplingMode.AREA,
    )
    grid_width = models.PositiveSmallIntegerField()
    grid_height = models.PositiveSmallIntegerField()
    covered_cell_count = models.PositiveIntegerField(default=0)
    covered_area_m2 = models.FloatField(default=0.0)

    temperature_mean_c = models.FloatField()
    temperature_min_c = models.FloatField()
    temperature_max_c = models.FloatField()
    temperature_p10_c = models.FloatField()
    temperature_p90_c = models.FloatField()
    humidity_mean_percent = models.FloatField()
    humidity_p10_percent = models.FloatField()
    humidity_p90_percent = models.FloatField()
    surface_pressure_mean_hpa = models.FloatField()
    cloud_cover_mean = models.FloatField()
    cloudy_area_fraction = models.FloatField()
    heavy_cloud_area_fraction = models.FloatField()

    precipitating_area_fraction = models.FloatField()
    rain_area_fraction = models.FloatField()
    snow_area_fraction = models.FloatField()
    area_mean_precipitation_rate_mm_h = models.FloatField()
    wet_area_mean_precipitation_rate_mm_h = models.FloatField()
    max_precipitation_rate_mm_h = models.FloatField()

    wind_mean_u_m_s = models.FloatField()
    wind_mean_v_m_s = models.FloatField()
    prevailing_wind_direction_degrees = models.FloatField(null=True, blank=True)
    wind_speed_mean_m_s = models.FloatField()
    wind_speed_p90_m_s = models.FloatField()
    wind_speed_max_m_s = models.FloatField()
    strong_wind_area_fraction = models.FloatField()

    fog_area_fraction = models.FloatField(default=0.0)
    dangerous_heat_area_fraction = models.FloatField(default=0.0)
    dangerous_cold_area_fraction = models.FloatField(default=0.0)

    source = models.CharField(
        max_length=30,
        choices=WeatherState.Source.choices,
        default=WeatherState.Source.ATMOSPHERIC_GRID_V3,
    )
    solver_version = models.PositiveSmallIntegerField(null=True, blank=True)
    atmosphere_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-world_minutes"]
        constraints = [
            models.UniqueConstraint(
                fields=["region", "world_minutes", "region_weather_revision"],
                name="unique_region_area_weather_time_revision",
            )
        ]
        indexes = [
            models.Index(
                fields=["region", "region_weather_revision", "-world_minutes"],
                name="world_raw_current_idx",
            )
        ]

    def __str__(self):
        return (
            f"{self.region}: {self.temperature_mean_c}°C area mean "
            f"at {self.world_minutes}"
        )


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
