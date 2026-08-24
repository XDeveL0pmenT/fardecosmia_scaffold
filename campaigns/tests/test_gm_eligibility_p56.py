import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.admin import UserAdmin
from accounts.models import User
from campaigns.admin import CampaignAdmin
from campaigns.models import Campaign, CampaignMembership
from campaigns.services.eligibility import (
    GM_ELIGIBILITY_PERMISSION,
    can_create_campaign,
    has_gm_eligibility,
    set_gm_eligibility,
)
from campaigns.services.lifecycle import create_campaign
from campaigns.services.memberships import MembershipConflict, change_membership_role
from world.models import AuditLog


PASSWORD = "Orbit!7826Nebula"


def verified_user(username, *, email=None, staff=False):
    email = email or f"{username}@example.com"
    user = User.objects.create_user(
        username=username,
        email=email,
        password=PASSWORD,
        is_staff=staff,
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


def superuser(username="p56-root"):
    return User.objects.create_superuser(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
    )


class CampaignCreationEligibilityTests(TestCase):
    def setUp(self):
        self.root = superuser()
        self.ordinary = verified_user("p56-ordinary")

    def test_ordinary_verified_user_cannot_create_campaign_through_service_or_view(self):
        self.assertFalse(has_gm_eligibility(self.ordinary))
        self.assertFalse(can_create_campaign(self.ordinary))
        with self.assertRaisesMessage(PermissionDenied, "доверенным Game Master"):
            create_campaign(actor=self.ordinary, name="Forbidden")
        self.assertFalse(Campaign.objects.filter(name="Forbidden").exists())

        self.client.force_login(self.ordinary)
        listing = self.client.get(reverse("campaigns:list"))
        self.assertContains(listing, "Участие по приглашению")
        self.assertContains(listing, "Новые кампании создают доверенные Game Master")
        self.assertNotContains(listing, f'href="{reverse("campaigns:create")}"')
        direct_get = self.client.get(reverse("campaigns:create"), follow=True)
        self.assertRedirects(direct_get, reverse("campaigns:list"))
        self.assertContains(direct_get, "Присоединиться к игре можно по приглашению")
        self.assertEqual(
            self.client.post(
                reverse("campaigns:create"),
                {"name": "Forged", "description": ""},
            ).status_code,
            403,
        )
        self.assertFalse(Campaign.objects.filter(name="Forged").exists())

    def test_superuser_granted_eligible_verified_user_creates_atomic_initial_gm(self):
        set_gm_eligibility(
            actor=self.root,
            user_id=self.ordinary.pk,
            eligible=True,
        )
        self.assertTrue(can_create_campaign(self.ordinary))
        campaign = create_campaign(actor=self.ordinary, name="Trusted Campaign")
        membership = CampaignMembership.objects.get(
            campaign=campaign,
            user=self.ordinary,
        )
        self.assertEqual(membership.role, CampaignMembership.Role.GM)
        self.assertTrue(
            AuditLog.objects.filter(
                action="campaign.created",
                campaign=campaign,
            ).exists()
        )

        self.client.force_login(self.ordinary)
        listing = self.client.get(reverse("campaigns:list"))
        self.assertContains(listing, f'href="{reverse("campaigns:create")}"')

    def test_eligible_unverified_user_is_still_blocked_and_superuser_is_compatible(self):
        unverified = User.objects.create_user(
            username="p56-unverified",
            email="p56-unverified@example.com",
            password=PASSWORD,
            email_verification_required=True,
        )
        set_gm_eligibility(actor=self.root, user_id=unverified.pk, eligible=True)
        self.assertTrue(has_gm_eligibility(unverified))
        self.assertFalse(can_create_campaign(unverified))
        with self.assertRaisesMessage(PermissionDenied, "подтвердите email"):
            create_campaign(actor=unverified, name="Unverified")

        campaign = create_campaign(actor=self.root, name="Root Campaign")
        self.assertTrue(
            campaign.memberships.filter(
                user=self.root,
                role=CampaignMembership.Role.GM,
            ).exists()
        )

    def test_group_or_canon_permission_does_not_grant_trusted_gm_eligibility(self):
        gm_permission = Permission.objects.get(
            content_type__app_label="campaigns",
            codename="create_campaign_as_gm",
        )
        group = Group.objects.create(name="Untrusted permission group")
        group.permissions.add(gm_permission)
        self.ordinary.groups.add(group)
        self.ordinary = User.objects.get(pk=self.ordinary.pk)
        self.assertTrue(self.ordinary.has_perm(GM_ELIGIBILITY_PERMISSION))
        self.assertFalse(has_gm_eligibility(self.ordinary))

        canon_permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        self.ordinary.groups.clear()
        self.ordinary.user_permissions.add(canon_permission)
        self.assertFalse(has_gm_eligibility(self.ordinary))
        with self.assertRaises(PermissionDenied):
            create_campaign(actor=self.ordinary, name="Canon is not GM")

    def test_revocation_blocks_future_creation_without_destroying_existing_gm_role(self):
        set_gm_eligibility(actor=self.root, user_id=self.ordinary.pk, eligible=True)
        campaign = create_campaign(actor=self.ordinary, name="Existing")
        set_gm_eligibility(actor=self.root, user_id=self.ordinary.pk, eligible=False)
        self.ordinary.refresh_from_db()
        self.assertFalse(has_gm_eligibility(self.ordinary))
        self.assertTrue(
            campaign.memberships.filter(
                user=self.ordinary,
                role=CampaignMembership.Role.GM,
            ).exists()
        )
        with self.assertRaises(PermissionDenied):
            create_campaign(actor=self.ordinary, name="After revoke")


class EligibilityAdministrationTests(TestCase):
    def setUp(self):
        self.root = superuser("p56-admin-root")
        self.staff = verified_user("p56-staff", staff=True)
        self.target = verified_user("p56-target")

    def test_only_superuser_can_grant_or_revoke_and_changes_are_audited(self):
        with self.assertRaisesMessage(PermissionDenied, "Только superuser"):
            set_gm_eligibility(
                actor=self.staff,
                user_id=self.target.pk,
                eligible=True,
            )
        self.assertFalse(has_gm_eligibility(self.target))

        set_gm_eligibility(actor=self.root, user_id=self.target.pk, eligible=True)
        self.target.refresh_from_db()
        self.assertTrue(has_gm_eligibility(self.target))
        self.assertEqual(
            AuditLog.objects.filter(action="account.gm_eligibility_granted").count(),
            1,
        )
        set_gm_eligibility(actor=self.root, user_id=self.target.pk, eligible=True)
        self.assertEqual(
            AuditLog.objects.filter(action="account.gm_eligibility_granted").count(),
            1,
        )

        set_gm_eligibility(actor=self.root, user_id=self.target.pk, eligible=False)
        self.target.refresh_from_db()
        self.assertFalse(has_gm_eligibility(self.target))
        audit = AuditLog.objects.get(action="account.gm_eligibility_revoked")
        self.assertEqual(audit.actor, self.root)
        self.assertNotIn(self.target.email, str(audit.after_state))

    def test_user_admin_exposes_audited_actions_only_to_superuser(self):
        model_admin = UserAdmin(User, admin.site)
        factory = RequestFactory()
        root_request = factory.get("/admin/accounts/user/")
        root_request.user = self.root
        staff_request = factory.get("/admin/accounts/user/")
        staff_request.user = self.staff

        self.assertIn("grant_gm_eligibility", model_admin.get_actions(root_request))
        self.assertIn("revoke_gm_eligibility", model_admin.get_actions(root_request))
        self.assertNotIn("grant_gm_eligibility", model_admin.get_actions(staff_request))
        self.assertNotIn("revoke_gm_eligibility", model_admin.get_actions(staff_request))
        self.assertIn("user_permissions", model_admin.get_readonly_fields(staff_request))

        permission_field = model_admin.formfield_for_manytomany(
            User._meta.get_field("user_permissions"),
            root_request,
        )
        self.assertFalse(
            permission_field.queryset.filter(
                content_type__app_label="campaigns",
                codename="create_campaign_as_gm",
            ).exists()
        )

    def test_campaign_admin_creation_is_superuser_only(self):
        model_admin = CampaignAdmin(Campaign, admin.site)
        factory = RequestFactory()
        root_request = factory.get("/admin/campaigns/campaign/add/")
        root_request.user = self.root
        staff_request = factory.get("/admin/campaigns/campaign/add/")
        staff_request.user = self.staff
        self.assertTrue(model_admin.has_add_permission(root_request))
        self.assertFalse(model_admin.has_add_permission(staff_request))


class MembershipPromotionEligibilityTests(TestCase):
    def setUp(self):
        self.root = superuser("p56-promotion-root")
        self.gm = verified_user("p56-campaign-gm")
        set_gm_eligibility(actor=self.root, user_id=self.gm.pk, eligible=True)
        self.campaign = create_campaign(actor=self.gm, name="Promotion Campaign")
        self.player = verified_user("p56-player")
        self.membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )

    def test_campaign_gm_and_superuser_cannot_promote_untrusted_player(self):
        for actor in (self.gm, self.root):
            with self.assertRaisesMessage(MembershipConflict, "Сначала superuser"):
                change_membership_role(
                    campaign=self.campaign,
                    membership_id=self.membership.pk,
                    actor=actor,
                    new_role=CampaignMembership.Role.GM,
                )
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, CampaignMembership.Role.PLAYER)

        self.client.force_login(self.gm)
        page = self.client.get(reverse("campaigns:members", args=[self.campaign.pk]))
        self.assertContains(page, "Нет права Game Master")
        self.assertNotContains(
            page,
            reverse(
                "campaigns:member_promote",
                args=[self.campaign.pk, self.membership.pk],
            ),
        )
        response = self.client.post(
            reverse(
                "campaigns:member_promote",
                args=[self.campaign.pk, self.membership.pk],
            ),
            follow=True,
        )
        self.assertContains(response, "Сначала superuser")

    def test_campaign_gm_can_promote_only_superuser_trusted_player(self):
        set_gm_eligibility(actor=self.root, user_id=self.player.pk, eligible=True)
        promoted = change_membership_role(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
            new_role=CampaignMembership.Role.GM,
        )
        self.assertEqual(promoted.role, CampaignMembership.Role.GM)
        self.assertTrue(
            AuditLog.objects.filter(
                action="campaign_member.role_changed",
                campaign=self.campaign,
            ).exists()
        )
        self.assertFalse(self.player.has_perm("world.manage_global_canon"))

    def test_revocation_does_not_rewrite_existing_role_but_blocks_repromotion(self):
        set_gm_eligibility(actor=self.root, user_id=self.player.pk, eligible=True)
        change_membership_role(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
            new_role=CampaignMembership.Role.GM,
        )
        set_gm_eligibility(actor=self.root, user_id=self.player.pk, eligible=False)

        self.client.force_login(self.player)
        self.assertEqual(
            self.client.get(
                reverse("campaigns:gm_dashboard", args=[self.campaign.pk])
            ).status_code,
            200,
        )
        change_membership_role(
            campaign=self.campaign,
            membership_id=self.membership.pk,
            actor=self.gm,
            new_role=CampaignMembership.Role.PLAYER,
        )
        with self.assertRaises(MembershipConflict):
            change_membership_role(
                campaign=self.campaign,
                membership_id=self.membership.pk,
                actor=self.gm,
                new_role=CampaignMembership.Role.GM,
            )


