from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef

from campaigns.services.eligibility import (
    GM_ELIGIBILITY_CODENAME,
    has_gm_eligibility,
    set_gm_eligibility,
)
from .models import EmailVerificationChallenge, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Фардекосмия",
            {
                "fields": (
                    "display_name",
                    "avatar",
                    "email_verification_required",
                    "email_verified_at",
                    "verified_email",
                )
            },
        ),
    )

    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Фардекосмия",
            {
                "classes": ("wide",),
                "fields": ("display_name",),
            },
        ),
    )

    list_display = (
        "username",
        "display_name",
        "email",
        "gm_eligibility_status",
        "is_staff",
        "is_active",
        "email_verified_at",
    )
    readonly_fields = DjangoUserAdmin.readonly_fields + (
        "email_verified_at",
        "verified_email",
    )
    search_fields = (
        "username",
        "display_name",
        "email",
        "first_name",
        "last_name",
    )
    actions = ("grant_gm_eligibility", "revoke_gm_eligibility")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        direct_permissions = User.user_permissions.through.objects.filter(
            user_id=OuterRef("pk"),
            permission__content_type__app_label="campaigns",
            permission__codename=GM_ELIGIBILITY_CODENAME,
        )
        return queryset.annotate(_has_direct_gm_eligibility=Exists(direct_permissions))

    @admin.display(boolean=True, description="Доверенный Game Master")
    def gm_eligibility_status(self, obj):
        return bool(obj.is_superuser or obj._has_direct_gm_eligibility)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            fields.extend(["groups", "user_permissions", "is_superuser"])
        return tuple(dict.fromkeys(fields))

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "user_permissions" and field is not None:
            # Eligibility has a dedicated, audited superuser-only action. It
            # cannot be silently changed through the generic permission widget.
            field.queryset = field.queryset.exclude(
                content_type__app_label="campaigns",
                codename=GM_ELIGIBILITY_CODENAME,
            )
        return field

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("grant_gm_eligibility", None)
            actions.pop("revoke_gm_eligibility", None)
        return actions

    @admin.action(description="Выдать право доверенного Game Master")
    def grant_gm_eligibility(self, request, queryset):
        changed = 0
        for user in queryset.order_by("pk"):
            before = has_gm_eligibility(user)
            set_gm_eligibility(actor=request.user, user_id=user.pk, eligible=True)
            if not before:
                changed += 1
        self.message_user(
            request,
            f"Право Game Master выдано: {changed}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Отозвать право доверенного Game Master")
    def revoke_gm_eligibility(self, request, queryset):
        changed = 0
        skipped = 0
        for user in queryset.order_by("pk"):
            before = has_gm_eligibility(user)
            try:
                set_gm_eligibility(
                    actor=request.user,
                    user_id=user.pk,
                    eligible=False,
                )
            except ValidationError:
                skipped += 1
                continue
            if before:
                changed += 1
        level = messages.WARNING if skipped else messages.SUCCESS
        text = f"Право Game Master отозвано: {changed}."
        if skipped:
            text += f" Superuser пропущено: {skipped}."
        self.message_user(request, text, level=level)


@admin.register(EmailVerificationChallenge)
class EmailVerificationChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "email_snapshot",
        "generation",
        "created_at",
        "expires_at",
        "attempt_count",
        "verified_at",
        "consumed_at",
    )
    search_fields = ("user__username", "email_snapshot")
    readonly_fields = tuple(field.name for field in EmailVerificationChallenge._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
