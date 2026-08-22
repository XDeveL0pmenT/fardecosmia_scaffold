from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from accounts.services.email_addresses import normalize_email_address


class User(AbstractUser):
    """
    Пользователь Фардекосмии.

    Не хранит роль "игрок/мастер" глобально: роль определяется отдельно
    через CampaignMembership, потому что один и тот же человек может быть
    мастером одной кампании и игроком другой.
    """

    display_name = models.CharField(
        "Отображаемое имя",
        max_length=120,
        blank=True,
    )
    avatar = models.ImageField(
        "Аватар",
        upload_to="users/avatars/",
        blank=True,
        null=True,
    )
    email_verified_at = models.DateTimeField(
        "Email подтверждён",
        null=True,
        blank=True,
        editable=False,
    )
    verified_email = models.EmailField(
        "Подтверждённый email",
        max_length=254,
        blank=True,
        editable=False,
    )
    email_verification_required = models.BooleanField(
        "Требовать подтверждение email",
        default=False,
        help_text=(
            "Включается для публичной регистрации и поддерживаемой смены email. "
            "Старые аккаунты не помечаются подтверждёнными автоматически."
        ),
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
            ),
        ]

    @property
    def has_verified_email(self):
        normalized = normalize_email_address(self.email)
        return bool(
            normalized
            and self.email_verified_at is not None
            and self.verified_email == normalized
        )

    def clean(self):
        super().clean()
        self.email = normalize_email_address(self.email)
        self.verified_email = normalize_email_address(self.verified_email)
        if self.email_verified_at is not None and self.verified_email != self.email:
            self.email_verified_at = None
            self.verified_email = ""
            self.email_verification_required = True

    def save(self, *args, **kwargs):
        self.email = normalize_email_address(self.email)
        self.verified_email = normalize_email_address(self.verified_email)
        email_changed = False
        if self.pk:
            previous_email = (
                type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()
            )
            email_changed = (
                previous_email is not None
                and normalize_email_address(previous_email) != self.email
            )
        if email_changed or (
            self.email_verified_at is not None and self.verified_email != self.email
        ):
            self.email_verified_at = None
            self.verified_email = ""
            self.email_verification_required = True
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {
                    "email",
                    "email_verified_at",
                    "verified_email",
                    "email_verification_required",
                }
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.username


class EmailVerificationChallenge(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="email_verification_challenges",
    )
    email_snapshot = models.EmailField(max_length=254)
    code_hash = models.CharField(max_length=256)
    generation = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_failed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "created_at"],
                name="email_verify_user_time_idx",
            ),
            models.Index(fields=["expires_at"], name="email_verify_expires_idx"),
        ]

    def __str__(self):
        return f"Подтверждение email для {self.user}"
