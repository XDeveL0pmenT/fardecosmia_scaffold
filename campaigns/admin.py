from django.contrib import admin

from .models import Campaign, CampaignMembership


class CampaignMembershipInline(admin.TabularInline):
    model = CampaignMembership
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "calendar_epoch_year",
        "world_minutes",
        "world_circumference_km",
        "light_season_min_red_turns",
        "created_at",
    )
    search_fields = ("name",)
    inlines = [CampaignMembershipInline]


@admin.register(CampaignMembership)
class CampaignMembershipAdmin(admin.ModelAdmin):
    list_display = ("campaign", "user", "role", "joined_at")
    list_filter = ("role", "campaign")
