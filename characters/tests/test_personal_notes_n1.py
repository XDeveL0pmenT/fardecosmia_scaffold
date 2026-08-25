from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from characters.models import Character, CharacterNote
from characters.notes import hold_personal_note
from characters.services import assign_character, set_active_character, set_character_archived
from integrations.roll20.models import Roll20CharacterBinding, Roll20Connection
from world.models import AuditLog


class PersonalNotesN1Mixin:
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.gm = User.objects.create_user(username="n1-gm", password="pass")
        self.player_a = User.objects.create_user(username="n1-a", password="pass")
        self.player_b = User.objects.create_user(username="n1-b", password="pass")
        self.outsider = User.objects.create_user(username="n1-out", password="pass")
        self.root = User.objects.create_superuser(
            username="n1-root",
            email="root@example.test",
            password="pass",
        )
        self.campaign = Campaign.objects.create(name="N1 Campaign")
        self.foreign_campaign = Campaign.objects.create(name="N1 Foreign")
        self.gm_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        self.membership_a = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player_a,
            role=CampaignMembership.Role.PLAYER,
        )
        self.membership_b = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player_b,
            role=CampaignMembership.Role.PLAYER,
        )
        self.character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_a,
            name="Вэрмин",
        )
        self.membership_a.active_character = self.character
        self.membership_a.save(update_fields=["active_character"])

    def note(self, *, character=None, memo="Памятка", body="Удержанная мысль"):
        return CharacterNote.objects.create(
            character=character or self.character,
            memo=memo,
            body=body,
        )

    def list_url(self, campaign=None):
        return reverse(
            "characters:personal_note_list",
            args=[(campaign or self.campaign).pk],
        )

    def hold_url(self):
        return reverse("characters:personal_note_hold", args=[self.campaign.pk])

    def detail_url(self, note):
        return reverse(
            "characters:personal_note_detail",
            args=[self.campaign.pk, note.pk],
        )

    def return_url(self, note):
        return reverse(
            "characters:personal_note_return",
            args=[self.campaign.pk, note.pk],
        )

    def release_url(self, note):
        return reverse(
            "characters:personal_note_release",
            args=[self.campaign.pk, note.pk],
        )


