import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from campaigns.models import Campaign, CampaignMembership
from world.admin import ApprovalRequestAdmin
from world.models import ApprovalRequest, AuditLog, Region
from world.services.approvals import (
    MAX_APPROVAL_JSON_BYTES,
    ApprovalAlreadyResolved,
    ApprovalConflict,
    ApprovalExpired,
    ApprovalPresentation,
    UnknownApprovalType,
    approve_request,
    cancel_request,
    create_approval_request,
    register_approval_handler,
    reject_request,
    unregister_approval_handler,
)
from world.services.audit import record_audit


REQUEST_TYPE = "test.approval"


def _validator(payload):
    allowed = {"message", "expected_description", "target_required"}
    if set(payload) - allowed:
        raise ValidationError("Payload содержит неизвестные поля.")
    if not isinstance(payload.get("message"), str) or not payload["message"].strip():
        raise ValidationError("Нужно понятное сообщение.")
    normalized = dict(payload)
    normalized["message"] = normalized["message"].strip()
    normalized.setdefault("expected_description", "")
    normalized.setdefault("target_required", False)
    return normalized


def _presenter(subject):
    return ApprovalPresentation(
        request_type_label="Тестовое изменение кампании",
        title=f"Изменить описание: {subject.payload['message']}",
        summary="Участник просит заменить краткое описание кампании.",
        details=(
            ("Новое описание", subject.payload["message"]),
            ("Текущее описание", subject.payload["expected_description"] or "Не задано"),
        ),
        consequences=(
            "Описание кампании будет заменено указанным текстом.",
            "Изменение будет записано в историю кампании.",
        ),
        target_label=subject.target_label,
        current_applicability_message="Текущее состояние подходит для выполнения.",
        result_summary="Описание кампании обновлено.",
    )


def _revalidate(subject):
    campaign = Campaign.objects.get(pk=subject.campaign.pk)
    if campaign.description != subject.payload["expected_description"]:
        raise ApprovalConflict("Запрос основан на устаревшем описании кампании.")
    target = subject.target
    if target is not None and getattr(target, "campaign_id", campaign.pk) != campaign.pk:
        raise ApprovalConflict("Цель запроса принадлежит другой кампании.")
    if subject.payload["target_required"] and target is None:
        raise ApprovalConflict("Связанный объект уже удалён.")


def _apply(subject, actor, operation_id):
    campaign = Campaign.objects.select_for_update().get(pk=subject.campaign.pk)
    before = {"description": campaign.description}
    campaign.description = subject.payload["message"]
    campaign.save(update_fields=["description"])
    record_audit(
        action="test_domain.applied",
        actor=actor,
        campaign=campaign,
        target=campaign,
        summary="Применено тестовое доменное изменение.",
        before_state=before,
        after_state={"description": campaign.description},
        operation_id=operation_id,
    )
    return {"description": campaign.description}


def register_test_handler(**overrides):
    config = {
        "request_type_label": "Тестовое изменение кампании",
        "validator": _validator,
        "presenter": _presenter,
        "apply": _apply,
        "revalidate": _revalidate,
    }
    config.update(overrides)
    unregister_approval_handler(REQUEST_TYPE)
    return register_approval_handler(REQUEST_TYPE, **config)


class ApprovalP4Mixin:
    def setUp(self):
        super().setUp()
        self.campaign_a = Campaign.objects.create(name="Campaign A")
        self.campaign_b = Campaign.objects.create(name="Campaign B")
        self.gm_a = User.objects.create_user(username="gm-a", password="pass")
        self.gm_b = User.objects.create_user(username="gm-b", password="pass")
        self.player = User.objects.create_user(username="player", password="pass")
        self.other_player = User.objects.create_user(username="other-player", password="pass")
        self.editor = User.objects.create_user(username="editor", password="pass")
        self.outsider = User.objects.create_user(username="outsider", password="pass")
        self.superuser = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="pass",
        )
        CampaignMembership.objects.bulk_create(
            [
                CampaignMembership(campaign=self.campaign_a, user=self.gm_a, role="gm"),
                CampaignMembership(campaign=self.campaign_b, user=self.gm_b, role="gm"),
                CampaignMembership(campaign=self.campaign_a, user=self.player, role="player"),
                CampaignMembership(campaign=self.campaign_a, user=self.other_player, role="player"),
            ]
        )
        permission = Permission.objects.get(
            content_type__app_label="world",
            codename="manage_global_canon",
        )
        self.editor.user_permissions.add(permission)
        register_test_handler()

    def tearDown(self):
        unregister_approval_handler(REQUEST_TYPE)
        super().tearDown()

    def make_request(self, *, requester=None, campaign=None, target=None, **kwargs):
        campaign = campaign or self.campaign_a
        return create_approval_request(
            campaign=campaign,
            requester=requester or self.player,
            request_type=REQUEST_TYPE,
            payload=kwargs.pop(
                "payload",
                {
                    "message": "Новое описание",
                    "expected_description": campaign.description,
                },
            ),
            target=target,
            **kwargs,
        )


