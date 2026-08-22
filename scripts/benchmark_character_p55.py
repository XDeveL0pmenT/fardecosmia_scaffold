"""Rollback-only P5.5 query/time benchmark for the development database."""

from __future__ import annotations

import os
from pathlib import Path
import statistics
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

from campaigns.models import Campaign, CampaignMembership  # noqa: E402
from characters.models import Character  # noqa: E402
from characters.services import assign_character, set_active_character  # noqa: E402


def timed_ms(callable_, *, repeats=12):
    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        callable_()
        timings.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(timings)


def request_measure(client, url):
    started = time.perf_counter()
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    elapsed = (time.perf_counter() - started) * 1000.0
    if response.status_code != 200:
        raise RuntimeError(f"Unexpected HTTP {response.status_code} for {url}")
    return len(queries), elapsed


def main():
    suffix = uuid.uuid4().hex[:10]
    with transaction.atomic():
        users = get_user_model().objects
        gm = users.create_user(username=f"bench-gm-{suffix}")
        player = users.create_user(username=f"bench-player-{suffix}")
        other = users.create_user(username=f"bench-other-{suffix}")
        campaign = Campaign.objects.create(name=f"P5.5 benchmark {suffix}")
        CampaignMembership.objects.create(
            campaign=campaign,
            user=gm,
            role=CampaignMembership.Role.GM,
        )
        player_membership = CampaignMembership.objects.create(
            campaign=campaign,
            user=player,
            role=CampaignMembership.Role.PLAYER,
        )
        other_membership = CampaignMembership.objects.create(
            campaign=campaign,
            user=other,
            role=CampaignMembership.Role.PLAYER,
        )
        characters = [
            Character.objects.create(
                campaign=campaign,
                owner=player_membership if index < 3 else None,
                name=f"Benchmark Character {index:02d}",
            )
            for index in range(20)
        ]
        player_membership.active_character = characters[0]
        player_membership.save(update_fields=["active_character"])

        player_client = Client(HTTP_HOST="localhost")
        player_client.force_login(player)
        gm_client = Client(HTTP_HOST="localhost")
        gm_client.force_login(gm)
        results = {
            "player_dashboard": request_measure(
                player_client,
                reverse("campaigns:campaign_detail", args=[campaign.pk]),
            ),
            "player_character_list": request_measure(
                player_client,
                reverse("characters:player_list", args=[campaign.pk]),
            ),
            "gm_character_list_20": request_measure(
                gm_client,
                reverse("characters:gm_list", args=[campaign.pk]),
            ),
            "gm_character_detail": request_measure(
                gm_client,
                reverse("characters:detail", args=[campaign.pk, characters[0].pk]),
            ),
        }

        assign_target = characters[-1]
        target_memberships = [player_membership, other_membership]
        assignment_index = 0

        def alternate_assignment():
            nonlocal assignment_index
            membership = target_memberships[assignment_index % 2]
            assignment_index += 1
            assign_character(
                campaign=campaign,
                character_id=assign_target.pk,
                actor=gm,
                membership_id=membership.pk,
            )

        switch_index = 0

        def alternate_active():
            nonlocal switch_index
            character = characters[switch_index % 2]
            switch_index += 1
            set_active_character(
                campaign=campaign,
                actor=player,
                character_id=character.pk,
            )

        assignment_median = timed_ms(alternate_assignment)
        switch_median = timed_ms(alternate_active)

        print("P5.5 CHARACTER BENCHMARK (rollback-only)")
        for label, (query_count, elapsed_ms) in results.items():
            print(f"{label}: queries={query_count}, elapsed_ms={elapsed_ms:.3f}")
        print(f"assignment_median_ms={assignment_median:.3f}")
        print(f"switch_active_median_ms={switch_median:.3f}")
        transaction.set_rollback(True)


if __name__ == "__main__":
    main()
