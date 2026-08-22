import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailVerificationChallenge, User
from accounts.services.verification import (
    VerificationCodeExpired,
    issue_verification_challenge,
    verify_email_code,
)


STRONG_PASSWORD = "Orbit!7826Nebula"


def code_from_message(message):
    match = re.search(r"Ваш код:\s*(\d{6})", message.body)
    if match is None:
        raise AssertionError("Verification code not found in test email.")
    return match.group(1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationAndVerificationTests(TestCase):
    def register(self, **overrides):
        payload = {
            "username": "wanderer",
            "email": "Wanderer@Example.COM",
            "password1": STRONG_PASSWORD,
            "password2": STRONG_PASSWORD,
        }
        payload.update(overrides)
        return self.client.post(reverse("accounts:register"), payload, follow=True)

    def test_registration_creates_existing_user_hashes_code_and_sends_branded_email(self):
        response = self.register()
        self.assertRedirects(response, reverse("accounts:verify_email"))
        user = User.objects.get(username="wanderer")
        self.assertEqual(user.email, "wanderer@example.com")
        self.assertTrue(user.email_verification_required)
        self.assertFalse(user.has_verified_email)
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        challenge = user.email_verification_challenges.get()
        code = code_from_message(mail.outbox[0])
        self.assertNotEqual(challenge.code_hash, code)
        self.assertTrue(check_password(code, challenge.code_hash))
        self.assertIn("Фардекосмия", mail.outbox[0].subject)
        self.assertIn(code, mail.outbox[0].body)
        self.assertNotIn(STRONG_PASSWORD, mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertContains(response, "Код отправлен на")
        self.assertContains(response, "w***@example.com")

    def test_registration_requires_email_valid_password_and_rejects_case_duplicate(self):
        response = self.register(email="", password1="123", password2="123")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Укажите email")
        self.assertContains(response, "слишком короткий")

        User.objects.create_user(
            username="existing",
            email="Person@Example.com",
            password=STRONG_PASSWORD,
        )
        response = self.register(
            username="second",
            email="person@example.COM",
        )
        self.assertContains(response, "Аккаунт с таким email уже существует")
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_database_enforces_case_insensitive_email_uniqueness(self):
        User.objects.create_user(username="one", email="same@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(username="two", email="SAME@example.com")

    def test_unverified_registered_user_is_restricted_and_get_is_read_only(self):
        self.register()
        user = User.objects.get(username="wanderer")
        before = list(
            user.email_verification_challenges.values_list(
                "pk", "attempt_count", "consumed_at"
            )
        )
        response = self.client.get(reverse("campaigns:list"))
        self.assertRedirects(response, reverse("accounts:verify_email"))
        response = self.client.get(reverse("accounts:verify_email"))
        self.assertEqual(response.status_code, 200)
        after = list(
            user.email_verification_challenges.values_list(
                "pk", "attempt_count", "consumed_at"
            )
        )
        self.assertEqual(before, after)

    def test_wrong_code_counts_attempts_and_correct_code_verifies(self):
        self.register()
        user = User.objects.get(username="wanderer")
        correct = code_from_message(mail.outbox[0])
        response = self.client.post(
            reverse("accounts:verify_email"),
            {"code": "000000" if correct != "000000" else "111111"},
        )
        self.assertContains(response, "Осталось попыток: 4")
        challenge = EmailVerificationChallenge.objects.get(user=user)
        self.assertEqual(challenge.attempt_count, 1)

        response = self.client.post(
            reverse("accounts:verify_email"),
            {"code": correct},
            follow=True,
        )
        self.assertRedirects(response, reverse("campaigns:list"))
        user.refresh_from_db()
        challenge.refresh_from_db()
        self.assertTrue(user.has_verified_email)
        self.assertIsNotNone(challenge.verified_at)
        self.assertIsNotNone(challenge.consumed_at)

    def test_attempt_limit_and_expiry_invalidate_challenge(self):
        self.register()
        user = User.objects.get(username="wanderer")
        correct = code_from_message(mail.outbox[0])
        wrong = "000000" if correct != "000000" else "111111"
        for _ in range(5):
            self.client.post(reverse("accounts:verify_email"), {"code": wrong})
        challenge = EmailVerificationChallenge.objects.get(user=user)
        self.assertEqual(challenge.attempt_count, 5)
        self.assertIsNotNone(challenge.consumed_at)

        challenge = issue_verification_challenge(
            user=user,
            enforce_cooldown=False,
        ).challenge
        new_code = code_from_message(mail.outbox[-1])
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(VerificationCodeExpired):
            verify_email_code(user=user, code=new_code)

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=0)
    def test_resend_invalidates_old_code_and_new_code_works(self):
        self.register()
        user = User.objects.get(username="wanderer")
        old_code = code_from_message(mail.outbox[-1])
        old_challenge = EmailVerificationChallenge.objects.get(user=user)

        response = self.client.post(
            reverse("accounts:resend_verification"),
            follow=True,
        )
        self.assertContains(response, "Старый код больше не действует")
        new_code = code_from_message(mail.outbox[-1])
        old_challenge.refresh_from_db()
        self.assertIsNotNone(old_challenge.consumed_at)
        self.assertNotEqual(old_code, new_code)

        response = self.client.post(
            reverse("accounts:verify_email"),
            {"code": old_code},
        )
        self.assertContains(response, "Код неверный")
        self.client.post(reverse("accounts:verify_email"), {"code": new_code})
        user.refresh_from_db()
        self.assertTrue(user.has_verified_email)

    def test_resend_cooldown_does_not_issue_second_challenge(self):
        self.register()
        before = EmailVerificationChallenge.objects.count()
        response = self.client.post(
            reverse("accounts:resend_verification"),
            follow=True,
        )
        self.assertContains(response, "Новый код можно отправить через")
        self.assertEqual(EmailVerificationChallenge.objects.count(), before)

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=60)
    def test_verification_get_shows_server_remaining_and_disables_resend(self):
        self.register()
        challenge = EmailVerificationChallenge.objects.get()
        sent_at = timezone.now()
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            sent_at=sent_at
        )

        with patch(
            "accounts.services.verification.timezone.now",
            return_value=sent_at,
        ):
            response = self.client.get(reverse("accounts:verify_email"))

        self.assertEqual(response.context["retry_after_seconds"], 60)
        self.assertGreater(response.context["retry_after_seconds"], 0)
        self.assertContains(response, 'data-remaining-seconds="60"')
        self.assertContains(response, "Отправить код повторно через 01:00")
        self.assertContains(response, "disabled")

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=60)
    def test_refresh_returns_smaller_remaining_without_mutating_challenge(self):
        self.register()
        challenge = EmailVerificationChallenge.objects.get()
        sent_at = timezone.now()
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            sent_at=sent_at
        )
        immutable_before = EmailVerificationChallenge.objects.values_list(
            "pk", "generation", "attempt_count", "sent_at", "consumed_at"
        ).get(pk=challenge.pk)

        with patch(
            "accounts.services.verification.timezone.now",
            return_value=sent_at + timedelta(seconds=10),
        ):
            first = self.client.get(reverse("accounts:verify_email"))
        with patch(
            "accounts.services.verification.timezone.now",
            return_value=sent_at + timedelta(seconds=25),
        ):
            refreshed = self.client.get(reverse("accounts:verify_email"))

        self.assertEqual(first.context["retry_after_seconds"], 50)
        self.assertEqual(refreshed.context["retry_after_seconds"], 35)
        immutable_after = EmailVerificationChallenge.objects.values_list(
            "pk", "generation", "attempt_count", "sent_at", "consumed_at"
        ).get(pk=challenge.pk)
        self.assertEqual(immutable_after, immutable_before)

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=60)
    def test_forged_early_resend_post_is_rejected_with_remaining_time(self):
        self.register()
        challenge = EmailVerificationChallenge.objects.get()
        sent_at = timezone.now()
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            sent_at=sent_at
        )
        before = EmailVerificationChallenge.objects.count()

        with patch(
            "accounts.services.verification.timezone.now",
            return_value=sent_at + timedelta(seconds=13),
        ):
            response = self.client.post(
                reverse("accounts:resend_verification"),
                follow=True,
            )

        self.assertContains(response, "Новый код можно отправить через 00:47")
        self.assertEqual(EmailVerificationChallenge.objects.count(), before)
        challenge.refresh_from_db()
        self.assertIsNone(challenge.consumed_at)

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=60)
    def test_backend_allows_resend_after_cooldown(self):
        self.register()
        challenge = EmailVerificationChallenge.objects.get()
        sent_at = timezone.now()
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            sent_at=sent_at
        )

        with patch(
            "accounts.services.verification.timezone.now",
            return_value=sent_at + timedelta(seconds=61),
        ):
            response = self.client.post(
                reverse("accounts:resend_verification"),
                follow=True,
            )

        self.assertContains(response, "Новый код отправлен")
        self.assertEqual(response.context["retry_after_seconds"], 60)
        self.assertContains(response, "Отправить код повторно через 01:00")
        self.assertEqual(EmailVerificationChallenge.objects.count(), 2)
        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.consumed_at)

    def test_email_change_invalidates_previous_verification(self):
        user = User.objects.create_user(
            username="verified",
            email="old@example.com",
            password=STRONG_PASSWORD,
        )
        user.verified_email = user.email
        user.email_verified_at = timezone.now()
        user.save(update_fields=["verified_email", "email_verified_at"])
        self.assertTrue(user.has_verified_email)
        user.email = "new@example.com"
        user.save(update_fields=["email"])
        user.refresh_from_db()
        self.assertFalse(user.has_verified_email)
        self.assertTrue(user.email_verification_required)

    def test_email_provider_failure_keeps_account_and_shows_safe_message(self):
        with patch(
            "accounts.services.email.EmailMultiAlternatives.send",
            side_effect=RuntimeError("smtp secret detail"),
        ):
            response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "письмо сейчас не удалось отправить")
        self.assertNotContains(response, "smtp secret detail")
        user = User.objects.get(username="wanderer")
        challenge = user.email_verification_challenges.get()
        self.assertIsNotNone(challenge.delivery_failed_at)
        self.assertIsNotNone(challenge.consumed_at)

    def test_legacy_user_and_superuser_are_not_locked_out_or_falsely_verified(self):
        legacy = User.objects.create_user(username="legacy", password=STRONG_PASSWORD)
        self.client.force_login(legacy)
        self.assertEqual(self.client.get(reverse("campaigns:list")).status_code, 200)
        legacy.refresh_from_db()
        self.assertFalse(legacy.has_verified_email)

        root = User.objects.create_superuser(
            username="root-p45",
            email="",
            password=STRONG_PASSWORD,
        )
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse("campaigns:list")).status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password=STRONG_PASSWORD,
        )
        self.user.verified_email = self.user.email
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=["verified_email", "email_verified_at"])

    def test_known_and_unknown_email_receive_same_neutral_response(self):
        known = self.client.post(
            reverse("password_reset"),
            {"email": "RESET@example.com"},
            follow=True,
        )
        self.assertContains(known, "Если аккаунт с таким email существует")
        self.assertEqual(len(mail.outbox), 1)
        unknown = self.client.post(
            reverse("password_reset"),
            {"email": "unknown@example.com"},
            follow=True,
        )
        self.assertContains(unknown, "Если аккаунт с таким email существует")
        self.assertEqual(known.redirect_chain, unknown.redirect_chain)
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_email_has_plain_html_link_and_valid_single_use_token(self):
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        message = mail.outbox[0]
        self.assertIn("Фардекосмия", message.subject)
        self.assertIn("/accounts/reset/", message.body)
        self.assertEqual(len(message.alternatives), 1)
        self.assertNotIn(STRONG_PASSWORD, message.body)
        reset_url = re.search(r"http://testserver([^\s]+)", message.body).group(1)
        first = self.client.get(reset_url)
        self.assertEqual(first.status_code, 302)
        set_password_url = first.url
        invalid = self.client.post(
            set_password_url,
            {"new_password1": "123", "new_password2": "123"},
        )
        self.assertContains(invalid, "слишком короткий")
        new_password = "Comet!5297Archive"
        done = self.client.post(
            set_password_url,
            {"new_password1": new_password, "new_password2": new_password},
            follow=True,
        )
        self.assertContains(done, "Пароль изменён")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        reused = self.client.get(reset_url, follow=True)
        self.assertContains(reused, "Ссылка больше не действует")
