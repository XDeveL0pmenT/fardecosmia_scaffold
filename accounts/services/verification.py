"""Secure email-verification challenge lifecycle."""

from dataclasses import dataclass
from datetime import timedelta
import math
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import EmailVerificationChallenge, User
from accounts.services.email import send_verification_email
from accounts.services.email_addresses import mask_email_address, normalize_email_address


class VerificationError(Exception):
    pass


class VerificationCooldown(VerificationError):
    def __init__(self, retry_after_seconds):
        self.retry_after_seconds = max(1, math.ceil(retry_after_seconds))
        minutes, seconds = divmod(self.retry_after_seconds, 60)
        super().__init__(
            f"Новый код можно отправить через {minutes:02d}:{seconds:02d}."
        )


class VerificationCodeInvalid(VerificationError):
    def __init__(self, attempts_left):
        self.attempts_left = max(0, int(attempts_left))
        super().__init__(
            f"Код неверный. Осталось попыток: {self.attempts_left}."
        )


class VerificationCodeExpired(VerificationError):
    pass


class VerificationAttemptsExhausted(VerificationError):
    pass


@dataclass(frozen=True)
class ChallengeIssueResult:
    challenge: EmailVerificationChallenge
    email_sent: bool


def _generate_numeric_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def verification_required_for_access(user):
    return bool(
        user
        and user.is_authenticated
        and not user.is_superuser
        and not user.is_staff
        and user.email_verification_required
        and not user.has_verified_email
    )


def has_verified_transactional_email(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.has_verified_email
        )
    )


def verification_resend_remaining_seconds(challenge, *, now=None):
    """Return the server-authoritative whole seconds until resend is allowed."""
    if challenge is None or challenge.sent_at is None:
        return 0
    current_time = now or timezone.now()
    allowed_at = challenge.sent_at + timedelta(
        seconds=settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
    )
    return max(0, math.ceil((allowed_at - current_time).total_seconds()))


@transaction.atomic
def issue_verification_challenge(*, user, enforce_cooldown=True):
    user = User.objects.select_for_update().get(pk=user.pk)
    email = normalize_email_address(user.email)
    if not email:
        raise ValidationError("Сначала укажите email-адрес.")
    if user.has_verified_email:
        raise ValidationError("Этот email уже подтверждён.")

    now = timezone.now()
    latest = (
        EmailVerificationChallenge.objects.select_for_update()
        .filter(user=user)
        .order_by("-created_at", "-id")
        .first()
    )
    retry_after = verification_resend_remaining_seconds(latest, now=now)
    if enforce_cooldown and retry_after:
        raise VerificationCooldown(retry_after)

    EmailVerificationChallenge.objects.filter(
        user=user,
        consumed_at__isnull=True,
    ).update(consumed_at=now)

    generation = 1 if latest is None else latest.generation + 1
    code = _generate_numeric_code()
    challenge = EmailVerificationChallenge.objects.create(
        user=user,
        email_snapshot=email,
        code_hash=make_password(code),
        generation=generation,
        expires_at=now
        + timedelta(seconds=settings.EMAIL_VERIFICATION_LIFETIME_SECONDS),
        max_attempts=settings.EMAIL_VERIFICATION_MAX_ATTEMPTS,
    )
    delivery = send_verification_email(user=user, code=code)
    if delivery.sent:
        challenge.sent_at = timezone.now()
        challenge.save(update_fields=["sent_at"])
    else:
        failed_at = timezone.now()
        challenge.delivery_failed_at = failed_at
        challenge.consumed_at = failed_at
        challenge.save(update_fields=["delivery_failed_at", "consumed_at"])
    return ChallengeIssueResult(challenge=challenge, email_sent=delivery.sent)


def verify_email_code(*, user, code):
    normalized_code = str(code or "").strip()
    if len(normalized_code) != 6 or not normalized_code.isascii() or not normalized_code.isdigit():
        raise VerificationCodeInvalid(settings.EMAIL_VERIFICATION_MAX_ATTEMPTS)

    # Invalid attempts and expiry consume mutable challenge state.  Raise the
    # public error only after the atomic block has committed that state;
    # otherwise Django would roll the counter/consumed marker back together
    # with the exception.
    failure = None
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.has_verified_email:
            return user

        challenge = (
            EmailVerificationChallenge.objects.select_for_update()
            .filter(user=user, consumed_at__isnull=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if challenge is None:
            failure = VerificationCodeExpired(
                "Действующего кода нет. Отправьте новый код."
            )
        else:
            now = timezone.now()
            if challenge.email_snapshot != normalize_email_address(user.email):
                challenge.consumed_at = now
                challenge.save(update_fields=["consumed_at"])
                failure = VerificationCodeExpired(
                    "Email изменился. Отправьте новый код подтверждения."
                )
            elif challenge.expires_at <= now:
                challenge.consumed_at = now
                challenge.save(update_fields=["consumed_at"])
                failure = VerificationCodeExpired(
                    "Срок действия кода истёк. Отправьте новый код."
                )
            elif challenge.attempt_count >= challenge.max_attempts:
                challenge.consumed_at = now
                challenge.save(update_fields=["consumed_at"])
                failure = VerificationAttemptsExhausted(
                    "Попытки закончились. Отправьте новый код."
                )
            else:
                challenge.last_attempt_at = now
                challenge.attempt_count += 1
                if not check_password(normalized_code, challenge.code_hash):
                    fields = ["attempt_count", "last_attempt_at"]
                    attempts_left = challenge.max_attempts - challenge.attempt_count
                    if attempts_left <= 0:
                        challenge.consumed_at = now
                        fields.append("consumed_at")
                        failure = VerificationAttemptsExhausted(
                            "Попытки закончились. Отправьте новый код."
                        )
                    else:
                        failure = VerificationCodeInvalid(attempts_left)
                    challenge.save(update_fields=fields)
                else:
                    challenge.verified_at = now
                    challenge.consumed_at = now
                    challenge.save(
                        update_fields=[
                            "attempt_count",
                            "last_attempt_at",
                            "verified_at",
                            "consumed_at",
                        ]
                    )
                    user.email = challenge.email_snapshot
                    user.verified_email = challenge.email_snapshot
                    user.email_verified_at = now
                    user.email_verification_required = True
                    user.save(
                        update_fields=[
                            "email",
                            "verified_email",
                            "email_verified_at",
                            "email_verification_required",
                        ]
                    )
                    return user

    if failure is None:  # Defensive guard: every non-success path sets an error.
        raise VerificationError("Не удалось проверить код.")
    raise failure


def verification_page_context(user):
    latest = user.email_verification_challenges.order_by("-created_at", "-id").first()
    retry_after = verification_resend_remaining_seconds(latest)
    minutes, seconds = divmod(retry_after, 60)
    return {
        "masked_email": mask_email_address(user.email),
        "latest_challenge": latest,
        "retry_after_seconds": retry_after,
        "retry_after_label": f"{minutes:02d}:{seconds:02d}",
    }
