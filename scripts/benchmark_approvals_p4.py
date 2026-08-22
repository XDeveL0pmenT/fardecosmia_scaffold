"""Rollback-only benchmark for P4 service and server-rendered UI overhead."""

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
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from campaigns.models import Campaign
from world.services.approvals import (
    ApprovalPresentation,
    approve_request,
    create_approval_request,
    register_approval_handler,
    unregister_approval_handler,
)


REQUEST_TYPE = "benchmark.approval"


def timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return (time.perf_counter() - started) * 1000.0, value


def main(repetitions=20):
    unregister_approval_handler(REQUEST_TYPE)
    register_approval_handler(
        REQUEST_TYPE,
        request_type_label="Benchmark request",
        validator=lambda payload: payload,
        presenter=lambda subject: ApprovalPresentation(
            request_type_label="Benchmark request",
            title="Benchmark approval",
            summary="Measures framework overhead without a domain mutation.",
            details=(("Value", str(subject.payload["value"])),),
            consequences=("No domain state is changed.",),
        ),
        revalidate=lambda subject: None,
        apply=lambda subject, actor, operation_id: {},
    )
    try:
        with transaction.atomic():
            token = uuid.uuid4().hex[:10]
            actor = User.objects.create_superuser(
                username=f"approval-benchmark-{token}",
                email=f"{token}@example.invalid",
                password="benchmark-pass",
            )
            campaign = Campaign.objects.create(name=f"Approval benchmark {token}")

            create_times = []
            approve_times = []
            approvals = []
            for index in range(repetitions):
                elapsed, approval = timed(
                    lambda index=index: create_approval_request(
                        campaign=campaign,
                        requester=actor,
                        request_type=REQUEST_TYPE,
                        payload={"value": index},
                    )
                )
                create_times.append(elapsed)
                approvals.append(approval)
            for approval in approvals:
                elapsed, _ = timed(
                    lambda approval=approval: approve_request(
                        campaign=campaign,
                        request_id=approval.pk,
                        actor=actor,
                    )
                )
                approve_times.append(elapsed)

            pending = create_approval_request(
                campaign=campaign,
                requester=actor,
                request_type=REQUEST_TYPE,
                payload={"value": "pending"},
            )
            client = Client(HTTP_HOST="localhost")
            client.force_login(actor)
            queue_url = reverse("world:campaign_approval_queue", args=[campaign.pk])
            detail_url = reverse(
                "world:approval_request_detail",
                args=[campaign.pk, pending.pk],
            )
            client.get(queue_url)
            client.get(detail_url)
            with CaptureQueriesContext(connection) as queue_queries:
                queue_response = client.get(queue_url)
            with CaptureQueriesContext(connection) as detail_queries:
                detail_response = client.get(detail_url)

            result = {
                "repetitions": repetitions,
                "create_median_ms": statistics.median(create_times),
                "approve_framework_median_ms": statistics.median(approve_times),
                "queue_query_count": len(queue_queries),
                "detail_query_count": len(detail_queries),
                "queue_response_bytes": len(queue_response.content),
                "detail_response_bytes": len(detail_response.content),
            }
            transaction.set_rollback(True)
    finally:
        unregister_approval_handler(REQUEST_TYPE)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
