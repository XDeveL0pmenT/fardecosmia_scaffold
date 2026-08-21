from django.contrib import admin

from .models import (
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
    readonly_fields = ("updated_at",)


@admin.register(GlobalWorldMapLayer)
class GlobalWorldMapLayerAdmin(admin.ModelAdmin):
    list_display = ("slug", "grid_width", "grid_height", "updated_at")
    readonly_fields = ("grid_width", "grid_height", "updated_at")

    def has_module_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_global_canon(request.user)

    def has_add_permission(self, request):
        return can_manage_global_canon(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_global_canon(request.user)

    def has_delete_permission(self, request, obj=None):
        return can_manage_global_canon(request.user)


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
        return request.user.is_superuser


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
        obj.scope = WorldEntry.Scope.GLOBAL
        obj.campaign = None
        if change and form.changed_data:
            obj.revision += 1
        if obj.pk:
            obj.updated_by = request.user
        else:
            obj.created_by = request.user
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)

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
        return request.user.is_superuser


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
