import json

from django import template


register = template.Library()


ACTION_LABELS = {
    "world_entry.created": "Создана запись канона",
    "world_entry.updated": "Изменена запись канона",
    "world_entry.deleted": "Удалена запись канона",
    "campaign_override.created": "Создано отличие кампании",
    "campaign_override.updated": "Изменено отличие кампании",
    "campaign_override.removed": "Отличие кампании сброшено",
    "campaign_override.suppressed": "Запись скрыта в кампании",
    "campaign_override.restored": "Запись возвращена в кампанию",
    "region.created": "Создан регион",
    "region.updated": "Изменён регион",
    "region.deleted": "Удалён регион",
    "campaign.time_advanced": "Продвинуто время кампании",
    "campaign_biome.updated": "Изменены биомы кампании",
    "global_biome.updated": "Изменены глобальные биомы",
    "campaign.atmosphere_configured": "Настроена атмосфера",
    "campaign.time_simulation_configured": "Настроена симуляция времени",
    "campaign.created": "Создана кампания",
    "campaign.updated": "Изменена кампания",
    "campaign_invitation.created": "Создано приглашение",
    "campaign_invitation.revoked": "Приглашение отозвано",
    "campaign_invitation.accepted": "Приглашение подтверждено участником",
    "campaign_member.joined": "Игрок присоединился",
    "campaign_member.role_changed": "Изменена роль участника",
    "campaign_member.removed": "Участник удалён",
    "approval_request.created": "Создан запрос на одобрение",
    "approval_request.approved": "Запрос одобрен",
    "approval_request.rejected": "Запрос отклонён",
    "approval_request.cancelled": "Запрос отменён",
    "approval_request.expired": "Срок запроса истёк",
    "world_event_definition.created": "Событие запланировано",
    "world_event_definition.updated": "Определение события изменено",
    "world_event_definition.disabled": "Событие отключено",
    "world_event_definition.removed": "Определение события удалено",
    "world_event.occurred": "Событие мира произошло",
}

ACTION_DESCRIPTIONS = {
    "world_entry.created": "В каноне появилась новая запись.",
    "world_entry.updated": "Содержимое существующей записи было обновлено.",
    "world_entry.deleted": "Запись удалена, но её последнее состояние сохранено в истории.",
    "campaign_override.created": "Кампания получила собственную версию глобальной записи.",
    "campaign_override.updated": "Локальные отличия кампании были изменены.",
    "campaign_override.removed": "Кампания снова наследует глобальную версию без отличий.",
    "campaign_override.suppressed": "Глобальная запись перестала действовать в этой кампании.",
    "campaign_override.restored": "Глобальная запись снова действует в этой кампании.",
    "region.created": "На карте кампании появился новый регион.",
    "region.updated": "Изменены свойства, климат или контур региона.",
    "region.deleted": "Регион удалён вместе с зависимым текущим состоянием.",
    "campaign.time_advanced": "Мировое время и связанные системы кампании были продвинуты.",
    "campaign_biome.updated": "Изменён локальный слой биомов только этой кампании.",
    "global_biome.updated": "Изменён общий объективный слой биомов мира.",
    "campaign.atmosphere_configured": "Изменены технические настройки атмосферной модели.",
    "campaign.time_simulation_configured": "Изменены границы точной и ускоренной симуляции.",
    "campaign.created": "Создано новое пространство кампании и назначен первый Game Master.",
    "campaign.updated": "Обновлены основные сведения, видимые участникам кампании.",
    "campaign_invitation.created": "Выпущено безопасное приглашение, привязанное к email игрока.",
    "campaign_invitation.revoked": "Приглашение перестало действовать до принятия.",
    "campaign_invitation.accepted": "Уже состоящий в кампании участник подтвердил приглашение.",
    "campaign_member.joined": "Пользователь принял приглашение и стал игроком кампании.",
    "campaign_member.role_changed": "Права участника внутри кампании были изменены.",
    "campaign_member.removed": "Доступ участника к кампании был удалён без удаления аккаунта.",
    "approval_request.created": "Создано понятное намерение, ожидающее решения.",
    "approval_request.approved": "Решение принято, и зарегистрированное действие успешно применено.",
    "approval_request.rejected": "Мастер отклонил запрос без применения действия.",
    "approval_request.cancelled": "Автор отозвал запрос до принятия решения.",
    "approval_request.expired": "Срок принятия решения закончился.",
    "world_event_definition.created": "Создано новое условие или расписание события кампании.",
    "world_event_definition.updated": "Будущее поведение события изменено без переписывания истории.",
    "world_event_definition.disabled": "Событие больше не будет срабатывать автоматически.",
    "world_event_definition.removed": "Расписание удалено, но состоявшиеся факты остались в истории.",
    "world_event.occurred": "В объективной истории кампании зафиксирован неизменяемый факт.",
}

