import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone


class Character(models.Model):
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="characters",
    )
    owner = models.ForeignKey(
        "campaigns.CampaignMembership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="characters",
    )
    name = models.CharField(max_length=200)
    biography = models.TextField(blank=True)
    public_notes = models.TextField(blank=True)
    gm_notes = models.TextField(blank=True)
    portrait = models.ImageField(upload_to="characters/portraits/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["campaign", "is_active", "name"],
                name="character_campaign_active_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.owner_id and self.owner.campaign_id != self.campaign_id:
            raise ValidationError({"owner": "Владелец должен состоять в этой же кампании."})
        if self.is_active and self.archived_at is not None:
            raise ValidationError(
                {"archived_at": "У активного персонажа не может быть даты архивации."}
            )
        if not self.is_active and self.archived_at is None:
            self.archived_at = timezone.now()

    def __str__(self):
        return self.name


class CharacterLocationState(models.Model):
    """Durable world-facing position; absence means initial placement is pending."""

    character = models.OneToOneField(
        Character,
        on_delete=models.CASCADE,
        related_name="location_state",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=10, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="character_location_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lt=180),
                name="character_location_longitude_range",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            errors["latitude"] = "Широта должна находиться между -90 и 90 градусами."
        if self.longitude is not None and not -180 <= self.longitude < 180:
            errors["longitude"] = (
                "Долгота должна находиться в диапазоне от -180 включительно "
                "до 180 не включительно."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Исходное положение: {self.character}"


class CharacterNote(models.Model):
    """A private plain-text thought carried by the durable Character identity."""

    MAX_MEMO_LENGTH = 120
    MAX_BODY_LENGTH = 32 * 1024

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="personal_notes",
    )
    memo = models.CharField(max_length=MAX_MEMO_LENGTH, blank=True)
    body = models.TextField(
        max_length=MAX_BODY_LENGTH,
        validators=[MaxLengthValidator(MAX_BODY_LENGTH)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at", "-id")
        indexes = [
            models.Index(
                fields=("character", "updated_at"),
                name="char_note_character_time_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="character_note_body_not_empty",
            ),
        ]

    def clean(self):
        super().clean()
        self.memo = str(self.memo or "").strip()
        self.body = str(self.body or "").strip()
        if not self.body:
            raise ValidationError({"body": "Мысль не может быть пустой."})

    def __str__(self):
        return f"Удержанная мысль персонажа {self.character_id}"
