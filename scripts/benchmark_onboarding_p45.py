"""Rollback-only P4.5 service timings and server-rendered query counts.

Email delivery is replaced with a successful in-process result so the numbers
measure application work rather than network/provider latency.  All rows are
created inside one transaction and rolled back at the end.
"""

import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid
from datetime import timedelta
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailVerificationChallenge, User
from accounts.services.email import EmailDeliveryResult
from accounts.services.registration import register_account
from accounts.services.verification import verify_email_code
from campaigns.models import Campaign, CampaignInvitation, CampaignMembership
from campaigns.services.invitations import (
    accept_campaign_invitation,
    create_campaign_invitation,
)
from campaigns.services.lifecycle import create_campaign


PASSWORD = "Orbit!7826Nebula"
CODE = "425731"


def timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return (time.perf_counter() - started) * 1000.0, value


def make_verified_user(username, email):
    user = User.objects.create_user(username=username, email=email, password=None)
    user.verified_email = user.email
    user.email_verified_at = timezone.now()
    user.email_verification_required = True
    user.save(
        update_fields=[
            "verified_email",
            "email_verified_at",
            "email_verification_required",
        ]
    )
    return user


def main(repetitions=5):
    token = uuid.uuid4().hex[:10]
    with transaction.atomic():
        registration_times = []
        with patch(
            "accounts.services.verification.send_verification_email",
            return_value=EmailDeliveryResult(sent=True),
        ):
            for index in range(repetitions):
                elapsed, _result = timed(
                    lambda index=index: register_account(
                        username=f"p45-register-{token}-{index}",
                        email=f"register-{token}-{index}@example.invalid",
                        password=PASSWORD,
                    )
                )
                registration_times.append(elapsed)

        verification_users = []
        for index in range(repetitions):
            user = User.objects.create_user(
                username=f"p45-verify-{token}-{index}",
                email=f"verify-{token}-{index}@example.invalid",
                password=None,
                email_verification_required=True,
            )
            EmailVerificationChallenge.objects.create(
                user=user,
                email_snapshot=user.email,
                code_hash=make_password(CODE),
                expires_at=timezone.now() + timedelta(minutes=10),
                sent_at=timezone.now(),
            )
            verification_users.append(user)
        verification_times = [
            timed(lambda user=user: verify_email_code(user=user, code=CODE))[0]
            for user in verification_users
        ]

        gm = make_verified_user(
            f"p45-gm-{token}",
            f"gm-{token}@example.invalid",
        )
        campaign_times = []
        campaigns = []
        for index in range(repetitions):
            elapsed, campaign = timed(
                lambda index=index: create_campaign(
                    actor=gm,
                    name=f"P4.5 benchmark {token}-{index}",
                )
            )
            campaign_times.append(elapsed)
            campaigns.append(campaign)

        campaign = campaigns[0]
        invitation_times = []
        invitations = []
        for index in range(repetitions):
            email = f"invite-{token}-{index}@example.invalid"
            elapsed, result = timed(
                lambda email=email: create_campaign_invitation(
                    campaign=campaign,
                    actor=gm,
                    email=email,
                )
            )
            invitation_times.append(elapsed)
            invitations.append(result)

        acceptance_times = []
        for index, invitation in enumerate(invitations):
            player = make_verified_user(
                f"p45-player-{token}-{index}",
                invitation.invitation.email_normalized,
            )
            elapsed, _result = timed(
                lambda invitation=invitation, player=player: accept_campaign_invitation(
                    token=invitation.token,
                    actor=player,
                )
            )
            acceptance_times.append(elapsed)

        # Populate enough rows to expose accidental template N+1 behavior.
        list_user = make_verified_user(
            f"p45-list-{token}",
            f"list-{token}@example.invalid",
        )
        for index in range(12):
            listed_campaign = Campaign.objects.create(
                name=f"Listed {token}-{index}"
            )
            CampaignMembership.objects.create(
                campaign=listed_campaign,
                user=list_user,
                role=(
                    CampaignMembership.Role.GM
                    if index % 2 == 0
                    else CampaignMembership.Role.PLAYER
                ),
            )
        for index in range(20):
            member = make_verified_user(
                f"p45-member-{token}-{index}",
                f"member-{token}-{index}@example.invalid",
            )
            CampaignMembership.objects.create(campaign=campaign, user=member)
        now = timezone.now()
        for index in range(20):
            raw_token = f"b{index:02d}-{token}-" + ("x" * 32)
            CampaignInvitation.objects.create(
                campaign=campaign,
                email_normalized=f"pending-{token}-{index}@example.invalid",
                created_by=gm,
                created_by_label_snapshot=str(gm),
                expires_at=now + timedelta(days=7),
                token_prefix=raw_token[:16],
                token_hash=make_password(raw_token),
            )

        client = Client(HTTP_HOST="localhost")
        client.force_login(list_user)
        list_url = reverse("campaigns:list")
        client.get(list_url)
        with CaptureQueriesContext(connection) as list_queries:
            list_response = client.get(list_url)

        client.force_login(gm)
        members_url = reverse("campaigns:members", args=[campaign.pk])
        client.get(members_url)
        with CaptureQueriesContext(connection) as members_queries:
            members_response = client.get(members_url)

        result = {
            "repetitions": repetitions,
            "registration_without_network_median_ms": statistics.median(
                registration_times
            ),
            "verification_median_ms": statistics.median(verification_times),
            "campaign_create_median_ms": statistics.median(campaign_times),
            "invite_create_median_ms": statistics.median(invitation_times),
            "invite_accept_median_ms": statistics.median(acceptance_times),
            "campaign_list_rows": 12,
            "campaign_list_query_count": len(list_queries),
            "campaign_list_response_bytes": len(list_response.content),
            "members_page_members": 21,
            "members_page_invites": 25,
            "members_page_query_count": len(members_queries),
            "members_page_response_bytes": len(members_response.content),
        }
        transaction.set_rollback(True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
