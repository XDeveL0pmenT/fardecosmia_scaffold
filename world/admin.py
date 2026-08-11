from django.contrib import admin

from .models import (
    AtmosphericConfig,
    AtmosphericSnapshot,
    CampaignWorldMapOverride,
    GlobalWorldMapLayer,
    Region,
    WeatherState,
    WorldEvent,
    WorldMapLayer,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "campaign",
        "biome",
        "base_temperature",
        "humidity",
        "map_longitude",
        "map_latitude",
        "weather_update_interval_minutes",
    )
    list_filter = ("campaign", "biome")
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
    )
    list_filter = ("condition", "source", "region__campaign")


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


@admin.register(CampaignWorldMapOverride)
class CampaignWorldMapOverrideAdmin(admin.ModelAdmin):
    list_display = ("campaign", "grid_width", "grid_height", "updated_at")
    readonly_fields = ("grid_width", "grid_height", "updated_at")


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
