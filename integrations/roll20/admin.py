from django.contrib import admin, messages

from .models import (
    Roll20CharacterBinding,
    Roll20Command,
    Roll20Connection,
    Roll20DeviceToken,
    Roll20SyncEvent,
)


class Roll20DeviceTokenInline(admin.TabularInline):
    model = Roll20DeviceToken
    extra = 0
    readonly_fields = ("token_prefix", "last_seen_at", "created_at")
    fields = ("name", "token_prefix", "is_active", "last_seen_at", "created_at")


@admin.register(Roll20Connection)
class Roll20ConnectionAdmin(admin.ModelAdmin):
    list_display = ("campaign", "roll20_game_id", "sheet_type", "protocol_version", "is_enabled")
    inlines = [Roll20DeviceTokenInline]


@admin.register(Roll20CharacterBinding)
class Roll20CharacterBindingAdmin(admin.ModelAdmin):
    list_display = ("roll20_name", "connection", "character", "last_sync_at")
    search_fields = ("roll20_name", "roll20_character_id")
    list_filter = ("connection",)


@admin.register(Roll20DeviceToken)
class Roll20DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "connection", "token_prefix", "is_active", "last_seen_at")
    readonly_fields = ("token_hash", "token_prefix", "last_seen_at", "created_at")


@admin.register(Roll20SyncEvent)
class Roll20SyncEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "binding", "kind", "received_at")
    list_filter = ("kind",)
    readonly_fields = ("event_id", "binding", "kind", "payload", "received_at")


@admin.register(Roll20Command)
class Roll20CommandAdmin(admin.ModelAdmin):
    list_display = ("id", "binding", "command_type", "status", "created_at")
    list_filter = ("status", "command_type")