class PersonalNoteModelAndServiceTests(PersonalNotesN1Mixin, TestCase):
    def test_note_is_character_owned_without_user_or_visibility_fields(self):
        field_names = {field.name for field in CharacterNote._meta.fields}
        self.assertIn("character", field_names)
        self.assertNotIn("user", field_names)
        self.assertNotIn("author", field_names)
        self.assertNotIn("visibility", field_names)
        self.assertNotIn("gm_visible", field_names)
        self.assertNotIn(CharacterNote, admin.site._registry)

    def test_create_with_memo_and_without_campaign_audit(self):
        before = AuditLog.objects.count()
        note = hold_personal_note(
            actor=self.player_a,
            campaign=self.campaign,
            memo="  Северные болота  ",
            body="  Торговец что-то скрывал.  ",
        )
        self.assertEqual(note.character, self.character)
        self.assertEqual(note.memo, "Северные болота")
        self.assertEqual(note.body, "Торговец что-то скрывал.")
        self.assertEqual(AuditLog.objects.count(), before)

    def test_create_without_memo(self):
        note = hold_personal_note(
            actor=self.player_a,
            campaign=self.campaign,
            memo="",
            body="Только сама мысль",
        )
        self.assertEqual(note.memo, "")

    def test_body_required_and_size_limits(self):
        for memo, body in (
            ("", "   "),
            ("м" * 121, "мысль"),
            ("", "т" * (CharacterNote.MAX_BODY_LENGTH + 1)),
        ):
            with self.subTest(memo_length=len(memo), body_length=len(body)):
                with self.assertRaises(ValidationError):
                    hold_personal_note(
                        actor=self.player_a,
                        campaign=self.campaign,
                        memo=memo,
                        body=body,
                    )
        self.assertEqual(CharacterNote.objects.count(), 0)

    def test_reassignment_transfers_access_without_changing_note(self):
        note = self.note(body="Мысль следует за персонажем")
        original = (note.pk, note.memo, note.body)
        assign_character(
            campaign=self.campaign,
            character_id=self.character.pk,
            actor=self.gm,
            membership_id=self.membership_b.pk,
        )
        self.client.force_login(self.player_a)
        self.assertEqual(self.client.get(self.detail_url(note)).status_code, 403)
        self.client.force_login(self.player_b)
        self.assertEqual(self.client.get(self.detail_url(note)).status_code, 200)
        note.refresh_from_db()
        self.assertEqual((note.pk, note.memo, note.body), original)

    def test_unassignment_and_archive_preserve_rows_but_remove_access(self):
        note = self.note()
        assign_character(
            campaign=self.campaign,
            character_id=self.character.pk,
            actor=self.gm,
            membership_id=None,
        )
        self.assertTrue(CharacterNote.objects.filter(pk=note.pk).exists())
        self.client.force_login(self.player_a)
        self.assertEqual(self.client.get(self.detail_url(note)).status_code, 403)

        assign_character(
            campaign=self.campaign,
            character_id=self.character.pk,
            actor=self.gm,
            membership_id=self.membership_a.pk,
        )
        set_character_archived(
            campaign=self.campaign,
            character_id=self.character.pk,
            actor=self.gm,
            archived=True,
        )
        self.assertTrue(CharacterNote.objects.filter(pk=note.pk).exists())
        self.assertEqual(self.client.get(self.detail_url(note)).status_code, 403)

    def test_user_deletion_preserves_note_with_character(self):
        note = self.note()
        character_pk = self.character.pk
        self.player_a.delete()
        self.assertTrue(Character.objects.filter(pk=character_pk, owner=None).exists())
        self.assertTrue(CharacterNote.objects.filter(pk=note.pk, character_id=character_pk).exists())