class ApprovalModelAndRegistryTests(ApprovalP4Mixin, TestCase):
    def test_campaign_pending_snapshots_target_and_operation_id(self):
        self.campaign_a.world_minutes = 12_345
        self.campaign_a.save(update_fields=["world_minutes"])
        region = Region.objects.create(campaign=self.campaign_a, name="Север")
        approval = self.make_request(target=region)
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertEqual(approval.requester_label_snapshot, "player")
        self.assertEqual(approval.requested_world_minutes, 12_345)
        self.assertEqual(approval.target, region)
        self.assertEqual(approval.target_label, "Север")
        self.assertTrue(approval.operation_id)
        self.assertEqual(
            AuditLog.objects.get(action="approval_request.created").operation_id,
            approval.operation_id,
        )

    def test_campaign_is_required_and_new_status_must_be_pending(self):
        invalid = ApprovalRequest(
            request_type=REQUEST_TYPE,
            requester_label_snapshot="player",
            requested_world_minutes=0,
            title="Title",
            summary="Summary",
            payload={},
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        invalid.campaign = self.campaign_a
        invalid.status = ApprovalRequest.Status.APPROVED
        with self.assertRaises(ValidationError):
            invalid.save()

    def test_registry_requires_known_type_human_presenter_and_version(self):
        with self.assertRaises(UnknownApprovalType):
            create_approval_request(
                campaign=self.campaign_a,
                requester=self.player,
                request_type="unknown.intent",
                payload={},
            )
        with self.assertRaises(ValidationError):
            register_approval_handler(
                "broken.intent",
                request_type_label="Broken",
                validator=_validator,
                presenter=None,
                apply=_apply,
            )
        with self.assertRaises(ValidationError):
            self.make_request(payload_version=2)

        historical = self.make_request()
        unregister_approval_handler(REQUEST_TYPE)
        with self.assertRaises(UnknownApprovalType):
            approve_request(
                campaign=self.campaign_a,
                request_id=historical.pk,
                actor=self.gm_a,
            )
        historical.refresh_from_db()
        self.assertEqual(historical.status, ApprovalRequest.Status.PENDING)

    def test_payload_validation_size_secret_and_dedupe(self):
        with self.assertRaises(ValidationError):
            self.make_request(payload={"unexpected": "value"})
        with self.assertRaises(ValidationError):
            self.make_request(payload={"message": "ok", "access_token": "secret"})
        with self.assertRaises(ValidationError):
            self.make_request(payload={"message": "x" * (MAX_APPROVAL_JSON_BYTES + 1)})
        first = self.make_request(dedupe_key="same-intent")
        with self.assertRaises(ApprovalConflict):
            self.make_request(dedupe_key="same-intent")
        self.assertEqual(ApprovalRequest.objects.count(), 1)
        self.assertEqual(first.dedupe_key, "same-intent")

    def test_requester_permission_is_campaign_scoped(self):
        with self.assertRaises(PermissionDenied):
            self.make_request(requester=self.outsider)
        with self.assertRaises(PermissionDenied):
            self.make_request(requester=self.gm_b)

    def test_handler_rejects_target_from_another_campaign(self):
        foreign_region = Region.objects.create(campaign=self.campaign_b, name="Чужой регион")
        with self.assertRaises(ApprovalConflict):
            self.make_request(target=foreign_region)
        self.assertFalse(ApprovalRequest.objects.exists())

    def test_terminal_request_is_immutable_and_cannot_be_deleted_or_reopened(self):
        approval = self.make_request()
        approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        approval.refresh_from_db()
        approval.title = "Changed"
        with self.assertRaises(ValidationError):
            approval.save()
        approval.refresh_from_db()
        approval.status = ApprovalRequest.Status.PENDING
        with self.assertRaises(ValidationError):
            approval.save()
        with self.assertRaises(ValidationError):
            approval.delete()

    def test_user_snapshots_survive_deletion(self):
        approval = self.make_request()
        approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        self.player.delete()
        self.gm_a.delete()
        approval.refresh_from_db()
        self.assertIsNone(approval.requester)
        self.assertIsNone(approval.resolved_by)
        self.assertEqual(approval.requester_label_snapshot, "player")
        self.assertEqual(approval.resolved_by_label_snapshot, "gm-a")


class ApprovalLifecycleTests(ApprovalP4Mixin, TestCase):
    def test_approved_means_domain_action_and_audits_committed(self):
        approval = self.make_request()
        approved = approve_request(
            campaign=self.campaign_a,
            request_id=approval.pk,
            actor=self.gm_a,
            resolution_note="Согласовано.",
        )
        self.campaign_a.refresh_from_db()
        self.assertEqual(self.campaign_a.description, "Новое описание")
        self.assertEqual(approved.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(approved.resolved_by, self.gm_a)
        self.assertEqual(approved.resolved_world_minutes, self.campaign_a.world_minutes)
        self.assertEqual(approved.result, {"description": "Новое описание"})
        rows = AuditLog.objects.filter(operation_id=approval.operation_id)
        self.assertSetEqual(
            set(rows.values_list("action", flat=True)),
            {
                "approval_request.created",
                "test_domain.applied",
                "approval_request.approved",
            },
        )
        self.assertTrue(all(row.operation_id == approval.operation_id for row in rows))

    def test_double_approval_applies_once(self):
        approval = self.make_request()
        approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        with self.assertRaises(ApprovalAlreadyResolved):
            approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        self.assertEqual(AuditLog.objects.filter(action="test_domain.applied").count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="approval_request.approved").count(), 1)

    def test_stale_state_and_deleted_target_do_not_blind_apply(self):
        approval = self.make_request()
        self.campaign_a.description = "Изменено параллельно"
        self.campaign_a.save(update_fields=["description"])
        with self.assertRaises(ApprovalConflict):
            approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        approval.refresh_from_db()
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertFalse(AuditLog.objects.filter(action="approval_request.approved").exists())

        self.campaign_a.description = ""
        self.campaign_a.save(update_fields=["description"])
        region = Region.objects.create(campaign=self.campaign_a, name="Temporary")
        targeted = self.make_request(
            target=region,
            payload={
                "message": "Targeted",
                "expected_description": "",
                "target_required": True,
            },
        )
        Region.objects.filter(pk=region.pk).delete()
        with self.assertRaises(ApprovalConflict):
            approve_request(campaign=self.campaign_a, request_id=targeted.pk, actor=self.gm_a)
        targeted.refresh_from_db()
        self.assertEqual(targeted.status, ApprovalRequest.Status.PENDING)
        self.assertIsNone(targeted.target)
        self.assertEqual(targeted.target_label, "Temporary")

    def test_apply_failure_rolls_back_domain_request_and_success_audits(self):
        def failing_apply(subject, actor, operation_id):
            campaign = Campaign.objects.get(pk=subject.campaign.pk)
            campaign.description = "Must roll back"
            campaign.save(update_fields=["description"])
            raise ApprovalConflict("Доменное действие столкнулось с конфликтом.")

        register_test_handler(apply=failing_apply)
        approval = self.make_request()
        with self.assertRaises(ApprovalConflict):
            approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
        self.campaign_a.refresh_from_db()
        approval.refresh_from_db()
        self.assertEqual(self.campaign_a.description, "")
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertFalse(AuditLog.objects.filter(action="approval_request.approved").exists())

    def test_result_is_bounded_and_secret_safe(self):
        for result in (
            {"safe": "x" * (MAX_APPROVAL_JSON_BYTES + 1)},
            {"access_token": "secret"},
        ):
            register_test_handler(apply=lambda subject, actor, operation_id, value=result: value)
            approval = self.make_request()
            with self.assertRaises(ValidationError):
                approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_a)
            approval.refresh_from_db()
            self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
            ApprovalRequest.objects.filter(pk=approval.pk).delete()

    def test_handler_can_require_resolution_note(self):
        register_test_handler(requires_resolution_note=True)
        approval = self.make_request()
        with self.assertRaises(ValidationError):
            approve_request(
                campaign=self.campaign_a,
                request_id=approval.pk,
                actor=self.gm_a,
                resolution_note="",
            )
        approval.refresh_from_db()
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        approved = approve_request(
            campaign=self.campaign_a,
            request_id=approval.pk,
            actor=self.gm_a,
            resolution_note="Проверено мастером.",
        )
        self.assertEqual(approved.status, ApprovalRequest.Status.APPROVED)

    def test_reject_cancel_and_expiry_lifecycle(self):
        rejected = self.make_request()
        reject_request(
            campaign=self.campaign_a,
            request_id=rejected.pk,
            actor=self.gm_a,
            resolution_note="Не сейчас.",
        )
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, ApprovalRequest.Status.REJECTED)

        cancelled = self.make_request()
        cancel_request(
            campaign=self.campaign_a,
            request_id=cancelled.pk,
            actor=self.player,
        )
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, ApprovalRequest.Status.CANCELLED)

        expiring = self.make_request(expires_at=timezone.now() + timedelta(hours=1))
        ApprovalRequest.objects.filter(pk=expiring.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(ApprovalExpired):
            approve_request(
                campaign=self.campaign_a,
                request_id=expiring.pk,
                actor=self.gm_a,
            )
        expiring.refresh_from_db()
        self.assertEqual(expiring.status, ApprovalRequest.Status.EXPIRED)
        self.assertTrue(AuditLog.objects.filter(action="approval_request.expired").exists())

    def test_permissions_for_approve_reject_and_cancel(self):
        approval = self.make_request()
        with self.assertRaises(PermissionDenied):
            approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.player)
        with self.assertRaises(PermissionDenied):
            reject_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.gm_b)
        with self.assertRaises(PermissionDenied):
            cancel_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.other_player)
        with self.assertRaises(PermissionDenied):
            approve_request(campaign=self.campaign_a, request_id=approval.pk, actor=self.editor)


