"""Safe, explicit serializers and the only supported AuditLog write API."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import re
import uuid

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from world.models import AuditLog


MAX_AUDIT_COMPONENT_BYTES = 128 * 1024
MAX_AUDIT_SUMMARY_CHARS = 500
MAX_AUDIT_TARGET_LABEL_CHARS = 500

_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "authorization",
    "cookie",
    "csrf",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "oauth",
    "secret",
    "credential",
    "client_secret",
    "sessionid",
    "session_id",
)


def _actor_label(actor):
    if actor is None:
        return "Система"
    return str(getattr(actor, "display_name", "") or getattr(actor, "username", "") or actor)


def _assert_no_secret_keys(value, *, path="payload"):
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
                raise ValidationError(
                    f"Audit payload отклонён: технический секрет в ключе {path}.{key}."
                )
            _assert_no_secret_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_secret_keys(nested, path=f"{path}[{index}]")


def _validate_json_component(
    value,
    *,
    name,
    allow_none=True,
    max_bytes=MAX_AUDIT_COMPONENT_BYTES,
):
    if value is None and allow_none:
        return None
    if not isinstance(value, Mapping):
        raise ValidationError(f"{name} должен быть JSON-объектом.")
    _assert_no_secret_keys(value, path=name)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{name} содержит недопустимое JSON-значение.") from error
    if len(encoded) > max_bytes:
        raise ValidationError(
            f"{name} превышает безопасный лимит {max_bytes} байт."
        )
    # A JSON round-trip also guarantees the ORM receives plain, stable values.
    return json.loads(encoded.decode("utf-8"))


def validate_safe_json_object(value, *, name, max_bytes):
    """Validate a bounded, secret-safe JSON object for another domain service."""

    return _validate_json_component(
        value,
        name=name,
        allow_none=False,
        max_bytes=max_bytes,
    )


def record_audit(
    *,
    action,
    summary,
    source=AuditLog.Source.USER,
    actor=None,
    campaign=None,
    world_minutes=None,
    target=None,
    target_label=None,
    before_state=None,
    after_state=None,
    metadata=None,
    operation_id=None,
):
    """Record one meaningful action inside the caller's transaction.

    This function intentionally does not open a new transaction. A serializer
    or database failure must roll back the business mutation that called it.
    """

    if not isinstance(action, str) or not _ACTION_PATTERN.fullmatch(action):
        raise ValidationError("Audit action должен быть стабильным namespaced identifier.")
    if source not in AuditLog.Source.values:
        raise ValidationError("Неизвестный AuditLog source.")
    if source == AuditLog.Source.USER and actor is None:
        raise ValidationError("Для USER audit требуется actor.")
    if not isinstance(summary, str) or not summary.strip():
        raise ValidationError("Audit summary не может быть пустым.")
    summary = summary.strip()
    if len(summary) > MAX_AUDIT_SUMMARY_CHARS:
        raise ValidationError("Audit summary превышает безопасный лимит.")

    if campaign is None:
        if world_minutes is not None:
            raise ValidationError("Глобальный audit не может иметь мировое время кампании.")
        campaign_id_snapshot = None
        campaign_label_snapshot = ""
        resolved_world_minutes = None
    else:
        campaign_id_snapshot = str(campaign.pk)
        campaign_label_snapshot = str(campaign)
        resolved_world_minutes = (
            int(campaign.world_minutes) if world_minutes is None else int(world_minutes)
        )

    target_content_type = None
    target_object_id = ""
    if target is not None:
        if target.pk is None:
            raise ValidationError("Audit target должен иметь сохранённый идентификатор.")
        target_content_type = ContentType.objects.get_for_model(
            target,
            for_concrete_model=False,
        )
        target_object_id = str(target.pk)
        if target_label is None:
            target_label = str(target)
    target_label = "" if target_label is None else str(target_label)
    if len(target_label) > MAX_AUDIT_TARGET_LABEL_CHARS:
        raise ValidationError("Audit target label превышает безопасный лимит.")

    before_state = _validate_json_component(
        before_state,
        name="before_state",
    )
    after_state = _validate_json_component(
        after_state,
        name="after_state",
    )
    metadata = _validate_json_component(
        {} if metadata is None else metadata,
        name="metadata",
        allow_none=False,
    )
    if operation_id is not None:
        try:
            operation_id = uuid.UUID(str(operation_id))
        except (TypeError, ValueError) as error:
            raise ValidationError("operation_id должен быть UUID.") from error

    return AuditLog.objects.create(
        source=source,
        action=action,
        campaign=campaign,
        campaign_id_snapshot=campaign_id_snapshot,
        campaign_label_snapshot=campaign_label_snapshot,
        world_minutes=resolved_world_minutes,
        actor=actor,
        actor_label_snapshot=_actor_label(actor),
        target_content_type=target_content_type,
        target_object_id=target_object_id,
        target_label=target_label,
        summary=summary,
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
        **({"operation_id": operation_id} if operation_id is not None else {}),
    )


def serialize_region(region):
    return {
        "name": region.name,
        "map_latitude": region.map_latitude,
        "map_longitude": region.map_longitude,
        "map_polygon": region.map_polygon,
        "weather_geometry_revision": region.weather_geometry_revision,
        "biome": region.biome,
        "base_temperature": region.base_temperature,
        "humidity": region.humidity,
        "elevation": region.elevation,
        "use_manual_climate_overrides": region.use_manual_climate_overrides,
    }


def serialize_world_entry(entry):
    return {
        "scope": entry.scope,
        "campaign_id": None if entry.campaign_id is None else str(entry.campaign_id),
        "kind": entry.kind,
        "slug": entry.slug,
        "title": entry.title,
        "summary": entry.summary,
        "body": entry.body,
        "revision": entry.revision,
    }


def serialize_campaign_override(override):
    target = override.target
    return {
        "campaign_id": str(override.campaign_id),
        "target_type": (
            f"{override.content_type.app_label}.{override.content_type.model}"
        ),
        "target_id": override.object_id,
        "target_label": "" if target is None else str(target),
        "patch": override.patch,
        "is_suppressed": override.is_suppressed,
        "revision": override.revision,
        "base_revision_at_creation": override.base_revision_at_creation,
    }


def serialize_atmospheric_config(config):
    return {
        "enabled": config.enabled,
        "grid_width": config.grid_width,
        "grid_height": config.grid_height,
        "step_minutes": config.step_minutes,
        "world_seed": config.world_seed,
        "checkpoint_interval_minutes": config.checkpoint_interval_minutes,
        "checkpoint_retention_count": config.checkpoint_retention_count,
        "ocean_temperature_c": config.ocean_temperature_c,
        "oxygen_fraction": config.oxygen_fraction,
    }


def serialize_time_simulation_settings(campaign):
    return {
        "exact_simulation_max_turns": campaign.exact_simulation_max_turns,
        "fast_forward_spinup_turns": campaign.fast_forward_spinup_turns,
    }


def _cells_digest(cells):
    payload = json.dumps(
        cells or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compact_biome_change(*, scope, before_cells, after_cells, width, height):
    """Return compact states and metadata without copying a whole biome layer."""

    before_cells = before_cells or {}
    after_cells = after_cells or {}
    keys = set(before_cells) | set(after_cells)
    changed = sorted(
        (int(key) for key in keys if before_cells.get(str(key)) != after_cells.get(str(key))),
    )
    old_counts = Counter(
        before_cells.get(str(index), "__inherited__") for index in changed
    )
    new_counts = Counter(
        after_cells.get(str(index), "__inherited__") for index in changed
    )
    bbox = None
    if changed:
        rows = [index // width for index in changed]
        columns = [index % width for index in changed]
        bbox = {
            "longitude_min": round(-180.0 + min(columns) * 360.0 / width, 6),
            "longitude_max": round(-180.0 + (max(columns) + 1) * 360.0 / width, 6),
            "latitude_min": round(90.0 - (max(rows) + 1) * 180.0 / height, 6),
            "latitude_max": round(90.0 - min(rows) * 180.0 / height, 6),
        }
    before_digest = _cells_digest(before_cells)
    after_digest = _cells_digest(after_cells)
    return {
        "before_state": {
            "scope": scope,
            "authored_cell_count": len(before_cells),
            "digest": before_digest,
        },
        "after_state": {
            "scope": scope,
            "authored_cell_count": len(after_cells),
            "digest": after_digest,
        },
        "metadata": {
            "changed_cell_count": len(changed),
            "affected_bbox": bbox,
            "old_biome_counts": dict(sorted(old_counts.items())),
            "new_biome_counts": dict(sorted(new_counts.items())),
            "grid_width": int(width),
            "grid_height": int(height),
        },
    }


def changed_fields(before_state, after_state):
    return sorted(
        key
        for key in set(before_state) | set(after_state)
        if before_state.get(key) != after_state.get(key)
    )
