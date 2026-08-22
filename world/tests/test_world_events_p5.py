import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership, TimeAdvanceReport
from world.admin import WorldEventAdmin, WorldEventOccurrenceAdmin
from world.models import AuditLog, Region, WeatherState, WorldEvent, WorldEventOccurrence
from world.services.audit import record_audit
from world.services.events import (
    MAX_EVENT_COMPONENT_BYTES,
    UnknownWorldEventHandler,
    WorldEventConflict,
    create_world_event_definition,
    disable_world_event_definition,
    execute_due_world_events,
    record_narrative_event_now,
    register_world_event_effect,
    remove_world_event_definition,
    trigger_world_event_now,
    unregister_world_event_effect,
    update_world_event_definition,
)
from world.services.time import advance_world


EFFECT_TYPE = "test.campaign_description"


def _effect_validator(payload):
    allowed = {"value", "fail"}
    if set(payload) - allowed:
        raise ValidationError("Неизвестное поле тестового consequence.")
    value = payload.get("value")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Нужно новое описание кампании.")
    return {"value": value.strip(), "fail": bool(payload.get("fail", False))}


def _effect_presenter(payload):
    return f"Описание кампании станет «{payload['value']}»."


def _effect_apply(*, definition, campaign, actor, operation_id, payload):
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    before = {"description": campaign.description}
    campaign.description = payload["value"]
    campaign.save(update_fields=["description"])
    record_audit(
        action="test_world_event.description_changed",
        source=AuditLog.Source.USER if actor is not None else AuditLog.Source.SYSTEM,
        actor=actor,
        campaign=campaign,
        target=campaign,
        summary="Тестовое последствие события изменило описание кампании.",
        before_state=before,
        after_state={"description": campaign.description},
        operation_id=operation_id,
    )
    if payload["fail"]:
        raise WorldEventConflict("Тестовое последствие не удалось применить.")
    return {"description": campaign.description}


def register_test_effect():
    unregister_world_event_effect(EFFECT_TYPE)
    register_world_event_effect(
        EFFECT_TYPE,
        version=1,
        validator=_effect_validator,
        presenter=_effect_presenter,
        apply=_effect_apply,
    )


class WorldEventP5Mixin:
    def setUp(self):
        super().setUp()
        users = get_user_model().objects
        self.gm_a = users.create_user(username="p5-gm-a", password="pass")
        self.gm_b = users.create_user(username="p5-gm-b", password="pass")
        self.player = users.create_user(username="p5-player", password="pass")
        self.editor = users.create_user(username="p5-editor", password="pass")
        self.superuser = users.create_superuser(
            username="p5-root",
            email="p5-root@example.com",
            password="pass",
        )
        self.campaign_a = Campaign.objects.create(name="P5 Campaign A")
        self.campaign_b = Campaign.objects.create(name="P5 Campaign B")
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
        register_test_effect()

    def tearDown(self):
        unregister_world_event_effect(EFFECT_TYPE)
        super().tearDown()

    def definition(self, *, campaign=None, actor=None, trigger_at=100, **kwargs):
        campaign = campaign or self.campaign_a
        actor = actor or self.gm_a
        return create_world_event_definition(
            actor=actor,
            campaign=campaign,
            title=kwargs.pop("title", f"Событие {trigger_at}"),
            scheduled_world_minutes=trigger_at,
            **kwargs,
        )


