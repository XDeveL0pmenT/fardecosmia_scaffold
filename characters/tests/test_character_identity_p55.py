import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipUnless

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from campaigns.services.memberships import remove_campaign_member
from characters.admin import CharacterAdmin
from characters.models import Character
from characters.services import (
    CharacterConflict,
    assign_character,
    create_character,
    get_active_character,
    set_active_character,
    set_character_archived,
    update_character,
)
from integrations.roll20.models import Roll20CharacterBinding, Roll20Connection
from world.models import AuditLog


class CharacterP55Mixin:
    def setUp(self):
        super().setUp()
        users = get_user_model().objects
        self.gm_a = users.create_user(username="p55-gm-a", password="pass", display_name="Мастер А")
        self.gm_b = users.create_user(username="p55-gm-b", password="pass", display_name="Мастер Б")
        self.player = users.create_user(username="p55-player", password="pass", display_name="Игрок")
        self.other_player = users.create_user(username="p55-other", password="pass", display_name="Другой игрок")
        self.editor = users.create_user(username="p55-editor", password="pass")
        self.root = users.create_superuser(username="p55-root", email="root@example.com", password="pass")
        permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        self.editor.user_permissions.add(permission)
        self.campaign_a = Campaign.objects.create(name="P5.5 A")
        self.campaign_b = Campaign.objects.create(name="P5.5 B")
        self.gm_membership_a = CampaignMembership.objects.create(
            campaign=self.campaign_a,
            user=self.gm_a,
            role=CampaignMembership.Role.GM,
        )
        self.gm_membership_b = CampaignMembership.objects.create(
            campaign=self.campaign_b,
            user=self.gm_b,
            role=CampaignMembership.Role.GM,
        )
        self.player_membership = CampaignMembership.objects.create(
            campaign=self.campaign_a,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.other_membership = CampaignMembership.objects.create(
            campaign=self.campaign_a,
            user=self.other_player,
            role=CampaignMembership.Role.PLAYER,
        )

    def character(self, *, owner=None, campaign=None, name="Аэрион", is_active=True):
        return Character.objects.create(
            campaign=campaign or self.campaign_a,
            owner=owner,
            name=name,
            is_active=is_active,
            **({"archived_at": None} if is_active else {}),
        )


class CharacterCreationAndAuditTests(CharacterP55Mixin, TestCase):
    def test_gm_creates_only_basic_campaign_character_and_audit(self):
        character = create_character(
            campaign=self.campaign_a,
            actor=self.gm_a,
            name="  Аэрион  ",
            biography="  Следопыт.  ",
        )
        self.assertEqual(character.name, "Аэрион")
        self.assertEqual(character.biography, "Следопыт.")
        self.assertIsNone(character.owner)
        audit = AuditLog.objects.get(action="character.created")
        self.assertEqual(audit.summary, "Создан персонаж «Аэрион».")
        self.assertNotIn("raw_attributes", str(audit.after_state))

    def test_player_foreign_gm_and_canon_editor_cannot_create(self):
        for actor in (self.player, self.gm_b, self.editor):
            with self.subTest(actor=actor.username), self.assertRaises(PermissionDenied):
                create_character(
                    campaign=self.campaign_a,
                    actor=actor,
                    name="Недоступный",
                )
        self.assertFalse(Character.objects.exists())

    def test_superuser_can_create_without_campaign_membership(self):
        character = create_character(campaign=self.campaign_a, actor=self.root, name="Корень")
        self.assertEqual(character.campaign, self.campaign_a)

    def test_audit_failure_rolls_back_creation(self):
        with mock.patch("characters.services.record_audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                create_character(campaign=self.campaign_a, actor=self.gm_a, name="Rollback")
        self.assertFalse(Character.objects.filter(name="Rollback").exists())

    def test_update_is_audited_and_noop_is_not(self):
        character = self.character(name="Старое имя")
        update_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            name="Новое имя",
            biography="Описание",
        )
        self.assertEqual(AuditLog.objects.filter(action="character.updated").count(), 1)
        update_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            name="Новое имя",
            biography="Описание",
        )
        self.assertEqual(AuditLog.objects.filter(action="character.updated").count(), 1)


