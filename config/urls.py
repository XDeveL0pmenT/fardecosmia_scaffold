from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.urls import password_reset_patterns

urlpatterns = [
    path("", include("world.urls")),
    path("", include("campaigns.urls")),
    path("", include("characters.urls")),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include(password_reset_patterns)),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/v1/roll20/", include("integrations.roll20.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