class WorldEventCrossingTests(WorldEventP5Mixin, TestCase):
    def test_world_time_interval_is_open_left_and_closed_right(self):
        self.campaign_a.world_minutes = 100
        self.campaign_a.save(update_fields=["world_minutes"])
        before = WorldEvent.objects.create(
            campaign=self.campaign_a,
            title="До T1",
            trigger_at=90,
        )
        at_start = WorldEvent.objects.create(
            campaign=self.campaign_a,
            title="Ровно T1",
            trigger_at=100,
        )
        inside = self.definition(trigger_at=150, title="Внутри")
        at_end = self.definition(trigger_at=200, title="Ровно T2")
        after = self.definition(trigger_at=201, title="После T2")

        with transaction.atomic():
            occurrences = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=100,
                end_world_minutes=200,
            )

        self.assertEqual(
            [(item.definition_id, item.occurred_world_minutes) for item in occurrences],
            [(inside.pk, 150), (at_end.pk, 200)],
        )
        self.assertFalse(before.occurrences.exists())
        self.assertFalse(at_start.occurrences.exists())
        self.assertFalse(after.occurrences.exists())

    def test_equal_time_events_have_deterministic_id_order(self):
        first = self.definition(trigger_at=100, title="Первое")
        second = self.definition(trigger_at=100, title="Второе")
        with transaction.atomic():
            occurrences = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=100,
            )
        self.assertEqual(
            [item.definition_id for item in occurrences],
            [first.pk, second.pk],
        )

    def test_zero_or_repeated_interval_does_not_fire_twice(self):
        definition = self.definition(trigger_at=100)
        self.assertEqual(
            execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=0,
            ),
            [],
        )
        with transaction.atomic():
            first = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=100,
            )
        with transaction.atomic():
            second = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=200,
            )
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(definition.occurrences.count(), 1)

    def test_disabled_definition_does_not_fire(self):
        definition = self.definition(trigger_at=100)
        disable_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
        )
        with transaction.atomic():
            result = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=100,
            )
        self.assertEqual(result, [])


class WorldEventAdvanceAndReportTests(WorldEventP5Mixin, TestCase):
    def test_exact_and_fast_forward_cross_the_same_safe_events(self):
        turn = self.campaign_a.calendar_minutes_per_turn
        self.campaign_a.exact_simulation_max_turns = 4
        self.campaign_a.save(update_fields=["exact_simulation_max_turns"])
        self.campaign_b.exact_simulation_max_turns = 1
        self.campaign_b.fast_forward_spinup_turns = 1
        self.campaign_b.save(
            update_fields=["exact_simulation_max_turns", "fast_forward_spinup_turns"]
        )
        for campaign, actor in ((self.campaign_a, self.gm_a), (self.campaign_b, self.gm_b)):
            self.definition(
                campaign=campaign,
                actor=actor,
                trigger_at=turn,
                title="Первое событие",
            )
            self.definition(
                campaign=campaign,
                actor=actor,
                trigger_at=2 * turn,
                title="Второе событие",
            )

        exact = advance_world(
            self.campaign_a.pk,
            3 * turn,
            advanced_by=self.gm_a,
            requested_amount=3,
            requested_unit="turns",
        )
        fast = advance_world(
            self.campaign_b.pk,
            3 * turn,
            advanced_by=self.gm_b,
            requested_amount=3,
            requested_unit="turns",
        )

        compact = lambda result: [
            (item.title, item.event_type_snapshot, item.occurred_world_minutes)
            for item in result.world_events
        ]
        self.assertEqual(exact.report.simulation_mode, TimeAdvanceReport.SimulationMode.EXACT)
        self.assertEqual(fast.report.simulation_mode, TimeAdvanceReport.SimulationMode.FAST_FORWARD)
        self.assertEqual(compact(exact), compact(fast))
        self.assertEqual(WeatherState.objects.count(), 0)
        self.assertEqual(
            [item["title"] for item in exact.report.summary["world_events"]],
            ["Первое событие", "Второе событие"],
        )
        self.assertEqual(
            [item["title"] for item in fast.report.summary["world_events"]],
            ["Первое событие", "Второе событие"],
        )
        self.assertTrue(
            all("effect_payload" not in item for item in fast.report.summary["world_events"])
        )

    def test_advance_keeps_one_time_audit_plus_meaningful_event_audits(self):
        self.definition(trigger_at=30, title="Срок наступил")
        before = AuditLog.objects.filter(action="campaign.time_advanced").count()

        result = advance_world(
            self.campaign_a.pk,
            60,
            advanced_by=self.gm_a,
            requested_amount=1,
            requested_unit="hours",
        )

        self.assertEqual(
            AuditLog.objects.filter(action="campaign.time_advanced").count() - before,
            1,
        )
        self.assertEqual(len(result.world_events), 1)
        self.assertEqual(AuditLog.objects.filter(action="world_event.occurred").count(), 1)
        self.assertEqual(result.report.summary["world_events"][0]["occurrence_id"], result.world_events[0].pk)

    def test_old_report_json_without_occurrence_id_still_renders(self):
        report = TimeAdvanceReport.objects.create(
            campaign=self.campaign_a,
            gm=self.gm_a,
            start_world_minutes=0,
            end_world_minutes=60,
            requested_amount=1,
            requested_unit="hours",
            simulation_mode=TimeAdvanceReport.SimulationMode.EXACT,
            coverage=[{"kind": "exact", "start": 0, "end": 60}],
            summary={
                "elapsed_label": "1 час Витка",
                "world_events": [
                    {"id": 77, "title": "Старое событие", "trigger_at": 30, "region_name": ""}
                ],
                "astronomical_events": [],
                "global_highlights": [],
                "regional_weather": [],
                "extremes": {},
                "climate_summary": {"text": "Точная сводка."},
            },
        )
        self.client.force_login(self.gm_a)
        url = reverse("world:campaign_event_list", args=[self.campaign_a.pk])
        response = self.client.get(f"{url}?advance_report={report.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Старое событие")