class CharacterAssignmentTests(CharacterP55Mixin, TestCase):
    def test_assign_reassign_and_unassign_preserve_character(self):
        character = self.character()
        assign_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            membership_id=self.player_membership.pk,
        )
        character.refresh_from_db()
        self.assertEqual(character.owner, self.player_membership)
        self.player_membership.refresh_from_db()
        self.assertEqual(self.player_membership.active_character, character)

        assign_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            membership_id=self.other_membership.pk,
        )
        character.refresh_from_db()
        self.player_membership.refresh_from_db()
        self.assertEqual(character.owner, self.other_membership)
        self.assertIsNone(self.player_membership.active_character)

        assign_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            membership_id=None,
        )
        character.refresh_from_db()
        self.assertIsNone(character.owner)
        self.assertTrue(Character.objects.filter(pk=character.pk).exists())
        self.assertEqual(AuditLog.objects.filter(action="character.assigned").count(), 2)
        self.assertEqual(AuditLog.objects.filter(action="character.unassigned").count(), 1)

    def test_assignment_rejects_foreign_membership_and_gm_target(self):
        character = self.character()
        for membership in (self.gm_membership_a, self.gm_membership_b):
            with self.subTest(membership=membership.pk), self.assertRaises(CampaignMembership.DoesNotExist):
                assign_character(
                    campaign=self.campaign_a,
                    character_id=character.pk,
                    actor=self.gm_a,
                    membership_id=membership.pk,
                )

    def test_archived_character_cannot_receive_new_assignment(self):
        character = self.character()
        set_character_archived(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            archived=True,
        )
        with self.assertRaises(CharacterConflict):
            assign_character(
                campaign=self.campaign_a,
                character_id=character.pk,
                actor=self.gm_a,
                membership_id=self.player_membership.pk,
            )

    def test_player_foreign_gm_and_editor_cannot_assign(self):
        character = self.character()
        for actor in (self.player, self.gm_b, self.editor):
            with self.subTest(actor=actor.username), self.assertRaises(PermissionDenied):
                assign_character(
                    campaign=self.campaign_a,
                    character_id=character.pk,
                    actor=actor,
                    membership_id=self.player_membership.pk,
                )

    def test_noop_assignment_does_not_spam_audit(self):
        character = self.character(owner=self.player_membership)
        assign_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            membership_id=self.player_membership.pk,
        )
        self.assertFalse(AuditLog.objects.filter(action="character.assigned").exists())

    def test_assignment_audit_failure_rolls_back_owner_and_active(self):
        character = self.character()
        with mock.patch("characters.services.record_audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                assign_character(
                    campaign=self.campaign_a,
                    character_id=character.pk,
                    actor=self.gm_a,
                    membership_id=self.player_membership.pk,
                )
        character.refresh_from_db()
        self.player_membership.refresh_from_db()
        self.assertIsNone(character.owner)
        self.assertIsNone(self.player_membership.active_character)


class ActiveCharacterTests(CharacterP55Mixin, TestCase):
    def test_single_controlled_character_resolves_without_get_mutation(self):
        character = self.character(owner=self.player_membership)
        self.assertEqual(get_active_character(self.player, self.campaign_a), character)
        self.player_membership.refresh_from_db()
        self.assertIsNone(self.player_membership.active_character)

    def test_multiple_characters_use_persisted_choice(self):
        first = self.character(owner=self.player_membership, name="Первый")
        second = self.character(owner=self.player_membership, name="Второй")
        self.assertIsNone(get_active_character(self.player, self.campaign_a))
        selected = set_active_character(
            campaign=self.campaign_a,
            actor=self.player,
            character_id=second.pk,
        )
        self.assertEqual(selected, second)
        self.assertEqual(get_active_character(self.player, self.campaign_a), second)
        audit = AuditLog.objects.get(action="character.active_changed")
        self.assertIn("Второй", audit.summary)

    def test_foreign_unowned_and_archived_characters_are_rejected(self):
        foreign = self.character(campaign=self.campaign_b, name="Чужая кампания")
        unowned = self.character(name="Без владельца")
        archived = self.character(owner=self.player_membership, name="Архив")
        set_character_archived(
            campaign=self.campaign_a,
            character_id=archived.pk,
            actor=self.gm_a,
            archived=True,
        )
        for character in (foreign, unowned, archived):
            with self.subTest(character=character.name), self.assertRaises(Character.DoesNotExist):
                set_active_character(
                    campaign=self.campaign_a,
                    actor=self.player,
                    character_id=character.pk,
                )

    def test_reassignment_unassignment_and_archive_clear_active(self):
        character = self.character(owner=self.player_membership)
        self.player_membership.active_character = character
        self.player_membership.save(update_fields=["active_character"])
        assign_character(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            membership_id=self.other_membership.pk,
        )
        self.player_membership.refresh_from_db()
        self.assertIsNone(self.player_membership.active_character)
        self.other_membership.refresh_from_db()
        self.assertEqual(self.other_membership.active_character, character)
        set_character_archived(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            archived=True,
        )
        self.other_membership.refresh_from_db()
        self.assertIsNone(self.other_membership.active_character)


