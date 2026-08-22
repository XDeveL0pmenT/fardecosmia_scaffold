import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from campaigns.models import Campaign, CampaignInvitation, CampaignMembership
from campaigns.services.invitations import (
    InvitationEmailMismatch,
    InvitationUnavailable,
    accept_campaign_invitation,
    create_campaign_invitation,
    revoke_campaign_invitation,
)
from campaigns.services.lifecycle import create_campaign
from campaigns.services.memberships import (
    MembershipConflict,
    change_membership_role,
    remove_campaign_member,
)
from characters.models import Character
from world.models import AuditLog


STRONG_PASSWORD = "Orbit!7826Nebula"


def make_verified_user(username, email):
    user = User.objects.create_user(
        username=username,
        email=email,
        password=STRONG_PASSWORD,
    )
    user.verified_email = user.email
    user.email_verified_at = timezone.now()
    user.email_verification_required = True
    user.save(
        update_fields=[
            "verified_email",
            "email_verified_at",
            "email_verification_required",
        ]
    )
    return user


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CampaignLifecycleTests(TestCase):
    def setUp(self):
        self.creator = make_verified_user("creator", "creator@example.com")

    def test_verified_user_creates_campaign_and_initial_gm_atomically_with_audit(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse("campaigns:create"),
            {"name": "Путь через Лик", "description": "Новая кампания"},
        )
        campaign = Campaign.objects.get(name="Путь через Лик")
        self.assertRedirects(
            response,
            reverse("campaigns:gm_dashboard", args=[campaign.pk]),
        )
        membership = CampaignMembership.objects.get(campaign=campaign, user=self.creator)
        self.assertEqual(membership.role, CampaignMembership.Role.GM)
        audit = AuditLog.objects.get(action="campaign.created", campaign=campaign)
        self.assertEqual(audit.actor, self.creator)
        self.assertEqual(audit.after_state["name"], "Путь через Лик")
        self.assertFalse(hasattr(campaign, "owner"))

    def test_same_verified_user_can_be_gm_of_multiple_campaigns(self):
        first = create_campaign(actor=self.creator, name="First")
        second = create_campaign(actor=self.creator, name="Second")
        self.assertEqual(
            CampaignMembership.objects.filter(
                user=self.creator,
                role=CampaignMembership.Role.GM,
                campaign__in=[first, second],
            ).count(),
            2,
        )

    def test_campaign_creation_rolls_back_when_audit_fails(self):
        with patch(
            "campaigns.services.lifecycle.record_audit",
            side_effect=RuntimeError("audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_campaign(actor=self.creator, name="Не сохранится")
        self.assertFalse(Campaign.objects.filter(name="Не сохранится").exists())
        self.assertFalse(CampaignMembership.objects.exists())

    def test_unverified_user_cannot_create_but_superuser_compatibility_remains(self):
        unverified = User.objects.create_user(
            username="unverified",
            email="u@example.com",
            password=STRONG_PASSWORD,
            email_verification_required=True,
        )
        self.client.force_login(unverified)
        response = self.client.get(reverse("campaigns:create"))
        self.assertRedirects(response, reverse("accounts:verify_email"))
        with self.assertRaises(PermissionDenied):
            create_campaign(actor=unverified, name="Denied")

        root = User.objects.create_superuser(
            username="root-campaign",
            email="",
            password=STRONG_PASSWORD,
        )
        campaign = create_campaign(actor=root, name="Admin compatible")
        self.assertTrue(
            campaign.memberships.filter(user=root, role=CampaignMembership.Role.GM).exists()
        )

    def test_basic_edit_is_gm_scoped_and_audited_without_delete_ui(self):
        campaign = create_campaign(actor=self.creator, name="Before", description="A")
        other = make_verified_user("other-gm", "other-gm@example.com")
        self.client.force_login(other)
        self.assertEqual(
            self.client.post(
                reverse("campaigns:edit", args=[campaign.pk]),
                {"name": "Forged", "description": "B"},
            ).status_code,
            403,
        )
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse("campaigns:edit", args=[campaign.pk]),
            {"name": "After", "description": "B"},
            follow=True,
        )
        self.assertContains(response, "After")
        campaign.refresh_from_db()
        self.assertEqual(campaign.name, "After")
        self.assertTrue(AuditLog.objects.filter(action="campaign.updated").exists())
        self.assertNotContains(response, "Удалить кампанию")

    def test_campaign_list_empty_state_and_player_safe_landing(self):
        self.client.force_login(self.creator)
        empty = self.client.get(reverse("campaigns:list"))
        self.assertContains(empty, "Создать кампанию")
        self.assertContains(empty, "Откройте ссылку")
        campaign = create_campaign(actor=self.creator, name="Landing")
        player = make_verified_user("landing-player", "landing@example.com")
        CampaignMembership.objects.create(campaign=campaign, user=player)
        self.client.force_login(player)
        detail = self.client.get(reverse("campaigns:campaign_detail", args=[campaign.pk]))
        self.assertContains(detail, "Вы участник кампании")
        self.assertNotContains(detail, "Управлять участниками")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvitationTests(TestCase):
    def setUp(self):
        self.gm = make_verified_user("gm-invite", "gm@example.com")
        self.campaign = create_campaign(actor=self.gm, name="Invite Campaign")
        self.player = make_verified_user("player-invite", "player@example.com")
        self.other_gm = make_verified_user("gm-other", "gm-other@example.com")
        self.other_campaign = create_campaign(actor=self.other_gm, name="Other")

    def create_invite(self, email="player@example.com"):
        return create_campaign_invitation(
            campaign=self.campaign,
            actor=self.gm,
            email=email,
        )

    def test_gm_creates_high_entropy_email_bound_player_invite_without_plaintext_storage(self):
        result = self.create_invite()
        invite = result.invitation
        self.assertGreaterEqual(len(result.token), 40)
        self.assertNotEqual(invite.token_hash, result.token)
        self.assertNotIn(result.token, invite.token_hash)
        self.assertEqual(invite.role, CampaignMembership.Role.PLAYER)
        self.assertEqual(invite.email_normalized, "player@example.com")
        payloads = json.dumps(
            list(
                AuditLog.objects.filter(operation_id__isnull=False).values(
                    "before_state", "after_state", "metadata", "summary"
                )
            ),
            ensure_ascii=False,
        )
        self.assertNotIn(result.token, payloads)
        self.assertIn("p***@example.com", payloads)

    def test_invite_permissions_are_campaign_scoped_and_canon_editor_is_not_gm(self):
        player_member = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )
        with self.assertRaises(PermissionDenied):
            create_campaign_invitation(
                campaign=self.campaign,
                actor=self.player,
                email="new@example.com",
            )
        with self.assertRaises(PermissionDenied):
            create_campaign_invitation(
                campaign=self.campaign,
                actor=self.other_gm,
                email="new@example.com",
            )
        editor = make_verified_user("canon", "canon@example.com")
        permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        editor.user_permissions.add(permission)
        with self.assertRaises(PermissionDenied):
            create_campaign_invitation(
                campaign=self.campaign,
                actor=editor,
                email="new@example.com",
            )
        self.assertIsNotNone(player_member.pk)

    def test_invitation_view_sends_email_and_exposes_copy_link_only_in_response(self):
        self.client.force_login(self.gm)
        response = self.client.post(
            reverse("campaigns:invitation_create", args=[self.campaign.pk]),
            {"email": "fresh@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Скопируйте ссылку")
        invitation = CampaignInvitation.objects.get(email_normalized="fresh@example.com")
        self.assertIsNotNone(invitation.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.campaign.name, mail.outbox[0].body)
        self.assertIn("/invite/", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)

    def test_mail_failure_keeps_valid_invite_and_reports_without_provider_details(self):
        self.client.force_login(self.gm)
        with patch(
            "accounts.services.email.EmailMultiAlternatives.send",
            side_effect=RuntimeError("provider credential detail"),
        ):
            response = self.client.post(
                reverse("campaigns:invitation_create", args=[self.campaign.pk]),
                {"email": "failed@example.com"},
            )
        self.assertContains(response, "письмо сейчас не отправлено")
        self.assertNotContains(response, "provider credential detail")
        invitation = CampaignInvitation.objects.get(email_normalized="failed@example.com")
        self.assertTrue(invitation.is_pending)
        self.assertIsNotNone(invitation.delivery_failed_at)

    def test_duplicate_invite_replaces_old_and_old_token_cannot_be_used(self):
        first = self.create_invite()
        second = self.create_invite(email="PLAYER@example.com")
        first.invitation.refresh_from_db()
        self.assertIsNotNone(first.invitation.revoked_at)
        self.assertTrue(second.replaced_existing)
        self.assertEqual(
            CampaignInvitation.objects.filter(
                campaign=self.campaign,
                email_normalized="player@example.com",
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).count(),
            1,
        )
        with self.assertRaises(InvitationUnavailable):
            accept_campaign_invitation(token=first.token, actor=self.player)

    def test_expired_revoked_consumed_and_wrong_email_are_rejected(self):
        expired = self.create_invite()
        CampaignInvitation.objects.filter(pk=expired.invitation.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(InvitationUnavailable):
            accept_campaign_invitation(token=expired.token, actor=self.player)

        revoked = self.create_invite()
        revoke_campaign_invitation(
            campaign=self.campaign,
            invitation_id=revoked.invitation.pk,
            actor=self.gm,
        )
        with self.assertRaises(InvitationUnavailable):
            accept_campaign_invitation(token=revoked.token, actor=self.player)

        active = self.create_invite()
        wrong = make_verified_user("wrong", "wrong@example.com")
        with self.assertRaises(InvitationEmailMismatch):
            accept_campaign_invitation(token=active.token, actor=wrong)
        accepted = accept_campaign_invitation(token=active.token, actor=self.player)
        self.assertEqual(accepted.membership.role, CampaignMembership.Role.PLAYER)
        with self.assertRaises(InvitationUnavailable):
            accept_campaign_invitation(token=active.token, actor=self.player)

    def test_acceptance_is_atomic_and_audited(self):
        result = self.create_invite()
        with patch(
            "campaigns.services.invitations.record_audit",
            side_effect=RuntimeError("audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                accept_campaign_invitation(token=result.token, actor=self.player)
        self.assertFalse(
            CampaignMembership.objects.filter(
                campaign=self.campaign,
                user=self.player,
            ).exists()
        )
        result.invitation.refresh_from_db()
        self.assertIsNone(result.invitation.accepted_at)

        accepted = accept_campaign_invitation(token=result.token, actor=self.player)
        audit = AuditLog.objects.get(action="campaign_member.joined")
        self.assertEqual(audit.target, accepted.membership)
        self.assertNotIn(result.token, json.dumps(audit.after_state))

    def test_existing_member_is_graceful_and_consumes_invitation_once(self):
        result = self.create_invite()
        existing = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )
        accepted = accept_campaign_invitation(token=result.token, actor=self.player)
        self.assertTrue(accepted.already_member)
        self.assertEqual(accepted.membership, existing)
        self.assertEqual(
            CampaignMembership.objects.filter(campaign=self.campaign, user=self.player).count(),
            1,
        )
        self.assertTrue(AuditLog.objects.filter(action="campaign_invitation.accepted").exists())

    def test_invite_get_is_read_only_and_exposes_only_minimal_context(self):
        result = self.create_invite()
        audit_count = AuditLog.objects.count()
        before = CampaignInvitation.objects.values().get(pk=result.invitation.pk)
        response = self.client.get(
            reverse("campaigns:invitation_detail", args=[result.token])
        )
        after = CampaignInvitation.objects.values().get(pk=result.invitation.pk)
        self.assertContains(response, self.campaign.name)
        self.assertContains(response, "Роль")
        self.assertNotContains(response, "player@example.com")
        self.assertEqual(before, after)
        self.assertEqual(AuditLog.objects.count(), audit_count)
        session = self.client.session
        self.assertEqual(session["pending_campaign_invite_id"], result.invitation.pk)
        self.assertNotIn(result.token, session.values())

    def test_forged_token_and_cross_campaign_revoke_are_not_enumerable(self):
        forged = "x" * 48
        self.assertEqual(
            self.client.get(
                reverse("campaigns:invitation_detail", args=[forged])
            ).status_code,
            404,
        )
        self.client.force_login(self.player)
        self.assertEqual(
            self.client.post(
                reverse("campaigns:invitation_accept", args=[forged])
            ).status_code,
            404,
        )

        result = self.create_invite()
        foreign = create_campaign_invitation(
            campaign=self.other_campaign,
            actor=self.other_gm,
            email="foreign-player@example.com",
        )
        self.client.force_login(self.gm)
        response = self.client.post(
            reverse(
                "campaigns:invitation_revoke",
                args=[self.campaign.pk, foreign.invitation.pk],
            )
        )
        self.assertEqual(response.status_code, 404)
        foreign.invitation.refresh_from_db()
        result.invitation.refresh_from_db()
        self.assertIsNone(foreign.invitation.revoked_at)
        self.assertIsNone(result.invitation.revoked_at)

    def test_mutating_invitation_routes_reject_get(self):
        result = self.create_invite()
        self.client.force_login(self.gm)
        self.assertEqual(
            self.client.get(
                reverse("campaigns:invitation_create", args=[self.campaign.pk])
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "campaigns:invitation_revoke",
                    args=[self.campaign.pk, result.invitation.pk],
                )
            ).status_code,
            405,
        )
        result.invitation.refresh_from_db()
        self.assertIsNone(result.invitation.revoked_at)

    @override_settings(EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS=0)
    def test_full_new_user_invitation_onboarding_preserves_context(self):
        result = self.create_invite(email="newperson@example.com")
        invite_url = reverse("campaigns:invitation_detail", args=[result.token])
        self.client.get(invite_url)
        register = self.client.post(
            reverse("accounts:register") + f"?next={invite_url}",
            {
                "username": "new-person",
                "email": "NEWPERSON@example.com",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
            },
            follow=True,
        )
        self.assertContains(register, "Подтвердите")
        code = re.search(r"Ваш код:\s*(\d{6})", mail.outbox[-1].body).group(1)
        verified = self.client.post(
            reverse("accounts:verify_email"),
            {"code": code},
            follow=True,
        )
        self.assertRedirects(verified, reverse("campaigns:invitation_resume"))
        self.assertContains(verified, self.campaign.name)
        accepted = self.client.post(
            reverse("campaigns:invitation_resume_accept"),
            follow=True,
        )
        self.assertContains(accepted, "Вы участник кампании")
        user = User.objects.get(username="new-person")
        self.assertTrue(user.has_verified_email)
        self.assertTrue(
            CampaignMembership.objects.filter(
                campaign=self.campaign,
                user=user,
                role=CampaignMembership.Role.PLAYER,
            ).exists()
        )
        self.assertContains(self.client.get(reverse("campaigns:list")), self.campaign.name)


class MembershipManagementTests(TestCase):
    def setUp(self):
        self.gm = make_verified_user("gm-members", "gm-members@example.com")
        self.campaign = create_campaign(actor=self.gm, name="Members")
        self.player = make_verified_user("member", "member@example.com")
        self.membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )

    def test_gm_page_is_human_readable_and_players_cross_campaign_are_denied(self):
        self.client.force_login(self.gm)
        page = self.client.get(reverse("campaigns:members", args=[self.campaign.pk]))
        self.assertContains(page, "Участники кампании")
        self.assertContains(page, "Game Master")
        self.assertContains(page, "Сделать Game Master")
        self.client.force_login(self.player)
        self.assertEqual(
            self.client.get(reverse("campaigns:members", args=[self.campaign.pk])).status_code,
            403,
        )

    def test_promote_demote_and_role_audits_do_not_grant_global_canon(self):
        promoted = change_membership_role(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
            new_role=CampaignMembership.Role.GM,
        )
        self.assertEqual(promoted.role, CampaignMembership.Role.GM)
        self.assertFalse(self.player.has_perm("world.manage_global_canon"))
        demoted = change_membership_role(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
            new_role=CampaignMembership.Role.PLAYER,
        )
        self.assertEqual(demoted.role, CampaignMembership.Role.PLAYER)
        self.assertEqual(
            AuditLog.objects.filter(action="campaign_member.role_changed").count(),
            2,
        )

    def test_last_gm_cannot_be_demoted_or_removed(self):
        gm_membership = CampaignMembership.objects.get(
            campaign=self.campaign,
            user=self.gm,
        )
        with self.assertRaisesMessage(
            MembershipConflict,
            "должен остаться хотя бы один Game Master",
        ):
            change_membership_role(
                campaign=self.campaign,
                membership_id=gm_membership.pk,
                actor=self.gm,
                new_role=CampaignMembership.Role.PLAYER,
            )
        with self.assertRaisesMessage(
            MembershipConflict,
            "должен остаться хотя бы один Game Master",
        ):
            remove_campaign_member(
                campaign=self.campaign,
                membership_id=gm_membership.pk,
                actor=self.gm,
            )

    def test_remove_player_preserves_user_and_character(self):
        character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership,
            name="Сохранённый персонаж",
        )
        user_id = self.player.pk
        remove_campaign_member(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
        )
        self.assertTrue(User.objects.filter(pk=user_id).exists())
        character.refresh_from_db()
        self.assertIsNone(character.owner)
        self.assertTrue(AuditLog.objects.filter(action="campaign_member.removed").exists())

    def test_foreign_gm_cannot_change_membership(self):
        foreign = make_verified_user("foreign", "foreign@example.com")
        create_campaign(actor=foreign, name="Foreign")
        with self.assertRaises(PermissionDenied):
            change_membership_role(
                campaign=self.campaign,
                membership_id=self.membership.pk,
                actor=foreign,
                new_role=CampaignMembership.Role.GM,
            )

    def test_membership_database_uniqueness_and_get_routes_are_read_only(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CampaignMembership.objects.create(
                    campaign=self.campaign,
                    user=self.player,
                    role=CampaignMembership.Role.GM,
                )
        self.client.force_login(self.gm)
        self.assertEqual(
            self.client.get(
                reverse(
                    "campaigns:member_promote",
                    args=[self.campaign.pk, self.membership.pk],
                )
            ).status_code,
            405,
        )
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, CampaignMembership.Role.PLAYER)


