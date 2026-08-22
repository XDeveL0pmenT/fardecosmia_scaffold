import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import User
from campaigns.models import Campaign, CampaignMembership, TimeAdvanceReport
from world.admin import AuditLogAdmin, WorldEntryAdmin
from world.models import AuditLog, Region, WorldEntry
from world.services.audit import MAX_AUDIT_COMPONENT_BYTES, record_audit
from world.services.canon import (
    create_campaign_world_entry,
    create_global_world_entry,
    delete_global_world_entry,
    remove_campaign_override,
    set_campaign_override,
    set_campaign_suppression,
    update_global_world_entry,
)
from world.services.map_layers import (
    update_campaign_biome_layer,
    update_global_biome_layer,
)
from world.services.regions import create_region, delete_region, update_region
from world.services.time import advance_world
from world.services.world_data import load_land_mask


class AuditP3Mixin:
    def setUp(self):
        self.campaign_a = Campaign.objects.create(name="Campaign A")
        self.campaign_b = Campaign.objects.create(name="Campaign B")
        self.gm_a = User.objects.create_user(username="gm-a", password="pass")
        self.gm_b = User.objects.create_user(username="gm-b", password="pass")
        self.player = User.objects.create_user(username="player", password="pass")
        self.editor = User.objects.create_user(username="editor", password="pass")
        self.superuser = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="pass",
        )
        CampaignMembership.objects.bulk_create(
            [
                CampaignMembership(
                    campaign=self.campaign_a,
                    user=self.gm_a,
                    role=CampaignMembership.Role.GM,
                ),
                CampaignMembership(
                    campaign=self.campaign_b,
                    user=self.gm_b,
                    role=CampaignMembership.Role.GM,
                ),
                CampaignMembership(
                    campaign=self.campaign_a,
                    user=self.player,
                    role=CampaignMembership.Role.PLAYER,
                ),
            ]
        )
        permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        self.editor.user_permissions.add(permission)

    def global_entry(self, *, slug="entry", title="Entry"):
        return create_global_world_entry(
            actor=self.editor,
            kind="lore",
            slug=slug,
            title=title,
            summary="Summary",
            body="Body",
        )


