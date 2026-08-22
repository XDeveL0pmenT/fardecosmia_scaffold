from django import forms
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from accounts.services.email import send_templated_email
from accounts.services.email_addresses import normalize_email_address


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        label="Email",
        required=True,
        error_messages={"required": "Укажите email-адрес."},
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        labels = {"username": "Имя пользователя"}
        widgets = {
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Пароль"
        self.fields["password2"].label = "Повтор пароля"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data.get("email"))
        if not email:
            raise forms.ValidationError("Укажите email-адрес.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Аккаунт с таким email уже существует. Попробуйте войти или восстановить пароль."
            )
        return email


class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        label="Код подтверждения",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "pattern": "[0-9]{6}",
                "placeholder": "000000",
            }
        ),
        error_messages={
            "required": "Введите шестизначный код из письма.",
            "min_length": "Код состоит из шести цифр.",
            "max_length": "Код состоит из шести цифр.",
        },
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isascii() or not code.isdigit():
            raise forms.ValidationError("Код состоит только из шести цифр.")
        return code


class FardecosmiaPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def clean_email(self):
        return normalize_email_address(self.cleaned_data["email"])

    def get_users(self, email):
        users = User._default_manager.filter(email__iexact=normalize_email_address(email))
        return (
            user
            for user in users
            if user.is_active
            and user.has_usable_password()
            and (user.has_verified_email or user.is_staff or user.is_superuser)
        )

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        send_templated_email(
            to_email=to_email,
            subject_template=subject_template_name,
            text_template=email_template_name,
            html_template=html_email_template_name,
            context=context,
        )
