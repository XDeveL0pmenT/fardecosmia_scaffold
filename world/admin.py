from django.contrib import admin

from .models import (
    ApprovalRequest,
    AuditLog,
    AtmosphericConfig,
    AtmosphericSnapshot,
    CampaignEntityOverride,
    CampaignWorldMapOverride,
    GlobalWorldMapLayer,
    Region,
    RegionAreaWeatherState,
    WeatherState,
    WorldEntry,
    WorldEvent,
    WorldMapLayer,
)
from world.services.access import can_manage_global_canon


def _adopt_saved_instance(destination, source):
    destination.__dict__.update(source.__dict__)
    destination._state = source._state


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "campaign",
        "biome",
        "base_temperature",
        "humidity",
        "use_manual_climate_overrides",
        "map_longitude",
        "map_latitude",
        "weather_geometry_revision",
        "weather_update_interval_minutes",
    )
    list_filter = ("campaign", "biome", "use_manual_climate_overrides")
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        from world.services.regions import create_region, update_region

        if change:
            original = Region.objects.get(pk=obj.pk)
            editable_fields = {
                field.name
                for field in Region._meta.concrete_fields
                if field.editable and not field.primary_key
            } - {"campaign"}
            result = update_region(
                actor=request.user,
                campaign=original.campaign,
                region=original,
                changes={name: getattr(obj, name) for name in editable_fields},
                initialize_weather=False,
            )
        else:
            result = create_region(
                actor=request.user,
                campaign=obj.campaign,
                region=obj,
                auto_configure_from_map=False,
            )
        _adopt_saved_instance(obj, result.region)

    def delete_model(self, request, obj):
        from world.services.regions import delete_region

        delete_region(actor=request.user, campaign=obj.campaign, region=obj)

    def delete_queryset(self, request, queryset):
        from world.services.regions import delete_region

        for region in queryset.select_related("campaign"):
            delete_region(actor=request.user, campaign=region.campaign, region=region)


@admin.register(WeatherState)
class WeatherStateAdmin(admin.ModelAdmin):
    list_display = (
        "region",
        "world_minutes",
        "temperature",
        "condition",
        "humidity",
        "pressure_hpa",
        "source",
        "region_weather_revision",
    )
    list_filter = ("condition", "source", "region__campaign")


@admin.register(RegionAreaWeatherState)
class RegionAreaWeatherStateAdmin(admin.ModelAdmin):
    list_display = (
        "region",
        "world_minutes",
        "region_weather_revision",
        "sampling_mode",
        "temperature_mean_c",
        "precipitating_area_fraction",
        "wind_speed_mean_m_s",
        "source",
    )
    list_filter = ("sampling_mode", "source", "region__campaign")


@admin.register(WorldEvent)
class WorldEventAdmin(admin.ModelAdmin):
    list_display = ("title", "campaign", "region", "trigger_at", "status")
    list_filter = ("campaign", "status", "visible_to_players")
    search_fields = ("title", "description")


@admin.register(WorldMapLayer)
class WorldMapLayerAdmin(admin.ModelAdmin):
    list_display = ("campaign", "grid_width", "grid_height", "updated_at")
    readonly_fields = tuple(field.name for field in WorldMapLayer._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GlobalWorldMapLayer)
