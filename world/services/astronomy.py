import math
from dataclasses import dataclass

from world.services.calendar import (
    BLACK_TURN_PHASE_STATES,
    FACE_PHASE_NAMES,
    LIGHT_PHASES,
    PHASES_PER_TURN,
    RED_TURN_PHASE_STATES,
    TURNS_PER_FACE_CIRCLE,
    TURNS_PER_HALF_FACE_CIRCLE,
    TURNS_PER_SEASON,
    describe_time,
)


STAR_INTENSITY_BY_PHASE = (0.28, 0.76, 1.0, 0.38, 0.03, 0.0, 0.08)
SEASON_ADJECTIVES = {
    "Лето": {"light": "Светлое", "dark": "Тёмное", "mixed": "Смешанное"},
    "Осень": {"light": "Светлая", "dark": "Тёмная", "mixed": "Смешанная"},
    "Зима": {"light": "Светлая", "dark": "Тёмная", "mixed": "Смешанная"},
    "Весна": {"light": "Светлая", "dark": "Тёмная", "mixed": "Смешанная"},
}


@dataclass(frozen=True)
class RegionalSky:
    location_known: bool
    longitude: float
    latitude: float
    longitude_label: str
    latitude_label: str
    equatorial_offset_km: float
    timezone_offset_minutes: int
    timezone_label: str
    local_world_minutes: int
    local_moment: object
    star_intensity: float
    star_intensity_percent: int
    star_phase: str
    star_phase_code: str
    ympha_visibility: float
    ympha_visibility_percent: int
    effective_night_visibility_percent: int
    face_circle_turn: int
    face_phase: str
    face_phase_turn: int
    face_phase_name: str
    turn_type: str
    turn_type_code: str
    phase_state: str
    darkness: float
    season_ympha_visibility: float
    season_ympha_visibility_percent: int
    season_red_turns: int
    season_light_code: str
    season_light_label: str
    season_label: str


def wrap_longitude(longitude):
    return (longitude + 180) % 360 - 180


def angular_delta(longitude, reference_longitude):
    return wrap_longitude(longitude - reference_longitude)


def longitude_to_map_x(longitude):
    return (wrap_longitude(longitude) + 180) / 360


def _coordinate_label(value, positive, negative):
    if abs(value) < 0.0005:
        return "0°"
    suffix = positive if value > 0 else negative
    return f"{abs(value):.2f}° {suffix}"


def _timezone_label(offset_minutes):
    sign = "+" if offset_minutes >= 0 else "−"
    hours, minutes = divmod(abs(offset_minutes), 60)
    return f"{sign}{hours:03d}:{minutes:02d} от нулевого меридиана"


def _cyclic_interpolate(values, progress):
    scaled = (progress % 1) * len(values)
    index = int(math.floor(scaled))
    fraction = scaled - index
    return values[index] * (1 - fraction) + values[(index + 1) % len(values)] * fraction


def _ympha_visibility_at(campaign, world_minutes, longitude):
    global_turn_progress = world_minutes / campaign.calendar_minutes_per_turn
    ympha_delta = angular_delta(longitude, campaign.ympha_peak_longitude_at_epoch)
    local_face_progress = (
        TURNS_PER_HALF_FACE_CIRCLE
        + global_turn_progress
        - campaign.ympha_motion_direction
        * ympha_delta
        / 360
        * TURNS_PER_FACE_CIRCLE
    ) % TURNS_PER_FACE_CIRCLE
    visibility = 1 - abs(
        local_face_progress - TURNS_PER_HALF_FACE_CIRCLE
    ) / TURNS_PER_HALF_FACE_CIRCLE
    return local_face_progress, max(0, min(1, visibility))