class PersonalNoteViewSecurityTests(PersonalNotesN1Mixin, TestCase):
    def test_controller_can_create_list_and_open_note(self):
        self.client.force_login(self.player_a)
        response = self.client.post(
            self.hold_url(),
            {"memo": "Старый мост", "body": "Вернуться туда после заката."},
        )
        note = CharacterNote.objects.get()
        self.assertRedirects(response, self.detail_url(note))
        listing = self.client.get(self.list_url())
        detail = self.client.get(self.detail_url(note))
        self.assertContains(listing, "Старый мост")
        self.assertContains(detail, "Вернуться туда после заката.")

    def test_create_without_memo_and_body_validation(self):
        self.client.force_login(self.player_a)
        response = self.client.post(self.hold_url(), {"memo": "", "body": "Без памятки"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CharacterNote.objects.get().memo, "")
        invalid = self.client.post(self.hold_url(), {"memo": "", "body": "   "})
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Мысль не может быть пустой")
        self.assertEqual(CharacterNote.objects.count(), 1)

    def test_form_enforces_memo_and_body_limits(self):
        self.client.force_login(self.player_a)
        for memo, body in (
            ("м" * 121, "мысль"),
            ("", "т" * (CharacterNote.MAX_BODY_LENGTH + 1)),
        ):
            response = self.client.post(self.hold_url(), {"memo": memo, "body": body})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(CharacterNote.objects.count(), 0)

    def test_gm_and_superuser_have_no_personal_note_routes(self):
        note = self.note()
        urls = [
            self.list_url(),
            self.hold_url(),
            self.detail_url(note),
            self.return_url(note),
            self.release_url(note),
        ]
        for user in (self.gm, self.root):
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_other_player_foreign_campaign_and_forged_note_are_denied(self):
        note = self.note()
        other_character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_b,
            name="Другой",
        )
        self.membership_b.active_character = other_character
        self.membership_b.save(update_fields=["active_character"])
        self.client.force_login(self.player_b)
        self.assertEqual(self.client.get(self.detail_url(note)).status_code, 404)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.list_url()).status_code, 403)

        foreign_membership = CampaignMembership.objects.create(
            campaign=self.foreign_campaign,
            user=self.player_a,
            role=CampaignMembership.Role.PLAYER,
        )
        foreign_character = Character.objects.create(
            campaign=self.foreign_campaign,
            owner=foreign_membership,
            name="Чужая судьба",
        )
        foreign_membership.active_character = foreign_character
        foreign_membership.save(update_fields=["active_character"])
        foreign_note = CharacterNote.objects.create(
            character=foreign_character,
            body="Чужая память",
        )
        self.client.force_login(self.player_a)
        forged = reverse(
            "characters:personal_note_detail",
            args=[self.campaign.pk, foreign_note.pk],
        )
        self.assertEqual(self.client.get(forged).status_code, 404)

    def test_create_ignores_forged_character_identifier(self):
        second = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_a,
            name="Вторая судьба",
        )
        self.client.force_login(self.player_a)
        self.client.post(
            self.hold_url(),
            {"memo": "", "body": "Моя", "character": second.pk, "character_id": second.pk},
        )
        self.assertEqual(CharacterNote.objects.get().character, self.character)

    def test_switch_immediately_changes_note_source(self):
        first_note = self.note(body="Первая память")
        second = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_a,
            name="Вторая судьба",
        )
        second_note = self.note(character=second, body="Вторая память")
        self.client.force_login(self.player_a)
        first = self.client.get(self.list_url())
        self.assertContains(first, first_note.body)
        self.assertNotContains(first, second_note.body)
        self.client.post(
            reverse("characters:switch_active", args=[self.campaign.pk]),
            {"character": second.pk},
        )
        second_response = self.client.get(self.list_url())
        self.assertContains(second_response, second_note.body)
        self.assertNotContains(second_response, first_note.body)

    def test_edit_is_controller_only_and_scoped(self):
        note = self.note(body="Старая форма")
        self.client.force_login(self.player_a)
        response = self.client.post(
            self.return_url(note),
            {"memo": "Новая памятка", "body": "Новая форма"},
        )
        self.assertRedirects(response, self.detail_url(note))
        note.refresh_from_db()
        self.assertEqual(note.body, "Новая форма")

        other_character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_b,
            name="Другой",
        )
        self.membership_b.active_character = other_character
        self.membership_b.save(update_fields=["active_character"])
        self.client.force_login(self.player_b)
        self.assertEqual(
            self.client.post(
                self.return_url(note),
                {"memo": "Подделка", "body": "Подделка"},
            ).status_code,
            404,
        )
        note.refresh_from_db()
        self.assertEqual(note.body, "Новая форма")

    def test_release_requires_confirmation_post_and_is_scoped(self):
        note = self.note()
        self.client.force_login(self.player_a)
        confirmation = self.client.get(self.release_url(note))
        self.assertContains(confirmation, "Отпустить эту мысль?")
        self.assertTrue(CharacterNote.objects.filter(pk=note.pk).exists())

        other_character = Character.objects.create(
            campaign=self.campaign,
            owner=self.membership_b,
            name="Другой",
        )
        self.membership_b.active_character = other_character
        self.membership_b.save(update_fields=["active_character"])
        self.client.force_login(self.player_b)
        self.assertEqual(self.client.post(self.release_url(note)).status_code, 404)
        self.assertTrue(CharacterNote.objects.filter(pk=note.pk).exists())

        self.client.force_login(self.player_a)
        released = self.client.post(self.release_url(note))
        self.assertRedirects(released, self.list_url())
        self.assertFalse(CharacterNote.objects.filter(pk=note.pk).exists())

    def test_xss_is_escaped_and_dates_are_absent(self):
        note = self.note(
            memo='<img src=x onerror="alert(1)">',
            body='<script>alert("memory")</script>\nВторая строка',
        )
        CharacterNote.objects.filter(pk=note.pk).update(
            created_at=datetime(2042, 3, 4, 5, 6, tzinfo=datetime_timezone.utc),
            updated_at=datetime(2042, 3, 4, 5, 6, tzinfo=datetime_timezone.utc),
        )
        self.client.force_login(self.player_a)
        response = self.client.get(self.detail_url(note))
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertContains(response, "&lt;img", html=False)
        self.assertNotContains(response, "<script>alert", html=False)
        self.assertNotContains(response, "<img src=x", html=False)
        self.assertNotContains(response, "2042")
        self.assertNotContains(response, "Создано")
        self.assertNotContains(response, "Обновлено")

    def test_note_lifecycle_never_enters_campaign_audit(self):
        self.client.force_login(self.player_a)
        before = AuditLog.objects.count()
        self.client.post(self.hold_url(), {"memo": "secret-memo", "body": "secret-body"})
        note = CharacterNote.objects.get()
        self.client.post(self.return_url(note), {"memo": "changed-secret", "body": "changed"})
        self.client.post(self.release_url(note))
        self.assertEqual(AuditLog.objects.count(), before)
        self.client.force_login(self.gm)
        audit_page = self.client.get(
            reverse("world:campaign_audit_list", args=[self.campaign.pk])
        )
        self.assertNotContains(audit_page, "secret-memo")
        self.assertNotContains(audit_page, "secret-body")
        self.assertNotContains(audit_page, "changed-secret")