class CharacterArchiveAndDeletionTests(CharacterP55Mixin, TestCase):
    def test_archive_restore_preserves_row_and_roll20_binding(self):
        character = self.character(owner=self.player_membership)
        connection_obj = Roll20Connection.objects.create(campaign=self.campaign_a)
        binding = Roll20CharacterBinding.objects.create(
            connection=connection_obj,
            character=character,
            roll20_character_id="roll20-1",
        )
        set_character_archived(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            archived=True,
        )
        character.refresh_from_db()
        binding.refresh_from_db()
        self.assertFalse(character.is_active)
        self.assertIsNotNone(character.archived_at)
        self.assertEqual(binding.character, character)
        set_character_archived(
            campaign=self.campaign_a,
            character_id=character.pk,
            actor=self.gm_a,
            archived=False,
        )
        character.refresh_from_db()
        self.assertTrue(character.is_active)
        self.assertIsNone(character.archived_at)
        self.assertTrue(AuditLog.objects.filter(action="character.archived").exists())
        self.assertTrue(AuditLog.objects.filter(action="character.restored").exists())

    def test_player_cannot_archive(self):
        character = self.character(owner=self.player_membership)
        with self.assertRaises(PermissionDenied):
            set_character_archived(
                campaign=self.campaign_a,
                character_id=character.pk,
                actor=self.player,
                archived=True,
            )

    def test_membership_removal_preserves_character_and_audits_unassignment(self):
        character = self.character(owner=self.player_membership)
        self.player_membership.active_character = character
        self.player_membership.save(update_fields=["active_character"])
        remove_campaign_member(
            campaign=self.campaign_a,
            membership_id=self.player_membership.pk,
            actor=self.gm_a,
        )
        character.refresh_from_db()
        self.assertIsNone(character.owner)
        self.assertFalse(CampaignMembership.objects.filter(pk=self.player_membership.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="character.unassigned").exists())
        operation_ids = set(
            AuditLog.objects.filter(
                action__in=["character.unassigned", "campaign_member.removed"]
            ).values_list("operation_id", flat=True)
        )
        self.assertEqual(len(operation_ids), 1)

    def test_user_deletion_preserves_character_and_binding(self):
        character = self.character(owner=self.player_membership)
        connection_obj = Roll20Connection.objects.create(campaign=self.campaign_a)
        binding = Roll20CharacterBinding.objects.create(
            connection=connection_obj,
            character=character,
            roll20_character_id="roll20-delete-user",
        )
        self.player.delete()
        character.refresh_from_db()
        binding.refresh_from_db()
        self.assertIsNone(character.owner)
        self.assertEqual(binding.character, character)