class AuditModelAndSafetyTests(AuditP3Mixin, TestCase):
    def test_global_and_campaign_scope_snapshots(self):
        global_row = record_audit(
            action="test.global",
            source=AuditLog.Source.SYSTEM,
            summary="Global",
            metadata={},
        )
        campaign_row = record_audit(
            action="test.campaign",
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=self.campaign_a,
            summary="Campaign",
        )
        self.assertIsNone(global_row.campaign_id)
        self.assertIsNone(global_row.world_minutes)
        self.assertEqual(global_row.actor_label_snapshot, "Система")
        self.assertEqual(campaign_row.campaign_id_snapshot, str(self.campaign_a.pk))
        self.assertEqual(campaign_row.campaign_label_snapshot, "Campaign A")
        self.assertEqual(campaign_row.world_minutes, 0)
        self.assertEqual(campaign_row.actor_label_snapshot, "gm-a")
        self.assertTrue(campaign_row.operation_id)
        self.assertEqual(campaign_row.metadata, {})

    def test_actor_campaign_and_target_snapshots_survive_deletion(self):
        transient_actor = User.objects.create_user(username="temporary")
        region = Region.objects.create(campaign=self.campaign_a, name="North")
        row = record_audit(
            action="test.snapshot",
            actor=transient_actor,
            campaign=self.campaign_a,
            target=region,
            summary="Snapshot",
        )
        region_id = str(region.pk)
        transient_actor.delete()
        region.delete()
        self.campaign_a.delete()
        row.refresh_from_db()
        self.assertIsNone(row.actor)
        self.assertEqual(row.actor_label_snapshot, "temporary")
        self.assertIsNone(row.campaign)
        self.assertEqual(row.campaign_label_snapshot, "Campaign A")
        self.assertEqual(row.target_object_id, region_id)
        self.assertEqual(row.target_label, "North")

    def test_normal_update_and_delete_are_rejected(self):
        row = record_audit(
            action="test.append_only",
            source=AuditLog.Source.SYSTEM,
            summary="Append only",
        )
        row.summary = "Changed"
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(ValidationError):
            row.delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=row.pk).update(summary="Changed")
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=row.pk).delete()

    def test_secret_keys_and_oversized_payload_are_rejected_without_truncation(self):
        for metadata in (
            {"password": "bad"},
            {"headers": {"Authorization": "Bearer bad"}},
            {"roll20_access_token": "bad"},
            {"cookie": "bad"},
        ):
            with self.assertRaises(ValidationError):
                record_audit(
                    action="test.secret",
                    actor=self.gm_a,
                    campaign=self.campaign_a,
                    summary="Rejected",
                    metadata=metadata,
                )
        with self.assertRaises(ValidationError):
            record_audit(
                action="test.large",
                actor=self.gm_a,
                campaign=self.campaign_a,
                summary="Rejected",
                metadata={"safe_text": "x" * (MAX_AUDIT_COMPONENT_BYTES + 1)},
            )
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_serialization_failure_rolls_back_business_mutation(self):
        with self.assertRaises(ValidationError):
            create_global_world_entry(
                actor=self.editor,
                kind="lore",
                slug="too-large",
                title="Too large",
                body="x" * (MAX_AUDIT_COMPONENT_BYTES + 1),
            )
        self.assertFalse(WorldEntry.objects.filter(slug="too-large").exists())
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_forced_outer_rollback_removes_mutation_and_audit(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                create_global_world_entry(
                    actor=self.editor,
                    kind="lore",
                    slug="rollback",
                    title="Rollback",
                )
                raise RuntimeError("force rollback")
        self.assertFalse(WorldEntry.objects.filter(slug="rollback").exists())
        self.assertEqual(AuditLog.objects.count(), 0)


class AuditDomainIntegrationTests(AuditP3Mixin, TestCase):
    def test_ten_minute_advance_creates_exactly_one_audit(self):
        advance_world(
            self.campaign_a.pk,
            10,
            advanced_by=self.gm_a,
            requested_amount=10,
            requested_unit=TimeAdvanceReport.RequestedUnit.MINUTES,
        )
        rows = AuditLog.objects.filter(action="campaign.time_advanced")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().metadata["delta_minutes"], 10)

    def test_world_entry_create_update_delete_exactly_once(self):
        entry = self.global_entry()
        self.assertEqual(AuditLog.objects.count(), 1)
        created = AuditLog.objects.get()
        self.assertEqual(created.action, "world_entry.created")
        self.assertIsNone(created.before_state)
        self.assertEqual(created.after_state["revision"], 1)
        entry = update_global_world_entry(
            actor=self.editor,
            entry=entry,
            title="Changed",
        )
        self.assertEqual(AuditLog.objects.count(), 2)
        updated = AuditLog.objects.first()
        self.assertEqual(updated.action, "world_entry.updated")
        self.assertEqual(updated.before_state["revision"], 1)
        self.assertEqual(updated.after_state["revision"], 2)
        delete_global_world_entry(actor=self.editor, entry=entry)
        self.assertEqual(AuditLog.objects.count(), 3)
        deleted = AuditLog.objects.first()
        self.assertEqual(deleted.action, "world_entry.deleted")
        self.assertEqual(deleted.target_object_id, str(entry.pk))
        self.assertFalse(WorldEntry.objects.filter(slug="entry").exists())

    def test_campaign_world_entry_captures_scope_and_world_time(self):
        self.campaign_a.world_minutes = 1234
        self.campaign_a.save(update_fields=["world_minutes"])
        entry = create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="lore",
            slug="local",
            title="Local",
        )
        row = AuditLog.objects.get()
        self.assertEqual(row.action, "world_entry.created")
        self.assertEqual(row.campaign, self.campaign_a)
        self.assertEqual(row.world_minutes, 1234)
        self.assertEqual(row.after_state["campaign_id"], str(self.campaign_a.pk))
        self.assertEqual(row.target_object_id, str(entry.pk))

    def test_override_action_lifecycle_has_no_duplicates_or_base_mutation(self):
        entry = self.global_entry()
        AuditLog.objects.all()  # Keep the creation row visible but ignored below.
        override = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "Campaign"},
        )
        override = set_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            patch={"summary": "Campaign 2"},
        )
        set_campaign_suppression(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            is_suppressed=True,
        )
        set_campaign_suppression(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
            is_suppressed=False,
        )
        remove_campaign_override(
            actor=self.gm_a,
            campaign=self.campaign_a,
            target=entry,
        )
        actions = list(
            AuditLog.objects.filter(action__startswith="campaign_override").order_by("id")
            .values_list("action", flat=True)
        )
        self.assertEqual(
            actions,
            [
                "campaign_override.created",
                "campaign_override.updated",
                "campaign_override.suppressed",
                "campaign_override.restored",
                "campaign_override.removed",
            ],
        )
        entry.refresh_from_db()
        self.assertEqual(entry.summary, "Summary")
        self.assertEqual(override.base_revision_at_creation, 1)

    def test_denied_and_invalid_actions_create_no_success_audit(self):
        with self.assertRaises(PermissionDenied):
            create_global_world_entry(
                actor=self.gm_a,
                kind="lore",
                slug="denied",
                title="Denied",
            )
        with self.assertRaises(ValidationError):
            create_campaign_world_entry(
                actor=self.gm_a,
                campaign=self.campaign_a,
                kind="lore",
                slug="",
                title="Invalid",
            )
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_region_create_update_delete_and_weather_children_do_not_spam(self):
        result = create_region(
            actor=self.gm_a,
            campaign=self.campaign_a,
            region=Region(name="North", map_polygon=[]),
            auto_configure_from_map=False,
        )
        region = result.region
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertGreaterEqual(region.weather_history.count(), 1)
        result = update_region(
            actor=self.gm_a,
            campaign=self.campaign_a,
            region=region,
            changes={"name": "Far North"},
        )
        self.assertEqual(AuditLog.objects.count(), 2)
        self.assertEqual(
            AuditLog.objects.first().metadata["changed_fields"],
            ["name"],
        )
        result = update_region(
            actor=self.gm_a,
            campaign=self.campaign_a,
            region=result.region,
            changes={
                "map_polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                "map_latitude": 63.0,
                "map_longitude": -126.0,
            },
            initialize_weather=True,
        )
        self.assertEqual(AuditLog.objects.count(), 3)
        self.assertEqual(AuditLog.objects.first().after_state["weather_geometry_revision"], 1)
        delete_region(
            actor=self.gm_a,
            campaign=self.campaign_a,
            region=result.region,
        )
        self.assertEqual(AuditLog.objects.count(), 4)
        self.assertEqual(AuditLog.objects.first().action, "region.deleted")

    def test_campaign_and_global_biome_writes_are_compact_and_authorized(self):
        land_index = next(
            index for index, is_land in enumerate(load_land_mask()["values"]) if is_land
        )
        cells = {str(land_index): Region.Biome.TUNDRA}
        campaign_layer = update_campaign_biome_layer(
            actor=self.gm_a,
            campaign=self.campaign_a,
            cells=cells,
        )
        campaign_row = AuditLog.objects.get(action="campaign_biome.updated")
        self.assertEqual(campaign_row.campaign, self.campaign_a)
        self.assertEqual(campaign_row.metadata["changed_cell_count"], 1)
        self.assertNotIn("biome_cells", str(campaign_row.before_state))
        self.assertEqual(campaign_layer.biome_cells, cells)

        global_layer = update_global_biome_layer(actor=self.editor, cells=cells)
        global_row = AuditLog.objects.get(action="global_biome.updated")
        self.assertIsNone(global_row.campaign)
        self.assertEqual(global_row.metadata["changed_cell_count"], 1)
        self.assertEqual(global_layer.biome_cells, cells)
        with self.assertRaises(PermissionDenied):
            update_global_biome_layer(actor=self.gm_a, cells={})
        self.assertEqual(AuditLog.objects.filter(action="global_biome.updated").count(), 1)

    def test_exact_vitok_and_fast_forward_each_create_one_high_level_row(self):
        advance_world(
            self.campaign_a.pk,
            self.campaign_a.calendar_minutes_per_turn,
            advanced_by=self.gm_a,
            requested_amount=1,
            requested_unit=TimeAdvanceReport.RequestedUnit.TURNS,
        )
        exact = AuditLog.objects.get(action="campaign.time_advanced")
        self.assertEqual(exact.metadata["simulation_mode"], "exact")
        self.assertEqual(exact.before_state["world_minutes"], 0)
        self.assertEqual(
            exact.after_state["world_minutes"],
            self.campaign_a.calendar_minutes_per_turn,
        )
        self.assertEqual(exact.world_minutes, exact.after_state["world_minutes"])
        advance_world(
            self.campaign_b.pk,
            self.campaign_b.calendar_minutes_per_turn * 5,
            advanced_by=self.gm_b,
            requested_amount=5,
            requested_unit=TimeAdvanceReport.RequestedUnit.TURNS,
        )
        fast = AuditLog.objects.get(
            action="campaign.time_advanced",
            campaign=self.campaign_b,
        )
        self.assertEqual(fast.metadata["simulation_mode"], "fast_forward")
        self.assertEqual(
            AuditLog.objects.filter(action="campaign.time_advanced").count(),
            2,
        )

    def test_failed_time_advance_rolls_back_time_report_and_audit(self):
        with patch(
            "world.services.time.build_time_advance_summary",
            side_effect=RuntimeError("report failed"),
        ), self.assertRaises(RuntimeError):
            advance_world(
                self.campaign_a.pk,
                10,
                advanced_by=self.gm_a,
                requested_amount=10,
                requested_unit=TimeAdvanceReport.RequestedUnit.MINUTES,
            )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.world_minutes, 0)
        self.assertEqual(self.campaign_a.time_advance_reports.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)


