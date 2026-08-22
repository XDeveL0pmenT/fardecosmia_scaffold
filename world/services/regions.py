"""Transactional Region mutations with R1 lifecycle and P3 auditing."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from world.models import Region
from world.services.access import require_campaign_gm
from world.services.audit import changed_fields, record_audit, serialize_region
from world.services.map_geometry import polygon_center
from world.services.region_climate import apply_region_climate, region_climate_at
from world.services.region_weather import initialize_region_weather


@dataclass(frozen=True)
class RegionMutationResult:
    region: Region
    initialization: object | None


@transaction.atomic
def create_region(*, actor, campaign, region, auto_configure_from_map=True):
    require_campaign_gm(actor, campaign)
    if region.pk is not None:
        raise ValidationError("Новый регион уже сохранён.")
    region.campaign = campaign
    if auto_configure_from_map and region.map_polygon:
        longitude, latitude = polygon_center(region.map_polygon)
        region.map_longitude = longitude
        region.map_latitude = latitude
        apply_region_climate(
            region,
            region_climate_at(campaign, latitude, longitude),
        )
    region.full_clean()
    region.save()
    initialization = initialize_region_weather(region)
    after_state = serialize_region(region)
    record_audit(
        action="region.created",
        actor=actor,
        campaign=campaign,
        target=region,
        summary=f"Создан регион «{region.name}».",
        after_state=after_state,
        metadata={"changed_fields": sorted(after_state)},
    )
    return RegionMutationResult(region=region, initialization=initialization)


@transaction.atomic
def update_region(
    *,
    actor,
    campaign,
    region,
    changes,
    initialize_weather=False,
    summary=None,
):
    require_campaign_gm(actor, campaign)
    locked = Region.objects.select_for_update().get(pk=region.pk, campaign=campaign)
    before_state = serialize_region(locked)
    model_fields = {
        field.name for field in Region._meta.concrete_fields if not field.primary_key
    }
    forbidden = set(changes) - model_fields
    if forbidden or "campaign" in changes:
        raise ValidationError("Недопустимые поля изменения Region.")
    actual_changes = {
        field_name: value
        for field_name, value in changes.items()
        if getattr(locked, field_name) != value
    }
    if not actual_changes:
        return RegionMutationResult(region=locked, initialization=None)
    for field_name, value in actual_changes.items():
        setattr(locked, field_name, value)
    locked.full_clean()
    locked.save(update_fields=list(actual_changes))
    initialization = initialize_region_weather(locked) if initialize_weather else None
    after_state = serialize_region(locked)
    audited_changes = changed_fields(before_state, after_state)
    record_audit(
        action="region.updated",
        actor=actor,
        campaign=campaign,
        target=locked,
        summary=summary or f"Обновлён регион «{locked.name}».",
        before_state=before_state,
        after_state=after_state,
        metadata={"changed_fields": audited_changes},
    )
    return RegionMutationResult(region=locked, initialization=initialization)


def placement_changes(*, campaign, region, polygon):
    """Build server-authoritative position and climate values for a contour."""

    longitude, latitude = polygon_center(polygon)
    probe = Region.objects.get(pk=region.pk, campaign=campaign)
    probe.map_polygon = polygon
    probe.map_longitude = longitude
    probe.map_latitude = latitude
    climate_fields = apply_region_climate(
        probe,
        region_climate_at(campaign, latitude, longitude),
    )
    return {
        "map_polygon": polygon,
        "map_longitude": longitude,
        "map_latitude": latitude,
        **{field_name: getattr(probe, field_name) for field_name in climate_fields},
    }


def automatic_climate_changes(*, campaign, region):
    if region.map_latitude is None or region.map_longitude is None:
        raise ValidationError("Сначала расположите регион на карте.")
    probe = Region.objects.get(pk=region.pk, campaign=campaign)
    probe.use_manual_climate_overrides = False
    updated = apply_region_climate(
        probe,
        region_climate_at(campaign, probe.map_latitude, probe.map_longitude),
    )
    return {
        "use_manual_climate_overrides": False,
        **{field_name: getattr(probe, field_name) for field_name in updated},
    }


@transaction.atomic
def delete_region(*, actor, campaign, region):
    require_campaign_gm(actor, campaign)
    locked = Region.objects.select_for_update().get(pk=region.pk, campaign=campaign)
    before_state = serialize_region(locked)
    target_label = str(locked)
    record_audit(
        action="region.deleted",
        actor=actor,
        campaign=campaign,
        target=locked,
        target_label=target_label,
        summary=f"Удалён регион «{locked.name}».",
        before_state=before_state,
        metadata={"changed_fields": sorted(before_state)},
    )
    locked.delete()
