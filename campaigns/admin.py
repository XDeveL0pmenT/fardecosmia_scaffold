from django.contrib import admin

from .models import Campaign, CampaignMembership, TimeAdvanceReport


class CampaignMembershipInline(admin.TabularInline):
    model = CampaignMembership
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "calendar_epoch_year",
        "world_minutes",
        "exact_simulation_max_turns",
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


@admin.register(TimeAdvanceReport)
class TimeAdvanceReportAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "gm",
        "start_world_minutes",
        "end_world_minutes",
        "simulation_mode",
        "created_at",
    )
    list_filter = ("simulation_mode", "campaign")
    readonly_fields = (
        "campaign",
        "gm",
        "start_world_minutes",
        "end_world_minutes",
        "requested_amount",
        "requested_unit",
        "simulation_mode",
        "coverage",
        "summary",
        "created_at",
    )
