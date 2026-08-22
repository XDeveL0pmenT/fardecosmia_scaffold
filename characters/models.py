from django.core.exceptions import ValidationError
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
