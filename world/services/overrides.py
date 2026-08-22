from dataclasses import dataclass
from types import MappingProxyType

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q

from world.models import CampaignEntityOverride, WorldEntry


@dataclass(frozen=True)
class OverridePolicy:
    model: type
    allowed_fields: frozenset[str]


_POLICIES = {}


def register_override_policy(model, *, allowed_fields):
    policy = OverridePolicy(model=model, allowed_fields=frozenset(allowed_fields))
    _POLICIES[model] = policy
    return policy


def override_policy_for(model):
    try:
        return _POLICIES[model]
    except KeyError as error:
        raise ValidationError("Эта модель не поддерживает campaign overrides.") from error


WORLD_ENTRY_OVERRIDE_POLICY = register_override_policy(
    WorldEntry,
    allowed_fields={"title", "summary", "body"},
)


def validate_override_target(instance):
    policy = override_policy_for(type(instance))
    if not instance.pk or not type(instance).objects.filter(pk=instance.pk).exists():
        raise ValidationError("Override target не существует.")
    if isinstance(instance, WorldEntry) and instance.scope != WorldEntry.Scope.GLOBAL:
        raise ValidationError("Переопределять можно только глобальную запись канона.")
    return policy


def validate_override_patch(instance, patch):
    policy = validate_override_target(instance)
    if not isinstance(patch, dict):
        raise ValidationError("Override patch должен быть JSON-объектом.")
    forbidden = set(patch) - policy.allowed_fields
    if forbidden:
        raise ValidationError(
            "Поля нельзя переопределять: " + ", ".join(sorted(forbidden))
        )
    cleaned = {}
    for field_name, value in patch.items():
        field = instance._meta.get_field(field_name)
        try:
            cleaned[field_name] = field.clean(value, instance)
        except ValidationError as error:
            raise ValidationError({field_name: error.messages}) from error
    return cleaned


class EffectiveSource:
    GLOBAL = "global"
    GLOBAL_OVERRIDDEN = "global_overridden"
    CAMPAIGN_ONLY = "campaign_only"


@dataclass(frozen=True)
class EffectiveEntity:
    base: object
    effective_values: object
    source: str
    override: CampaignEntityOverride | None = None
    is_suppressed: bool = False
    base_revision: int | None = None
    override_revision: int | None = None

    def __getattr__(self, name):
        values = object.__getattribute__(self, "effective_values")
        if name in values:
            return values[name]
        base = object.__getattribute__(self, "base")
        return getattr(base, name)


def _effective_projection(instance, override=None):
    policy = override_policy_for(type(instance))
    values = {
        field_name: getattr(instance, field_name)
        for field_name in policy.allowed_fields
    }
    source = (
        EffectiveSource.CAMPAIGN_ONLY
        if isinstance(instance, WorldEntry)
        and instance.scope == WorldEntry.Scope.CAMPAIGN
        else EffectiveSource.GLOBAL
    )
    if override is not None:
        values.update(override.patch)
        source = EffectiveSource.GLOBAL_OVERRIDDEN
    return EffectiveEntity(
        base=instance,
        effective_values=MappingProxyType(values),
        source=source,
        override=override,
        is_suppressed=bool(override and override.is_suppressed),
        base_revision=getattr(instance, "revision", None),
        override_revision=None if override is None else override.revision,
    )


def resolve_for_campaign(instance, campaign):
    validate_override_target(instance) if getattr(instance, "scope", None) == WorldEntry.Scope.GLOBAL else override_policy_for(type(instance))
    if isinstance(instance, WorldEntry) and instance.scope == WorldEntry.Scope.CAMPAIGN:
        if instance.campaign_id != campaign.pk:
            raise ValidationError("Campaign-запись не принадлежит этой кампании.")
        return _effective_projection(instance)
    content_type = ContentType.objects.get_for_model(type(instance))
    override = CampaignEntityOverride.objects.filter(
        campaign=campaign,
        content_type=content_type,
        object_id=str(instance.pk),
    ).first()
    return _effective_projection(instance, override)


def effective_world_entries(campaign, kind=None, *, include_suppressed=False):
    query = Q(scope=WorldEntry.Scope.GLOBAL) | Q(
        scope=WorldEntry.Scope.CAMPAIGN,
        campaign=campaign,
    )
    entries = list(
        WorldEntry.objects.filter(query)
        .filter(**({"kind": kind} if kind else {}))
        .select_related("campaign")
        .order_by("kind", "title", "pk")
    )
    global_ids = [str(entry.pk) for entry in entries if entry.scope == WorldEntry.Scope.GLOBAL]
    content_type = ContentType.objects.get_for_model(WorldEntry)
    overrides = {
        row.object_id: row
        for row in CampaignEntityOverride.objects.filter(
            campaign=campaign,
            content_type=content_type,
            object_id__in=global_ids,
        ).select_related("content_type")
    }
    result = []
    for entry in entries:
        override = overrides.get(str(entry.pk))
        projection = _effective_projection(entry, override)
        if projection.is_suppressed and not include_suppressed:
            continue
        result.append(projection)
    return result
