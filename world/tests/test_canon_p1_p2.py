from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from world.models import CampaignEntityOverride, Region, WorldEntry
from world.services.access import (
    can_manage_campaign,
    can_manage_global_canon,
    can_view_campaign,
    can_view_global_atlas,
)
from world.services.canon import (
    create_campaign_world_entry,
    create_global_world_entry,
    delete_global_world_entry,
    remove_campaign_override,
    set_campaign_override,
    set_campaign_suppression,
    update_campaign_world_entry,
    update_global_world_entry,
)
from world.services.overrides import (
    EffectiveSource,
    effective_world_entries,
    resolve_for_campaign,
)


class CanonFoundationMixin:
    def setUp(self):
        self.campaign_a = Campaign.objects.create(name="Campaign A")
        self.campaign_b = Campaign.objects.create(name="Campaign B")
        users = get_user_model().objects
        self.gm_a = users.create_user(username="gm-a", password="pass")
        self.gm_b = users.create_user(username="gm-b", password="pass")
        self.player_a = users.create_user(username="player-a", password="pass")
        self.editor = users.create_user(username="editor", password="pass")
        self.editor_gm_a = users.create_user(username="editor-gm-a", password="pass")
        self.superuser = users.create_superuser(
            username="root", email="root@example.com", password="pass"
        )
        CampaignMembership.objects.bulk_create(
            [
                CampaignMembership(campaign=self.campaign_a, user=self.gm_a, role=CampaignMembership.Role.GM),
                CampaignMembership(campaign=self.campaign_b, user=self.gm_b, role=CampaignMembership.Role.GM),
                CampaignMembership(campaign=self.campaign_a, user=self.player_a, role=CampaignMembership.Role.PLAYER),
                CampaignMembership(campaign=self.campaign_a, user=self.editor_gm_a, role=CampaignMembership.Role.GM),
            ]
        )
        permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        self.editor.user_permissions.add(permission)
        self.editor_gm_a.user_permissions.add(permission)

    def global_entry(self, **overrides):
        values = {
            "actor": self.editor,
            "kind": "lore",
            "slug": "entry",
            "title": "A",
            "summary": "A",
            "body": "Base body",
        }
        values.update(overrides)
        return create_global_world_entry(**values)


class WorldEntryModelTests(CanonFoundationMixin, TestCase):
    def test_global_requires_null_campaign_and_campaign_scope_requires_campaign(self):
        global_entry = WorldEntry(
            scope=WorldEntry.Scope.GLOBAL,
            campaign=self.campaign_a,
            kind="lore",
            slug="invalid-global",
            title="Invalid",
        )
        with self.assertRaises(ValidationError):
            global_entry.full_clean()

        campaign_entry = WorldEntry(
            scope=WorldEntry.Scope.CAMPAIGN,
            kind="lore",
            slug="invalid-campaign",
            title="Invalid",
        )
        with self.assertRaises(ValidationError):
            campaign_entry.full_clean()

    def test_scope_consistency_is_a_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorldEntry.objects.create(
                scope=WorldEntry.Scope.GLOBAL,
                campaign=self.campaign_a,
                kind="lore",
                slug="db-invalid",
                title="Invalid",
            )

    def test_global_and_campaign_identity_constraints(self):
        self.global_entry()
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorldEntry.objects.create(
                scope=WorldEntry.Scope.GLOBAL,
                kind="lore",
                slug="entry",
                title="Duplicate",
            )

        first = create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="concept",
            slug="local",
            title="Local A",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorldEntry.objects.create(
                scope=WorldEntry.Scope.CAMPAIGN,
                campaign=self.campaign_a,
                kind=first.kind,
                slug=first.slug,
                title="Duplicate local",
            )
        other = create_campaign_world_entry(
            actor=self.gm_b,
            campaign=self.campaign_b,
            kind="concept",
            slug="local",
            title="Local B",
        )
        self.assertNotEqual(first.pk, other.pk)

    def test_campaign_only_collision_with_global_requires_override(self):
        self.global_entry()
        with self.assertRaisesMessage(ValidationError, "создайте override"):
            create_campaign_world_entry(
                actor=self.gm_a,
                campaign=self.campaign_a,
                kind="lore",
                slug="entry",
                title="Collision",
            )

    def test_scope_and_campaign_are_immutable_in_normal_services(self):
        global_entry = self.global_entry()
        with self.assertRaises(ValidationError):
            update_global_world_entry(
                actor=self.editor,
                entry=global_entry,
                scope=WorldEntry.Scope.CAMPAIGN,
            )
        local = create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="lore",
            slug="local",
            title="Local",
        )
        with self.assertRaises(ValidationError):
            update_campaign_world_entry(
                actor=self.gm_b,
                campaign=self.campaign_b,
                entry=local,
                title="Cannot move",
            )

    def test_revision_increments_only_on_meaningful_service_change(self):
        entry = self.global_entry()
        unchanged = update_global_world_entry(
            actor=self.editor,
            entry=entry,
            title="A",
        )
        self.assertEqual(unchanged.revision, 1)
        changed = update_global_world_entry(
            actor=self.editor,
            entry=entry,
            title="C",
        )
        self.assertEqual(changed.revision, 2)
        self.client.force_login(self.editor)
        self.client.get(reverse("world:global_world_entry_detail", args=[entry.pk]))
        entry.refresh_from_db()
        self.assertEqual(entry.revision, 2)


