from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("world.urls")),
    path("", include("campaigns.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/v1/roll20/", include("integrations.roll20.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
