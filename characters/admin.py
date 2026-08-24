from django.contrib import admin

from .models import Character, CharacterLocationState


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    """Diagnostic only; supported mutations go through audited services."""

    list_display = ("name", "campaign", "owner", "is_active", "updated_at")
    list_filter = ("campaign", "is_active")
    search_fields = ("name", "biography", "public_notes", "gm_notes")
    readonly_fields = tuple(field.name for field in Character._meta.fields)

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


@admin.register(CharacterLocationState)
class CharacterLocationStateAdmin(admin.ModelAdmin):
    """Superuser diagnostic view; normal placement is audited application flow."""

    list_display = ("character", "latitude", "longitude", "created_at")
    list_select_related = ("character", "character__campaign")
    search_fields = ("character__name", "character__campaign__name")
    readonly_fields = tuple(field.name for field in CharacterLocationState._meta.fields)

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
