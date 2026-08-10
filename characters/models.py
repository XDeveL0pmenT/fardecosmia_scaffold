from django.core.exceptions import ValidationError
from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.owner_id and self.owner.campaign_id != self.campaign_id:
            raise ValidationError({"owner": "Владелец должен состоять в этой же кампании."})

    def __str__(self):
        return self.name
