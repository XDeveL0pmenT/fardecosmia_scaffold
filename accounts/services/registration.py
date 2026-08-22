"""Public account-registration orchestration."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from accounts.models import User
from accounts.services.email_addresses import normalize_email_address
from accounts.services.verification import issue_verification_challenge


class RegistrationConflict(Exception):
    pass


@dataclass(frozen=True)
class RegistrationResult:
    user: User
    email_sent: bool


def register_account(*, username, email, password):
    email = normalize_email_address(email)
    try:
        with transaction.atomic():
            if User.objects.filter(email__iexact=email).exists():
                raise RegistrationConflict(
                    "Аккаунт с таким email уже существует."
                )
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                email_verification_required=True,
            )
    except IntegrityError as error:
        raise RegistrationConflict(
            "Имя пользователя или email уже используются."
        ) from error
    issue = issue_verification_challenge(user=user, enforce_cooldown=False)
    return RegistrationResult(user=user, email_sent=issue.email_sent)
