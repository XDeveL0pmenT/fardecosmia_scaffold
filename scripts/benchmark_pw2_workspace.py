"""Small rollback-only render benchmark for the PW2 handoff report."""

from time import perf_counter

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from campaigns.models import Campaign, CampaignMembership
from campaigns.views import campaign_detail
from characters.models import Character, CharacterLocationState
from world.models import AtmosphericConfig
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint
from world.services.atmosphere.grid import AtmosphericGrid
from world.services.atmosphere.persistence import save_snapshot


def measure(*, label, request_factory, user, campaign):
    warm_request = request_factory.get("/")
    warm_request.user = user
    campaign_detail(warm_request, campaign.pk)

    samples_ms = []
    query_counts = []
    for _iteration in range(20):
        request = request_factory.get("/")
        request.user = user
        started = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            response = campaign_detail(request, campaign.pk)
        samples_ms.append((perf_counter() - started) * 1000.0)
        query_counts.append(len(queries))

    print(
        f"PW2_WORKSPACE_BENCHMARK mode={label} "
        f"render_ms_avg={sum(samples_ms) / len(samples_ms):.3f} "
        f"render_ms_min={min(samples_ms):.3f} "
        f"render_ms_max={max(samples_ms):.3f} "
        f"queries={sorted(set(query_counts))} "
        f"status={response.status_code}"
    )


with transaction.atomic():
    user = get_user_model().objects.create_user(
        username="pw2-benchmark-temp",
        password="not-used",
    )
    campaign = Campaign.objects.create(name="PW2 benchmark temp")
    membership = CampaignMembership.objects.create(
        campaign=campaign,
        user=user,
        role=CampaignMembership.Role.PLAYER,
    )
    character = Character.objects.create(
        campaign=campaign,
        owner=membership,
        name="Benchmark",
    )

    request_factory = RequestFactory()
    measure(
        label="neutral",
        request_factory=request_factory,
        user=user,
        campaign=campaign,
    )

    CharacterLocationState.objects.create(
        character=character,
        latitude=0,
        longitude=0,
    )
    config = AtmosphericConfig.objects.create(
        campaign=campaign,
        enabled=True,
        grid_width=24,
        grid_height=12,
        step_minutes=360,
    )
    campaign.refresh_from_db()
    config.refresh_from_db()
    atmospheric_settings = AtmosphericSettings.from_model(config, campaign)
    grid = AtmosphericGrid.empty(
        atmospheric_settings.width,
        atmospheric_settings.height,
    )
    grid.fields["temperature"].fill(24.0)
    grid.fields["water_vapor_specific_humidity"].fill(0.006)
    grid.fields["cloud_condensate_specific_humidity"].fill(0.0)
    grid.fields["circulation_pressure_hpa"].fill(1000.0)
    grid.fields["pressure_hpa"].fill(1000.0)
    grid.fields["wind_u"].fill(2.0)
    grid.fields["wind_v"].fill(0.0)
    grid.fields["cloud_cover"].fill(0.25)
    grid.fields["precipitation_rate"].fill(0.0)
    grid.fields["surface_temperature"].fill(24.0)
    grid.fields["sea_surface_temperature_c"].fill(24.0)
    save_snapshot(
        campaign,
        campaign.world_minutes,
        grid,
        input_fingerprint=atmospheric_input_fingerprint(campaign, config),
    )
    measure(
        label="live-point",
        request_factory=request_factory,
        user=user,
        campaign=campaign,
    )
    transaction.set_rollback(True)