def _describe_local_season_light(
    campaign,
    moment,
    longitude,
    timezone_offset,
):
    minutes_per_turn = campaign.calendar_minutes_per_turn
    # CalendarMoment intentionally contains no real-world datetime.  Rebuild the
    # local season boundary from its integer Turn counters.
    local_season_start = (
        (moment.absolute_turn - (moment.turn_of_season - 1)) * minutes_per_turn
    )
    global_season_start = local_season_start - timezone_offset
    visibilities = []
    for turn_index in range(TURNS_PER_SEASON):
        sample_time = global_season_start + round((turn_index + 0.5) * minutes_per_turn)
        _, visibility = _ympha_visibility_at(campaign, sample_time, longitude)
        visibilities.append(visibility)

    red_turns = sum(
        visibility >= campaign.red_turn_visibility_threshold
        for visibility in visibilities
    )
    if red_turns >= campaign.light_season_min_red_turns:
        code = "light"
        label = "Светлый сезон"
    elif red_turns <= campaign.dark_season_max_red_turns:
        code = "dark"
        label = "Тёмный сезон"
    else:
        code = "mixed"
        label = "Смешанный сезон"
    adjective = SEASON_ADJECTIVES[moment.season][code]
    return {
        "visibility": sum(visibilities) / len(visibilities),
        "red_turns": red_turns,
        "code": code,
        "label": label,
        "season_label": f"{adjective} {moment.season}",
    }


def calculate_local_sky(
    campaign,
    world_minutes,
    longitude,
    latitude=0,
    *,
    location_known=True,
):
    minutes_per_turn = campaign.calendar_minutes_per_turn
    star_delta = angular_delta(longitude, campaign.star_reference_longitude)
    timezone_offset = round(
        -campaign.star_motion_direction * star_delta / 360 * minutes_per_turn
    )
    local_world_minutes = world_minutes + timezone_offset
    moment = describe_time(
        local_world_minutes,
        epoch_year=campaign.calendar_epoch_year,
        hours_per_turn=campaign.calendar_hours_per_turn,
        minutes_per_hour=campaign.calendar_minutes_per_hour,
        red_turn_visibility_threshold=campaign.red_turn_visibility_threshold,
    )

    star_progress = (
        (moment.phase_of_turn - 1) + moment.phase_fraction
    ) / PHASES_PER_TURN
    star_intensity = max(0, min(1, _cyclic_interpolate(
        STAR_INTENSITY_BY_PHASE,
        star_progress,
    )))

    local_face_progress, ympha_visibility = _ympha_visibility_at(
        campaign,
        world_minutes,
        longitude,
    )

    if local_face_progress < TURNS_PER_HALF_FACE_CIRCLE:
        face_phase = "Рассветание"
        face_phase_turn = int(local_face_progress) + 1
    else:
        face_phase = "Угасание"
        face_phase_turn = int(local_face_progress - TURNS_PER_HALF_FACE_CIRCLE) + 1
    face_circle_turn = int(local_face_progress) + 1

    is_red_turn = ympha_visibility >= campaign.red_turn_visibility_threshold
    phase_states = RED_TURN_PHASE_STATES if is_red_turn else BLACK_TURN_PHASE_STATES
    effective_night_visibility = (1 - star_intensity) * ympha_visibility
    # A Black deep night must reach real darkness, while a visible Ympha turns
    # the same night red and substantially brighter.
    darkness = (1 - star_intensity) * (1 - ympha_visibility * 0.72)
    darkness = max(0, min(1, darkness))
    season_light = _describe_local_season_light(
        campaign,
        moment,
        longitude,
        timezone_offset,
    )

    equatorial_offset_km = (
        star_delta / 360 * campaign.world_circumference_km
    )
    return RegionalSky(
        location_known=location_known,
        longitude=longitude,
        latitude=latitude,
        longitude_label=_coordinate_label(longitude, "в.д.", "з.д."),
        latitude_label=_coordinate_label(latitude, "с.ш.", "ю.ш."),
        equatorial_offset_km=round(equatorial_offset_km, 1),
        timezone_offset_minutes=timezone_offset,
        timezone_label=_timezone_label(timezone_offset),
        local_world_minutes=local_world_minutes,
        local_moment=moment,
        star_intensity=round(star_intensity, 4),
        star_intensity_percent=round(star_intensity * 100),
        star_phase=LIGHT_PHASES[moment.phase_of_turn - 1],
        star_phase_code=(
            "bright" if moment.phase_of_turn == 3
            else "day" if moment.phase_of_turn == 2
            else "dawn" if moment.phase_of_turn == 1
            else "sunset" if moment.phase_of_turn == 4
            else "night" if moment.phase_of_turn == 5
            else "deep-night" if moment.phase_of_turn == 6
            else "predawn"
        ),
        ympha_visibility=round(ympha_visibility, 4),
        ympha_visibility_percent=round(ympha_visibility * 100),
        effective_night_visibility_percent=round(effective_night_visibility * 100),
        face_circle_turn=face_circle_turn,
        face_phase=face_phase,
        face_phase_turn=face_phase_turn,
        face_phase_name=FACE_PHASE_NAMES[face_phase][face_phase_turn - 1],
        turn_type="Красный Виток" if is_red_turn else "Чёрный Виток",
        turn_type_code="red" if is_red_turn else "black",
        phase_state=phase_states[moment.phase_of_turn - 1],
        darkness=round(darkness, 4),
        season_ympha_visibility=round(season_light["visibility"], 4),
        season_ympha_visibility_percent=round(season_light["visibility"] * 100),
        season_red_turns=season_light["red_turns"],
        season_light_code=season_light["code"],
        season_light_label=season_light["label"],
        season_label=season_light["season_label"],
    )