class GmEligibilityMigrationTests(TransactionTestCase):
    migrate_from = {"campaigns": "0010_campaignmembership_active_character"}
    migrate_to = {"campaigns": "0011_gm_eligibility_p56"}

    @staticmethod
    def _targets(executor, overrides):
        return [
            (app_label, overrides.get(app_label, migration_name))
            for app_label, migration_name in executor.loader.graph.leaf_nodes()
        ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        from_targets = self._targets(executor, self.migrate_from)
        executor.migrate(from_targets)
        old_apps = executor.loader.project_state(from_targets).apps
        UserModel = old_apps.get_model("accounts", "User")
        CampaignModel = old_apps.get_model("campaigns", "Campaign")
        MembershipModel = old_apps.get_model("campaigns", "CampaignMembership")
        gm = UserModel.objects.create(username="legacy-p56-gm")
        player = UserModel.objects.create(username="legacy-p56-player")
        campaign = CampaignModel.objects.create(name="Legacy P5.6 Campaign")
        MembershipModel.objects.create(campaign=campaign, user=gm, role="gm")
        MembershipModel.objects.create(campaign=campaign, user=player, role="player")
        self.gm_id = gm.pk
        self.player_id = player.pk
        self.campaign_id = campaign.pk

        executor = MigrationExecutor(connection)
        to_targets = self._targets(executor, self.migrate_to)
        executor.migrate(to_targets)
        self.apps = executor.loader.project_state(to_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self._targets(executor, self.migrate_to))
        super().tearDown()

    def test_existing_gms_gain_explicit_permission_players_and_rows_are_preserved(self):
        UserModel = self.apps.get_model("accounts", "User")
        CampaignModel = self.apps.get_model("campaigns", "Campaign")
        MembershipModel = self.apps.get_model("campaigns", "CampaignMembership")
        PermissionModel = self.apps.get_model("auth", "Permission")
        permission = PermissionModel.objects.get(
            content_type__app_label="campaigns",
            codename="create_campaign_as_gm",
        )
        eligible_ids = set(
            UserModel.user_permissions.through.objects.filter(
                permission_id=permission.pk,
            ).values_list("user_id", flat=True)
        )
        self.assertIn(self.gm_id, eligible_ids)
        self.assertNotIn(self.player_id, eligible_ids)
        self.assertTrue(CampaignModel.objects.filter(pk=self.campaign_id).exists())
        self.assertEqual(
            MembershipModel.objects.filter(campaign_id=self.campaign_id).count(),
            2,
        )


@skipUnless(connection.vendor == "postgresql", "Row-lock race proof requires PostgreSQL.")
class GmEligibilityConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_revoke_and_promotion_serialize_on_target_user(self):
        root = superuser("p56-race-root")
        gm = verified_user("p56-race-gm")
        target = verified_user("p56-race-target")
        set_gm_eligibility(actor=root, user_id=gm.pk, eligible=True)
        set_gm_eligibility(actor=root, user_id=target.pk, eligible=True)
        campaign = create_campaign(actor=gm, name="P5.6 Race")
        membership = CampaignMembership.objects.create(
            campaign=campaign,
            user=target,
            role=CampaignMembership.Role.PLAYER,
        )
        barrier = threading.Barrier(2)

        def revoke_worker():
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                set_gm_eligibility(
                    actor=User.objects.get(pk=root.pk),
                    user_id=target.pk,
                    eligible=False,
                )
                return "revoked"
            finally:
                close_old_connections()

        def promote_worker():
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                change_membership_role(
                    campaign=Campaign.objects.get(pk=campaign.pk),
                    membership_id=membership.pk,
                    actor=User.objects.get(pk=gm.pk),
                    new_role=CampaignMembership.Role.GM,
                )
                return "promoted"
            except MembershipConflict:
                return "blocked"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda fn: fn(), [revoke_worker, promote_worker]))
        self.assertEqual(outcomes[0], "revoked")
        self.assertIn(outcomes[1], {"promoted", "blocked"})
        target.refresh_from_db()
        self.assertFalse(has_gm_eligibility(target))
        membership.refresh_from_db()
        if outcomes[1] == "blocked":
            self.assertEqual(membership.role, CampaignMembership.Role.PLAYER)
        else:
            self.assertEqual(membership.role, CampaignMembership.Role.GM)
