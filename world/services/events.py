"""Registered, campaign-scoped WorldEvent definition and occurrence services."""

from __future__ import annotations

from dataclasses import dataclass
import re
import uuid

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from world.models import AuditLog, WorldEvent, WorldEventOccurrence
from world.services.access import can_manage_campaign
from world.services.audit import record_audit, validate_safe_json_object


MAX_EVENT_COMPONENT_BYTES = 64 * 1024
NARRATIVE_EVENT_TYPE = "narrative.event"
_NAMESPACED_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class WorldEventError(Exception):
    pass


class WorldEventConflict(WorldEventError):
    pass


class UnknownWorldEventHandler(WorldEventError):
    pass


@dataclass(frozen=True)
class WorldEventTriggerHandler:
    trigger_type: str
    version: int
    validator: object
    presenter: object


@dataclass(frozen=True)
class WorldEventEffectHandler:
    effect_type: str
    version: int
    validator: object
    presenter: object
    apply: object


_TRIGGER_HANDLERS = {}
_EFFECT_HANDLERS = {}


def _actor_label(actor):
    if actor is None:
        return ""
    return str(getattr(actor, "display_name", "") or getattr(actor, "username", "") or actor)


def _validate_namespaced(value, *, label):
    if not isinstance(value, str) or not _NAMESPACED_PATTERN.fullmatch(value):
        raise ValidationError(f"{label} должен быть namespaced identifier.")
    return value


def _validate_empty_trigger_config(config):
    config = validate_safe_json_object(
        config,
        name="trigger_config",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )
    if config:
        raise ValidationError("Этот trigger не принимает дополнительные параметры.")
    return {}


def register_world_event_trigger(trigger_type, *, version, validator, presenter):
    if trigger_type not in WorldEvent.TriggerType.values:
        raise ValidationError("Неизвестный базовый тип trigger.")
    if not isinstance(version, int) or version < 1:
        raise ValidationError("Версия trigger должна быть положительным числом.")
    if not all(callable(item) for item in (validator, presenter)):
        raise ValidationError("Trigger handler должен иметь validator и presenter.")
    key = (trigger_type, version)
    if key in _TRIGGER_HANDLERS:
        raise ValidationError("Trigger handler уже зарегистрирован.")
    _TRIGGER_HANDLERS[key] = WorldEventTriggerHandler(
        trigger_type=trigger_type,
        version=version,
        validator=validator,
        presenter=presenter,
    )


def get_world_event_trigger(trigger_type, version):
    try:
        return _TRIGGER_HANDLERS[(trigger_type, version)]
    except KeyError as error:
        raise UnknownWorldEventHandler(
            "Версия условия события больше не поддерживается; событие не выполнено."
        ) from error


def register_world_event_effect(
    effect_type,
    *,
    version=1,
    validator,
    presenter,
    apply,
):
    _validate_namespaced(effect_type, label="Effect type")
    if not isinstance(version, int) or version < 1:
        raise ValidationError("Версия effect должна быть положительным числом.")
    if not all(callable(item) for item in (validator, presenter, apply)):
        raise ValidationError("Effect handler должен иметь validator, presenter и apply.")
    key = (effect_type, version)
    if key in _EFFECT_HANDLERS:
        raise ValidationError("Effect handler уже зарегистрирован.")
    _EFFECT_HANDLERS[key] = WorldEventEffectHandler(
        effect_type=effect_type,
        version=version,
        validator=validator,
        presenter=presenter,
        apply=apply,
    )


def unregister_world_event_effect(effect_type, *, version=1):
    _EFFECT_HANDLERS.pop((effect_type, version), None)


def get_world_event_effect(effect_type, version):
    try:
        return _EFFECT_HANDLERS[(effect_type, version)]
    except KeyError as error:
        raise UnknownWorldEventHandler(
            "Последствие события не зарегистрировано; событие не выполнено."
        ) from error


def world_event_type_label(event_type):
    if event_type == NARRATIVE_EVENT_TYPE:
        return "Сюжетное событие"
    return event_type.replace("_", " ").replace(".", " · ")


