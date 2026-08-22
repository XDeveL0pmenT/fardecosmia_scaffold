import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contenttypes", "0002_remove_content_type_name"),
        ("world", "0016_region_weather_lifecycle"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorldEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(choices=[("global", "Глобальный канон"), ("campaign", "Только кампания")], max_length=20)),
                ("kind", models.SlugField(help_text="Техническое пространство имён, например lore или concept.", max_length=80)),
                ("slug", models.SlugField(max_length=160)),
                ("title", models.CharField(max_length=240)),
                ("summary", models.TextField(blank=True)),
                ("body", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("campaign", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="world_entries", to="campaigns.campaign")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_world_entries", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_world_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["kind", "title", "pk"],
                "permissions": [("manage_global_canon", "Can manage global Fardecosmia canon")],
                "indexes": [
                    models.Index(fields=["scope"], name="world_entry_scope_idx"),
                    models.Index(fields=["campaign", "kind"], name="world_entry_campaign_kind_idx"),
                    models.Index(fields=["kind", "slug"], name="world_entry_kind_slug_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(models.Q(("campaign__isnull", True), ("scope", "global")), models.Q(("campaign__isnull", False), ("scope", "campaign")), _connector="OR"), name="world_entry_scope_campaign_consistent"),
                    models.UniqueConstraint(condition=models.Q(("scope", "global")), fields=("kind", "slug"), name="unique_global_world_entry_identity"),
                    models.UniqueConstraint(condition=models.Q(("scope", "campaign")), fields=("campaign", "kind", "slug"), name="unique_campaign_world_entry_identity"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CampaignEntityOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.CharField(max_length=64)),
                ("patch", models.JSONField(blank=True, default=dict)),
                ("is_suppressed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("base_revision_at_creation", models.PositiveIntegerField(blank=True, null=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entity_overrides", to="campaigns.campaign")),
                ("content_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="contenttypes.contenttype")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_campaign_entity_overrides", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_campaign_entity_overrides", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["campaign_id", "content_type_id", "object_id"],
                "indexes": [
                    models.Index(fields=["campaign"], name="world_override_campaign_idx"),
                    models.Index(fields=["content_type", "object_id"], name="world_override_target_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("campaign", "content_type", "object_id"), name="unique_campaign_entity_override"),
                ],
            },
        ),
    ]
