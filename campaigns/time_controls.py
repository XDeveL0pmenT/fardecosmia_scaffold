TIME_ADVANCE_UNITS = (
    {"value": "minutes", "label": "Минуты", "max": 180, "default": 10, "help": ""},
    {"value": "hours", "label": "Часы Витка", "max": 168, "default": 1, "help": ""},
    {
        "value": "phases",
        "label": "Фазы Витка",
        "max": 28,
        "default": 1,
        "help": "1 Фаза = 24 часа = 1/7 Витка.",
    },
    {
        "value": "turns",
        "label": "Витки — дни мира",
        "max": 16,
        "default": 1,
        "help": "1 Виток = 168 часов = 7 фаз света.",
    },
    {
        "value": "seasons",
        "label": "Сезоны",
        "max": 8,
        "default": 1,
        "help": (
            "Сезоны имеют разную длину из-за эллиптической орбиты: "
            "Лето короче Зимы. Шаг сохраняет текущую долю сезона."
        ),
    },
    {
        "value": "years",
        "label": "Годы",
        "max": 4,
        "default": 1,
        "help": "1 Великий Круг = 364 дня = 52 Витка; четыре орбитальных сезона неравны.",
    },
)
TIME_ADVANCE_LIMITS = {item["value"]: item["max"] for item in TIME_ADVANCE_UNITS}