def trigger_presentation(definition):
    try:
        handler = get_world_event_trigger(
            definition.trigger_type,
            definition.trigger_version,
        )
    except UnknownWorldEventHandler:
        return "Условие больше не поддерживается; событие не будет запущено автоматически."
    return str(handler.presenter(definition))


def effect_presentation(definition):
    if not definition.effect_type:
        return "Событие будет добавлено в историю мира без автоматического изменения других систем."
    try:
        handler = get_world_event_effect(definition.effect_type, definition.effect_version)
    except UnknownWorldEventHandler:
        return "Последствие больше не поддерживается; событие не будет запущено."
    return str(handler.presenter(definition.effect_payload))


def trigger_type_label(trigger_type):
    if trigger_type == WorldEvent.TriggerType.WORLD_TIME:
        return "Запланировано по мировому времени"
    if trigger_type == WorldEvent.TriggerType.MANUAL:
        return "Зафиксировано Game Master"
    return "Неизвестное условие"


def serialize_world_event_definition(definition):
    return {
        "event_type": definition.event_type,
        "title": definition.title,
        "description": definition.description,
        "trigger_type": definition.trigger_type,
        "scheduled_world_minutes": definition.trigger_at,
        "trigger_version": definition.trigger_version,
        "effect_type": definition.effect_type,
        "effect_version": definition.effect_version,
        "enabled": definition.enabled,
        "one_shot": definition.one_shot,
        "region_id": definition.region_id,
        "region_label": "" if definition.region_id is None else definition.region.name,
        "latitude": definition.latitude,
        "longitude": definition.longitude,
        "target_label": definition.target_label,
        "revision": definition.revision,
    }


def serialize_world_event_occurrence(occurrence):
    return {
        "occurrence_id": occurrence.pk,
        "event_type": occurrence.event_type_snapshot,
        "title": occurrence.title,
        "summary": occurrence.summary,
        "occurred_world_minutes": occurrence.occurred_world_minutes,
        "scheduled_world_minutes": occurrence.scheduled_world_minutes,
        "trigger_type": occurrence.trigger_type_snapshot,
        "region_label": occurrence.region_label_snapshot,
        "target_label": occurrence.target_label,
        "effect_type": occurrence.effect_type_snapshot,
        "source": occurrence.source,
    }


def _validate_definition_payloads(*, trigger_type, trigger_version, trigger_config, effect_type, effect_version, effect_payload):
    trigger_handler = get_world_event_trigger(trigger_type, trigger_version)
    normalized_trigger = trigger_handler.validator(trigger_config)
    normalized_trigger = validate_safe_json_object(
        normalized_trigger,
        name="trigger_config",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )

    normalized_effect = validate_safe_json_object(
        effect_payload,
        name="effect_payload",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )
    if effect_type:
        effect_handler = get_world_event_effect(effect_type, effect_version)
        normalized_effect = effect_handler.validator(normalized_effect)
        normalized_effect = validate_safe_json_object(
            normalized_effect,
            name="effect_payload",
            max_bytes=MAX_EVENT_COMPONENT_BYTES,
        )
    elif effect_version is not None or normalized_effect:
        raise ValidationError("Без effect type payload и версия должны быть пустыми.")
    return normalized_trigger, normalized_effect


def _target_values(target):
    if target is None:
        return None, "", ""
    if target.pk is None:
        raise ValidationError("Цель события должна быть сохранена.")
    return (
        ContentType.objects.get_for_model(target, for_concrete_model=False),
        str(target.pk),
        str(target),
    )


def _validate_campaign_target(campaign, target):
    target_campaign_id = getattr(target, "campaign_id", None) if target is not None else None
    if target_campaign_id is not None and target_campaign_id != campaign.pk:
        raise PermissionDenied("Цель события принадлежит другой кампании.")


