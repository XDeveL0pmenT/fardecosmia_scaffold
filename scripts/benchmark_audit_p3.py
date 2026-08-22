"""Small non-unit benchmark for the P3 AuditLog write/read overhead."""

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

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from campaigns.models import Campaign, TimeAdvanceReport
from world.models import AuditLog, Region, WorldEntry
from world.services.canon import create_global_world_entry
from world.services.regions import update_region
from world.services.time import advance_world


def timed(callable_):
    started = time.perf_counter()
    callable_()
    return (time.perf_counter() - started) * 1000.0


def main(repetitions=12):
    token = uuid.uuid4().hex[:10]
    with transaction.atomic():
        actor = User.objects.create_superuser(
            username=f"audit-benchmark-{token}",
            email=f"{token}@example.invalid",
            password=None,
        )
        campaign = Campaign.objects.create(name=f"Audit benchmark {token}")
        region = Region.objects.create(campaign=campaign, name="Benchmark region")

        raw_world = []
        audited_world = []
        for index in range(repetitions):
            raw_world.append(
                timed(
                    lambda index=index: _raw_world_entry(
                        token=token,
                        index=index,
                    )
                )
            )
            audited_world.append(
                timed(
                    lambda index=index: create_global_world_entry(
                        actor=actor,
                        kind="benchmark",
                        slug=f"audited-{token}-{index}",
                        title=f"Audited {index}",
                    )
                )
            )

        raw_region = []
        audited_region = []
        for index in range(repetitions):
            raw_region.append(
                timed(lambda index=index: _raw_region_rename(region, f"Raw {index}"))
            )
            audited_region.append(
                timed(
                    lambda index=index: update_region(
                        actor=actor,
                        campaign=campaign,
                        region=region,
                        changes={"name": f"Audited {index}"},
                    )
                )
            )
            region.refresh_from_db()

        exact_raw_campaign = Campaign.objects.create(name="Vitok without report")
        exact_audit_campaign = Campaign.objects.create(name="Vitok with report and audit")
        vitok_without_user_boundary_ms = timed(
            lambda: advance_world(
                exact_raw_campaign.pk,
                exact_raw_campaign.calendar_minutes_per_turn,
            )
        )
        vitok_with_report_audit_ms = timed(
            lambda: advance_world(
                exact_audit_campaign.pk,
                exact_audit_campaign.calendar_minutes_per_turn,
                advanced_by=actor,
                requested_amount=1,
                requested_unit=TimeAdvanceReport.RequestedUnit.TURNS,
            )
        )

        with CaptureQueriesContext(connection) as query_context:
            rows = list(
                AuditLog.objects.select_related(
                    "campaign",
                    "actor",
                    "target_content_type",
                ).order_by("-occurred_at", "-id")[:50]
            )
            for row in rows:
                _ = (row.campaign, row.actor, row.target_content_type)

        result = {
            "repetitions": repetitions,
            "world_entry_raw_median_ms": statistics.median(raw_world),
            "world_entry_audited_median_ms": statistics.median(audited_world),
            "world_entry_increment_ms": (
                statistics.median(audited_world) - statistics.median(raw_world)
            ),
            "region_rename_raw_median_ms": statistics.median(raw_region),
            "region_rename_audited_median_ms": statistics.median(audited_region),
            "region_rename_increment_ms": (
                statistics.median(audited_region) - statistics.median(raw_region)
            ),
            "vitok_without_user_boundary_ms": vitok_without_user_boundary_ms,
            "vitok_with_report_and_audit_ms": vitok_with_report_audit_ms,
            "audit_list_rows": len(rows),
            "audit_list_queries": len(query_context),
        }
        transaction.set_rollback(True)
    print(json.dumps(result, indent=2, sort_keys=True))


def _raw_world_entry(*, token, index):
    entry = WorldEntry(
        scope=WorldEntry.Scope.GLOBAL,
        kind="benchmark",
        slug=f"raw-{token}-{index}",
        title=f"Raw {index}",
    )
    entry.full_clean()
    entry.save()


def _raw_region_rename(region, name):
    region.name = name
    region.full_clean()
    region.save(update_fields=["name"])


if __name__ == "__main__":
    main()
