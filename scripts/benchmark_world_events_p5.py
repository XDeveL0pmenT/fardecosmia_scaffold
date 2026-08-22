"""Rollback-only benchmark for P5 WorldEvent lookup, crossing and GM pages."""

from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connection, transaction  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

from accounts.models import User  # noqa: E402
from campaigns.models import Campaign  # noqa: E402
from world.models import WorldEvent  # noqa: E402
from world.services.events import execute_due_world_events  # noqa: E402
from world.services.time import advance_world  # noqa: E402


def timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return (time.perf_counter() - started) * 1000.0, value


def main(repetitions=25):
    with transaction.atomic():
        token = uuid.uuid4().hex[:10]
        actor = User.objects.create_superuser(
            username=f"event-benchmark-{token}",
            email=f"{token}@example.invalid",
            password="benchmark-pass",
        )
        empty_campaign = Campaign.objects.create(name=f"P5 empty {token}")
        crossing_campaign = Campaign.objects.create(name=f"P5 crossing {token}")

        zero_due_times = []
        zero_due_query_counts = []
        for _index in range(repetitions):
            with CaptureQueriesContext(connection) as queries:
                elapsed, result = timed(
                    lambda: execute_due_world_events(
                        campaign=empty_campaign,
                        start_world_minutes=0,
                        end_world_minutes=60,
                    )
                )
            assert result == []
            zero_due_times.append(elapsed)
            zero_due_query_counts.append(len(queries))

        WorldEvent.objects.bulk_create(
            [
                WorldEvent(
                    campaign=crossing_campaign,
                    title=f"Benchmark event {index + 1}",
                    trigger_at=(index + 1) * 10,
                )
                for index in range(10)
            ]
        )
        with CaptureQueriesContext(connection) as upcoming_queries:
            upcoming_ms, upcoming = timed(
                lambda: list(
                    WorldEvent.objects.filter(
                        campaign=crossing_campaign,
                        enabled=True,
                        trigger_type=WorldEvent.TriggerType.WORLD_TIME,
                        trigger_at__gt=0,
                        occurrences__isnull=True,
                    ).order_by("trigger_at", "id")
                )
            )
        upcoming_query_count = len(upcoming_queries)
        with CaptureQueriesContext(connection) as crossing_queries:
            crossing_ms, result = timed(
                lambda: advance_world(crossing_campaign.pk, 100)
            )
        crossing_query_count = len(crossing_queries)
        assert len(upcoming) == 10
        assert len(result.world_events) == 10

        pending = WorldEvent.objects.create(
            campaign=crossing_campaign,
            title="Pending UI benchmark",
            trigger_at=200,
        )
        client = Client(HTTP_HOST="localhost")
        client.force_login(actor)
        list_url = reverse("world:campaign_event_list", args=[crossing_campaign.pk])
        detail_url = reverse(
            "world:world_event_definition_detail",
            args=[crossing_campaign.pk, pending.pk],
        )
        client.get(list_url)
        client.get(detail_url)
        with CaptureQueriesContext(connection) as list_queries:
            list_ms, list_response = timed(lambda: client.get(list_url))
        list_query_count = len(list_queries)
        with CaptureQueriesContext(connection) as detail_queries:
            detail_ms, detail_response = timed(lambda: client.get(detail_url))
        detail_query_count = len(detail_queries)

        output = {
            "repetitions": repetitions,
            "zero_due_median_ms": statistics.median(zero_due_times),
            "zero_due_query_count_median": statistics.median(zero_due_query_counts),
            "ten_upcoming_lookup_ms": upcoming_ms,
            "ten_upcoming_lookup_queries": upcoming_query_count,
            "advance_crossing_ten_events_ms": crossing_ms,
            "advance_crossing_ten_events_queries": crossing_query_count,
            "event_list_ms": list_ms,
            "event_list_queries": list_query_count,
            "event_list_response_bytes": len(list_response.content),
            "event_detail_ms": detail_ms,
            "event_detail_queries": detail_query_count,
            "event_detail_response_bytes": len(detail_response.content),
        }
        transaction.set_rollback(True)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
