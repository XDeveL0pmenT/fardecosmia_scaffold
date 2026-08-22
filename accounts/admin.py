from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

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
