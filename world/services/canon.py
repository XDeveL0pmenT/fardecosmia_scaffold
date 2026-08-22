from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from world.models import CampaignEntityOverride, WorldEntry
from world.services.access import require_campaign_gm, require_global_canon_editor
from world.services.audit import (
    changed_fields,
    record_audit,
    serialize_campaign_override,
    serialize_world_entry,
)
from world.services.overrides import validate_override_patch, validate_override_target


CONTENT_FIELDS = ("kind", "slug", "title", "summary", "body")


def _validate_campaign_identity(*, campaign, kind, slug, exclude_pk=None):
    global_collision = WorldEntry.objects.filter(
        scope=WorldEntry.Scope.GLOBAL,
        kind=kind,
        slug=slug,
    ).exists()
    if global_collision:
        raise ValidationError(
            "Глобальная запись с таким kind/slug уже существует; создайте override."
        )
    query = WorldEntry.objects.filter(
        scope=WorldEntry.Scope.CAMPAIGN,
        campaign=campaign,
        kind=kind,
        slug=slug,
    )
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    if query.exists():
        raise ValidationError("В этой кампании уже есть запись с таким kind/slug.")


def _validate_global_identity(*, kind, slug, exclude_pk=None):
    query = WorldEntry.objects.filter(
        scope=WorldEntry.Scope.GLOBAL,
        kind=kind,
        slug=slug,
    )
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    if query.exists():
        raise ValidationError("Глобальная запись с таким kind/slug уже существует.")
    if WorldEntry.objects.filter(
        scope=WorldEntry.Scope.CAMPAIGN,
        kind=kind,
        slug=slug,
    ).exists():
        raise ValidationError(
            "Campaign-запись уже использует такой kind/slug; сначала разрешите конфликт."
        )


@transaction.atomic
def create_global_world_entry(*, actor, kind, slug, title, summary="", body=""):
    require_global_canon_editor(actor)
    _validate_global_identity(kind=kind, slug=slug)
    entry = WorldEntry(
        scope=WorldEntry.Scope.GLOBAL,
        kind=kind,
        slug=slug,
        title=title,
        summary=summary,
        body=body,
        created_by=actor,
        updated_by=actor,
    )
    entry.full_clean()
    entry.save()
    after_state = serialize_world_entry(entry)
    record_audit(
        action="world_entry.created",
        actor=actor,
        target=entry,
        summary=f"Создана глобальная запись «{entry.title}».",
        after_state=after_state,
        metadata={"changed_fields": sorted(after_state)},
    )
    return entry


@transaction.atomic
def update_global_world_entry(*, actor, entry, **changes):
    require_global_canon_editor(actor)
    locked = WorldEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.scope != WorldEntry.Scope.GLOBAL:
        raise ValidationError("Эта запись не является глобальным каноном.")
    if set(changes) - set(CONTENT_FIELDS):
        raise ValidationError("Scope, campaign и provenance нельзя менять этим сервисом.")
    before_state = serialize_world_entry(locked)
    values = {name: changes.get(name, getattr(locked, name)) for name in CONTENT_FIELDS}
    _validate_global_identity(
        kind=values["kind"],
        slug=values["slug"],
        exclude_pk=locked.pk,
    )
    changed = [name for name in CONTENT_FIELDS if getattr(locked, name) != values[name]]
    if not changed:
        return locked
    for name in CONTENT_FIELDS:
        setattr(locked, name, values[name])
    locked.updated_by = actor
    locked.revision += 1
    locked.full_clean()
    locked.save(update_fields=[*changed, "updated_by", "revision", "updated_at"])
    after_state = serialize_world_entry(locked)
    record_audit(
        action="world_entry.updated",
        actor=actor,
        target=locked,
        summary=f"Обновлена глобальная запись «{locked.title}».",
        before_state=before_state,
        after_state=after_state,
        metadata={"changed_fields": changed_fields(before_state, after_state)},
    )
    return locked


