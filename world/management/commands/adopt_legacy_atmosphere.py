from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from campaigns.models import Campaign
from world.atmosphere_defaults import (
    ATMOSPHERIC_FORMAT_VERSION,
    ATMOSPHERIC_SOLVER_VERSION,
)
from world.models import AtmosphericConfig, AtmosphericSnapshot
from world.services.atmosphere.fingerprint import atmospheric_input_fingerprint


class Command(BaseCommand):
    help = (
        "Explicitly copy the latest compatible-shaped pre-fingerprint snapshot "
        "into the current input-fingerprint branch. The legacy row is retained."
    )

    def add_arguments(self, parser):
        parser.add_argument("campaign_id")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Create the versioned copy. Without this flag the command is read-only.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            campaign = Campaign.objects.get(pk=options["campaign_id"])
        except (Campaign.DoesNotExist, ValueError) as exc:
            raise CommandError("Campaign not found.") from exc
        try:
            config = AtmosphericConfig.objects.get(campaign=campaign, enabled=True)
        except AtmosphericConfig.DoesNotExist as exc:
            raise CommandError("The campaign has no enabled AtmosphericConfig.") from exc

        legacy = (
            campaign.atmospheric_snapshots.filter(
                input_fingerprint="",
                world_minutes__lte=campaign.world_minutes,
            )
            .order_by("-world_minutes", "-created_at")
            .first()
        )
        if legacy is None:
            raise CommandError("No legacy snapshot exists at or before campaign time.")
        if (legacy.grid_width, legacy.grid_height) != (
            config.grid_width,
            config.grid_height,
        ):
            raise CommandError("Legacy grid dimensions do not match AtmosphericConfig.")
        if legacy.format_version != ATMOSPHERIC_FORMAT_VERSION:
            raise CommandError("Legacy payload format is not supported by this solver.")
        if legacy.solver_version != ATMOSPHERIC_SOLVER_VERSION:
            raise CommandError("Legacy solver version is not compatible with this solver.")

        fingerprint = atmospheric_input_fingerprint(campaign, config)
        if campaign.atmospheric_snapshots.filter(
            input_fingerprint=fingerprint,
        ).exists():
            raise CommandError("A snapshot branch for the current fingerprint already exists.")
        action = "ADOPT" if options["confirm"] else "DRY RUN"
        self.stdout.write(
            f"{action}: legacy snapshot {legacy.pk} at {legacy.world_minutes}; "
            f"fingerprint {fingerprint}. Original row will be retained."
        )
        if not options["confirm"]:
            return
        AtmosphericSnapshot.objects.create(
            campaign=campaign,
            world_minutes=legacy.world_minutes,
            grid_width=legacy.grid_width,
            grid_height=legacy.grid_height,
            format_version=legacy.format_version,
            solver_version=ATMOSPHERIC_SOLVER_VERSION,
            input_fingerprint=fingerprint,
            is_checkpoint=False,
            payload=legacy.payload,
        )
        self.stdout.write(self.style.SUCCESS("Created versioned copy."))
