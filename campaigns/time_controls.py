TIME_ADVANCE_UNITS = (
    {"value": "minutes", "label": "Минуты", "max": 180, "default": 10},
    {"value": "hours", "label": "Часы Витка", "max": 168, "default": 1},
    {"value": "phases", "label": "Фазы Витка", "max": 28, "default": 1},
    {"value": "turns", "label": "Витки — дни мира", "max": 16, "default": 1},
    {"value": "seasons", "label": "Сезоны", "max": 8, "default": 1},
    {"value": "years", "label": "Годы", "max": 4, "default": 1},
)
TIME_ADVANCE_LIMITS = {item["value"]: item["max"] for item in TIME_ADVANCE_UNITS}
