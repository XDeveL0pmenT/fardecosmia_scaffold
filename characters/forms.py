from django import forms
from decimal import Decimal

from campaigns.models import CampaignMembership
from characters.models import Character


class CharacterIdentityForm(forms.ModelForm):
    class Meta:
        model = Character
        fields = ("name", "biography")
        labels = {
            "name": "Имя персонажа",
            "biography": "Краткое описание",
        }
        help_texts = {
            "biography": (
                "Коротко опишите, кем является персонаж в мире. "
                "Боевые характеристики по-прежнему хранятся в Roll20."
            ),
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "biography": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Укажите имя персонажа.")
        return name

    def clean_biography(self):
        return self.cleaned_data["biography"].strip()


class PlayerMembershipChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, membership):
        user = membership.user
        return str(user.display_name or user.username)


class CharacterAssignmentForm(forms.Form):
    player = PlayerMembershipChoiceField(
        label="Игрок",
        queryset=CampaignMembership.objects.none(),
        required=False,
        empty_label="Игрок не назначен",
        help_text="Выбрать можно только игрока из этой кампании.",
    )

    def __init__(self, *args, campaign, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["player"].queryset = (
            campaign.memberships.filter(role=CampaignMembership.Role.PLAYER)
            .select_related("user")
            .order_by("user__display_name", "user__username")
        )


class CharacterInitialPlacementForm(forms.Form):
    latitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
        widget=forms.HiddenInput(),
    )
    longitude = forms.DecimalField(
        max_digits=10,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
        widget=forms.HiddenInput(),
    )
    confirmed = forms.BooleanField(
        label="Я проверил выбранную точку и подтверждаю исходное положение.",
        required=True,
    )
