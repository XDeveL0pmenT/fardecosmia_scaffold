import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("world", "0018_auditlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("request_type", models.CharField(max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Ожидает решения"),
                            ("APPROVED", "Одобрено"),
                            ("REJECTED", "Отклонено"),
                            ("CANCELLED", "Отменено"),
                            ("EXPIRED", "Истекло"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("requester_label_snapshot", models.CharField(max_length=240)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("requested_world_minutes", models.BigIntegerField()),
                ("title", models.CharField(max_length=240)),
                ("summary", models.TextField()),
                ("target_object_id", models.CharField(blank=True, max_length=128)),
                ("target_label", models.CharField(blank=True, max_length=500)),
                ("payload", models.JSONField(default=dict)),
                ("payload_version", models.PositiveSmallIntegerField(default=1)),
                (
                    "dedupe_key",
                    models.CharField(blank=True, max_length=240, null=True),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_by_label_snapshot", models.CharField(blank=True, max_length=240)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_world_minutes", models.BigIntegerField(blank=True, null=True)),
                ("resolution_note", models.TextField(blank=True)),
                ("result", models.JSONField(blank=True, default=dict)),
                (
                    "operation_id",
                    models.UUIDField(db_index=True, default=uuid.uuid4),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approval_requests",
                        to="campaigns.campaign",
                    ),
                ),
                (
                    "requester",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approval_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_approval_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "ordering": ["-requested_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["campaign", "status", "requested_at"],
                        name="approval_campaign_status_idx",
                    ),
                    models.Index(
                        fields=["requester", "requested_at"],
                        name="approval_requester_time_idx",
                    ),
                    models.Index(fields=["request_type"], name="approval_type_idx"),
                    models.Index(fields=["status"], name="approval_status_idx"),
                    models.Index(fields=["expires_at"], name="approval_expires_idx"),
                    models.Index(
                        fields=["target_content_type", "target_object_id"],
                        name="approval_target_idx",
                    ),
                ],
            },
        ),
    ]
