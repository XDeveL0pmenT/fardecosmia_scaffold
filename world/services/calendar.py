from dataclasses import dataclass

from world.services.orbital_climate import (
    CANONICAL_YEAR_MINUTES,
    SEASON_CODES,
    orbital_climate_state,
    shift_orbital_seasons,
)


PHASES_PER_TURN = 7
TURNS_PER_FACE_CIRCLE = 16
TURNS_PER_HALF_FACE_CIRCLE = 8
# Deprecated compatibility constant.  Since C1, active season boundaries come
# from the annual Keplerian orbit rather than four fixed blocks of 13 Vitok.
TURNS_PER_SEASON = 13
SEASONS_PER_YEAR = 4
# The year remains exactly 52 Vitok; this no longer implies 13 Vitok per season.
TURNS_PER_YEAR = 52
PHASES_PER_SEASON = TURNS_PER_SEASON * PHASES_PER_TURN
PHASES_PER_YEAR = TURNS_PER_YEAR * PHASES_PER_TURN

SEASONS = ("Лето", "Осень", "Зима", "Весна")
LIGHT_PHASES = (
    "Рассвет",
    "День",
    "Яркий день",
    "Закат",
    "Ночь",
    "Глубокая ночь",
    "Предрассвет",
)
RED_TURN_PHASE_STATES = (
    "Яркий рассвет",
    "Светлый день",
    "Белый жар",
    "Светлый закат",
    "Светлая ночь",
    "Красная ночь",
    "Красный предрассвет",
)
BLACK_TURN_PHASE_STATES = (
    "Холодный рассвет",
    "Светлый день",
    "Сухой день",
    "Тёмный закат",
    "Чёрная ночь",
    "Глухая ночь",
    "Тёмный предрассвет",
)
FACE_PHASE_NAMES = {
    "Рассветание": (
        "Начало Рассветания",
        "Бледные ночи",
        "Красный край",
        "Половинная ночь",
        "Светлые ночи",
        "Красные ночи",
        "Высокий Лик",
        "Пик Рассветания",
    ),
    "Угасание": (
        "Начало Угасания",
        "Тусклый Лик",
        "Длинные тени",
        "Половинная ночь",
        "Тёмные ночи",
        "Чёрные ночи",
        "Глухие ночи",
        "Пик Угасания",
    ),
}


@dataclass(frozen=True)
class CalendarMoment:
    year: int
    year_index: int
    phase_of_year: int
    season: str
    season_code: str
    season_number: int
    season_progress: float
    season_duration_minutes: float
    season_duration_days: float
    season_duration_turns: float
    season_start_world_minutes: float
    season_end_world_minutes: float
    turns_in_season: int
    phase_of_season: int
    turn_of_season: int
    turn_of_year: int
    absolute_turn: int
    phase_of_turn: int
    light_phase: str
    phase_state: str
    turn_type: str
    turn_type_code: str
    face_circle_turn: int
    face_phase: str
    face_phase_turn: int
    face_phase_name: str
    ympha_visibility: float
    hour_of_turn: int
    minute: int
    turn_clock: str
    phase_fraction: float

    @property
    def season_progress_percent(self):
        return self.season_progress * 100.0


def _ympha_visibility(face_circle_turn):
    """Technical 0..1 interpolation of the confirmed 16-turn face cycle."""
    if face_circle_turn <= TURNS_PER_HALF_FACE_CIRCLE:
        return (face_circle_turn - 1) / (TURNS_PER_HALF_FACE_CIRCLE - 1)
    return (TURNS_PER_FACE_CIRCLE - face_circle_turn) / (
        TURNS_PER_HALF_FACE_CIRCLE - 1
    )