@transaction.atomic
def create_world_event_definition(
    *,
    actor,
    campaign,
    title,
    description="",
    event_type=NARRATIVE_EVENT_TYPE,
    trigger_type=WorldEvent.TriggerType.WORLD_TIME,
    scheduled_world_minutes=None,
    trigger_config=None,
    trigger_version=1,
    effect_type=None,
    effect_payload=None,
    effect_version=None,
    region=None,
    target=None,
    latitude=None,
    longitude=None,
    operation_id=None,
):
    if not can_manage_campaign(actor, campaign):
        raise PermissionDenied("Создавать события может только GM кампании.")
    _validate_namespaced(event_type, label="Event type")
    title = str(title or "").strip()
    description = str(description or "").strip()
    if not title:
        raise ValidationError("Укажите название события.")
    if len(title) > 200:
        raise ValidationError("Название события слишком длинное.")
    if trigger_type == WorldEvent.TriggerType.WORLD_TIME:
        if scheduled_world_minutes is None or scheduled_world_minutes <= campaign.world_minutes:
            raise ValidationError(
                "Запланированное время должно быть позже текущего. Для события сейчас используйте ручную запись."
            )
    elif scheduled_world_minutes is not None:
        raise ValidationError("Ручное событие не имеет будущей даты.")
    _validate_campaign_target(campaign, target)
    if region is not None and region.campaign_id != campaign.pk:
        raise PermissionDenied("Регион события принадлежит другой кампании.")

    trigger_config, effect_payload = _validate_definition_payloads(
        trigger_type=trigger_type,
        trigger_version=trigger_version,
        trigger_config={} if trigger_config is None else trigger_config,
        effect_type=effect_type,
        effect_version=effect_version,
        effect_payload={} if effect_payload is None else effect_payload,
    )
    target_content_type, target_object_id, target_label = _target_values(target)
    operation_id = uuid.UUID(str(operation_id)) if operation_id else uuid.uuid4()
    definition = WorldEvent(
        campaign=campaign,
        region=region,
        title=title,
        description=description,
        event_type=event_type,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        trigger_version=trigger_version,
        trigger_at=scheduled_world_minutes,
        effect_type=effect_type,
        effect_payload=effect_payload,
        effect_version=effect_version,
        enabled=True,
        one_shot=True,
        status=WorldEvent.Status.PLANNED,
        target_content_type=target_content_type,
        target_object_id=target_object_id,
        target_label=target_label,
        latitude=latitude if latitude is not None else getattr(region, "map_latitude", None),
        longitude=longitude if longitude is not None else getattr(region, "map_longitude", None),
        created_by=actor,
        created_by_label_snapshot=_actor_label(actor),
        revision=1,
    )
    definition.full_clean()
    definition.save()
    state = serialize_world_event_definition(definition)
    record_audit(
        action="world_event_definition.created",
        actor=actor,
        campaign=campaign,
        target=definition,
        summary=f"Запланировано событие «{definition.title}».",
        before_state=None,
        after_state=state,
        metadata={"changed_fields": sorted(state)},
        operation_id=operation_id,
    )
    return definition


@transaction.atomic
def update_world_event_definition(*, actor, campaign, definition, title, description, region=None):
    if not can_manage_campaign(actor, campaign):
        raise PermissionDenied("Изменять события может только GM кампании.")
    locked = WorldEvent.objects.select_for_update().select_related("region").get(
        pk=definition.pk,
        campaign=campaign,
    )
    if region is not None and region.campaign_id != campaign.pk:
        raise PermissionDenied("Регион события принадлежит другой кампании.")
    before = serialize_world_event_definition(locked)
    locked.title = str(title or "").strip()
    locked.description = str(description or "").strip()
    locked.region = region
    if region is not None:
        locked.latitude = region.map_latitude
        locked.longitude = region.map_longitude
    locked.revision += 1
    locked.full_clean()
    locked.save()
    after = serialize_world_event_definition(locked)
    record_audit(
        action="world_event_definition.updated",
        actor=actor,
        campaign=campaign,
        target=locked,
        summary=f"Изменено событие «{locked.title}».",
        before_state=before,
        after_state=after,
        metadata={
            "changed_fields": [key for key in after if before.get(key) != after.get(key)]
        },
    )
    return locked


