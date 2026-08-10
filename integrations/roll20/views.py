import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .auth import roll20_token_required
from .services.sync import process_sync


@require_GET
@roll20_token_required
def ping(request):
    return JsonResponse({
        "ok": True,
        "protocol": request.roll20_connection.protocol_version,
        "sheet": request.roll20_connection.sheet_type,
        "campaign": str(request.roll20_connection.campaign_id),
    })


@csrf_exempt
@require_POST
@roll20_token_required
def sync_character(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    if payload.get("protocol") != 1:
        return JsonResponse({"error": "unsupported_protocol"}, status=400)

    mode = payload.get("mode")
    if mode not in {"snapshot", "delta"}:
        return JsonResponse({"error": "invalid_mode"}, status=400)

    character = payload.get("character", {})
    if character.get("sheet") != "dnd5e_2014":
        return JsonResponse({"error": "unsupported_sheet"}, status=400)
    if not character.get("id"):
        return JsonResponse({"error": "missing_character_id"}, status=400)
    if not payload.get("event_id"):
        return JsonResponse({"error": "missing_event_id"}, status=400)
    if not isinstance(payload.get("attributes", {}), dict):
        return JsonResponse({"error": "invalid_attributes"}, status=400)

    try:
        binding, duplicate = process_sync(request.roll20_connection, payload)
    except (KeyError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "duplicate": duplicate,
        "roll20_character_id": binding.roll20_character_id,
        "binding_id": binding.pk,
        "character_id": binding.character_id,
        "needs_binding": binding.character_id is None,
    })