@transaction.atomic
def delete_global_world_entry(*, actor, entry):
    require_global_canon_editor(actor)
    locked = WorldEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.scope != WorldEntry.Scope.GLOBAL:
        raise ValidationError("Эта запись не является глобальным каноном.")
    content_type = ContentType.objects.get_for_model(WorldEntry)
    overrides = CampaignEntityOverride.objects.filter(
        content_type=content_type,
        object_id=str(locked.pk),
    ).select_related("campaign")
    campaigns = list(overrides.values_list("campaign__name", flat=True))
    if campaigns:
        raise ValidationError(
            "Нельзя удалить глобальную запись: активные overrides в кампаниях: "
            + ", ".join(campaigns)
        )
    before_state = serialize_world_entry(locked)
    record_audit(
        action="world_entry.deleted",
        actor=actor,
        target=locked,
        summary=f"Удалена глобальная запись «{locked.title}».",
        before_state=before_state,
        metadata={"changed_fields": sorted(before_state)},
    )
    locked.delete()


@transaction.atomic
def create_campaign_world_entry(
    *, actor, campaign, kind, slug, title, summary="", body=""
):
    require_campaign_gm(actor, campaign)
    _validate_campaign_identity(campaign=campaign, kind=kind, slug=slug)
    entry = WorldEntry(
        scope=WorldEntry.Scope.CAMPAIGN,
        campaign=campaign,
        kind=kind,
        slug=slug,
        title=title,
        summary=summary,
        body=body,
        created_by=actor,
        updated_by=actor,
    )
    entry.full_clean()
    entry.save()
    after_state = serialize_world_entry(entry)
    record_audit(
        action="world_entry.created",
        actor=actor,
        campaign=campaign,
        target=entry,
        summary=f"Создана запись кампании «{entry.title}».",
        after_state=after_state,
        metadata={"changed_fields": sorted(after_state)},
    )
    return entry


@transaction.atomic
def update_campaign_world_entry(*, actor, campaign, entry, **changes):
    require_campaign_gm(actor, campaign)
    locked = WorldEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.scope != WorldEntry.Scope.CAMPAIGN or locked.campaign_id != campaign.pk:
        raise ValidationError("Запись не принадлежит этой кампании.")
    if set(changes) - set(CONTENT_FIELDS):
        raise ValidationError("Scope и campaign нельзя менять этим сервисом.")
    before_state = serialize_world_entry(locked)
    values = {name: changes.get(name, getattr(locked, name)) for name in CONTENT_FIELDS}
    _validate_campaign_identity(
        campaign=campaign,
        kind=values["kind"],
        slug=values["slug"],
        exclude_pk=locked.pk,
    )
    changed = [name for name in CONTENT_FIELDS if getattr(locked, name) != values[name]]
    if not changed:
        return locked
    for name in CONTENT_FIELDS:
        setattr(locked, name, values[name])
    locked.updated_by = actor
    locked.revision += 1
    locked.full_clean()
    locked.save(update_fields=[*changed, "updated_by", "revision", "updated_at"])
    after_state = serialize_world_entry(locked)
    record_audit(
        action="world_entry.updated",
        actor=actor,
        campaign=campaign,
        target=locked,
        summary=f"Обновлена запись кампании «{locked.title}».",
        before_state=before_state,
        after_state=after_state,
        metadata={"changed_fields": changed_fields(before_state, after_state)},
    )
    return locked


@transaction.atomic
def delete_campaign_world_entry(*, actor, campaign, entry):
    require_campaign_gm(actor, campaign)
    locked = WorldEntry.objects.select_for_update().get(pk=entry.pk)
    if locked.scope != WorldEntry.Scope.CAMPAIGN or locked.campaign_id != campaign.pk:
        raise ValidationError("Запись не принадлежит этой кампании.")
    before_state = serialize_world_entry(locked)
    record_audit(
        action="world_entry.deleted",
        actor=actor,
        campaign=campaign,
        target=locked,
        summary=f"Удалена запись кампании «{locked.title}».",
        before_state=before_state,
        metadata={"changed_fields": sorted(before_state)},
    )
    locked.delete()


