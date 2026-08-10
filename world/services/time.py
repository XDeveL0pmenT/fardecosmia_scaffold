from django.db import transaction

from campaigns.models import Campaign
from world.models import AtmosphericConfig, WorldEvent
from world.services.atmosphere.persistence import advance_atmosphere_for_period
from world.services.atmosphere.sampling import weather_for_regions_from_snapshots
from world.services.weather import update_weather_for_period


@transaction.atomic
def advance_world(campaign_id, minutes):
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
        raise ValueError("Мир можно продвигать только на положительное число минут.")

    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    old_time = campaign.world_minutes
    new_time = old_time + minutes

    campaign.world_minutes = new_time
    campaign.save(update_fields=["world_minutes"])

    weather_results = []
    regions = list(campaign.regions.select_related("campaign").all())
    atmospheric_config = (
        AtmosphericConfig.objects.select_for_update()
        .filter(campaign=campaign, enabled=True)
        .first()
    )
    if atmospheric_config is None:
        for region in regions:
            weather_results.extend(update_weather_for_period(region, old_time, new_time))
    else:
        snapshots = advance_atmosphere_for_period(
            campaign,
            atmospheric_config,
            old_time,
            new_time,
        )
        located_regions = []
        for region in regions:
            if region.map_latitude is None or region.map_longitude is None:
                weather_results.extend(update_weather_for_period(region, old_time, new_time))
                continue
            located_regions.append(region)
        weather_results.extend(
            weather_for_regions_from_snapshots(
                located_regions,
                snapshots,
                parameters=atmospheric_config.parameters,
            )
        )

    triggered_events = list(
        campaign.events.select_for_update().filter(
            status=WorldEvent.Status.PLANNED,
            trigger_at__gt=old_time,
            trigger_at__lte=new_time,
        )
    )
    for event in triggered_events:
        event.status = WorldEvent.Status.TRIGGERED
        event.triggered_at = event.trigger_at
        event.save(update_fields=["status", "triggered_at"])

    return campaign, weather_results, triggered_events