class CampaignOverrideTests(CanonFoundationMixin, TestCase):
    def test_sparse_override_resolution_tracks_later_base_changes(self):
        entry = self.global_entry()
        override = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "B"},
        )
        self.assertEqual(override.patch, {"summary": "B"})
        resolved = resolve_for_campaign(entry, self.campaign_a)
        self.assertEqual(resolved.title, "A")
        self.assertEqual(resolved.summary, "B")
        self.assertEqual(resolved.source, EffectiveSource.GLOBAL_OVERRIDDEN)

        entry = update_global_world_entry(actor=self.editor, entry=entry, title="C")
        resolved = resolve_for_campaign(entry, self.campaign_a)
        self.assertEqual(resolved.title, "C")
        self.assertEqual(resolved.summary, "B")

        set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"title": "D", "summary": "B"},
        )
        resolved = resolve_for_campaign(entry, self.campaign_a)
        self.assertEqual((resolved.title, resolved.summary), ("D", "B"))
        entry.refresh_from_db()
        self.assertEqual((entry.title, entry.summary), ("C", "A"))

    def test_effective_projection_is_read_only_and_does_not_mutate_base(self):
        entry = self.global_entry()
        set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"title": "Campaign title"},
        )
        resolved = resolve_for_campaign(entry, self.campaign_a)
        with self.assertRaises((AttributeError, TypeError)):
            resolved.title = "Mutation"
        with self.assertRaises(TypeError):
            resolved.effective_values["title"] = "Mutation"
        entry.refresh_from_db()
        self.assertEqual(entry.title, "A")

    def test_campaign_target_non_whitelist_forbidden_and_null_validation(self):
        local = create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="lore",
            slug="local",
            title="Local",
        )
        with self.assertRaises(ValidationError):
            set_campaign_override(
                actor=self.gm_a,
                campaign=self.campaign_a,
                target=local,
                patch={"title": "No"},
            )
        region = Region.objects.create(campaign=self.campaign_a, name="Region")
        with self.assertRaises(ValidationError):
            set_campaign_override(
                actor=self.gm_a,
                campaign=self.campaign_a,
                target=region,
                patch={"name": "No"},
            )
        entry = self.global_entry(slug="nullable")
        with self.assertRaises(ValidationError):
            set_campaign_override(
                actor=self.gm_a,
                campaign=self.campaign_a,
                target=entry,
                patch={"title": None},
            )

    def test_forbidden_malformed_and_missing_target_rejected(self):
        entry = self.global_entry()
        for patch in (["title"], {"slug": "forbidden"}):
            with self.assertRaises(ValidationError):
                set_campaign_override(
                    actor=self.gm_a,
                    campaign=self.campaign_a,
                    target=entry,
                    patch=patch,
                )
        entry.delete()
        with self.assertRaises(ValidationError):
            set_campaign_override(
                actor=self.gm_a,
                campaign=self.campaign_a,
                target=entry,
                patch={"title": "Missing"},
            )

    def test_override_unique_revision_base_provenance_and_cleanup(self):
        entry = self.global_entry()
        override = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "B"},
        )
        self.assertEqual(override.base_revision_at_creation, entry.revision)
        self.assertEqual(override.revision, 1)
        same = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "B"},
        )
        self.assertEqual(same.revision, 1)
        changed = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "C"},
        )
        self.assertEqual(changed.revision, 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampaignEntityOverride.objects.create(
                campaign=self.campaign_a,
                content_type=ContentType.objects.get_for_model(WorldEntry),
                object_id=str(entry.pk),
            )
        cleaned = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": entry.summary},
        )
        self.assertIsNone(cleaned)
        self.assertFalse(CampaignEntityOverride.objects.exists())

    def test_suppression_restore_remove_and_campaign_isolation(self):
        entry = self.global_entry()
        set_campaign_suppression(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            is_suppressed=True,
        )
        self.assertEqual(effective_world_entries(self.campaign_a), [])
        self.assertEqual(len(effective_world_entries(self.campaign_b)), 1)
        diagnostics = effective_world_entries(self.campaign_a, include_suppressed=True)
        self.assertTrue(diagnostics[0].is_suppressed)
        set_campaign_suppression(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            is_suppressed=False,
        )
        self.assertEqual(len(effective_world_entries(self.campaign_a)), 1)
        set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"title": "Only A"},
        )
        remove_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
        )
        self.assertEqual(resolve_for_campaign(entry, self.campaign_a).title, "A")

    def test_campaign_only_entries_do_not_leak_and_list_is_bulk_loaded(self):
        global_entry = self.global_entry()
        local = create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="concept",
            slug="local-a",
            title="Only A",
        )
        set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=global_entry,
            patch={"summary": "A summary"},
        )
        ContentType.objects.clear_cache()
        with self.assertNumQueries(3):
            rows = effective_world_entries(self.campaign_a)
        self.assertEqual({row.pk for row in rows}, {global_entry.pk, local.pk})
        self.assertEqual(
            {row.pk for row in effective_world_entries(self.campaign_b)},
            {global_entry.pk},
        )

    def test_global_delete_is_blocked_while_override_exists(self):
        entry = self.global_entry()
        set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "B"},
        )
        with self.assertRaisesMessage(ValidationError, "Campaign A"):
            delete_global_world_entry(actor=self.editor, entry=entry)
        self.assertTrue(WorldEntry.objects.filter(pk=entry.pk).exists())