class AuditUiAndAdminTests(AuditP3Mixin, TestCase):
    def test_canon_document_and_audit_use_human_readable_presentation(self):
        entry = self.global_entry(title="Readable canon")
        self.client.force_login(self.editor)
        canon_response = self.client.get(
            reverse("world:global_world_entry_detail", args=[entry.pk])
        )
        self.assertContains(canon_response, "Подробное описание")
        self.assertContains(canon_response, "canon-reading-shell")
        audit = AuditLog.objects.get(action="world_entry.created")
        audit_response = self.client.get(
            reverse("world:global_audit_detail", args=[audit.pk])
        )
        self.assertContains(audit_response, "Создана запись канона")
        self.assertContains(audit_response, "Что именно поменялось")
        self.assertContains(audit_response, "Название")
        self.assertContains(audit_response, "Технические подробности")

    def test_leaflet_and_region_gets_create_zero_audits(self):
        region = Region.objects.create(campaign=self.campaign_a, name="Read only")
        self.client.force_login(self.gm_a)
        self.assertEqual(
            self.client.get(
                reverse("world:world_map", args=[self.campaign_a.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "world:region_detail",
                    args=[self.campaign_a.pk, region.pk],
                )
            ).status_code,
            200,
        )
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_campaign_biome_view_audits_own_gm_and_denies_other_gm(self):
        land_index = next(
            index for index, is_land in enumerate(load_land_mask()["values"]) if is_land
        )
        url = reverse("world:world_map", args=[self.campaign_a.pk])
        payload = {
            "action": "save-layer",
            "layer-layer_type": "biome",
            "layer-layer_cells": json.dumps(
                {str(land_index): Region.Biome.TUNDRA}
            ),
        }
        self.client.force_login(self.gm_b)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.assertEqual(AuditLog.objects.count(), 0)
        self.client.force_login(self.gm_a)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(
            AuditLog.objects.filter(action="campaign_biome.updated").count(),
            1,
        )

    def test_campaign_and_global_access_matrix_and_detail_idor(self):
        global_entry = self.global_entry()
        global_row = AuditLog.objects.get(target_object_id=str(global_entry.pk))
        create_campaign_world_entry(
            actor=self.gm_a,
            campaign=self.campaign_a,
            kind="lore",
            slug="local-a",
            title="Local A",
        )
        campaign_row = AuditLog.objects.get(campaign=self.campaign_a)
        campaign_url = reverse("world:campaign_audit_list", args=[self.campaign_a.pk])
        global_url = reverse("world:global_audit_list")
        for denied in (self.gm_b, self.player, self.editor):
            self.client.force_login(denied)
            self.assertEqual(self.client.get(campaign_url).status_code, 403)
        for allowed in (self.gm_a, self.superuser):
            self.client.force_login(allowed)
            self.assertEqual(self.client.get(campaign_url).status_code, 200)
        for denied in (self.gm_a, self.player):
            self.client.force_login(denied)
            self.assertEqual(self.client.get(global_url).status_code, 403)
        for allowed in (self.editor, self.superuser):
            self.client.force_login(allowed)
            self.assertEqual(self.client.get(global_url).status_code, 200)

        self.client.force_login(self.gm_a)
        self.assertEqual(
            self.client.get(
                reverse(
                    "world:campaign_audit_detail",
                    args=[self.campaign_a.pk, global_row.pk],
                )
            ).status_code,
            404,
        )
        self.client.force_login(self.editor)
        self.assertEqual(
            self.client.get(
                reverse("world:global_audit_detail", args=[campaign_row.pk])
            ).status_code,
            404,
        )

    def test_deleted_campaign_history_does_not_become_global_history(self):
        row = record_audit(
            action="test.orphaned_campaign",
            actor=self.gm_a,
            campaign=self.campaign_a,
            summary="Orphaned campaign row",
        )
        self.campaign_a.delete()
        row.refresh_from_db()
        self.assertIsNone(row.campaign)
        self.assertIsNotNone(row.campaign_id_snapshot)
        self.client.force_login(self.editor)
        response = self.client.get(reverse("world:global_audit_list"))
        self.assertNotContains(response, "Orphaned campaign row")
        self.assertEqual(
            self.client.get(
                reverse("world:global_audit_detail", args=[row.pk])
            ).status_code,
            404,
        )

    def test_scope_safe_filters_pagination_and_escaped_json(self):
        for index in range(51):
            record_audit(
                action="test.page",
                actor=self.gm_a,
                campaign=self.campaign_a,
                target=self.campaign_a,
                summary=f"Page {index}",
                metadata={"safe_html": "<script>alert(1)</script>"},
            )
        record_audit(
            action="test.other",
            actor=self.gm_b,
            campaign=self.campaign_b,
            summary="Campaign B secret",
        )
        self.client.force_login(self.gm_a)
        url = reverse("world:campaign_audit_list", args=[self.campaign_a.pk])
        response = self.client.get(url, {"action": "test.page"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["audit_rows"]), 50)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)
        self.assertContains(response, "Фильтры журнала")
        self.assertNotContains(response, "Campaign B secret")
        response = self.client.get(
            reverse(
                "world:campaign_audit_detail",
                args=[self.campaign_a.pk, AuditLog.objects.filter(campaign=self.campaign_a).first().pk],
            )
        )
        self.assertContains(response, "Реальное время изменения")
        self.assertContains(response, "Мировое время кампании")
        self.assertContains(response, "Что именно поменялось")
        self.assertContains(response, "Технические подробности")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>", html=False)

    def test_deleted_target_row_remains_readable(self):
        result = create_region(
            actor=self.gm_a,
            campaign=self.campaign_a,
            region=Region(name="Temporary"),
            auto_configure_from_map=False,
        )
        row = AuditLog.objects.get(action="region.created")
        result.region.delete()
        self.client.force_login(self.gm_a)
        response = self.client.get(
            reverse(
                "world:campaign_audit_detail",
                args=[self.campaign_a.pk, row.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Temporary")

    def test_admin_world_entry_writes_are_audited_once_and_audit_admin_is_read_only(self):
        model_admin = WorldEntryAdmin(WorldEntry, admin.site)
        request = RequestFactory().post("/admin/world/worldentry/add/")
        request.user = self.editor
        obj = WorldEntry(
            kind="lore",
            slug="admin-entry",
            title="Admin entry",
            summary="",
            body="",
        )
        model_admin.save_model(request, obj, SimpleNamespace(), change=False)
        self.assertEqual(AuditLog.objects.count(), 1)
        obj.title = "Admin changed"
        model_admin.save_model(request, obj, SimpleNamespace(), change=True)
        self.assertEqual(AuditLog.objects.count(), 2)
        model_admin.delete_model(request, obj)
        self.assertEqual(AuditLog.objects.count(), 3)
        self.assertEqual(
            list(AuditLog.objects.order_by("id").values_list("action", flat=True)),
            ["world_entry.created", "world_entry.updated", "world_entry.deleted"],
        )

        audit_admin = AuditLogAdmin(AuditLog, admin.site)
        self.assertFalse(audit_admin.has_add_permission(request))
        self.assertFalse(audit_admin.has_change_permission(request))
        self.assertFalse(audit_admin.has_delete_permission(request))

    def test_real_admin_canon_editor_create_update_delete_has_no_double_audit(self):
        self.editor.is_staff = True
        self.editor.save(update_fields=["is_staff"])
        self.client.force_login(self.editor)
        add_url = reverse("admin:world_worldentry_add")
        payload = {
            "kind": "lore",
            "slug": "admin-live",
            "title": "Admin live",
            "summary": "Initial",
            "body": "Body",
            "_save": "Сохранить",
        }
        response = self.client.post(add_url, payload)
        self.assertEqual(response.status_code, 302)
        entry = WorldEntry.objects.get(slug="admin-live")
        self.assertEqual(AuditLog.objects.count(), 1)
        payload["title"] = "Admin live changed"
        response = self.client.post(
            reverse("admin:world_worldentry_change", args=[entry.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AuditLog.objects.count(), 2)
        response = self.client.post(
            reverse("admin:world_worldentry_delete", args=[entry.pk]),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AuditLog.objects.count(), 3)
        self.assertEqual(
            list(AuditLog.objects.order_by("id").values_list("action", flat=True)),
            ["world_entry.created", "world_entry.updated", "world_entry.deleted"],
        )
