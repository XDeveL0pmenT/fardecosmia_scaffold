import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
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
from characters.admin import CharacterLocationStateAdmin
from characters.models import Character, CharacterLocationState
from characters.services import (
    CharacterLocationConflict,
    get_effective_character_location,
    initialize_character_location,
)
from world.models import AuditLog


class CharacterLocationL1Mixin:
    def setUp(self):
        super().setUp()
        users = get_user_model().objects
        self.gm = users.create_user(username="l1-gm", password="pass")
        self.foreign_gm = users.create_user(username="l1-foreign-gm", password="pass")
        self.player = users.create_user(username="l1-player", password="pass")
        self.editor = users.create_user(username="l1-editor", password="pass")
        self.root = users.create_superuser(
            username="l1-root", email="root@example.com", password="pass"
        )
        self.editor.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="world",
                codename="manage_global_canon",
            )
        )
        self.campaign = Campaign.objects.create(
            name="L1 Campaign",
            world_minutes=765432,
        )
        self.foreign_campaign = Campaign.objects.create(name="Foreign Campaign")
        self.gm_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        CampaignMembership.objects.create(
            campaign=self.foreign_campaign,
            user=self.foreign_gm,
            role=CampaignMembership.Role.GM,
        )
        self.player_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )

    def character(self, *, name="Лиора", owner=None, is_active=True, campaign=None):
        character = Character(
            campaign=campaign or self.campaign,
            owner=owner,
            name=name,
            is_active=is_active,
        )
        character.full_clean()
        character.save()
        return character

    def place(self, character, **overrides):
        return initialize_character_location(
            campaign=self.campaign,
            character_id=character.pk,
            actor=self.gm,
            latitude=overrides.get("latitude", "12.345678"),
            longitude=overrides.get("longitude", "-45.123456"),
        )