class ApprovalUiAndSecurityTests(ApprovalP4Mixin, TestCase):
    def test_queue_empty_state_filters_and_dashboard_link(self):
        self.client.force_login(self.gm_a)
        queue_url = reverse("world:campaign_approval_queue", args=[self.campaign_a.pk])
        response = self.client.get(queue_url)
        self.assertContains(response, "Сейчас нет запросов, ожидающих решения")
        self.assertContains(response, "Ожидают")
        self.make_request()
        response = self.client.get(queue_url)
        self.assertContains(response, "Изменить описание")
        self.assertContains(response, "Тестовое изменение кампании")
        self.assertContains(response, "Ожидает решения")
        self.assertNotContains(response, "PENDING")
        dashboard = self.client.get(
            reverse("campaigns:gm_dashboard", args=[self.campaign_a.pk])
        )
        self.assertContains(dashboard, "Запросы на одобрение")

    def test_detail_is_human_first_and_technical_json_is_collapsed_escaped(self):
        approval = self.make_request(
            payload={"message": "<script>alert(1)</script>", "expected_description": ""}
        )
        self.client.force_login(self.gm_a)
        response = self.client.get(
            reverse(
                "world:approval_request_detail",
                args=[self.campaign_a.pk, approval.pk],
            )
        )
        self.assertContains(response, "Кто запросил")
        self.assertContains(response, "Что запрашивается")
        self.assertContains(response, "Что произойдёт после одобрения")
        self.assertContains(response, "Ожидает решения")
        self.assertContains(response, "Одобрить")
        self.assertContains(response, "Отклонить")
        self.assertContains(response, "Технические данные")
        self.assertContains(response, '<details class="panel technical-details')
        self.assertNotContains(response, '<details class="panel technical-details audit-technical approval-technical" open')
        self.assertNotContains(response, "<script>alert(1)</script>", html=False)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;", html=False)
        self.assertNotContains(response, "PENDING")
        content = response.content.decode()
        self.assertGreater(content.index(str(approval.operation_id)), content.index("Технические данные"))

    def test_player_sees_only_own_requests_and_only_cancel_control(self):
        own = self.make_request()
        other = self.make_request(requester=self.other_player, payload={"message": "Other"})
        self.client.force_login(self.player)
        mine_url = reverse("world:my_approval_requests", args=[self.campaign_a.pk])
        response = self.client.get(mine_url)
        self.assertContains(response, own.title)
        self.assertNotContains(response, other.title)
        own_detail = self.client.get(
            reverse("world:approval_request_detail", args=[self.campaign_a.pk, own.pk])
        )
        self.assertContains(own_detail, "Отменить запрос")
        self.assertNotContains(own_detail, ">Одобрить<", html=False)
        other_detail = self.client.get(
            reverse("world:approval_request_detail", args=[self.campaign_a.pk, other.pk])
        )
        self.assertEqual(other_detail.status_code, 404)

    def test_idor_role_matrix_and_superuser(self):
        approval = self.make_request()
        detail = reverse("world:approval_request_detail", args=[self.campaign_a.pk, approval.pk])
        queue = reverse("world:campaign_approval_queue", args=[self.campaign_a.pk])
        for denied in (self.gm_b, self.editor, self.outsider):
            self.client.force_login(denied)
            self.assertEqual(self.client.get(queue).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(queue).status_code, 200)
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_get_does_not_mutate_expired_request_or_audit(self):
        approval = self.make_request(expires_at=timezone.now() + timedelta(hours=1))
        ApprovalRequest.objects.filter(pk=approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        audit_count = AuditLog.objects.count()
        self.client.force_login(self.gm_a)
        response = self.client.get(
            reverse("world:approval_request_detail", args=[self.campaign_a.pk, approval.pk])
        )
        approval.refresh_from_db()
        self.assertContains(response, "Истекло")
        self.assertEqual(approval.status, ApprovalRequest.Status.PENDING)
        self.assertEqual(AuditLog.objects.count(), audit_count)

    def test_redirect_after_approval_shows_resolver_note_result_and_history(self):
        approval = self.make_request()
        self.client.force_login(self.gm_a)
        response = self.client.post(
            reverse("world:approve_approval_request", args=[self.campaign_a.pk, approval.pk]),
            {"resolution_note": "Разрешаю."},
            follow=True,
        )
        self.assertContains(response, "Одобрено")
        self.assertContains(response, "gm-a")
        self.assertContains(response, "Разрешаю.")
        self.assertContains(response, "Описание кампании обновлено")
        self.assertContains(response, "История изменений")
        self.assertNotContains(response, ">Одобрить<", html=False)

    def test_admin_is_superuser_read_only(self):
        model_admin = ApprovalRequestAdmin(ApprovalRequest, admin.site)
        request = type("Request", (), {"user": self.superuser})()
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


@skipUnless(
    connection.features.has_select_for_update,
    "SQLite не предоставляет row-level SELECT FOR UPDATE; проверка выполняется на PostgreSQL.",
)
class ApprovalConcurrencyTests(ApprovalP4Mixin, TransactionTestCase):
    reset_sequences = True

    def test_two_concurrent_approvers_apply_once(self):
        approval = self.make_request()
        barrier = threading.Barrier(2)

        def worker():
            close_old_connections()
            barrier.wait(timeout=5)
            try:
                approve_request(
                    campaign=Campaign.objects.get(pk=self.campaign_a.pk),
                    request_id=approval.pk,
                    actor=User.objects.get(pk=self.gm_a.pk),
                )
                return "approved"
            except ApprovalAlreadyResolved:
                return "resolved"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(outcomes, ["approved", "resolved"])
        self.assertEqual(AuditLog.objects.filter(action="test_domain.applied").count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="approval_request.approved").count(), 1)
