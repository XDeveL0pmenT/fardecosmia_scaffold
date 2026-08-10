import secrets
import uuid

from django.contrib.auth.hashers import make_password
from django.db import models


class Roll20Connection(models.Model):
    SHEET_DND5E_2014 = "dnd5e_2014"

    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="roll20_connections",
    )
    roll20_game_id = models.CharField(max_length=100, blank=True)
    sheet_type = models.CharField(max_length=50, default=SHEET_DND5E_2014)
    protocol_version = models.PositiveIntegerField(default=1)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.campaign} / Roll20"


class Roll20DeviceToken(models.Model):
    connection = models.ForeignKey(
        Roll20Connection,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    name = models.CharField(max_length=100, default="Browser Extension")
    token_prefix = models.CharField(max_length=20, unique=True)
    token_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, connection, name="Browser Extension"):
        raw_token = secrets.token_urlsafe(48)
        device = cls.objects.create(
            connection=connection,
            name=name,
            token_prefix=raw_token[:16],
            token_hash=make_password(raw_token),
        )
        return device, raw_token

    def __str__(self):
        return f"{self.name} / {self.connection}"


class Roll20CharacterBinding(models.Model):
    connection = models.ForeignKey(
        Roll20Connection,
        on_delete=models.CASCADE,
        related_name="character_bindings",
    )
    character = models.OneToOneField(
        "characters.Character",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roll20_binding",
    )
    roll20_character_id = models.CharField(max_length=100)
    roll20_name = models.CharField(max_length=255, blank=True)
    raw_attributes = models.JSONField(default=dict, blank=True)
    normalized_state = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "roll20_character_id"],
                name="unique_roll20_character_per_connection",
            )
        ]

    def __str__(self):
        return self.roll20_name or self.roll20_character_id


class Roll20SyncEvent(models.Model):
    class Kind(models.TextChoices):
        SNAPSHOT = "snapshot", "Snapshot"
        DELTA = "delta", "Delta"

    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    binding = models.ForeignKey(
        Roll20CharacterBinding,
        on_delete=models.CASCADE,
        related_name="sync_events",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]


class Roll20Command(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        CONFLICT = "conflict", "Conflict"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    binding = models.ForeignKey(
        Roll20CharacterBinding,
        on_delete=models.CASCADE,
        related_name="commands",
    )
    command_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