class WorldEventEffectAndAtomicityTests(WorldEventP5Mixin, TestCase):
    def effect_definition(self, *, trigger_type=WorldEvent.TriggerType.MANUAL, fail=False):
        return create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="С доменным последствием",
            trigger_type=trigger_type,
            scheduled_world_minutes=(100 if trigger_type == WorldEvent.TriggerType.WORLD_TIME else None),
            effect_type=EFFECT_TYPE,
            effect_version=1,
            effect_payload={"value": "После события", "fail": fail},
        )

    def test_registered_effect_applies_once_and_groups_audits(self):
        definition = self.effect_definition()
        occurrence = trigger_world_event_now(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
        )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.description, "После события")
        grouped = AuditLog.objects.filter(operation_id=occurrence.operation_id)
        self.assertEqual(
            set(grouped.values_list("action", flat=True)),
            {"test_world_event.description_changed", "world_event.occurred"},
        )
        with self.assertRaises(WorldEventConflict):
            trigger_world_event_now(
                actor=self.gm_a,
                campaign=self.campaign_a,
                definition=definition,
            )
        self.assertEqual(definition.occurrences.count(), 1)

    def test_failed_effect_rolls_back_domain_mutation_occurrence_and_audits(self):
        definition = self.effect_definition(fail=True)
        audit_count = AuditLog.objects.count()
        with self.assertRaises(WorldEventConflict):
            trigger_world_event_now(
                actor=self.gm_a,
                campaign=self.campaign_a,
                definition=definition,
            )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.description, "")
        self.assertFalse(definition.occurrences.exists())
        self.assertEqual(AuditLog.objects.count(), audit_count)

    def test_failed_due_effect_rolls_back_world_time_and_report(self):
        self.effect_definition(trigger_type=WorldEvent.TriggerType.WORLD_TIME, fail=True)
        with self.assertRaises(WorldEventConflict):
            advance_world(
                self.campaign_a.pk,
                100,
                advanced_by=self.gm_a,
                requested_amount=100,
                requested_unit="minutes",
            )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.world_minutes, 0)
        self.assertEqual(self.campaign_a.description, "")
        self.assertFalse(WorldEventOccurrence.objects.exists())
        self.assertFalse(TimeAdvanceReport.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action="world_event.occurred").exists())

    def test_validation_unknown_handler_and_payload_safety(self):
        with self.assertRaises(ValidationError):
            create_world_event_definition(
                actor=self.gm_a,
                campaign=self.campaign_a,
                title="Плохой payload",
                trigger_type=WorldEvent.TriggerType.MANUAL,
                effect_type=EFFECT_TYPE,
                effect_version=1,
                effect_payload={"value": 42},
            )
        with self.assertRaises(ValidationError):
            create_world_event_definition(
                actor=self.gm_a,
                campaign=self.campaign_a,
                title="С секретом",
                trigger_type=WorldEvent.TriggerType.MANUAL,
                effect_type=EFFECT_TYPE,
                effect_version=1,
                effect_payload={"value": "x", "access_token": "never"},
            )
        with self.assertRaises(ValidationError):
            create_world_event_definition(
                actor=self.gm_a,
                campaign=self.campaign_a,
                title="Слишком большой",
                trigger_type=WorldEvent.TriggerType.MANUAL,
                effect_type=EFFECT_TYPE,
                effect_version=1,
                effect_payload={"value": "x" * (MAX_EVENT_COMPONENT_BYTES + 1)},
            )
        with self.assertRaises(ValidationError):
            create_world_event_definition(
                actor=self.gm_a,
                campaign=self.campaign_a,
                title="Не JSON",
                trigger_type=WorldEvent.TriggerType.MANUAL,
                effect_type=EFFECT_TYPE,
                effect_version=1,
                effect_payload={"value": {"not-json"}},
            )
        with self.assertRaises(UnknownWorldEventHandler):
            create_world_event_definition(
                actor=self.gm_a,
                campaign=self.campaign_a,
                title="Неизвестное последствие",
                trigger_type=WorldEvent.TriggerType.MANUAL,
                effect_type="unknown.effect",
                effect_version=1,
            )

    def test_missing_generic_target_causes_safe_conflict(self):
        region = Region.objects.create(campaign=self.campaign_a, name="Временная цель")
        definition = create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Нужна цель",
            trigger_type=WorldEvent.TriggerType.MANUAL,
            target=region,
            effect_type=EFFECT_TYPE,
            effect_version=1,
            effect_payload={"value": "Не должно примениться"},
        )
        region.delete()
        with self.assertRaises(WorldEventConflict):
            trigger_world_event_now(
                actor=self.gm_a,
                campaign=self.campaign_a,
                definition=definition,
            )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.description, "")
        self.assertFalse(definition.occurrences.exists())