class CharacterPermissionAndUITests(CharacterP55Mixin, TestCase):
    def test_gm_management_create_and_player_denial(self):
        self.client.force_login(self.gm_a)
        response = self.client.get(reverse("characters:gm_list", args=[self.campaign_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="minutes"', html=False)
        response = self.client.post(
            reverse("characters:create", args=[self.campaign_a.pk]),
            {"name": "Созданный", "biography": "Описание"},
        )
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.player)
        self.assertEqual(
            self.client.get(reverse("characters:gm_list", args=[self.campaign_a.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("characters:create", args=[self.campaign_a.pk]),
                {"name": "Подделка", "biography": ""},
            ).status_code,
            403,
        )

    def test_player_dashboard_shows_own_active_character(self):
        character = self.character(owner=self.player_membership, name="Мой герой")
        self.client.force_login(self.player)
        response = self.client.get(reverse("campaigns:campaign_detail", args=[self.campaign_a.pk]))
        self.assertContains(response, "Ваш персонаж")
        self.assertContains(response, "Мой герой")
        self.assertContains(response, reverse("characters:detail", args=[self.campaign_a.pk, character.pk]))

    def test_player_empty_state_and_multiple_selector(self):
        self.client.force_login(self.player)
        response = self.client.get(reverse("characters:player_list", args=[self.campaign_a.pk]))
        self.assertContains(response, "Персонаж ещё не назначен")
        self.character(owner=self.player_membership, name="Один")
        self.character(owner=self.player_membership, name="Два")
        response = self.client.get(reverse("campaigns:campaign_detail", args=[self.campaign_a.pk]))
        self.assertContains(response, "Выберите активного персонажа")
        response = self.client.get(reverse("characters:player_list", args=[self.campaign_a.pk]))
        self.assertContains(response, "Играть за Один")
        self.assertContains(response, "Играть за Два")

    def test_player_only_sees_controlled_character_and_no_technical_payload(self):
        own = self.character(owner=self.player_membership, name="Свой")
        other = self.character(owner=self.other_membership, name="Чужой")
        connection_obj = Roll20Connection.objects.create(campaign=self.campaign_a)
        Roll20CharacterBinding.objects.create(
            connection=connection_obj,
            character=own,
            roll20_character_id="secret-internal-roll20-id",
            raw_attributes={"hp": 10, "private": "raw-secret"},
        )
        self.client.force_login(self.player)
        listing = self.client.get(reverse("characters:player_list", args=[self.campaign_a.pk]))
        self.assertContains(listing, "Свой")
        self.assertNotContains(listing, "Чужой")
        detail = self.client.get(reverse("characters:detail", args=[self.campaign_a.pk, own.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "secret-internal-roll20-id")
        self.assertNotContains(detail, "raw-secret")
        self.assertEqual(
            self.client.get(reverse("characters:detail", args=[self.campaign_a.pk, other.pk])).status_code,
            404,
        )

    def test_forged_self_assignment_and_foreign_campaign_are_denied(self):
        character = self.character()
        self.client.force_login(self.player)
        response = self.client.post(
            reverse("characters:assign", args=[self.campaign_a.pk, character.pk]),
            {"player": self.player_membership.pk},
        )
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.gm_a)
        response = self.client.post(
            reverse("characters:assign", args=[self.campaign_a.pk, character.pk]),
            {"player": self.gm_membership_b.pk},
        )
        self.assertEqual(response.status_code, 302)
        character.refresh_from_db()
        self.assertIsNone(character.owner)

    def test_switch_is_post_only_and_rejects_foreign_character(self):
        own = self.character(owner=self.player_membership)
        foreign = self.character(campaign=self.campaign_b, name="Чужой")
        self.client.force_login(self.player)
        url = reverse("characters:switch_active", args=[self.campaign_a.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"character": foreign.pk}).status_code, 403)
        response = self.client.post(url, {"character": own.pk})
        self.assertEqual(response.status_code, 302)
        self.player_membership.refresh_from_db()
        self.assertEqual(self.player_membership.active_character, own)

    def test_canon_editor_has_no_character_authority(self):
        self.client.force_login(self.editor)
        self.assertEqual(
            self.client.get(reverse("characters:gm_list", args=[self.campaign_a.pk])).status_code,
            403,
        )

    def test_dashboard_and_lists_have_bounded_queries(self):
        for index in range(20):
            self.character(
                owner=self.player_membership if index < 3 else None,
                name=f"Персонаж {index:02d}",
            )
        self.client.force_login(self.player)
        with CaptureQueriesContext(connection) as dashboard_queries:
            response = self.client.get(reverse("campaigns:campaign_detail", args=[self.campaign_a.pk]))
            self.assertEqual(response.status_code, 200)
        with CaptureQueriesContext(connection) as player_queries:
            response = self.client.get(reverse("characters:player_list", args=[self.campaign_a.pk]))
            self.assertEqual(response.status_code, 200)
        self.client.force_login(self.gm_a)
        with CaptureQueriesContext(connection) as gm_queries:
            response = self.client.get(reverse("characters:gm_list", args=[self.campaign_a.pk]))
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(dashboard_queries), 12)
        self.assertLessEqual(len(player_queries), 12)
        self.assertLessEqual(len(gm_queries), 12)

    def test_character_admin_is_diagnostic_only(self):
        model_admin = CharacterAdmin(Character, admin.site)
        request = RequestFactory().get("/admin/characters/character/")
        request.user = self.root
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


class CharacterMigrationTests(TransactionTestCase):
    migrate_from = {
        "campaigns": "0009_campaigninvitation",
        "characters": "0001_initial",
    }
    migrate_to = {
        "campaigns": "0010_campaignmembership_active_character",
        "characters": "0002_character_archived_at_character_is_active_and_more",
    }

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
        User = old_apps.get_model("accounts", "User")
        CampaignModel = old_apps.get_model("campaigns", "Campaign")
        Membership = old_apps.get_model("campaigns", "CampaignMembership")
        CharacterModel = old_apps.get_model("characters", "Character")
        ConnectionModel = old_apps.get_model("roll20", "Roll20Connection")
        BindingModel = old_apps.get_model("roll20", "Roll20CharacterBinding")
        user = User.objects.create(username="legacy-character-owner")
        campaign = CampaignModel.objects.create(name="Legacy Character Campaign")
        membership = Membership.objects.create(campaign=campaign, user=user, role="player")
        character = CharacterModel.objects.create(
            campaign=campaign,
            owner=membership,
            name="Legacy Character",
            biography="Preserved biography",
        )
        roll20_connection = ConnectionModel.objects.create(campaign=campaign)
        binding = BindingModel.objects.create(
            connection=roll20_connection,
            character=character,
            roll20_character_id="legacy-roll20-id",
        )
        self.character_id = character.pk
        self.membership_id = membership.pk
        self.binding_id = binding.pk
        executor = MigrationExecutor(connection)
        to_targets = self._targets(executor, self.migrate_to)
        executor.migrate(to_targets)
        self.apps = executor.loader.project_state(to_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self._targets(executor, self.migrate_to))
        super().tearDown()

    def test_existing_character_pk_owner_campaign_and_binding_are_preserved(self):
        CharacterModel = self.apps.get_model("characters", "Character")
        Membership = self.apps.get_model("campaigns", "CampaignMembership")
        BindingModel = self.apps.get_model("roll20", "Roll20CharacterBinding")
        character = CharacterModel.objects.get(pk=self.character_id)
        membership = Membership.objects.get(pk=self.membership_id)
        binding = BindingModel.objects.get(pk=self.binding_id)
        self.assertEqual(character.name, "Legacy Character")
        self.assertEqual(character.biography, "Preserved biography")
        self.assertEqual(character.owner_id, membership.pk)
        self.assertTrue(character.is_active)
        self.assertIsNone(character.archived_at)
        self.assertIsNone(membership.active_character_id)
        self.assertEqual(binding.character_id, character.pk)


@skipUnless(connection.vendor == "postgresql", "Row-lock race proof requires PostgreSQL.")
class CharacterConcurrencyTests(CharacterP55Mixin, TransactionTestCase):
    reset_sequences = True

    def test_two_gms_cannot_leave_cross_campaign_or_multiple_owner_state(self):
        second_gm = get_user_model().objects.create_user(username="p55-gm-second", password="pass")
        CampaignMembership.objects.create(
            campaign=self.campaign_a,
            user=second_gm,
            role=CampaignMembership.Role.GM,
        )
        character = self.character()
        barrier = threading.Barrier(2)

        def worker(actor_id, membership_id):
            close_old_connections()
            actor = get_user_model().objects.get(pk=actor_id)
            campaign = Campaign.objects.get(pk=self.campaign_a.pk)
            barrier.wait()
            assign_character(
                campaign=campaign,
                character_id=character.pk,
                actor=actor,
                membership_id=membership_id,
            )
            close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(worker, self.gm_a.pk, self.player_membership.pk),
                pool.submit(worker, second_gm.pk, self.other_membership.pk),
            ]
            for future in futures:
                future.result()
        character.refresh_from_db()
        self.assertIn(character.owner_id, {self.player_membership.pk, self.other_membership.pk})
