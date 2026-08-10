from copy import deepcopy

from django.db import transaction
from django.utils import timezone

from integrations.roll20.adapters.dnd5e_2014 import normalize
from integrations.roll20.models import Roll20CharacterBinding, Roll20SyncEvent


def merge_attributes(old, new):
    result = deepcopy(old)
    result.update(new)
    return result


@transaction.atomic
def process_sync(connection, payload):
    event_id = payload["event_id"]
    existing = Roll20SyncEvent.objects.filter(event_id=event_id).select_related("binding").first()
    if existing:
        return existing.binding, True

    game_id = str(payload.get("game", {}).get("id", "")).strip()
    if game_id:
        if connection.roll20_game_id and connection.roll20_game_id != game_id:
            raise ValueError("game_mismatch")
        if not connection.roll20_game_id:
            connection.roll20_game_id = game_id
            connection.save(update_fields=["roll20_game_id"])

    character_data = payload["character"]
    binding, _ = (
        Roll20CharacterBinding.objects
        .select_for_update()
        .get_or_create(
            connection=connection,
            roll20_character_id=character_data["id"],
            defaults={"roll20_name": character_data.get("name", "")},
        )
    )

    binding.roll20_name = character_data.get("name", binding.roll20_name)
    incoming = payload.get("attributes", {})
    mode = payload.get("mode", "delta")
    raw = incoming if mode == "snapshot" else merge_attributes(binding.raw_attributes, incoming)

    binding.raw_attributes = raw
    binding.normalized_state = normalize(raw)
    binding.last_sync_at = timezone.now()
    binding.save(update_fields=["roll20_name", "raw_attributes", "normalized_state", "last_sync_at"])

    Roll20SyncEvent.objects.create(
        event_id=event_id,
        binding=binding,
        kind=mode,
        payload=payload,
    )
    return binding, False