class WorldEventHistoryTests(WorldEventP5Mixin, TestCase):
    def test_occurrence_is_immutable_through_instance_and_queryset(self):
        occurrence = record_narrative_event_now(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Неподвижный факт",
        )
        occurrence.title = "Переписанный факт"
        with self.assertRaises(ValidationError):
            occurrence.save()
        with self.assertRaises(ValidationError):
            WorldEventOccurrence.objects.filter(pk=occurrence.pk).update(title="Подмена")
        with self.assertRaises(ValidationError):
            occurrence.delete()
        with self.assertRaises(ValidationError):
            WorldEventOccurrence.objects.filter(pk=occurrence.pk).delete()

    def test_definition_edit_and_removal_do_not_rewrite_history(self):
        definition = create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Старое название",
            description="Старое описание",
            trigger_type=WorldEvent.TriggerType.MANUAL,
        )
        occurrence = trigger_world_event_now(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
        )
        definition = update_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
            title="Новое название",
            description="Новое описание",
        )
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.title, "Старое название")
        self.assertEqual(occurrence.summary, "Старое описание")
        self.assertEqual(occurrence.definition_revision, 1)

        remove_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
        )
        occurrence.refresh_from_db()
        self.assertIsNone(occurrence.definition_id)
        self.assertEqual(occurrence.title, "Старое название")

    def test_deleted_target_and_region_leave_durable_labels(self):
        region = Region.objects.create(
            campaign=self.campaign_a,
            name="Исчезнувший порт",
            map_latitude=12.5,
            map_longitude=-8.25,
        )
        definition = create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Падение маяка",
            trigger_type=WorldEvent.TriggerType.MANUAL,
            region=region,
            target=region,
        )
        occurrence = trigger_world_event_now(
            actor=self.gm_a,
            campaign=self.campaign_a,
            definition=definition,
        )
        region.delete()
        occurrence.refresh_from_db()
        self.assertIsNone(occurrence.region_id)
        self.assertIsNone(occurrence.target)
        self.assertEqual(occurrence.region_label_snapshot, "Исчезнувший порт")
        self.assertEqual(occurrence.target_label, "Исчезнувший порт")
        self.assertEqual((occurrence.latitude, occurrence.longitude), (12.5, -8.25))

    def test_manual_and_world_time_source_actor_semantics(self):
        manual = record_narrative_event_now(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Ручная запись",
        )
        scheduled_definition = self.definition(trigger_at=10, title="Системная запись")
        with transaction.atomic():
            scheduled = execute_due_world_events(
                campaign=self.campaign_a,
                start_world_minutes=0,
                end_world_minutes=10,
            )[0]
        self.assertEqual(manual.source, WorldEventOccurrence.Source.USER)
        self.assertEqual(manual.actor, self.gm_a)
        self.assertEqual(manual.occurred_world_minutes, self.campaign_a.world_minutes)
        self.assertEqual(scheduled.source, WorldEventOccurrence.Source.SYSTEM)
        self.assertIsNone(scheduled.actor)
        self.assertEqual(scheduled.definition_id, scheduled_definition.pk)

    def test_admin_occurrence_and_definition_are_read_only(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser
        occurrence_admin = WorldEventOccurrenceAdmin(WorldEventOccurrence, admin.site)
        definition_admin = WorldEventAdmin(WorldEvent, admin.site)
        for model_admin in (occurrence_admin, definition_admin):
            self.assertTrue(model_admin.has_view_permission(request))
            self.assertFalse(model_admin.has_add_permission(request))
            self.assertFalse(model_admin.has_change_permission(request))
            self.assertFalse(model_admin.has_delete_permission(request))


class WorldEventPermissionAndUiTests(WorldEventP5Mixin, TestCase):
    def setUp(self):
        super().setUp()
        self.region = Region.objects.create(campaign=self.campaign_a, name="Северный предел")
        self.list_url = reverse("world:campaign_event_list", args=[self.campaign_a.pk])

    def test_only_own_gm_or_superuser_can_view_objective_events(self):
        for user, expected in (
            (self.gm_a, 200),
            (self.superuser, 200),
            (self.player, 403),
            (self.gm_b, 403),
            (self.editor, 403),
        ):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.list_url).status_code, expected)

    def test_get_never_creates_or_triggers_and_post_creates_one_occurrence(self):
        definition = create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Ручной запуск",
            trigger_type=WorldEvent.TriggerType.MANUAL,
        )
        trigger_url = reverse(
            "world:world_event_trigger_now",
            args=[self.campaign_a.pk, definition.pk],
        )
        self.client.force_login(self.gm_a)
        self.assertEqual(self.client.get(trigger_url).status_code, 405)
        self.assertFalse(definition.occurrences.exists())
        response = self.client.post(trigger_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(definition.occurrences.count(), 1)
        self.client.post(trigger_url)
        self.assertEqual(definition.occurrences.count(), 1)

    def test_schedule_and_record_now_forms_are_human_facing(self):
        self.client.force_login(self.gm_a)
        schedule_url = reverse("world:world_event_schedule", args=[self.campaign_a.pk])
        response = self.client.get(schedule_url)
        self.assertContains(response, "Через")
        self.assertContains(response, "Единица времени")
        self.assertNotContains(response, "trigger_config")
        self.assertNotContains(response, "effect_payload")
        response = self.client.post(
            schedule_url,
            {"title": "Прибытие каравана", "description": "С юга", "amount": 1, "unit": "phases", "region": self.region.pk},
        )
        definition = WorldEvent.objects.get(title="Прибытие каравана")
        self.assertRedirects(
            response,
            reverse(
                "world:world_event_definition_detail",
                args=[self.campaign_a.pk, definition.pk],
            ),
        )
        self.assertEqual(
            definition.trigger_at,
            self.campaign_a.world_minutes + self.campaign_a.calendar_minutes_per_phase,
        )

        now_url = reverse("world:world_event_record_now", args=[self.campaign_a.pk])
        response = self.client.post(
            now_url,
            {"title": "Врата закрылись", "description": "На рассвете", "region": self.region.pk},
        )
        self.assertEqual(response.status_code, 302)
        occurrence = WorldEventOccurrence.objects.get(title="Врата закрылись")
        self.assertEqual(occurrence.occurred_world_minutes, self.campaign_a.world_minutes)

    def test_service_rejects_current_or_past_schedule_with_human_message(self):
        for minute in (self.campaign_a.world_minutes, self.campaign_a.world_minutes - 1):
            with self.assertRaisesMessage(ValidationError, "Для события сейчас"):
                self.definition(trigger_at=minute)

    def test_cross_campaign_definition_and_occurrence_idor(self):
        foreign_definition = create_world_event_definition(
            actor=self.gm_b,
            campaign=self.campaign_b,
            title="Чужое событие",
            trigger_type=WorldEvent.TriggerType.MANUAL,
        )
        foreign_occurrence = trigger_world_event_now(
            actor=self.gm_b,
            campaign=self.campaign_b,
            definition=foreign_definition,
        )
        self.client.force_login(self.gm_a)
        definition_url = reverse(
            "world:world_event_definition_detail",
            args=[self.campaign_a.pk, foreign_definition.pk],
        )
        occurrence_url = reverse(
            "world:world_event_occurrence_detail",
            args=[self.campaign_a.pk, foreign_occurrence.pk],
        )
        self.assertEqual(self.client.get(definition_url).status_code, 404)
        self.assertEqual(self.client.get(occurrence_url).status_code, 404)

    def test_human_first_pages_and_collapsed_technical_details(self):
        definition = self.definition(
            trigger_at=self.campaign_a.calendar_minutes_per_phase,
            title="Прибытие каравана",
            description="Караван войдёт в северные ворота.",
            region=self.region,
        )
        self.client.force_login(self.gm_a)
        detail = self.client.get(
            reverse(
                "world:world_event_definition_detail",
                args=[self.campaign_a.pk, definition.pk],
            )
        )
        self.assertContains(detail, "Прибытие каравана")
        self.assertContains(detail, "Условие срабатывания")
        self.assertContains(detail, "Северный предел")
        self.assertContains(detail, "<details", html=False)
        self.assertNotContains(detail, "Мировая минута")

        advance_world(self.campaign_a.pk, definition.trigger_at)
        occurrence = definition.occurrences.get()
        history = self.client.get(f"{self.list_url}?tab=occurred")
        self.assertContains(history, "Произошло")
        self.assertContains(history, "Запланировано по мировому времени")
        occurrence_detail = self.client.get(
            reverse(
                "world:world_event_occurrence_detail",
                args=[self.campaign_a.pk, occurrence.pk],
            )
        )
        self.assertContains(occurrence_detail, "Событие было запланировано")
        self.assertContains(occurrence_detail, "Связанные изменения")

    def test_list_and_detail_queries_stay_bounded(self):
        definition = self.definition(trigger_at=100)
        self.client.force_login(self.gm_a)
        with CaptureQueriesContext(connection) as list_queries:
            response = self.client.get(self.list_url)
            self.assertEqual(response.status_code, 200)
        with CaptureQueriesContext(connection) as detail_queries:
            response = self.client.get(
                reverse(
                    "world:world_event_definition_detail",
                    args=[self.campaign_a.pk, definition.pk],
                )
            )
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(list_queries), 12)
        self.assertLessEqual(len(detail_queries), 12)


