from functools import wraps

from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from django.utils import timezone

from .models import Roll20DeviceToken


def roll20_token_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return JsonResponse({"error": "missing_token"}, status=401)

        raw_token = header[7:].strip()
        if len(raw_token) < 16:
            return JsonResponse({"error": "invalid_token"}, status=401)

        try:
            device = (
                Roll20DeviceToken.objects
                .select_related("connection", "connection__campaign")
                .get(token_prefix=raw_token[:16], is_active=True)
            )
        except Roll20DeviceToken.DoesNotExist:
            return JsonResponse({"error": "invalid_token"}, status=401)

        if not check_password(raw_token, device.token_hash):
            return JsonResponse({"error": "invalid_token"}, status=401)
        if not device.connection.is_enabled:
            return JsonResponse({"error": "connection_disabled"}, status=403)

        Roll20DeviceToken.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
        request.roll20_device = device
        request.roll20_connection = device.connection
        return view(request, *args, **kwargs)

    return wrapper
