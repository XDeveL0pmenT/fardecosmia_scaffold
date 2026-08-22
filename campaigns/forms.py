from django import forms

from accounts.services.email_addresses import normalize_email_address
from .models import Campaign


class CampaignCreateForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ("name", "description")
        labels = {
            "name": "Название кампании",
            "description": "Краткое описание",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Укажите название кампании.")
        return name


class CampaignBasicForm(CampaignCreateForm):
    pass


class CampaignInvitationForm(forms.Form):
    email = forms.EmailField(
        label="Email будущего игрока",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "player@example.com",
            }
        ),
        help_text="Приглашение сможет принять только аккаунт с этим подтверждённым email.",
    )

    def clean_email(self):
        return normalize_email_address(self.cleaned_data["email"])


class TimeSimulationSettingsForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = (
            "exact_simulation_max_turns",
            "fast_forward_spinup_turns",
        )
        labels = {
            "exact_simulation_max_turns": "Точная симуляция до, Витков",
            "fast_forward_spinup_turns": "Финальный spin-up, Витков",
        }
        help_texts = {
            "exact_simulation_max_turns": (
                "Более длинная прокрутка использует fast-forward. "
                "Это технический порог, а не правило мира."
            ),
            "fast_forward_spinup_turns": (
                "Финальный отрезок, который после fast-forward рассчитывается подробно."
            ),
        }

    def clean(self):
        cleaned = super().clean()
        exact = cleaned.get("exact_simulation_max_turns")
        spinup = cleaned.get("fast_forward_spinup_turns")
        if exact is not None and spinup is not None and spinup > exact:
            raise forms.ValidationError(
                "Финальный spin-up не должен быть длиннее exact-порога."
            )
        return cleaned