class PersonalNotePresentationTests(PersonalNotesN1Mixin, TestCase):
    def test_workspace_preview_is_bounded_to_three_and_has_no_dates(self):
        for number in range(5):
            self.note(memo=f"Память {number}", body=f"Мысль {number}")
        self.client.force_login(self.player_a)
        response = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        self.assertEqual(len(response.context["held_thoughts_preview"]), 3)
        self.assertContains(response, "Удержанные мысли")
        self.assertContains(response, "Удержать мысль")
        self.assertNotContains(response, "Память 0")
        self.assertNotContains(response, "Память 1")
        self.assertNotContains(response, "created_at")

    def test_full_index_uses_twenty_four_row_pagination(self):
        CharacterNote.objects.bulk_create(
            [
                CharacterNote(character=self.character, body=f"Мысль {number}")
                for number in range(25)
            ]
        )
        self.client.force_login(self.player_a)
        first = self.client.get(self.list_url())
        second = self.client.get(self.list_url() + "?page=2")
        self.assertEqual(len(first.context["page"].object_list), 24)
        self.assertEqual(len(second.context["page"].object_list), 1)
        self.assertContains(first, "Более далёкие мысли")

    def test_conversational_copy_and_plain_form_contract(self):
        self.client.force_login(self.player_a)
        response = self.client.get(self.hold_url())
        self.assertContains(response, "Желаете дать памятку этой мысли?")
        self.assertContains(response, "Что вы хотите сохранить в памяти?")
        self.assertContains(response, "оставить без памятки")
        self.assertContains(response, ">Удержать<", html=False)
        for forbidden in ("Создать заметку", "Title", "Content", "Save", "Author", "Created at"):
            self.assertNotContains(response, forbidden)
        self.assertNotContains(response, 'name="character"', html=False)

    def test_reduced_motion_and_progressive_enhancement_assets_exist(self):
        root = Path(__file__).resolve().parents[2]
        css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
        script = (root / "static" / "js" / "held-thoughts.js").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn(".held-thought", css)
        self.assertIn("animation: none !important", css)
        self.assertIn("memory-writing-manifest", css)
        self.assertIn("prefers-reduced-motion", script)
        self.assertIn("compositionend", script)
        self.assertIn("data-thought-step", script)
        self.assertNotIn("innerHTML", script)

    def test_workspace_keeps_pw2_but_notes_use_neutral_memory_space(self):
        self.client.force_login(self.player_a)
        workspace = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        notes = self.client.get(self.list_url())
        self.assertIn("character_ambience", workspace.context)
        self.assertIn("character_ambience", notes.context)
        self.assertContains(workspace, 'class="ambient-scene ambient-scene--neutral character-ambience"', html=False)
        self.assertNotContains(notes, 'class="ambient-scene', html=False)
        self.assertContains(notes, 'data-memory-space', html=False)
        self.assertNotContains(notes, 'data-condition=', html=False)

    def test_ux11_character_facing_copy_avoids_meta_character_wording(self):
        self.client.force_login(self.player_a)
        workspace = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        notes = self.client.get(self.list_url())
        hold = self.client.get(self.hold_url())
        for response in (workspace, notes, hold):
            for forbidden in (
                "ваш персонаж",
                "персонаж знает",
                "данные отсутствуют",
                "список пуст",
            ):
                self.assertNotContains(response, forbidden)
        self.assertNotContains(hold, "Она может остаться без памятки")
        self.assertNotContains(hold, "Слова останутся только")

    def test_ux11_workspace_modules_are_reflection_nodes_not_generic_panels(self):
        self.client.force_login(self.player_a)
        workspace = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        self.assertContains(workspace, 'class="workspace-module workspace-module--tiamana"', html=False)
        self.assertNotContains(workspace, 'class="panel workspace-module', html=False)
        self.assertContains(workspace, 'class="reflection-action reflection-action--manifest"', html=False)


