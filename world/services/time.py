from dataclasses import dataclass

from django.db import transaction

from campaigns.models import (
    Campaign,
    CampaignMembership,
    TimeAdvanceReport,
)
from world.models import AtmosphericConfig, WorldEvent
from world.services.atmosphere.persistence import advance_atmosphere_for_period
from world.services.time_reports import build_time_advance_summary
from world.services.weather import update_weather_for_period


@dataclass
class WorldAdvanceResult:
    campaign: Campaign
    weather_states: list
    world_events: list
    report: TimeAdvanceReport | None = None

    def __iter__(self):
        # Preserve the former three-value unpacking contract.
        yield self.campaign
        yield self.weather_states
        yield self.world_events


@dataclass(frozen=True)
class SimulationPlan:
    mode: str
    detailed_start: int
    coverage: list


def simulation_plan(campaign, old_time, new_time):
    exact_limit = (
        campaign.exact_simulation_max_turns * campaign.calendar_minutes_per_turn
    )
    if new_time - old_time <= exact_limit:
        return SimulationPlan(
            mode=TimeAdvanceReport.SimulationMode.EXACT,
            detailed_start=old_time,
            coverage=[
                {"kind": "exact", "start": old_time, "end": new_time}
            ],
        )

    spinup_minutes = (
        campaign.fast_forward_spinup_turns * campaign.calendar_minutes_per_turn
    )
    spinup_start = max(old_time, new_time - spinup_minutes)
    coverage = []
    if spinup_start > old_time:
        coverage.append(
            {"kind": "fast_forwarded", "start": old_time, "end": spinup_start}
        )
    coverage.append({"kind": "spinup", "start": spinup_start, "end": new_time})
    return SimulationPlan(
        mode=TimeAdvanceReport.SimulationMode.FAST_FORWARD,
        detailed_start=spinup_start,
        coverage=coverage,
    )


@transaction.atomic
def advance_world(
    campaign_id,
    minutes,
    *,
    advanced_by=None,
    requested_amount=None,
    requested_unit=None,
):
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
        raise ValueError("Мир можно продвигать только на положительное число минут.")

    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    if advanced_by is not None and not campaign.memberships.filter(
        user=advanced_by,
        role=CampaignMembership.Role.GM,
    ).exists():
        raise ValueError("Отчёт о продвижении времени может создать только GM кампании.")
    old_time = campaign.world_minutes
    new_time = old_time + minutes
    plan = simulation_plan(campaign, old_time, new_time)

    campaign.world_minutes = new_time
    campaign.save(update_fields=["world_minutes"])

    weather_results = []
    atmospheric_result = None
    regions = list(campaign.regions.select_related("campaign").all())
    atmospheric_config = (
        AtmosphericConfig.objects.select_for_update()
        .filter(campaign=campaign, enabled=True)
        .first()
    )
    if atmospheric_config is None:
        for region in regions:
            weather_results.extend(
                update_weather_for_period(
                    region,
                    plan.detailed_start,
                    new_time,
                    force_initialize=(
                        plan.mode == TimeAdvanceReport.SimulationMode.FAST_FORWARD
                    ),
                )
            )
    else:
        located_regions = []
        for region in regions:
            if region.map_latitude is None or region.map_longitude is None:
                weather_results.extend(
                    update_weather_for_period(
                        region,
                        plan.detailed_start,
                        new_time,
                        force_initialize=(
                            plan.mode == TimeAdvanceReport.SimulationMode.FAST_FORWARD
                        ),
                    )
                )
                continue
            located_regions.append(region)
        atmospheric_result = advance_atmosphere_for_period(
            campaign,
            atmospheric_config,
            plan.detailed_start,
            new_time,
            regions=located_regions,
            force_initialize=(
                plan.mode == TimeAdvanceReport.SimulationMode.FAST_FORWARD
            ),
            fast_forward_start=(
                old_time
                if plan.mode == TimeAdvanceReport.SimulationMode.FAST_FORWARD
                else None
            ),
        )
        weather_results.extend(atmospheric_result.weather_states)

    triggered_events = list(
        campaign.events.select_for_update()
        .select_related("region")
        .filter(
            status=WorldEvent.Status.PLANNED,
            trigger_at__gt=old_time,
            trigger_at__lte=new_time,
        )
    )
    for event in triggered_events:
        event.status = WorldEvent.Status.TRIGGERED
        event.triggered_at = event.trigger_at
    if triggered_events:
        WorldEvent.objects.bulk_update(
            triggered_events,
            fields=["status", "triggered_at"],
        )

    report = None
    if advanced_by is not None:
        requested_amount = requested_amount if requested_amount is not None else minutes
        requested_unit = requested_unit or TimeAdvanceReport.RequestedUnit.MINUTES
        valid_units = {value for value, _label in TimeAdvanceReport.RequestedUnit.choices}
        if requested_unit not in valid_units or requested_amount < 1:
            raise ValueError("Недопустимые исходные параметры отчёта времени.")
        summary = build_time_advance_summary(
            campaign,
            regions,
            weather_results,
            triggered_events,
            start=old_time,
            end=new_time,
            amount=requested_amount,
            unit=requested_unit,
            simulation_mode=plan.mode,
            weather_coverage_start=plan.detailed_start,
            atmospheric_summary=(
                None
                if atmospheric_result is None
                else atmospheric_result.ocean_summary
            ),
        )
        report = TimeAdvanceReport.objects.create(
            campaign=campaign,
            gm=advanced_by,
            start_world_minutes=old_time,
            end_world_minutes=new_time,
            requested_amount=requested_amount,
            requested_unit=requested_unit,
            simulation_mode=plan.mode,
            coverage=plan.coverage,
            summary=summary,
        )

    return WorldAdvanceResult(
        campaign=campaign,
        weather_states=weather_results,
        world_events=triggered_events,
        report=report,
    )