class WorldEventMigrationTests(TransactionTestCase):
    """The additive P5 migration must retain legacy scheduled and triggered rows."""

    migrate_from = ("world", "0019_approvalrequest")
    migrate_to = ("world", "0020_worldevent_foundation")

    @staticmethod
    def _targets_with_world(executor, world_target):
        return [
            world_target if app_label == "world" else (app_label, migration_name)
            for app_label, migration_name in executor.loader.graph.leaf_nodes()
        ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        from_targets = self._targets_with_world(executor, self.migrate_from)
        executor.migrate(from_targets)
        old_apps = executor.loader.project_state(from_targets).apps
        CampaignModel = old_apps.get_model("campaigns", "Campaign")
        EventModel = old_apps.get_model("world", "WorldEvent")
        campaign = CampaignModel.objects.create(name="Legacy events")
        self.campaign_id = campaign.pk
        self.planned_id = EventModel.objects.create(
            campaign_id=campaign.pk,
            title="Legacy planned",
            trigger_at=120,
            status="planned",
        ).pk
        self.triggered_id = EventModel.objects.create(
            campaign_id=campaign.pk,
            title="Legacy triggered",
            description="Already happened",
            trigger_at=80,
            triggered_at=82,
            status="triggered",
        ).pk
        executor = MigrationExecutor(connection)
        to_targets = self._targets_with_world(executor, self.migrate_to)
        executor.migrate(to_targets)
        self.apps = executor.loader.project_state(to_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self._targets_with_world(executor, self.migrate_to))
        super().tearDown()

    def test_legacy_rows_are_preserved_and_triggered_row_gets_occurrence(self):
        EventModel = self.apps.get_model("world", "WorldEvent")
        OccurrenceModel = self.apps.get_model("world", "WorldEventOccurrence")
        planned = EventModel.objects.get(pk=self.planned_id)
        triggered = EventModel.objects.get(pk=self.triggered_id)
        occurrence = OccurrenceModel.objects.get(definition_id=self.triggered_id)

        self.assertEqual(planned.trigger_type, "WORLD_TIME")
        self.assertEqual(planned.trigger_at, 120)
        self.assertTrue(planned.enabled)
        self.assertEqual(triggered.status, "triggered")
        self.assertEqual(occurrence.title, "Legacy triggered")
        self.assertEqual(occurrence.summary, "Already happened")
        self.assertEqual(occurrence.occurred_world_minutes, 82)
        self.assertEqual(occurrence.scheduled_world_minutes, 80)


@skipUnless(connection.vendor == "postgresql", "Row-lock race proof requires PostgreSQL.")
class WorldEventConcurrencyTests(WorldEventP5Mixin, TransactionTestCase):
    reset_sequences = True

    def _run_concurrently(self, callable_):
        barrier = threading.Barrier(2)

        def worker():
            close_old_connections()
            barrier.wait()
            try:
                return callable_()
            except Exception as error:  # outcomes are asserted by durable state
                return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _index: worker(), range(2)))

    def test_concurrent_time_advances_do_not_double_fire(self):
        self.definition(trigger_at=10)
        self._run_concurrently(lambda: advance_world(self.campaign_a.pk, 10))
        self.assertEqual(WorldEventOccurrence.objects.count(), 1)

    def test_concurrent_manual_triggers_do_not_double_fire(self):
        definition = create_world_event_definition(
            actor=self.gm_a,
            campaign=self.campaign_a,
            title="Однократный ручной факт",
            trigger_type=WorldEvent.TriggerType.MANUAL,
        )

        def trigger():
            campaign = Campaign.objects.get(pk=self.campaign_a.pk)
            current = WorldEvent.objects.get(pk=definition.pk)
            return trigger_world_event_now(actor=self.gm_a, campaign=campaign, definition=current)

        self._run_concurrently(trigger)
        self.assertEqual(WorldEventOccurrence.objects.count(), 1)
