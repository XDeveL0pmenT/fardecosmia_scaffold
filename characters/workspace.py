from characters.services import controlled_characters, get_active_character
from world.services.ambience import build_character_ambience


WORKSPACE_NOTE_PREVIEW_LIMIT = 3


def build_character_workspace_context(*, campaign, membership):
    """Compose the shared PLAYER Workspace context for every compatible route."""

    characters = list(controlled_characters(membership=membership))
    active_character = get_active_character(membership.user, campaign)
    character_ambience = build_character_ambience(active_character, campaign)
    held_thoughts_preview = []
    if active_character is not None:
        held_thoughts_preview = list(
            active_character.personal_notes.all()[:WORKSPACE_NOTE_PREVIEW_LIMIT]
        )
    return {
        "campaign": campaign,
        "membership": membership,
        "characters": characters,
        "active_character": active_character,
        "character_location_available": character_ambience.location_available,
        "character_ambience": character_ambience,
        "held_thoughts_preview": held_thoughts_preview,
    }