@transaction.atomic
def set_campaign_override(
    *, actor, campaign, target, patch, is_suppressed=False
):
    require_campaign_gm(actor, campaign)
    validate_override_target(target)
    cleaned_patch = validate_override_patch(target, patch)
    sparse_patch = {
        name: value
        for name, value in cleaned_patch.items()
        if value != getattr(target, name)
    }
    content_type = ContentType.objects.get_for_model(type(target))
    override = CampaignEntityOverride.objects.select_for_update().filter(
        campaign=campaign,
        content_type=content_type,
        object_id=str(target.pk),
    ).first()
    if not sparse_patch and not is_suppressed:
        if override is not None:
            before_state = serialize_campaign_override(override)
            record_audit(
                action=(
                    "campaign_override.restored"
                    if override.is_suppressed and not override.patch
                    else "campaign_override.removed"
                ),
                actor=actor,
                campaign=campaign,
                target=target,
                summary=f"Удалено переопределение «{target}».",
                before_state=before_state,
                after_state={"inherits_global": True},
                metadata={"changed_fields": sorted(before_state)},
            )
            override.delete()
        return None
    if override is None:
        override = CampaignEntityOverride.objects.create(
            campaign=campaign,
            content_type=content_type,
            object_id=str(target.pk),
            patch=sparse_patch,
            is_suppressed=is_suppressed,
            created_by=actor,
            updated_by=actor,
            base_revision_at_creation=getattr(target, "revision", None),
        )
        after_state = serialize_campaign_override(override)
        record_audit(
            action=(
                "campaign_override.suppressed"
                if is_suppressed
                else "campaign_override.created"
            ),
            actor=actor,
            campaign=campaign,
            target=target,
            summary=(
                f"Глобальная запись «{target}» скрыта в кампании."
                if is_suppressed
                else f"Создано переопределение «{target}»."
            ),
            after_state=after_state,
            metadata={"changed_fields": sorted(after_state)},
        )
        return override
    if override.patch == sparse_patch and override.is_suppressed == is_suppressed:
        return override
    before_state = serialize_campaign_override(override)
    was_suppressed = override.is_suppressed
    override.patch = sparse_patch
    override.is_suppressed = is_suppressed
    override.updated_by = actor
    override.revision += 1
    override.full_clean()
    override.save(
        update_fields=["patch", "is_suppressed", "updated_by", "revision", "updated_at"]
    )
    after_state = serialize_campaign_override(override)
    if was_suppressed != is_suppressed:
        action = (
            "campaign_override.suppressed"
            if is_suppressed
            else "campaign_override.restored"
        )
    else:
        action = "campaign_override.updated"
    record_audit(
        action=action,
        actor=actor,
        campaign=campaign,
        target=target,
        summary=(
            f"Глобальная запись «{target}» скрыта в кампании."
            if action == "campaign_override.suppressed"
            else (
                f"Глобальная запись «{target}» восстановлена в кампании."
                if action == "campaign_override.restored"
                else f"Обновлено переопределение «{target}»."
            )
        ),
        before_state=before_state,
        after_state=after_state,
        metadata={"changed_fields": changed_fields(before_state, after_state)},
    )
    return override


@transaction.atomic
def remove_campaign_override(*, actor, campaign, target):
    require_campaign_gm(actor, campaign)
    validate_override_target(target)
    content_type = ContentType.objects.get_for_model(type(target))
    override = CampaignEntityOverride.objects.select_for_update().filter(
        campaign=campaign,
        content_type=content_type,
        object_id=str(target.pk),
    ).first()
    if override is None:
        return
    before_state = serialize_campaign_override(override)
    record_audit(
        action="campaign_override.removed",
        actor=actor,
        campaign=campaign,
        target=target,
        summary=f"Удалено переопределение «{target}».",
        before_state=before_state,
        after_state={"inherits_global": True},
        metadata={"changed_fields": sorted(before_state)},
    )
    override.delete()


def set_campaign_suppression(*, actor, campaign, target, is_suppressed):
    validate_override_target(target)
    content_type = ContentType.objects.get_for_model(type(target))
    current = CampaignEntityOverride.objects.filter(
        campaign=campaign,
        content_type=content_type,
        object_id=str(target.pk),
    ).first()
    return set_campaign_override(
        actor=actor,
        campaign=campaign,
        target=target,
        patch={} if current is None else current.patch,
        is_suppressed=is_suppressed,
    )