class CharacterNoteMigrationTests(TransactionTestCase):
    migrate_from = {"characters": "0003_character_location_state_l1"}
    migrate_to = {"characters": "0004_character_note_n1"}

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
        LocationModel = old_apps.get_model("characters", "CharacterLocationState")
        ConnectionModel = old_apps.get_model("roll20", "Roll20Connection")
        BindingModel = old_apps.get_model("roll20", "Roll20CharacterBinding")

        user = User.objects.create(username="n1-legacy-owner")
        campaign = CampaignModel.objects.create(name="N1 Legacy Campaign")
        membership = Membership.objects.create(campaign=campaign, user=user, role="player")
        character = CharacterModel.objects.create(
            campaign=campaign,
            owner=membership,
            name="Preserved Character",
            is_active=True,
        )
        archived = CharacterModel.objects.create(
            campaign=campaign,
            name="Preserved Archive",
            is_active=False,
            archived_at=datetime.now(datetime_timezone.utc),
        )
        location = LocationModel.objects.create(
            character=character,
            latitude="12.345678",
            longitude="-87.654321",
        )
        roll20_connection = ConnectionModel.objects.create(campaign=campaign)
        binding = BindingModel.objects.create(
            connection=roll20_connection,
            character=character,
            roll20_character_id="n1-preserved-roll20",
        )
        self.ids = {
            "character": character.pk,
            "archived": archived.pk,
            "membership": membership.pk,
            "location": location.pk,
            "binding": binding.pk,
        }

        executor = MigrationExecutor(connection)
        to_targets = self._targets(executor, self.migrate_to)
        executor.migrate(to_targets)
        self.apps = executor.loader.project_state(to_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_additive_migration_preserves_character_state_and_creates_zero_notes(self):
        CharacterModel = self.apps.get_model("characters", "Character")
        CharacterNoteModel = self.apps.get_model("characters", "CharacterNote")
        LocationModel = self.apps.get_model("characters", "CharacterLocationState")
        BindingModel = self.apps.get_model("roll20", "Roll20CharacterBinding")
        character = CharacterModel.objects.get(pk=self.ids["character"])
        archived = CharacterModel.objects.get(pk=self.ids["archived"])
        self.assertEqual(character.owner_id, self.ids["membership"])
        self.assertTrue(character.is_active)
        self.assertFalse(archived.is_active)
        self.assertTrue(LocationModel.objects.filter(pk=self.ids["location"], character=character).exists())
        self.assertTrue(BindingModel.objects.filter(pk=self.ids["binding"], character=character).exists())
        self.assertEqual(CharacterNoteModel.objects.count(), 0)
