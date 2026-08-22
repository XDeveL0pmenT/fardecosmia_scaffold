"""Registered, campaign-scoped approval workflows.

Approval payloads describe a whitelisted intent.  They are never interpreted as
model names, Python methods, field setters, SQL, or other arbitrary commands.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import uuid

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.models import ApprovalRequest, AuditLog
from world.services.access import can_manage_campaign, can_view_campaign
from world.services.audit import record_audit, validate_safe_json_object


MAX_APPROVAL_JSON_BYTES = 64 * 1024
MAX_RESOLUTION_NOTE_CHARS = 4_000
MAX_PRESENTATION_SUMMARY_CHARS = 4_000
_REQUEST_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class ApprovalWorkflowError(Exception):
    """Expected, human-readable workflow failure."""


class UnknownApprovalType(ApprovalWorkflowError):
    pass


class ApprovalConflict(ApprovalWorkflowError):
    pass


class ApprovalAlreadyResolved(ApprovalWorkflowError):
    pass


class ApprovalExpired(ApprovalWorkflowError):
    pass


@dataclass(frozen=True)
class ApprovalPresentation:
    request_type_label: str
    title: str
    summary: str
    details: tuple[tuple[str, str], ...]
    consequences: tuple[str, ...]
    target_label: str = ""
    current_applicability_message: str = ""
    result_summary: str = ""


@dataclass(frozen=True)
class ApprovalDraft:
    campaign: object
    requester: object | None
    request_type: str
    payload: dict
    payload_version: int
    target: object | None
    target_label: str


@dataclass(frozen=True)
class ApprovalHandler:
    request_type: str
    request_type_label: str
    payload_version: int
    validator: object
    presenter: object
    apply: object
    can_request: object
    can_approve: object
    can_cancel: object
    revalidate: object
    requires_resolution_note: bool = False


_HANDLERS: dict[str, ApprovalHandler] = {}


def _default_can_request(actor, subject):
    return can_view_campaign(actor, subject.campaign)


def _default_can_approve(actor, subject):
    return can_manage_campaign(actor, subject.campaign)


def _default_can_cancel(actor, subject):
    return bool(
        actor
        and actor.is_authenticated
        and subject.requester is not None
        and subject.requester.pk == actor.pk
    )


def _noop_revalidate(subject):
    return None


def register_approval_handler(
    request_type,
    *,
    request_type_label,
    validator,
    presenter,
    apply,
    payload_version=1,
    can_request=None,
    can_approve=None,
    can_cancel=None,
    revalidate=None,
    requires_resolution_note=False,
):
    """Register one explicit intent handler.

    Registration is normally performed by a concrete future domain.  P4 itself
    intentionally registers no invented purchase/travel gameplay handler.
    """

    if not isinstance(request_type, str) or not _REQUEST_TYPE_PATTERN.fullmatch(request_type):
        raise ValidationError("request_type должен быть namespaced identifier.")
    if request_type in _HANDLERS:
        raise ValidationError(f"Approval handler {request_type} уже зарегистрирован.")
    if not isinstance(request_type_label, str) or not request_type_label.strip():
        raise ValidationError("Approval handler обязан иметь человекочитаемое название.")
    if not isinstance(payload_version, int) or payload_version < 1:
        raise ValidationError("payload_version должен быть положительным целым числом.")
    for name, callback in (
        ("validator", validator),
        ("presenter", presenter),
        ("apply", apply),
    ):
        if not callable(callback):
            raise ValidationError(f"Approval handler обязан определить {name}.")
    handler = ApprovalHandler(
        request_type=request_type,
        request_type_label=request_type_label.strip(),
        payload_version=payload_version,
        validator=validator,
        presenter=presenter,
        apply=apply,
        can_request=can_request or _default_can_request,
        can_approve=can_approve or _default_can_approve,
        can_cancel=can_cancel or _default_can_cancel,
        revalidate=revalidate or _noop_revalidate,
        requires_resolution_note=bool(requires_resolution_note),
    )
    _HANDLERS[request_type] = handler
    return handler


def unregister_approval_handler(request_type):
    """Remove a handler, primarily for isolated tests and deployment reloads."""

    return _HANDLERS.pop(request_type, None)


def get_approval_handler(request_type):
    try:
        return _HANDLERS[request_type]
    except KeyError as error:
        raise UnknownApprovalType(
            "Этот тип запроса не зарегистрирован и не может быть выполнен."
        ) from error


def registered_approval_type_choices():
    return sorted(
        ((key, handler.request_type_label) for key, handler in _HANDLERS.items()),
        key=lambda item: item[1].casefold(),
    )


def approval_type_label(request_type):
    handler = _HANDLERS.get(request_type)
    return handler.request_type_label if handler else "Архивный тип запроса"


def _user_label(user):
    if user is None:
        return "Система"
    return str(getattr(user, "display_name", "") or getattr(user, "username", "") or user)


def _normalize_note(note):
    note = "" if note is None else str(note).strip()
    if len(note) > MAX_RESOLUTION_NOTE_CHARS:
        raise ValidationError("Комментарий к решению слишком длинный.")
    return note


def _normalize_operation_id(operation_id):
    if operation_id is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(operation_id))
    except (TypeError, ValueError) as error:
        raise ValidationError("operation_id должен быть UUID.") from error


def _validate_presentation(value, *, handler):
    if not isinstance(value, ApprovalPresentation):
        raise ValidationError("Presenter должен вернуть ApprovalPresentation.")
    title = str(value.title).strip()
    summary = str(value.summary).strip()
    type_label = str(value.request_type_label or handler.request_type_label).strip()
    if not title or len(title) > 240:
        raise ValidationError("Presenter должен вернуть короткий понятный заголовок.")
    if not summary or len(summary) > MAX_PRESENTATION_SUMMARY_CHARS:
        raise ValidationError("Presenter должен вернуть понятное краткое описание.")
    if not type_label:
        raise ValidationError("Presenter должен вернуть название типа запроса.")

    details = tuple((str(label).strip(), str(content).strip()) for label, content in value.details)
    consequences = tuple(str(item).strip() for item in value.consequences if str(item).strip())
    if not consequences:
        raise ValidationError("Presenter обязан объяснить последствия одобрения.")
    if len(details) > 30 or len(consequences) > 20:
        raise ValidationError("Presenter вернул слишком много элементов.")
    if any(not label or len(label) > 160 or len(content) > 2_000 for label, content in details):
        raise ValidationError("Presenter вернул недопустимую деталь.")
    if any(len(item) > 2_000 for item in consequences):
        raise ValidationError("Presenter вернул слишком длинное описание последствия.")
    return replace(
        value,
        request_type_label=type_label,
        title=title,
        summary=summary,
        details=details,
        consequences=consequences,
        target_label=str(value.target_label).strip()[:500],
        current_applicability_message=str(value.current_applicability_message).strip(),
        result_summary=str(value.result_summary).strip(),
    )


def _validated_payload(handler, payload, payload_version):
    if payload_version != handler.payload_version:
        raise ValidationError(
            f"Версия payload {payload_version} не поддерживается этим обработчиком."
        )
    safe_payload = validate_safe_json_object(
        payload,
        name="approval payload",
        max_bytes=MAX_APPROVAL_JSON_BYTES,
    )
    normalized = handler.validator(safe_payload)
    return validate_safe_json_object(
        normalized,
        name="normalized approval payload",
        max_bytes=MAX_APPROVAL_JSON_BYTES,
    )


def serialize_approval_request(approval):
    """Compact, explicit P3 representation; raw intent payload is omitted."""

    return {
        "campaign_id": str(approval.campaign_id),
        "request_type": approval.request_type,
        "status": approval.status,
        "requester": approval.requester_label_snapshot,
        "requested_world_minutes": approval.requested_world_minutes,
        "title": approval.title,
        "summary": approval.summary,
        "target_label": approval.target_label,
        "payload_version": approval.payload_version,
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "resolved_by": approval.resolved_by_label_snapshot,
        "resolved_world_minutes": approval.resolved_world_minutes,
        "resolution_note": approval.resolution_note,
        "result": approval.result,
    }


def presentation_for(approval):
    """Return a human DTO; normal templates never interpret raw payload."""

    handler = _HANDLERS.get(approval.request_type)
    if handler is None:
        applicability = "Обработчик этого архивного типа больше не зарегистрирован."
        if approval.is_effectively_expired:
            applicability = "Срок запроса истёк. Решение больше не требуется."
        return ApprovalPresentation(
            request_type_label="Архивный тип запроса",
            title=approval.title,
            summary=approval.summary,
            details=(("Цель", approval.target_label),) if approval.target_label else (),
            consequences=("Запрос нельзя применить без зарегистрированного обработчика.",),
            target_label=approval.target_label,
            current_applicability_message=applicability,
            result_summary=("Действие успешно применено." if approval.status == ApprovalRequest.Status.APPROVED else ""),
        )
    try:
        current = _validate_presentation(handler.presenter(approval), handler=handler)
    except (ApprovalWorkflowError, ValidationError, AttributeError, TypeError, ValueError):
        current = ApprovalPresentation(
            request_type_label=handler.request_type_label,
            title=approval.title,
            summary=approval.summary,
            details=(("Цель", approval.target_label),) if approval.target_label else (),
            consequences=("Актуальные сведения о последствиях сейчас недоступны.",),
            target_label=approval.target_label,
            current_applicability_message="Связанный объект изменён или недоступен.",
        )
    applicability = current.current_applicability_message
    if approval.is_effectively_expired:
        applicability = "Срок запроса истёк. Решение больше не требуется."
    return replace(
        current,
        title=approval.title,
        summary=approval.summary,
        target_label=approval.target_label or current.target_label,
        current_applicability_message=applicability,
    )


def can_user_approve_request(user, approval):
    if approval.status != ApprovalRequest.Status.PENDING or approval.is_effectively_expired:
        return False
    handler = _HANDLERS.get(approval.request_type)
    return bool(handler and handler.can_approve(user, approval))


def can_user_cancel_request(user, approval):
    if approval.status != ApprovalRequest.Status.PENDING or approval.is_effectively_expired:
        return False
    handler = _HANDLERS.get(approval.request_type)
    return bool(handler and handler.can_cancel(user, approval))


@transaction.atomic
def create_approval_request(
    *,
    campaign,
    requester,
    request_type,
    payload,
    payload_version=1,
    target=None,
    target_label=None,
    dedupe_key=None,
    expires_at=None,
    operation_id=None,
):
    handler = get_approval_handler(request_type)
    payload = _validated_payload(handler, payload, payload_version)
    if expires_at is not None:
        if timezone.is_naive(expires_at):
            raise ValidationError("expires_at должен содержать часовой пояс.")
        if expires_at <= timezone.now():
            raise ValidationError("Новый запрос не может уже быть истёкшим.")
    if target is not None and getattr(target, "pk", None) is None:
        raise ValidationError("Цель запроса должна быть сохранена.")
    target_label = str(target_label if target_label is not None else (target or "")).strip()
    if len(target_label) > 500:
        raise ValidationError("Название цели запроса слишком длинное.")
    dedupe_key = str(dedupe_key).strip() if dedupe_key not in (None, "") else None
    if dedupe_key is not None and len(dedupe_key) > 240:
        raise ValidationError("dedupe_key слишком длинный.")

    draft = ApprovalDraft(
        campaign=campaign,
        requester=requester,
        request_type=request_type,
        payload=payload,
        payload_version=payload_version,
        target=target,
        target_label=target_label,
    )
    if not handler.can_request(requester, draft):
        raise PermissionDenied("Вы не можете создать такой запрос в этой кампании.")
    handler.revalidate(draft)
    presentation = _validate_presentation(handler.presenter(draft), handler=handler)

    if dedupe_key is not None:
        duplicate = (
            ApprovalRequest.objects.select_for_update()
            .filter(
                campaign=campaign,
                request_type=request_type,
                status=ApprovalRequest.Status.PENDING,
                dedupe_key=dedupe_key,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
            .exists()
        )
        if duplicate:
            raise ApprovalConflict("Такой запрос уже ожидает решения.")

    operation_id = _normalize_operation_id(operation_id)
    content_type = (
        ContentType.objects.get_for_model(target, for_concrete_model=False)
        if target is not None
        else None
    )
    approval = ApprovalRequest(
        campaign=campaign,
        request_type=request_type,
        requester=requester,
        requester_label_snapshot=_user_label(requester),
        requested_world_minutes=int(campaign.world_minutes),
        title=presentation.title,
        summary=presentation.summary,
        target_content_type=content_type,
        target_object_id="" if target is None else str(target.pk),
        target_label=target_label or presentation.target_label,
        payload=payload,
        payload_version=payload_version,
        dedupe_key=dedupe_key,
        expires_at=expires_at,
        operation_id=operation_id,
    )
    approval.full_clean()
    approval.save()
    record_audit(
        action="approval_request.created",
        actor=requester,
        source=AuditLog.Source.USER if requester is not None else AuditLog.Source.SYSTEM,
        campaign=campaign,
        target=approval,
        summary=f"Создан запрос «{approval.title}».",
        before_state=None,
        after_state=serialize_approval_request(approval),
        metadata={"request_type": request_type, "payload_version": payload_version},
        operation_id=operation_id,
    )
    return approval


def _locked_request(*, campaign, request_id):
    try:
        return (
            ApprovalRequest.objects.select_for_update()
            .select_related(
                "campaign",
                "requester",
                "resolved_by",
                "target_content_type",
            )
            .get(pk=request_id, campaign=campaign)
        )
    except ApprovalRequest.DoesNotExist as error:
        raise ApprovalWorkflowError("Запрос не найден в этой кампании.") from error


def _assert_pending(approval):
    if approval.status != ApprovalRequest.Status.PENDING:
        raise ApprovalAlreadyResolved(
            f"Запрос уже завершён: {approval.get_status_display().lower()}."
        )


def _apply_resolution(
    approval,
    *,
    status,
    actor,
    resolution_note="",
    result=None,
):
    approval.status = status
    approval.resolved_by = actor
    approval.resolved_by_label_snapshot = _user_label(actor) if actor is not None else "Система"
    approval.resolved_at = timezone.now()
    approval.resolved_world_minutes = int(approval.campaign.world_minutes)
    approval.resolution_note = resolution_note
    approval.result = {} if result is None else result
    approval.full_clean()
    approval.save(
        update_fields=[
            "status",
            "resolved_by",
            "resolved_by_label_snapshot",
            "resolved_at",
            "resolved_world_minutes",
            "resolution_note",
            "result",
        ]
    )


def _record_resolution_audit(approval, *, action, actor, before_state, summary):
    return record_audit(
        action=action,
        actor=actor,
        source=AuditLog.Source.USER if actor is not None else AuditLog.Source.SYSTEM,
        campaign=approval.campaign,
        target=approval,
        summary=summary,
        before_state=before_state,
        after_state=serialize_approval_request(approval),
        metadata={"request_type": approval.request_type},
        operation_id=approval.operation_id,
    )


def _expire_locked(approval, *, actor=None):
    before_state = serialize_approval_request(approval)
    _apply_resolution(
        approval,
        status=ApprovalRequest.Status.EXPIRED,
        actor=None,
    )
    _record_resolution_audit(
        approval,
        action="approval_request.expired",
        actor=actor,
        before_state=before_state,
        summary=f"Срок запроса «{approval.title}» истёк.",
    )


def _due_for_expiry(approval):
    return approval.expires_at is not None and approval.expires_at <= timezone.now()


def approve_request(*, campaign, request_id, actor, resolution_note=""):
    expired = False
    approved = None
    with transaction.atomic():
        approval = _locked_request(campaign=campaign, request_id=request_id)
        _assert_pending(approval)
        if _due_for_expiry(approval):
            if not can_manage_campaign(actor, campaign):
                raise PermissionDenied("Только мастер кампании может принять решение.")
            _expire_locked(approval, actor=actor)
            expired = True
        else:
            handler = get_approval_handler(approval.request_type)
            if not handler.can_approve(actor, approval):
                raise PermissionDenied("Вы не можете одобрить этот запрос.")
            note = _normalize_note(resolution_note)
            if handler.requires_resolution_note and not note:
                raise ValidationError("Для этого решения требуется комментарий.")
            handler.revalidate(approval)
            before_state = serialize_approval_request(approval)
            result = handler.apply(approval, actor, approval.operation_id)
            result = validate_safe_json_object(
                {} if result is None else result,
                name="approval result",
                max_bytes=MAX_APPROVAL_JSON_BYTES,
            )
            _apply_resolution(
                approval,
                status=ApprovalRequest.Status.APPROVED,
                actor=actor,
                resolution_note=note,
                result=result,
            )
            _record_resolution_audit(
                approval,
                action="approval_request.approved",
                actor=actor,
                before_state=before_state,
                summary=f"{_user_label(actor)} одобрил запрос «{approval.title}».",
            )
            approved = approval
    if expired:
        raise ApprovalExpired("Срок запроса истёк; он отмечен как истёкший.")
    return approved


def reject_request(*, campaign, request_id, actor, resolution_note=""):
    expired = False
    rejected = None
    with transaction.atomic():
        approval = _locked_request(campaign=campaign, request_id=request_id)
        _assert_pending(approval)
        if _due_for_expiry(approval):
            if not can_manage_campaign(actor, campaign):
                raise PermissionDenied("Только мастер кампании может принять решение.")
            _expire_locked(approval, actor=actor)
            expired = True
        else:
            handler = get_approval_handler(approval.request_type)
            if not handler.can_approve(actor, approval):
                raise PermissionDenied("Вы не можете отклонить этот запрос.")
            note = _normalize_note(resolution_note)
            if handler.requires_resolution_note and not note:
                raise ValidationError("Для этого решения требуется комментарий.")
            before_state = serialize_approval_request(approval)
            _apply_resolution(
                approval,
                status=ApprovalRequest.Status.REJECTED,
                actor=actor,
                resolution_note=note,
            )
            _record_resolution_audit(
                approval,
                action="approval_request.rejected",
                actor=actor,
                before_state=before_state,
                summary=f"Запрос «{approval.title}» отклонён.",
            )
            rejected = approval
    if expired:
        raise ApprovalExpired("Срок запроса истёк; он отмечен как истёкший.")
    return rejected


def cancel_request(*, campaign, request_id, actor, resolution_note=""):
    expired = False
    cancelled = None
    with transaction.atomic():
        approval = _locked_request(campaign=campaign, request_id=request_id)
        _assert_pending(approval)
        if _due_for_expiry(approval):
            if not can_view_campaign(actor, campaign):
                raise PermissionDenied("Нет доступа к этой кампании.")
            _expire_locked(approval, actor=actor)
            expired = True
        else:
            handler = get_approval_handler(approval.request_type)
            if not handler.can_cancel(actor, approval):
                raise PermissionDenied("Вы не можете отменить этот запрос.")
            note = _normalize_note(resolution_note)
            before_state = serialize_approval_request(approval)
            _apply_resolution(
                approval,
                status=ApprovalRequest.Status.CANCELLED,
                actor=actor,
                resolution_note=note,
            )
            _record_resolution_audit(
                approval,
                action="approval_request.cancelled",
                actor=actor,
                before_state=before_state,
                summary=f"Запрос «{approval.title}» отменён.",
            )
            cancelled = approval
    if expired:
        raise ApprovalExpired("Срок запроса истёк; он отмечен как истёкший.")
    return cancelled


def expire_request(*, campaign, request_id, actor=None):
    with transaction.atomic():
        approval = _locked_request(campaign=campaign, request_id=request_id)
        _assert_pending(approval)
        if not _due_for_expiry(approval):
            raise ApprovalConflict("Срок этого запроса ещё не истёк.")
        _expire_locked(approval, actor=actor)
        return approval
