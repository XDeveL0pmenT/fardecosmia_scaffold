from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from campaigns.models import Campaign


class Command(BaseCommand):
    help = (
        "Preview or explicitly prune pre-fingerprint atmospheric snapshots. "
        "Regional WeatherState rows and versioned snapshots are never touched."
    )

    def add_arguments(self, parser):
        parser.add_argument("campaign_id")
        parser.add_argument(
            "--keep",
            type=int,
            default=1,
            help="Number of newest legacy snapshots to protect (minimum 1).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Perform deletion. Without this flag the command is read-only.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        keep = options["keep"]
        if keep < 1:
            raise CommandError("--keep must be at least 1 so the legacy tip is protected.")
        try:
            campaign = Campaign.objects.get(pk=options["campaign_id"])
        except (Campaign.DoesNotExist, ValueError) as exc:
            raise CommandError("Campaign not found.") from exc

        legacy = campaign.atmospheric_snapshots.filter(
            input_fingerprint="",
        ).order_by("-world_minutes", "-created_at")
        protected_ids = list(legacy.values_list("pk", flat=True)[:keep])
        candidates = legacy.exclude(pk__in=protected_ids)
        candidate_count = candidates.count()
        candidate_bytes = sum(
            len(bytes(payload))
            for payload in candidates.values_list("payload", flat=True).iterator()
        )
        action = "DELETE" if options["confirm"] else "DRY RUN"
        self.stdout.write(
            f"{action}: {candidate_count} legacy snapshots, "
            f"{candidate_bytes} payload bytes; protecting newest {len(protected_ids)}."
        )
        if not options["confirm"]:
            return
        deleted, _ = candidates.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} legacy snapshots."))