@transaction.atomic
def disable_world_event_definition(*, actor, campaign, definition):
    if not can_manage_campaign(actor, campaign):
        raise PermissionDenied("Отключать события может только GM кампании.")
    locked = WorldEvent.objects.select_for_update().select_related("region").get(
        pk=definition.pk,
        campaign=campaign,
    )
    if not locked.enabled:
        return locked
    before = serialize_world_event_definition(locked)
    locked.enabled = False
    locked.status = WorldEvent.Status.CANCELLED
    locked.revision += 1
    locked.save(update_fields=["enabled", "status", "revision", "updated_at"])
    after = serialize_world_event_definition(locked)
    record_audit(
        action="world_event_definition.disabled",
        actor=actor,
        campaign=campaign,
        target=locked,
        summary=f"Отключено событие «{locked.title}».",
        before_state=before,
        after_state=after,
        metadata={"changed_fields": ["enabled", "revision"]},
    )
    return locked


@transaction.atomic
def remove_world_event_definition(*, actor, campaign, definition):
    if not can_manage_campaign(actor, campaign):
        raise PermissionDenied("Удалять определения событий может только GM.")
    locked = WorldEvent.objects.select_for_update().select_related("region").get(
        pk=definition.pk,
        campaign=campaign,
    )
    before = serialize_world_event_definition(locked)
    label = locked.title
    record_audit(
        action="world_event_definition.removed",
        actor=actor,
        campaign=campaign,
        target=locked,
        target_label=label,
        summary=f"Удалено определение события «{label}»; история срабатываний сохранена.",
        before_state=before,
        after_state={"removed": True},
        metadata={"changed_fields": ["removed"]},
    )
    locked.delete()


def _apply_effect(definition, *, actor, operation_id):
    if not definition.effect_type:
        return {}
    if definition.target_content_type_id and definition.target is None:
        raise WorldEventConflict("Цель события больше не существует; событие не выполнено.")
    handler = get_world_event_effect(definition.effect_type, definition.effect_version)
    normalized = handler.validator(definition.effect_payload)
    normalized = validate_safe_json_object(
        normalized,
        name="effect_payload",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )
    result = handler.apply(
        definition=definition,
        campaign=definition.campaign,
        actor=actor,
        operation_id=operation_id,
        payload=normalized,
    )
    return validate_safe_json_object(
        {} if result is None else result,
        name="effect_result",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )


def _trigger_locked(definition, *, actor, source, occurred_world_minutes):
    if not definition.enabled:
        raise WorldEventConflict("Событие отключено.")
    get_world_event_trigger(definition.trigger_type, definition.trigger_version).validator(
        definition.trigger_config
    )
    if definition.one_shot and definition.occurrences.exists():
        raise WorldEventConflict("Это событие уже произошло.")
    operation_id = uuid.uuid4()
    effect_result = _apply_effect(definition, actor=actor, operation_id=operation_id)
    trigger_snapshot = validate_safe_json_object(
        {
            **definition.trigger_config,
            **(
                {"scheduled_world_minutes": definition.trigger_at}
                if definition.trigger_type == WorldEvent.TriggerType.WORLD_TIME
                else {}
            ),
        },
        name="trigger_snapshot",
        max_bytes=MAX_EVENT_COMPONENT_BYTES,
    )
    # All inputs below are normalized by the registered handlers and bounded
    # JSON validators above. This internal insert avoids three full_clean()
    # relation/constraint probes for every due event; the database uniqueness
    # constraint remains the final one-shot race guard.
    occurrence = WorldEventOccurrence.objects._create_from_validated_event_service(
        campaign=definition.campaign,
        definition=definition,
        definition_revision=definition.revision,
        event_type_snapshot=definition.event_type,
        title=definition.title,
        summary=definition.description,
        occurred_world_minutes=int(occurred_world_minutes),
        scheduled_world_minutes=(
            definition.trigger_at
            if definition.trigger_type == WorldEvent.TriggerType.WORLD_TIME
            else None
        ),
        source=source,
        actor=actor,
        actor_label_snapshot=_actor_label(actor),
        trigger_type_snapshot=definition.trigger_type,
        trigger_snapshot=trigger_snapshot,
        trigger_version_snapshot=definition.trigger_version,
        target_content_type=definition.target_content_type,
        target_object_id=definition.target_object_id,
        target_label=definition.target_label,
        region=definition.region,
        region_label_snapshot="" if definition.region_id is None else definition.region.name,
        latitude=definition.latitude,
        longitude=definition.longitude,
        effect_type_snapshot=definition.effect_type,
        effect_version_snapshot=definition.effect_version,
        effect_result=effect_result,
        operation_id=operation_id,
    )
    WorldEvent.objects.filter(pk=definition.pk).update(
        status=WorldEvent.Status.TRIGGERED,
        triggered_at=occurrence.occurred_world_minutes,
    )
    record_audit(
        action="world_event.occurred",
        source=(AuditLog.Source.USER if source == WorldEventOccurrence.Source.USER else AuditLog.Source.SYSTEM),
        actor=actor,
        campaign=definition.campaign,
        world_minutes=occurrence.occurred_world_minutes,
        target=occurrence,
        summary=f"Событие «{occurrence.title}» произошло.",
        before_state=None,
        after_state=serialize_world_event_occurrence(occurrence),
        metadata={
            "definition_id": definition.pk,
            "definition_revision": definition.revision,
        },
        operation_id=operation_id,
    )
    return occurrence


@transaction.atomic
def trigger_world_event_now(*, actor, campaign, definition):
    if not can_manage_campaign(actor, campaign):
        raise PermissionDenied("Запускать события может только GM кампании.")
    locked = (
        WorldEvent.objects.select_for_update()
        .select_related("campaign", "region", "target_content_type")
        .get(pk=definition.pk, campaign=campaign)
    )
    if locked.trigger_type != WorldEvent.TriggerType.MANUAL:
        raise WorldEventConflict("Сейчас можно запустить только ручное событие.")
    return _trigger_locked(
        locked,
        actor=actor,
        source=WorldEventOccurrence.Source.USER,
        occurred_world_minutes=campaign.world_minutes,
    )


@transaction.atomic
def record_narrative_event_now(*, actor, campaign, title, description="", region=None):
    operation_id = uuid.uuid4()
    definition = create_world_event_definition(
        actor=actor,
        campaign=campaign,
        title=title,
        description=description,
        trigger_type=WorldEvent.TriggerType.MANUAL,
        region=region,
        operation_id=operation_id,
    )
    return trigger_world_event_now(actor=actor, campaign=campaign, definition=definition)


def execute_due_world_events(*, campaign, start_world_minutes, end_world_minutes):
    if end_world_minutes <= start_world_minutes:
        return []
    definitions = list(
        WorldEvent.objects.select_for_update()
        .select_related("campaign", "region", "target_content_type")
        .filter(
            campaign=campaign,
            enabled=True,
            one_shot=True,
            trigger_type=WorldEvent.TriggerType.WORLD_TIME,
            trigger_at__gt=start_world_minutes,
            trigger_at__lte=end_world_minutes,
            occurrences__isnull=True,
        )
        .order_by("trigger_at", "id")
    )
    return [
        _trigger_locked(
            definition,
            actor=None,
            source=WorldEventOccurrence.Source.SYSTEM,
            occurred_world_minutes=definition.trigger_at,
        )
        for definition in definitions
    ]


register_world_event_trigger(
    WorldEvent.TriggerType.MANUAL,
    version=1,
    validator=_validate_empty_trigger_config,
    presenter=lambda _definition: "Событие фиксирует Game Master.",
)
register_world_event_trigger(
    WorldEvent.TriggerType.WORLD_TIME,
    version=1,
    validator=_validate_empty_trigger_config,
    presenter=lambda _definition: "Событие сработает при пересечении запланированного мирового времени.",
)