def describe_region_sky(region, world_minutes):
    location_known = region.map_longitude is not None and region.map_latitude is not None
    longitude = (
        region.map_longitude
        if region.map_longitude is not None
        else region.campaign.star_reference_longitude
    )
    latitude = region.map_latitude if region.map_latitude is not None else 0
    return calculate_local_sky(
        region.campaign,
        world_minutes,
        longitude,
        latitude,
        location_known=location_known,
    )


def celestial_positions(campaign, world_minutes):
    turn_progress = world_minutes / campaign.calendar_minutes_per_turn
    star_bright_longitude = wrap_longitude(
        campaign.star_reference_longitude
        + campaign.star_motion_direction * 360 * (turn_progress - 2 / PHASES_PER_TURN)
    )
    ympha_peak_longitude = wrap_longitude(
        campaign.ympha_peak_longitude_at_epoch
        + campaign.ympha_motion_direction
        * 360
        * turn_progress
        / TURNS_PER_FACE_CIRCLE
    )
    star_x = longitude_to_map_x(star_bright_longitude) * 1000
    ympha_x = longitude_to_map_x(ympha_peak_longitude) * 1000
    return {
        "star_longitude": star_bright_longitude,
        "star_x": f"{star_x:.4f}",
        "star_label_x": "-10" if star_x > 820 else "10",
        "star_text_anchor": "end" if star_x > 820 else "start",
        "ympha_longitude": ympha_peak_longitude,
        "ympha_x": f"{ympha_x:.4f}",
        "ympha_label_x": "-10" if ympha_x > 820 else "10",
        "ympha_text_anchor": "end" if ympha_x > 820 else "start",
    }


def build_light_bands(campaign, world_minutes, steps=360):
    bands = []
    width = 1000 / steps
    for index in range(steps):
        longitude = -180 + (index + 0.5) * 360 / steps
        sky = calculate_local_sky(campaign, world_minutes, longitude)
        bands.append(
            {
                "x": f"{index * width:.4f}",
                "width": f"{width + 0.05:.4f}",
                "star_opacity": f"{sky.star_intensity * 0.34:.4f}",
                "darkness_opacity": f"{sky.darkness * 0.975:.4f}",
                "ympha_opacity": f"{(1 - sky.star_intensity) * sky.ympha_visibility * 0.52:.4f}",
            }
        )
    return bands
