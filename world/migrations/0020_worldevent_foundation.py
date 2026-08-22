import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def preserve_existing_world_events(apps, schema_editor):
    WorldEvent = apps.get_model("world", "WorldEvent")
    WorldEventOccurrence = apps.get_model("world", "WorldEventOccurrence")

    for event in WorldEvent.objects.select_related("region").order_by("id"):
        event.event_type = "narrative.event"
        event.trigger_type = "WORLD_TIME"
        event.trigger_config = {}
        event.trigger_version = 1
        event.effect_payload = {}
        event.enabled = event.status != "cancelled"
        event.one_shot = True
        event.revision = 1
        event.save(
            update_fields=[
                "event_type",
                "trigger_type",
                "trigger_config",
                "trigger_version",
                "effect_payload",
                "enabled",
                "one_shot",
                "revision",
            ]
        )
        if event.status != "triggered":
            continue
        occurred_world_minutes = (
            event.triggered_at if event.triggered_at is not None else event.trigger_at
        )
        WorldEventOccurrence.objects.get_or_create(
            definition_id=event.pk,
            defaults={
                "campaign_id": event.campaign_id,
                "definition_revision": 1,
                "event_type_snapshot": "narrative.event",
                "title": event.title,
                "summary": event.description,
                "occurred_world_minutes": occurred_world_minutes,
                "scheduled_world_minutes": event.trigger_at,
                "source": "SYSTEM",
                "actor_label_snapshot": "",
                "trigger_type_snapshot": "WORLD_TIME",
                "trigger_snapshot": {
                    "scheduled_world_minutes": event.trigger_at,
                },
                "trigger_version_snapshot": 1,
                "region_id": event.region_id,
                "region_label_snapshot": (
                    event.region.name if event.region_id else ""
                ),
                "effect_result": {},
                "operation_id": uuid.uuid4(),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("world", "0019_approvalrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="worldevent",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="worldevent",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_world_event_definitions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="created_by_label_snapshot",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="effect_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="effect_type",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="effect_version",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="event_type",
            field=models.CharField(default="narrative.event", max_length=120),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="latitude",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(-90),
                    django.core.validators.MaxValueValidator(90),
                ],
            ),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="longitude",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(-180),
                    django.core.validators.MaxValueValidator(180),
                ],
            ),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="one_shot",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="revision",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="target_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="world_event_definitions",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="target_label",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="target_object_id",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="trigger_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="trigger_type",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Вручную"),
                    ("WORLD_TIME", "По мировому времени"),
                ],
                default="WORLD_TIME",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="trigger_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="worldevent",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="worldevent",
            name="trigger_at",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                help_text="Игровая минута запуска для WORLD_TIME",
                null=True,
            ),
        ),
        migrations.AlterModelOptions(
            name="worldevent",
            options={"ordering": ["trigger_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="worldevent",
            index=models.Index(
                fields=["campaign", "enabled", "trigger_type", "trigger_at"],
                name="event_due_lookup_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="worldevent",
            index=models.Index(
                fields=["campaign", "event_type"],
                name="event_campaign_type_idx",
            ),
        ),
        migrations.CreateModel(
            name="WorldEventOccurrence",
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
                ("definition_revision", models.PositiveIntegerField(default=1)),
                ("event_type_snapshot", models.CharField(max_length=120)),
                ("title", models.CharField(max_length=200)),
                ("summary", models.TextField(blank=True)),
                ("occurred_world_minutes", models.BigIntegerField()),
                ("scheduled_world_minutes", models.BigIntegerField(blank=True, null=True)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source",
                    models.CharField(
                        choices=[("USER", "Game Master"), ("SYSTEM", "Система")],
                        max_length=20,
                    ),
                ),
                ("actor_label_snapshot", models.CharField(blank=True, max_length=240)),
                ("trigger_type_snapshot", models.CharField(max_length=30)),
                ("trigger_snapshot", models.JSONField(blank=True, default=dict)),
                ("trigger_version_snapshot", models.PositiveSmallIntegerField(default=1)),
                ("target_object_id", models.CharField(blank=True, max_length=128)),
                ("target_label", models.CharField(blank=True, max_length=500)),
                ("region_label_snapshot", models.CharField(blank=True, max_length=200)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("effect_type_snapshot", models.CharField(blank=True, max_length=120, null=True)),
                ("effect_version_snapshot", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("effect_result", models.JSONField(blank=True, default=dict)),
                ("operation_id", models.UUIDField(db_index=True, default=uuid.uuid4)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="world_event_occurrences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="world_event_occurrences",
                        to="campaigns.campaign",
                    ),
                ),
                (
                    "definition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="occurrences",
                        to="world.worldevent",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_occurrences",
                        to="world.region",
                    ),
                ),
                (
                    "target_content_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="world_event_occurrences",
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_world_minutes", "-id"],
                "indexes": [
                    models.Index(
                        fields=["campaign", "occurred_world_minutes"],
                        name="event_occ_campaign_time_idx",
                    ),
                    models.Index(
                        fields=["campaign", "event_type_snapshot"],
                        name="event_occ_campaign_type_idx",
                    ),
                    models.Index(
                        fields=["region", "occurred_world_minutes"],
                        name="event_occ_region_time_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("definition__isnull", False)),
                        fields=("definition",),
                        name="unique_world_event_occurrence",
                    )
                ],
            },
        ),
        migrations.RunPython(
            preserve_existing_world_events,
            migrations.RunPython.noop,
        ),
    ]