FIELD_LABELS = {
    "scope": "Область действия",
    "campaign_id": "Кампания",
    "kind": "Раздел канона",
    "slug": "Системное имя",
    "title": "Название",
    "summary": "Краткое описание",
    "body": "Подробное описание",
    "revision": "Ревизия",
    "name": "Название",
    "map_latitude": "Широта опорной точки",
    "map_longitude": "Долгота опорной точки",
    "map_polygon": "Контур региона",
    "weather_geometry_revision": "Ревизия геометрии погоды",
    "biome": "Биом",
    "base_temperature": "Средняя температура",
    "humidity": "Влажность",
    "elevation": "Высота",
    "use_manual_climate_overrides": "Ручные климатические поправки",
    "world_minutes": "Мировое время",
    "patch": "Локальные отличия",
    "is_suppressed": "Скрыто в кампании",
    "inherits_global": "Наследует глобальный канон",
    "target_type": "Тип исходной записи",
    "target_id": "ID исходной записи",
    "target_label": "Исходная запись",
    "base_revision_at_creation": "Базовая ревизия при создании",
    "enabled": "Атмосфера включена",
    "grid_width": "Ширина сетки",
    "grid_height": "Высота сетки",
    "step_minutes": "Шаг атмосферы",
    "world_seed": "Seed мира",
    "checkpoint_interval_minutes": "Интервал checkpoint",
    "checkpoint_retention_count": "Количество checkpoints",
    "ocean_temperature_c": "Fallback температуры океана",
    "oxygen_fraction": "Доля кислорода",
    "exact_simulation_max_turns": "Предел точной симуляции",
    "fast_forward_spinup_turns": "Финальный точный spin-up",
    "description": "Описание",
    "user_label": "Участник",
    "role": "Роль в кампании",
    "removed": "Удалён из кампании",
    "email_masked": "Email приглашения",
    "invitation_email_masked": "Email приглашения",
    "expires_at": "Действует до",
    "status": "Состояние",
    "created_by": "Создал",
    "event_type": "Тип события",
    "trigger_type": "Условие срабатывания",
    "scheduled_world_minutes": "Запланированное мировое время",
    "occurred_world_minutes": "Мировое время события",
    "effect_type": "Автоматическое последствие",
    "authored_cell_count": "Нарисовано ячеек",
    "digest": "Контрольная сумма слоя",
}


@register.filter
def pretty_json(value):
    if value is None:
        return "—"
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


@register.filter
def audit_action_label(action):
    return ACTION_LABELS.get(action, action.replace("_", " ").replace(".", " · "))


@register.simple_tag
def audit_action_choices():
    return sorted(ACTION_LABELS.items(), key=lambda item: item[1])


@register.filter
def audit_action_description(action):
    return ACTION_DESCRIPTIONS.get(action, "Зафиксировано значимое изменение состояния.")


@register.filter
def audit_action_tone(action):
    if action.endswith(".deleted") or action.endswith(".removed"):
        return "danger"
    if action.endswith(".created") or action.endswith(".restored") or action.endswith(".approved"):
        return "success"
    if action.endswith(".suppressed") or action.endswith(".rejected"):
        return "warning"
    if action == "campaign.time_advanced":
        return "time"
    return "change"


@register.filter
def audit_field_label(field_name):
    return FIELD_LABELS.get(field_name, str(field_name).replace("_", " ").capitalize())


def _display_value(field_name, value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if field_name == "map_polygon" and isinstance(value, list):
        return f"{len(value)} точек контура"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return str(value)


@register.filter
def audit_diff(audit):
    before = audit.before_state if isinstance(audit.before_state, dict) else {}
    after = audit.after_state if isinstance(audit.after_state, dict) else {}
    preferred = audit.metadata.get("changed_fields", []) if isinstance(audit.metadata, dict) else []
    keys = []
    for key in [*preferred, *before, *after]:
        if key not in keys and before.get(key) != after.get(key):
            keys.append(key)
    return [
        {
            "field": key,
            "label": audit_field_label(key),
            "before": _display_value(key, before.get(key)),
            "after": _display_value(key, after.get(key)),
        }
        for key in keys
    ]
