from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Фардекосмия",
            {
                "fields": (
                    "display_name",
                    "avatar",
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
    )
    search_fields = (
        "username",
        "display_name",
        "email",
        "first_name",
        "last_name",
    )
