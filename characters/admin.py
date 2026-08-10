from django.contrib import admin

from .models import Character


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "campaign", "owner", "updated_at")
    list_filter = ("campaign",)
    search_fields = ("name", "biography", "public_notes", "gm_notes")