class AccessPolicyAndUiTests(CanonFoundationMixin, TestCase):
    def test_access_policy_matrix(self):
        self.assertFalse(can_view_global_atlas(self.player_a))
        self.assertTrue(can_view_global_atlas(self.gm_a))
        self.assertTrue(can_view_global_atlas(self.editor))
        self.assertTrue(can_view_global_atlas(self.superuser))

        self.assertFalse(can_manage_global_canon(self.gm_a))
        self.assertTrue(can_manage_global_canon(self.editor))
        self.assertTrue(can_manage_global_canon(self.editor_gm_a))
        self.assertTrue(can_manage_global_canon(self.superuser))

        self.assertTrue(can_view_campaign(self.player_a, self.campaign_a))
        self.assertFalse(can_manage_campaign(self.player_a, self.campaign_a))
        self.assertTrue(can_manage_campaign(self.gm_a, self.campaign_a))
        self.assertFalse(can_manage_campaign(self.gm_a, self.campaign_b))
        self.assertFalse(can_manage_campaign(self.editor, self.campaign_a))
        self.assertTrue(can_manage_campaign(self.editor_gm_a, self.campaign_a))
        self.assertTrue(can_manage_campaign(self.superuser, self.campaign_a))

    def test_global_list_is_read_only_for_gm_and_editable_for_editor(self):
        entry = self.global_entry()
        self.client.force_login(self.gm_a)
        response = self.client.get(reverse("world:global_world_entry_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, entry.title)
        self.assertNotContains(response, "Новая запись")

        self.client.force_login(self.editor)
        response = self.client.get(reverse("world:global_world_entry_list"))
        self.assertContains(response, "Новая запись")
        self.assertContains(
            self.client.get(reverse("world:global_world_entry_detail", args=[entry.pk])),
            "Изменить",
        )

    def test_global_create_server_permission(self):
        url = reverse("world:global_world_entry_create")
        payload = {"kind": "lore", "slug": "created", "title": "Created", "summary": "", "body": ""}
        self.client.force_login(self.gm_a)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertTrue(WorldEntry.objects.filter(slug="created", scope=WorldEntry.Scope.GLOBAL).exists())

    def test_campaign_write_and_idor_permissions(self):
        create_url = reverse("world:campaign_world_entry_create", args=[self.campaign_a.pk])
        payload = {"kind": "lore", "slug": "local", "title": "Local", "summary": "", "body": ""}
        for denied_user in (self.player_a, self.gm_b, self.editor):
            self.client.force_login(denied_user)
            self.assertEqual(self.client.post(create_url, payload).status_code, 403)
        self.client.force_login(self.gm_a)
        self.assertEqual(self.client.post(create_url, payload).status_code, 302)
        entry = WorldEntry.objects.get(scope=WorldEntry.Scope.CAMPAIGN)

        self.client.force_login(self.gm_b)
        response = self.client.post(
            reverse("world:campaign_world_entry_edit", args=[self.campaign_a.pk, entry.pk]),
            {**payload, "title": "Forged"},
        )
        self.assertEqual(response.status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Local")

    def test_override_ui_badges_and_sparse_patch(self):
        entry = self.global_entry()
        self.client.force_login(self.gm_a)
        response = self.client.post(
            reverse("world:campaign_world_entry_override", args=[self.campaign_a.pk, entry.pk]),
            {"title": "", "summary": "Campaign summary", "body": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        override = CampaignEntityOverride.objects.get(campaign=self.campaign_a)
        self.assertEqual(override.patch, {"summary": "Campaign summary"})
        self.assertContains(response, "Изменено в кампании")
        self.assertContains(response, "Campaign summary")

    def test_player_cannot_open_effective_canon_or_gm_inspector(self):
        self.client.force_login(self.player_a)
        self.assertEqual(
            self.client.get(reverse("world:campaign_world_entry_list", args=[self.campaign_a.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("world:campaign_point_inspection", args=[self.campaign_a.pk]),
                {"latitude": 0, "longitude": 0},
            ).status_code,
            403,
        )

    def test_global_atlas_access_and_post_are_hardened(self):
        url = reverse("world:global_world_map")
        for allowed in (self.gm_a, self.editor, self.superuser):
            self.client.force_login(allowed)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-leaflet-map")
        self.client.force_login(self.player_a)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.gm_a)
        self.assertEqual(self.client.post(url, {}).status_code, 405)

    def test_canon_editor_without_membership_cannot_advance_campaign(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("campaigns:advance_time", args=[self.campaign_a.pk]),
            {"amount": "10", "unit": "minutes"},
        )
        self.assertEqual(response.status_code, 403)
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.world_minutes, 0)

    def test_superuser_can_manage_both_scopes(self):
        global_entry = create_global_world_entry(
            actor=self.superuser,
            kind="lore",
            slug="super-global",
            title="Global",
        )
        local = create_campaign_world_entry(
            actor=self.superuser,
            campaign=self.campaign_a,
            kind="lore",
            slug="super-local",
            title="Local",
        )
        set_campaign_override(
            actor=self.superuser,
            campaign=self.campaign_a,
            target=global_entry,
            patch={"title": "Super override"},
        )
        self.assertEqual(resolve_for_campaign(global_entry, self.campaign_a).title, "Super override")
        self.assertEqual(local.campaign, self.campaign_a)