def describe_time(
    world_minutes,
    *,
    epoch_year=0,
    hours_per_turn=168,
    minutes_per_hour=60,
    red_turn_visibility_threshold=0.5,
    season_world_minutes=None,
):
    if hours_per_turn < 1 or minutes_per_hour < 1:
        raise ValueError("Длительность Витка должна быть положительной.")
    if not 0 <= red_turn_visibility_threshold <= 1:
        raise ValueError("Порог Красного Витка должен находиться между 0 и 1.")

    minutes_per_turn = hours_per_turn * minutes_per_hour
    absolute_turn, minute_of_turn = divmod(world_minutes, minutes_per_turn)
    _legacy_year_index, turn_of_year_zero = divmod(absolute_turn, TURNS_PER_YEAR)
    orbital = orbital_climate_state(
        world_minutes if season_world_minutes is None else season_world_minutes
    )
    year_index = orbital.year_index
    season_index = SEASON_CODES.index(orbital.global_season)
    season_elapsed = max(
        0.0,
        (world_minutes if season_world_minutes is None else season_world_minutes)
        - orbital.season_start_world_minutes,
    )
    turn_of_season_zero = int(season_elapsed // minutes_per_turn)
    face_circle_turn = absolute_turn % TURNS_PER_FACE_CIRCLE + 1

    phase_progress = minute_of_turn * PHASES_PER_TURN / minutes_per_turn
    phase_of_turn_zero = min(int(phase_progress), PHASES_PER_TURN - 1)
    phase_fraction = phase_progress - phase_of_turn_zero

    if face_circle_turn <= TURNS_PER_HALF_FACE_CIRCLE:
        face_phase = "Рассветание"
        face_phase_turn = face_circle_turn
    else:
        face_phase = "Угасание"
        face_phase_turn = face_circle_turn - TURNS_PER_HALF_FACE_CIRCLE

    visibility = _ympha_visibility(face_circle_turn)
    is_red_turn = visibility >= red_turn_visibility_threshold
    phase_states = (
        RED_TURN_PHASE_STATES if is_red_turn else BLACK_TURN_PHASE_STATES
    )
    hour_of_turn, minute = divmod(minute_of_turn, minutes_per_hour)

    return CalendarMoment(
        year=epoch_year + year_index,
        year_index=year_index,
        phase_of_year=turn_of_year_zero * PHASES_PER_TURN + phase_of_turn_zero + 1,
        season=orbital.global_season_label,
        season_code=orbital.global_season,
        season_number=season_index + 1,
        season_progress=orbital.season_progress,
        season_duration_minutes=orbital.season_duration_minutes,
        season_duration_days=orbital.season_duration_days,
        season_duration_turns=orbital.season_duration_minutes / minutes_per_turn,
        season_start_world_minutes=orbital.season_start_world_minutes,
        season_end_world_minutes=orbital.season_end_world_minutes,
        turns_in_season=max(1, int(-(-orbital.season_duration_minutes // minutes_per_turn))),
        phase_of_season=(
            int(season_elapsed // (minutes_per_turn / PHASES_PER_TURN)) + 1
        ),
        turn_of_season=turn_of_season_zero + 1,
        turn_of_year=turn_of_year_zero + 1,
        absolute_turn=absolute_turn,
        phase_of_turn=phase_of_turn_zero + 1,
        light_phase=LIGHT_PHASES[phase_of_turn_zero],
        phase_state=phase_states[phase_of_turn_zero],
        turn_type="Красный Виток" if is_red_turn else "Чёрный Виток",
        turn_type_code="red" if is_red_turn else "black",
        face_circle_turn=face_circle_turn,
        face_phase=face_phase,
        face_phase_turn=face_phase_turn,
        face_phase_name=FACE_PHASE_NAMES[face_phase][face_phase_turn - 1],
        ympha_visibility=round(visibility, 4),
        hour_of_turn=hour_of_turn,
        minute=minute,
        turn_clock=f"{hour_of_turn:03d}:{minute:02d}",
        phase_fraction=phase_fraction,
    )


def describe_campaign_time(campaign, world_minutes=None):
    if world_minutes is None:
        world_minutes = campaign.world_minutes
    return describe_time(
        world_minutes,
        epoch_year=campaign.calendar_epoch_year,
        hours_per_turn=campaign.calendar_hours_per_turn,
        minutes_per_hour=campaign.calendar_minutes_per_hour,
        red_turn_visibility_threshold=campaign.red_turn_visibility_threshold,
    )


def minutes_for_time_step(campaign, amount, unit):
    if amount < 1:
        raise ValueError("Шаг времени должен быть положительным.")
    if campaign.calendar_minutes_per_turn % PHASES_PER_TURN:
        raise ValueError("Виток должен делиться на семь равных фаз.")

    minute_multipliers = {
        "minutes": 1,
        "hours": campaign.calendar_minutes_per_hour,
        "phases": campaign.calendar_minutes_per_phase,
        "turns": campaign.calendar_minutes_per_turn,
        # Legacy request value: a world day is one full Turn, not 24 hours.
        "days": campaign.calendar_minutes_per_turn,
        "years": CANONICAL_YEAR_MINUTES,
    }
    if unit == "seasons":
        return shift_orbital_seasons(campaign.world_minutes, amount)
    try:
        return amount * minute_multipliers[unit]
    except KeyError as error:
        raise ValueError("Неизвестная единица времени.") from error
