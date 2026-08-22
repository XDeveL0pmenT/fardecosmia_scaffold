from django.contrib import admin

from world.services.audit import changed_fields, record_audit

from .models import Campaign, CampaignInvitation, CampaignMembership, TimeAdvanceReport
from .services.lifecycle import serialize_campaign_basics


class CampaignMembershipInline(admin.TabularInline):
    model = CampaignMembership
    extra = 0
    can_delete = False
    readonly_fields = ("user", "role", "active_character", "joined_at")

    def has_add_permission(self, request, obj=None):
        return False


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

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            before = serialize_campaign_basics(Campaign.objects.get(pk=obj.pk))
        super().save_model(request, obj, form, change)
        after = serialize_campaign_basics(obj)
        if not change:
            CampaignMembership.objects.get_or_create(
                campaign=obj,
                user=request.user,
                defaults={"role": CampaignMembership.Role.GM},
            )
            record_audit(
                action="campaign.created",
                actor=request.user,
                campaign=obj,
                target=obj,
                summary=f"Создана кампания «{obj.name}».",
                before_state=None,
                after_state=after,
            )
        elif before != after:
            record_audit(
                action="campaign.updated",
                actor=request.user,
                campaign=obj,
                target=obj,
                summary=f"Обновлено описание кампании «{obj.name}».",
                before_state=before,
                after_state=after,
                metadata={"changed_fields": changed_fields(before, after)},
            )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignMembership)
class CampaignMembershipAdmin(admin.ModelAdmin):
    list_display = ("campaign", "user", "role", "active_character", "joined_at")
    list_filter = ("role", "campaign")
    readonly_fields = ("campaign", "user", "role", "active_character", "joined_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CampaignInvitation)
class CampaignInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "email_normalized",
        "role",
        "created_at",
        "expires_at",
        "accepted_at",
        "revoked_at",
    )
    list_filter = ("campaign", "role")
    search_fields = ("email_normalized", "campaign__name")
    readonly_fields = tuple(field.name for field in CampaignInvitation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