class GlobalWorldMapLayerAdmin(admin.ModelAdmin):
    list_display = ("slug", "grid_width", "grid_height", "updated_at")
    readonly_fields = (
        "slug",
        "grid_width",
        "grid_height",
        "elevation_cells",
        "updated_at",
    )

    def has_module_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_global_canon(request.user)

    def has_add_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_global_canon(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from world.services.map_layers import update_global_biome_layer

        saved = update_global_biome_layer(
            actor=request.user,
            cells=obj.biome_cells,
        )
        _adopt_saved_instance(obj, saved)


@admin.register(CampaignWorldMapOverride)
class CampaignWorldMapOverrideAdmin(admin.ModelAdmin):
    list_display = ("campaign", "grid_width", "grid_height", "updated_at")
    readonly_fields = ("grid_width", "grid_height", "updated_at")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields.append("campaign")
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        from world.services.map_layers import update_campaign_biome_layer

        campaign = (
            CampaignWorldMapOverride.objects.get(pk=obj.pk).campaign
            if change
            else obj.campaign
        )
        saved = update_campaign_biome_layer(
            actor=request.user,
            campaign=campaign,
            cells=obj.biome_cells,
        )
        _adopt_saved_instance(obj, saved)


@admin.register(WorldEntry)
class WorldEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "slug", "revision", "updated_at")
    search_fields = ("title", "kind", "slug", "summary", "body")
    fields = ("kind", "slug", "title", "summary", "body", "revision", "created_by", "updated_by", "created_at", "updated_at")
    readonly_fields = ("revision", "created_by", "updated_by", "created_at", "updated_at")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset.filter(scope=WorldEntry.Scope.GLOBAL)
        if can_manage_global_canon(request.user):
            return queryset.filter(scope=WorldEntry.Scope.GLOBAL)
        return queryset.none()

    def has_module_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_global_canon(request.user) and (
            obj is None or obj.scope == WorldEntry.Scope.GLOBAL
        )

    def has_add_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_global_canon(request.user) and (
            obj is None or obj.scope == WorldEntry.Scope.GLOBAL
        )

    def has_delete_permission(self, request, obj=None):
        return can_manage_global_canon(request.user) and (
            obj is None or obj.scope == WorldEntry.Scope.GLOBAL
        )

    def save_model(self, request, obj, form, change):
        from world.services.canon import (
            create_global_world_entry,
            update_global_world_entry,
        )

        values = {
            field_name: getattr(obj, field_name)
            for field_name in ("kind", "slug", "title", "summary", "body")
        }
        if change:
            saved = update_global_world_entry(
                actor=request.user,
                entry=WorldEntry.objects.get(pk=obj.pk),
                **values,
            )
        else:
            saved = create_global_world_entry(actor=request.user, **values)
        _adopt_saved_instance(obj, saved)

    def delete_model(self, request, obj):
        from world.services.canon import delete_global_world_entry

        delete_global_world_entry(actor=request.user, entry=obj)

    def delete_queryset(self, request, queryset):
        from world.services.canon import delete_global_world_entry

        for entry in queryset:
            delete_global_world_entry(actor=request.user, entry=entry)


@admin.register(CampaignEntityOverride)
class CampaignEntityOverrideAdmin(admin.ModelAdmin):
    list_display = ("campaign", "content_type", "object_id", "is_suppressed", "revision")
    readonly_fields = (
        "campaign", "content_type", "object_id", "patch", "is_suppressed",
        "created_by", "updated_by", "created_at", "updated_at", "revision",
        "base_revision_at_creation",
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "action",
        "campaign_label_snapshot",
        "world_minutes",
        "actor_label_snapshot",
        "target_label",
        "source",
    )
    list_filter = ("source", "action", "target_content_type")
    search_fields = (
        "summary",
        "target_label",
        "actor_label_snapshot",
        "campaign_label_snapshot",
        "target_object_id",
    )
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    """Diagnostic view only; decisions belong to the campaign workflow UI."""

    list_display = (
        "requested_at",
        "campaign",
        "status",
        "title",
        "requester_label_snapshot",
        "resolved_by_label_snapshot",
    )
    list_filter = ("status", "request_type", "campaign")
    search_fields = (
        "title",
        "summary",
        "requester_label_snapshot",
        "resolved_by_label_snapshot",
        "target_label",
    )
    readonly_fields = tuple(field.name for field in ApprovalRequest._meta.fields)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AtmosphericConfig)
class AtmosphericConfigAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "enabled",
        "grid_width",
        "grid_height",
        "step_minutes",
        "oxygen_fraction",
        "checkpoint_interval_minutes",
        "checkpoint_retention_count",
    )
    list_filter = ("enabled",)
    readonly_fields = tuple(field.name for field in AtmosphericConfig._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AtmosphericSnapshot)
class AtmosphericSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "world_minutes",
        "grid_width",
        "grid_height",
        "format_version",
        "solver_version",
        "is_checkpoint",
        "created_at",
    )
    readonly_fields = (
        "campaign",
        "world_minutes",
        "grid_width",
        "grid_height",
        "format_version",
        "solver_version",
        "input_fingerprint",
        "is_checkpoint",
        "payload",
        "created_at",
    )
