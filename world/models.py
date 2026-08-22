import math
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from world.atmosphere_defaults import (
    ATMOSPHERIC_DEFAULT_HEIGHT,
    ATMOSPHERIC_DEFAULT_STEP_MINUTES,
    ATMOSPHERIC_DEFAULT_WIDTH,
    ATMOSPHERIC_FORMAT_VERSION,
    ATMOSPHERIC_SOLVER_VERSION,
    default_atmospheric_parameters,
)
from world.biomes import Biome as RegionBiome


class AuditLogQuerySet(models.QuerySet):
    """Keep audit history append-only through the normal ORM surface."""

    def update(self, **kwargs):
        raise ValidationError("AuditLog является неизменяемой историей.")

    def delete(self):
        raise ValidationError("AuditLog нельзя удалять через приложение.")


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    pass


class AuditLog(models.Model):
    """Durable, append-only history of meaningful authored actions."""

    class Source(models.TextChoices):
        USER = "USER", "Пользователь"
        SYSTEM = "SYSTEM", "Система"
        INTEGRATION = "INTEGRATION", "Интеграция"
        IMPORT = "IMPORT", "Импорт"

    occurred_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.USER,
    )
    action = models.CharField(max_length=120)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    campaign_id_snapshot = models.CharField(max_length=64, null=True, blank=True)
    campaign_label_snapshot = models.CharField(max_length=240, blank=True)
    world_minutes = models.BigIntegerField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    actor_label_snapshot = models.CharField(max_length=240, blank=True)
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_object_id = models.CharField(max_length=128, blank=True)
    target_label = models.CharField(max_length=500, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    summary = models.CharField(max_length=500)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    operation_id = models.UUIDField(default=uuid.uuid4, db_index=True)

    objects = AuditLogManager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["campaign", "occurred_at"],
                name="audit_campaign_time_idx",
            ),
            models.Index(
                fields=["campaign", "world_minutes"],
                name="audit_campaign_world_idx",
            ),
            models.Index(
                fields=["actor", "occurred_at"],
                name="audit_actor_time_idx",
            ),
            models.Index(fields=["action"], name="audit_action_idx"),
            models.Index(fields=["source"], name="audit_source_idx"),
            models.Index(
                fields=["target_content_type", "target_object_id"],
                name="audit_target_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("AuditLog является неизменяемой историей.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AuditLog нельзя удалять через приложение.")

    def __str__(self):
        return f"{self.action}: {self.summary}"


class ApprovalRequest(models.Model):
    """A campaign-scoped, registered intent waiting for a human decision.

    The payload is data for a whitelisted handler, never an arbitrary model
    command.  Normal lifecycle mutations belong to ``services.approvals``.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает решения"
        APPROVED = "APPROVED", "Одобрено"
        REJECTED = "REJECTED", "Отклонено"
        CANCELLED = "CANCELLED", "Отменено"
        EXPIRED = "EXPIRED", "Истекло"

    TERMINAL_STATUSES = frozenset(
        {Status.APPROVED, Status.REJECTED, Status.CANCELLED, Status.EXPIRED}
    )
    IMMUTABLE_FIELDS = (
        "campaign_id",
        "request_type",
        "requester_id",
        "requester_label_snapshot",
        "requested_world_minutes",
        "title",
        "summary",
        "target_content_type_id",
        "target_object_id",
        "target_label",
        "payload",
        "payload_version",
        "dedupe_key",
        "expires_at",
        "operation_id",
    )

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    request_type = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approval_requests",
        null=True,
        blank=True,
    )
    requester_label_snapshot = models.CharField(max_length=240)
    requested_at = models.DateTimeField(auto_now_add=True)
    requested_world_minutes = models.BigIntegerField()
    title = models.CharField(max_length=240)
    summary = models.TextField()
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_object_id = models.CharField(max_length=128, blank=True)
    target_label = models.CharField(max_length=500, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    payload = models.JSONField(default=dict)
    payload_version = models.PositiveSmallIntegerField(default=1)
    dedupe_key = models.CharField(max_length=240, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resolved_approval_requests",
        null=True,
        blank=True,
    )
    resolved_by_label_snapshot = models.CharField(max_length=240, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_world_minutes = models.BigIntegerField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)
    operation_id = models.UUIDField(default=uuid.uuid4, db_index=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(
                fields=["campaign", "status", "requested_at"],
                name="approval_campaign_status_idx",
            ),
            models.Index(
                fields=["requester", "requested_at"],
                name="approval_requester_time_idx",
            ),
            models.Index(fields=["request_type"], name="approval_type_idx"),
            models.Index(fields=["status"], name="approval_status_idx"),
            models.Index(fields=["expires_at"], name="approval_expires_idx"),
            models.Index(
                fields=["target_content_type", "target_object_id"],
                name="approval_target_idx",
            ),
        ]

    @property
    def is_effectively_expired(self):
        return bool(
            self.status == self.Status.PENDING
            and self.expires_at is not None
            and self.expires_at <= timezone.now()
        )

    @property
    def effective_status(self):
        if self.is_effectively_expired:
            return self.Status.EXPIRED
        return self.status

    @property
    def effective_status_label(self):
        return dict(self.Status.choices)[self.effective_status]

    def clean(self):
        super().clean()
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "Payload запроса должен быть JSON-объектом."})
        if not isinstance(self.result, dict):
            raise ValidationError({"result": "Result запроса должен быть JSON-объектом."})
        if bool(self.target_content_type_id) != bool(self.target_object_id):
            raise ValidationError("Тип и ID цели должны быть указаны вместе.")

        if self.status == self.Status.PENDING:
            if any(
                (
                    self.resolved_by_id,
                    self.resolved_by_label_snapshot,
                    self.resolved_at,
                    self.resolved_world_minutes is not None,
                    self.resolution_note,
                    self.result,
                )
            ):
                raise ValidationError("Ожидающий запрос не может содержать решение.")
            return

        if self.status not in self.TERMINAL_STATUSES:
            raise ValidationError({"status": "Неизвестный статус запроса."})
        if self.resolved_at is None or self.resolved_world_minutes is None:
            raise ValidationError("Завершённый запрос должен хранить время решения.")
        if self.status in {self.Status.APPROVED, self.Status.REJECTED, self.Status.CANCELLED}:
            if self.resolved_by_id is None or not self.resolved_by_label_snapshot:
                raise ValidationError("Решение должно хранить автора и его подпись.")
        if self.status != self.Status.APPROVED and self.result:
            raise ValidationError("Structured result допустим только для одобренного запроса.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self._state.adding:
            if self.status != self.Status.PENDING:
                raise ValidationError("Новый ApprovalRequest должен начинаться в PENDING.")
        else:
            previous = type(self).objects.get(pk=self.pk)
            for field_name in self.IMMUTABLE_FIELDS:
                if getattr(previous, field_name) != getattr(self, field_name):
                    raise ValidationError(
                        f"Поле {field_name} ApprovalRequest неизменяемо после создания."
                    )
            if previous.status in self.TERMINAL_STATUSES:
                changed = any(
                    getattr(previous, field.attname) != getattr(self, field.attname)
                    for field in self._meta.concrete_fields
                    if field.name != "id"
                )
                if changed:
                    raise ValidationError("Завершённый ApprovalRequest неизменяем.")
            elif previous.status == self.Status.PENDING:
                if self.status not in {self.Status.PENDING, *self.TERMINAL_STATUSES}:
                    raise ValidationError("Недопустимый переход статуса ApprovalRequest.")
            else:
                raise ValidationError("Недопустимый исходный статус ApprovalRequest.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("ApprovalRequest нельзя удалять через приложение.")

    def __str__(self):
        return self.title


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


class WorldEntry(models.Model):
    """A small encyclopedic record with explicit global/campaign scope.

    This is deliberately not a universal JSON container for future structured
    world entities.  Countries, settlements and other domains retain their own
    future models.
    """

    class Scope(models.TextChoices):
        GLOBAL = "global", "Глобальный канон"
        CAMPAIGN = "campaign", "Только кампания"

    scope = models.CharField(max_length=20, choices=Scope.choices)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="world_entries",
        null=True,
        blank=True,
    )
    kind = models.SlugField(
        max_length=80,
        help_text="Техническое пространство имён, например lore или concept.",
    )
    slug = models.SlugField(max_length=160)
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_world_entries",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="updated_world_entries",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["kind", "title", "pk"]
        permissions = [
            ("manage_global_canon", "Can manage global Fardecosmia canon"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="global", campaign__isnull=True)
                    | models.Q(scope="campaign", campaign__isnull=False)
                ),
                name="world_entry_scope_campaign_consistent",
            ),
            models.UniqueConstraint(
                fields=["kind", "slug"],
                condition=models.Q(scope="global"),
                name="unique_global_world_entry_identity",
            ),
            models.UniqueConstraint(
                fields=["campaign", "kind", "slug"],
                condition=models.Q(scope="campaign"),
                name="unique_campaign_world_entry_identity",
            ),
        ]
        indexes = [
            models.Index(fields=["scope"], name="world_entry_scope_idx"),
            models.Index(fields=["campaign", "kind"], name="world_entry_campaign_kind_idx"),
            models.Index(fields=["kind", "slug"], name="world_entry_kind_slug_idx"),
        ]

    def clean(self):
        super().clean()
        if self.scope == self.Scope.GLOBAL and self.campaign_id is not None:
            raise ValidationError({"campaign": "Глобальная запись не принадлежит кампании."})
        if self.scope == self.Scope.CAMPAIGN and self.campaign_id is None:
            raise ValidationError({"campaign": "Для campaign-записи требуется кампания."})

    def __str__(self):
        return self.title


class CampaignEntityOverride(models.Model):
    """A sparse, whitelist-validated campaign patch over global canon."""

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="entity_overrides",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey("content_type", "object_id")
    patch = models.JSONField(default=dict, blank=True)
    is_suppressed = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_campaign_entity_overrides",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="updated_campaign_entity_overrides",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=1)
    base_revision_at_creation = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["campaign_id", "content_type_id", "object_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "content_type", "object_id"],
                name="unique_campaign_entity_override",
            )
        ]
        indexes = [
            models.Index(fields=["campaign"], name="world_override_campaign_idx"),
            models.Index(
                fields=["content_type", "object_id"],
                name="world_override_target_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.patch, dict):
            raise ValidationError({"patch": "Override patch должен быть JSON-объектом."})

    def __str__(self):
        return f"{self.campaign}: {self.content_type} #{self.object_id}"


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
    """Campaign-scoped event definition/schedule.

    This is the additive evolution of the original mixed WorldEvent table.
    Historical facts belong to ``WorldEventOccurrence`` below.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        TRIGGERED = "triggered", "Произошло"
        CANCELLED = "cancelled", "Отменено"

    class TriggerType(models.TextChoices):
        MANUAL = "MANUAL", "Вручную"
        WORLD_TIME = "WORLD_TIME", "По мировому времени"

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
    event_type = models.CharField(max_length=120, default="narrative.event")
    trigger_type = models.CharField(
        max_length=30,
        choices=TriggerType.choices,
        default=TriggerType.WORLD_TIME,
    )
    trigger_config = models.JSONField(default=dict, blank=True)
    trigger_version = models.PositiveSmallIntegerField(default=1)
    trigger_at = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Игровая минута запуска для WORLD_TIME",
    )
    effect_type = models.CharField(max_length=120, null=True, blank=True)
    effect_payload = models.JSONField(default=dict, blank=True)
    effect_version = models.PositiveSmallIntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    one_shot = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    # Retained only for safe migration/legacy compatibility. P5 objective
    # visibility will be introduced later through CharacterKnowledge.
    visible_to_players = models.BooleanField(default=False)
    triggered_at = models.BigIntegerField(null=True, blank=True)
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="world_event_definitions",
    )
    target_object_id = models.CharField(max_length=128, blank=True)
    target_label = models.CharField(max_length=500, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    latitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_world_event_definitions",
        null=True,
        blank=True,
    )
    created_by_label_snapshot = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["trigger_at", "id"]
        indexes = [
            models.Index(
                fields=["campaign", "enabled", "trigger_type", "trigger_at"],
                name="event_due_lookup_idx",
            ),
            models.Index(
                fields=["campaign", "event_type"],
                name="event_campaign_type_idx",
            ),
        ]

    @property
    def scheduled_world_minutes(self):
        return self.trigger_at

    def clean(self):
        super().clean()
        if not isinstance(self.trigger_config, dict):
            raise ValidationError({"trigger_config": "Trigger config должен быть JSON-объектом."})
        if not isinstance(self.effect_payload, dict):
            raise ValidationError({"effect_payload": "Effect payload должен быть JSON-объектом."})
        if bool(self.target_content_type_id) != bool(self.target_object_id):
            raise ValidationError("Тип и ID цели должны быть указаны вместе.")
        if self.trigger_type == self.TriggerType.WORLD_TIME:
            if self.trigger_at is None:
                raise ValidationError({"trigger_at": "Укажите мировое время события."})
        elif self.trigger_at is not None:
            raise ValidationError({"trigger_at": "Ручное событие не имеет будущего времени."})
        if bool(self.effect_type) != (self.effect_version is not None):
            raise ValidationError("Тип и версия effect должны быть указаны вместе.")

    def __str__(self):
        return self.title


class WorldEventOccurrenceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Факт мирового события неизменяем.")

    def delete(self):
        raise ValidationError("Историю мировых событий нельзя удалять.")


class WorldEventOccurrenceManager(
    models.Manager.from_queryset(WorldEventOccurrenceQuerySet)
):
    def _create_from_validated_event_service(self, **values):
        """Insert a service-validated fact without per-row relational probes.

        The P5 event service validates the complete snapshot and runs inside
        the same transaction as the effect/audits. The database still enforces
        the one-occurrence constraint. Normal ORM ``create`` continues through
        ``save()`` and full model validation.
        """

        occurrence = self.model(**values)
        models.Model.save(occurrence, force_insert=True, using=self.db)
        return occurrence


class WorldEventOccurrence(models.Model):
    """Immutable objective fact that an event happened in a Campaign."""

    class Source(models.TextChoices):
        USER = "USER", "Game Master"
        SYSTEM = "SYSTEM", "Система"

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="world_event_occurrences",
    )
    definition = models.ForeignKey(
        WorldEvent,
        on_delete=models.SET_NULL,
        related_name="occurrences",
        null=True,
        blank=True,
    )
    definition_revision = models.PositiveIntegerField(default=1)
    event_type_snapshot = models.CharField(max_length=120)
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    occurred_world_minutes = models.BigIntegerField()
    scheduled_world_minutes = models.BigIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="world_event_occurrences",
        null=True,
        blank=True,
    )
    actor_label_snapshot = models.CharField(max_length=240, blank=True)
    trigger_type_snapshot = models.CharField(max_length=30)
    trigger_snapshot = models.JSONField(default=dict, blank=True)
    trigger_version_snapshot = models.PositiveSmallIntegerField(default=1)
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="world_event_occurrences",
    )
    target_object_id = models.CharField(max_length=128, blank=True)
    target_label = models.CharField(max_length=500, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        related_name="event_occurrences",
        null=True,
        blank=True,
    )
    region_label_snapshot = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    effect_type_snapshot = models.CharField(max_length=120, null=True, blank=True)
    effect_version_snapshot = models.PositiveSmallIntegerField(null=True, blank=True)
    effect_result = models.JSONField(default=dict, blank=True)
    operation_id = models.UUIDField(default=uuid.uuid4, db_index=True)

    objects = WorldEventOccurrenceManager()

    class Meta:
        ordering = ["-occurred_world_minutes", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition"],
                condition=models.Q(definition__isnull=False),
                name="unique_world_event_occurrence",
            )
        ]
        indexes = [
            models.Index(
                fields=["campaign", "occurred_world_minutes"],
                name="event_occ_campaign_time_idx",
            ),
            models.Index(
                fields=["campaign", "event_type_snapshot"],
                name="event_occ_campaign_type_idx",
            ),
            models.Index(
                fields=["region", "occurred_world_minutes"],
                name="event_occ_region_time_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.trigger_snapshot, dict):
            raise ValidationError({"trigger_snapshot": "Trigger snapshot должен быть JSON-объектом."})
        if not isinstance(self.effect_result, dict):
            raise ValidationError({"effect_result": "Effect result должен быть JSON-объектом."})
        if self.source == self.Source.USER and self.actor_id is None:
            raise ValidationError("Ручное событие должно хранить автора.")
        if self.source == self.Source.SYSTEM and self.actor_id is not None:
            raise ValidationError("Системное событие не должно иметь fake actor.")
        if bool(self.target_content_type_id) != bool(self.target_object_id):
            raise ValidationError("Тип и ID цели должны быть указаны вместе.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Факт мирового события неизменяем.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Историю мировых событий нельзя удалять.")

    def __str__(self):
        return self.title