class CharacterLocationServiceTests(CharacterLocationL1Mixin, TestCase):
    def test_gm_initial_placement_succeeds_and_is_audited_at_world_time(self):
        character = self.character(owner=self.player_membership)
        state = self.place(character)
        self.assertEqual(state.latitude, Decimal("12.345678"))
        self.assertEqual(state.longitude, Decimal("-45.123456"))
        audit = AuditLog.objects.get(action="character.location_initialized")
        self.assertEqual(audit.actor, self.gm)
        self.assertEqual(audit.campaign, self.campaign)
        self.assertEqual(audit.world_minutes, 765432)
        self.assertEqual(audit.target_object_id, str(character.pk))
        self.assertEqual(audit.before_state, {"location": None})
        self.assertEqual(audit.after_state["latitude"], "12.345678")
        self.assertEqual(
            audit.metadata["coordinate_system"],
            "fardecosmia_planetary_lonlat",
        )

    def test_audit_failure_rolls_back_location(self):
        character = self.character()
        with mock.patch(
            "characters.services.record_audit",
            side_effect=RuntimeError("audit failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.place(character)
        self.assertFalse(CharacterLocationState.objects.filter(character=character).exists())

    def test_player_foreign_gm_and_canon_editor_are_denied(self):
        for actor in (self.player, self.foreign_gm, self.editor):
            character = self.character(name=f"Denied {actor.pk}")
            with self.subTest(actor=actor.username), self.assertRaises(PermissionDenied):
                initialize_character_location(
                    campaign=self.campaign,
                    character_id=character.pk,
                    actor=actor,
                    latitude=1,
                    longitude=2,
                )
            self.assertFalse(
                CharacterLocationState.objects.filter(character=character).exists()
            )

    def test_superuser_can_place_without_membership(self):
        character = self.character()
        state = initialize_character_location(
            campaign=self.campaign,
            character_id=character.pk,
            actor=self.root,
            latitude=1,
            longitude=2,
        )
        self.assertEqual(state.character, character)

    def test_invalid_latitude_and_precision_are_denied(self):
        for latitude in ("90.000001", "-90.000001", "NaN", True, "1.1234567"):
            character = self.character(name=f"Invalid {latitude}")
            with self.subTest(latitude=latitude), self.assertRaises(
                CharacterLocationConflict
            ):
                self.place(character, latitude=latitude)
        self.assertEqual(CharacterLocationState.objects.count(), 0)

    def test_longitude_seam_is_canonical_and_invalid_values_are_denied(self):
        character = self.character(name="Seam")
        state = self.place(character, longitude="180")
        self.assertEqual(state.longitude, Decimal("-180.000000"))
        for longitude in ("180.000001", "-180.000001", "Infinity", "1.1234567"):
            target = self.character(name=f"Invalid {longitude}")
            with self.subTest(longitude=longitude), self.assertRaises(
                CharacterLocationConflict
            ):
                self.place(target, longitude=longitude)

    def test_second_placement_is_denied_and_original_is_unchanged(self):
        character = self.character()
        original = self.place(character)
        with self.assertRaises(CharacterLocationConflict):
            self.place(character, latitude="55", longitude="66")
        original.refresh_from_db()
        self.assertEqual(original.latitude, Decimal("12.345678"))
        self.assertEqual(original.longitude, Decimal("-45.123456"))
        self.assertEqual(
            AuditLog.objects.filter(action="character.location_initialized").count(),
            1,
        )

    def test_archived_character_is_denied_but_unassigned_active_is_allowed(self):
        archived = self.character(name="Archived", is_active=False)
        with self.assertRaises(CharacterLocationConflict):
            self.place(archived)
        unassigned = self.character(name="Unassigned")
        self.assertIsNone(unassigned.owner)
        self.assertEqual(self.place(unassigned).character, unassigned)

    def test_resolver_is_empty_before_and_canonical_after_placement(self):
        character = self.character()
        self.assertIsNone(get_effective_character_location(character))
        self.place(character, latitude="-12.5", longitude="180")
        character = Character.objects.select_related("location_state").get(pk=character.pk)
        resolved = get_effective_character_location(character)
        self.assertEqual(resolved.character_id, character.pk)
        self.assertEqual(resolved.latitude, Decimal("-12.500000"))
        self.assertEqual(resolved.longitude, Decimal("-180.000000"))
        self.assertEqual(resolved.source, "initial_placement")


class CharacterLocationViewTests(CharacterLocationL1Mixin, TestCase):
    def placement_url(self, character, campaign=None):
        return reverse(
            "characters:initial_placement",
            args=[(campaign or self.campaign).pk, character.pk],
        )

    def test_get_renders_local_fardecosmia_atlas_without_mutation(self):
        character = self.character()
        self.client.force_login(self.gm)
        response = self.client.get(self.placement_url(character))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "characters/character_initial_placement.html")
        self.assertContains(response, "vendor/leaflet/1.9.4/dist/leaflet.js")
        self.assertContains(response, "character_initial_placement.js")
        self.assertContains(response, "fardecosmia-atlas-config")
        self.assertNotContains(response, "unpkg.com")
        self.assertNotContains(response, "tile.openstreetmap")
        self.assertEqual(CharacterLocationState.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_gm_post_persists_then_normal_ui_has_no_replace_action(self):
        character = self.character()
        detail_url = reverse("characters:detail", args=[self.campaign.pk, character.pk])
        self.client.force_login(self.gm)
        before = self.client.get(detail_url)
        self.assertContains(before, "Установить исходное положение")
        response = self.client.post(
            self.placement_url(character),
            {"latitude": "22.000001", "longitude": "33.000002", "confirmed": "on"},
            follow=True,
        )
        self.assertRedirects(response, detail_url)
        # Django's active Russian locale renders the decimal separator as a
        # comma; persistence itself is asserted through the model below.
        self.assertContains(response, "22,000001")
        self.assertContains(response, "33,000002")
        state = CharacterLocationState.objects.get(character=character)
        self.assertEqual(state.latitude, Decimal("22.000001"))
        self.assertEqual(state.longitude, Decimal("33.000002"))
        self.assertNotContains(response, ">Установить исходное положение</a>", html=False)
        repeat = self.client.get(self.placement_url(character))
        self.assertRedirects(repeat, detail_url)

    def test_confirmation_and_invalid_coordinates_are_server_enforced(self):
        character = self.character()
        self.client.force_login(self.gm)
        for payload in (
            {"latitude": "1", "longitude": "2"},
            {"latitude": "91", "longitude": "2", "confirmed": "on"},
            {"latitude": "1", "longitude": "181", "confirmed": "on"},
        ):
            response = self.client.post(self.placement_url(character), payload)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(CharacterLocationState.objects.exists())

    def test_player_foreign_gm_and_canon_editor_direct_urls_are_denied(self):
        character = self.character(owner=self.player_membership)
        for actor in (self.player, self.foreign_gm, self.editor):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                self.assertEqual(self.client.get(self.placement_url(character)).status_code, 403)
                self.assertEqual(
                    self.client.post(
                        self.placement_url(character),
                        {"latitude": "1", "longitude": "2", "confirmed": "on"},
                    ).status_code,
                    403,
                )
        self.assertFalse(CharacterLocationState.objects.exists())

    def test_foreign_campaign_character_forgery_is_404(self):
        foreign_character = self.character(campaign=self.foreign_campaign)
        self.client.force_login(self.gm)
        self.assertEqual(self.client.get(self.placement_url(foreign_character)).status_code, 404)
        self.assertEqual(
            self.client.post(
                self.placement_url(foreign_character),
                {"latitude": "1", "longitude": "2", "confirmed": "on"},
            ).status_code,
            404,
        )

    def test_archived_character_has_no_action_and_direct_route_is_denied(self):
        character = self.character(is_active=False)
        self.client.force_login(self.gm)
        detail = self.client.get(
            reverse("characters:detail", args=[self.campaign.pk, character.pk])
        )
        self.assertNotContains(detail, "Установить исходное положение")
        self.assertEqual(self.client.get(self.placement_url(character)).status_code, 403)

    def test_player_workspace_exposes_presence_only_and_no_gm_atlas_or_coordinates(self):
        character = self.character(owner=self.player_membership)
        self.place(character, latitude="17.123456", longitude="-88.654321")
        self.client.force_login(self.player)
        response = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        self.assertContains(response, "Ваше положение отражено.")
        for hidden in (
            "17.123456",
            "-88.654321",
            "fardecosmia-atlas-config",
            "leaflet.js",
            "Установить исходное положение",
            "Погода",
        ):
            self.assertNotContains(response, hidden)

    def test_workspace_queries_remain_bounded_with_location_prefetched(self):
        selected = None
        for index in range(20):
            character = self.character(
                name=f"L1 Character {index:02d}",
                owner=self.player_membership,
            )
            CharacterLocationState.objects.create(
                character=character,
                latitude=Decimal(index),
                longitude=Decimal(index),
            )
            selected = selected or character
        self.player_membership.active_character = selected
        self.player_membership.save(update_fields=["active_character"])
        self.client.force_login(self.player)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("campaigns:campaign_detail", args=[self.campaign.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 12)

    def test_location_admin_is_superuser_read_only(self):
        model_admin = CharacterLocationStateAdmin(CharacterLocationState, admin.site)
        request = RequestFactory().get("/admin/characters/characterlocationstate/")
        request.user = self.root
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_client_code_uses_custom_planet_crs_and_no_earth_distance_helper(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "static"
            / "js"
            / "atlas"
            / "character_initial_placement.js"
        ).read_text(encoding="utf-8")
        self.assertIn("createFardecosmiaCRS", source)
        self.assertIn("normalizeLongitude", source)
        self.assertNotIn("L.CRS.Earth", source)
        self.assertNotIn("distanceTo", source)
        self.assertNotIn("haversine", source.lower())


class CharacterLocationMigrationTests(TransactionTestCase):
    migrate_from = {"characters": "0002_character_archived_at_character_is_active_and_more"}
    migrate_to = {"characters": "0003_character_location_state_l1"}

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
        user = User.objects.create(username="l1-legacy-owner")
        campaign = CampaignModel.objects.create(name="L1 Legacy")
        membership = Membership.objects.create(campaign=campaign, user=user, role="player")
        character = CharacterModel.objects.create(
            campaign=campaign,
            owner=membership,
            name="L1 Legacy Character",
            biography="Preserved",
        )
        roll20_connection = ConnectionModel.objects.create(campaign=campaign)
        binding = BindingModel.objects.create(
            connection=roll20_connection,
            character=character,
            roll20_character_id="l1-legacy-roll20",
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
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_additive_migration_preserves_character_membership_and_roll20(self):
        CharacterModel = self.apps.get_model("characters", "Character")
        Membership = self.apps.get_model("campaigns", "CampaignMembership")
        BindingModel = self.apps.get_model("roll20", "Roll20CharacterBinding")
        LocationModel = self.apps.get_model("characters", "CharacterLocationState")
        character = CharacterModel.objects.get(pk=self.character_id)
        self.assertEqual(character.owner_id, self.membership_id)
        self.assertTrue(character.is_active)
        self.assertEqual(Membership.objects.get(pk=self.membership_id).campaign_id, character.campaign_id)
        self.assertEqual(BindingModel.objects.get(pk=self.binding_id).character_id, character.pk)
        self.assertEqual(LocationModel.objects.count(), 0)


@skipUnless(connection.vendor == "postgresql", "Row-lock race proof requires PostgreSQL.")
class CharacterLocationConcurrencyTests(CharacterLocationL1Mixin, TransactionTestCase):
    reset_sequences = True

    def test_two_gms_can_create_only_one_initial_location(self):
        second_gm = get_user_model().objects.create_user(
            username="l1-second-gm", password="pass"
        )
        CampaignMembership.objects.create(
            campaign=self.campaign,
            user=second_gm,
            role=CampaignMembership.Role.GM,
        )
        character = self.character()
        barrier = threading.Barrier(2)

        def worker(actor_id, latitude):
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                initialize_character_location(
                    campaign=Campaign.objects.get(pk=self.campaign.pk),
                    character_id=character.pk,
                    actor=get_user_model().objects.get(pk=actor_id),
                    latitude=latitude,
                    longitude="40",
                )
                return "placed"
            except CharacterLocationConflict:
                return "blocked"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(
                    lambda args: worker(*args),
                    [(self.gm.pk, "10"), (second_gm.pk, "20")],
                )
            )
        self.assertCountEqual(outcomes, ["placed", "blocked"])
        self.assertEqual(CharacterLocationState.objects.filter(character=character).count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(action="character.location_initialized").count(),
            1,
        )