@skipUnless(
    connection.features.has_select_for_update,
    "SQLite не предоставляет row-level SELECT FOR UPDATE; проверка выполняется на PostgreSQL.",
)
class CampaignConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.gm_a = make_verified_user("concurrent-a", "ca@example.com")
        self.gm_b = make_verified_user("concurrent-b", "cb@example.com")
        self.campaign = create_campaign(actor=self.gm_a, name="Concurrent")
        self.membership_a = CampaignMembership.objects.get(
            campaign=self.campaign,
            user=self.gm_a,
        )
        self.membership_b = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm_b,
            role=CampaignMembership.Role.GM,
        )

    def test_concurrent_last_gm_demotions_cannot_orphan_campaign(self):
        barrier = threading.Barrier(2)

        def worker(membership_id, actor_id):
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                change_membership_role(
                    campaign=Campaign.objects.get(pk=self.campaign.pk),
                    membership_id=membership_id,
                    actor=User.objects.get(pk=actor_id),
                    new_role=CampaignMembership.Role.PLAYER,
                )
                return "demoted"
            except MembershipConflict:
                return "blocked"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(
                    lambda args: worker(*args),
                    [
                        (self.membership_a.pk, self.gm_a.pk),
                        (self.membership_b.pk, self.gm_b.pk),
                    ],
                )
            )
        self.assertCountEqual(outcomes, ["demoted", "blocked"])
        self.assertEqual(
            CampaignMembership.objects.filter(
                campaign=self.campaign,
                role=CampaignMembership.Role.GM,
            ).count(),
            1,
        )

    def test_concurrent_invitation_acceptance_creates_one_membership(self):
        player = make_verified_user("concurrent-player", "cp@example.com")
        invitation = create_campaign_invitation(
            campaign=self.campaign,
            actor=self.gm_a,
            email=player.email,
        )
        barrier = threading.Barrier(2)

        def worker():
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                accept_campaign_invitation(
                    token=invitation.token,
                    actor=User.objects.get(pk=player.pk),
                )
                return "accepted"
            except InvitationUnavailable:
                return "unavailable"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: worker(), range(2)))
        self.assertCountEqual(outcomes, ["accepted", "unavailable"])
        self.assertEqual(
            CampaignMembership.objects.filter(
                campaign=self.campaign,
                user=player,
            ).count(),
            1,
        )

    def test_concurrent_duplicate_invites_leave_one_open_invitation(self):
        barrier = threading.Barrier(2)

        def worker(actor_id):
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                create_campaign_invitation(
                    campaign=Campaign.objects.get(pk=self.campaign.pk),
                    actor=User.objects.get(pk=actor_id),
                    email="duplicate@example.com",
                )
                return "created"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker, [self.gm_a.pk, self.gm_b.pk]))
        self.assertEqual(outcomes, ["created", "created"])
        self.assertEqual(
            CampaignInvitation.objects.filter(
                campaign=self.campaign,
                email_normalized="duplicate@example.com",
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).count(),
            1,
        )
