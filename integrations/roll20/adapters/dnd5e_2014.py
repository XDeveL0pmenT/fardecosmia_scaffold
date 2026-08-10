def current(attributes, name, default=None):
    value = attributes.get(name)
    if not isinstance(value, dict):
        return default
    return value.get("current", default)


def maximum(attributes, name, default=None):
    value = attributes.get(name)
    if not isinstance(value, dict):
        return default
    return value.get("max", default)


def as_int(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize(attributes):
    """Stable internal representation of Roll20 D&D 5E (Legacy/2014)."""
    return {
        "system": "dnd5e_2014",
        "hp": {
            "current": as_int(current(attributes, "hp")),
            "max": as_int(maximum(attributes, "hp")),
            "temporary": as_int(current(attributes, "hp_temp")) or 0,
        },
        "ac": as_int(current(attributes, "ac")),
        "abilities": {
            "strength": as_int(current(attributes, "strength")),
            "dexterity": as_int(current(attributes, "dexterity")),
            "constitution": as_int(current(attributes, "constitution")),
            "intelligence": as_int(current(attributes, "intelligence")),
            "wisdom": as_int(current(attributes, "wisdom")),
            "charisma": as_int(current(attributes, "charisma")),
        },
        "speed": current(attributes, "speed"),
        "inspiration": current(attributes, "inspiration"),
        "resources": {},
        "spell_slots": {},
        "death_saves": {},
        "inventory": [],
        "spells": [],
        "attacks": [],
    }
