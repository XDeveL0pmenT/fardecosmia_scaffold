import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("world", "0017_p1_p2_canon_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
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
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("USER", "Пользователь"),
                            ("SYSTEM", "Система"),
                            ("INTEGRATION", "Интеграция"),
                            ("IMPORT", "Импорт"),
                        ],
                        default="USER",
                        max_length=20,
                    ),
                ),
                ("action", models.CharField(max_length=120)),
                (
                    "campaign_id_snapshot",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                ("campaign_label_snapshot", models.CharField(blank=True, max_length=240)),
                ("world_minutes", models.BigIntegerField(blank=True, null=True)),
                ("actor_label_snapshot", models.CharField(blank=True, max_length=240)),
                ("target_object_id", models.CharField(blank=True, max_length=128)),
                ("target_label", models.CharField(blank=True, max_length=500)),
                ("summary", models.CharField(max_length=500)),
                ("before_state", models.JSONField(blank=True, null=True)),
                ("after_state", models.JSONField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "operation_id",
                    models.UUIDField(db_index=True, default=uuid.uuid4),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="campaigns.campaign",
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
                "ordering": ["-occurred_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["campaign", "occurred_at"],
                        name="audit_campaign_time_idx",
                    ),
                    models.Index(
                        fields=["campaign", "world_minutes"],
                        name="audit_campaign_world_idx",
                    ),
                    models.Index(
                        fields=["actor", "occurred_at"],
                        name="audit_actor_time_idx",
                    ),
                    models.Index(fields=["action"], name="audit_action_idx"),
                    models.Index(fields=["source"], name="audit_source_idx"),
                    models.Index(
                        fields=["target_content_type", "target_object_id"],
                        name="audit_target_idx",
                    ),
                ],
            },
        ),
    ]
