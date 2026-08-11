import math
import random

from world.models import WeatherState
from world.services.astronomy import describe_region_sky
from world.services.calendar import (
    PHASES_PER_TURN,
)
from world.services.orbital_climate import orbital_climate_state


PRECIPITATION_CONDITIONS = {
    WeatherState.Condition.RAIN,
    WeatherState.Condition.SNOW,
    WeatherState.Condition.STORM,
}
NIGHT_EXPOSURE_BY_TURN_DAY = (0, 0, 0, 0.2, 0.8, 1, 0.5)
MAX_WEATHER_TRANSITIONS_PER_ADVANCE = 10_000
LEGACY_ORBITAL_FLUX_RESPONSE_SCALE = 0.42
SEASON_CODES = {
    "Лето": "summer",
    "Осень": "autumn",
    "Зима": "winter",
    "Весна": "spring",
}


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _season_weather_modifier(campaign, season, key):
    season_data = campaign.season_weather_modifiers.get(SEASON_CODES[season], {})
    raw_value = season_data.get(key, 0) if isinstance(season_data, dict) else 0
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return 0
    if key == "humidity":
        return clamp(float(raw_value), -50, 50)
    return clamp(float(raw_value), -1, 1)


def _target_temperature(region, world_minutes, rng):
    sky = describe_region_sky(region, world_minutes)
    moment = sky.local_moment

    orbital = orbital_climate_state(world_minutes)
    # Legacy weather keeps its configurable amplitude, but C1 drives it with
    # the physical inverse-square flux anomaly instead of a fixed 13-turn cosine.
    # The calibration divisor is technical and merely preserves a readable
    # meaning for existing Region.seasonal_amplitude values.
    seasonal_factor = clamp(
        (orbital.flux_anomaly_ratio - 1.0) / LEGACY_ORBITAL_FLUX_RESPONSE_SCALE,
        -1.5,
        1.5,
    )

    turn_progress = (moment.phase_of_turn - 1) + moment.phase_fraction
    # The confirmed light cycle peaks on day 3 and reaches its minimum near day 6.
    light_cycle_factor = math.cos(
        2 * math.pi * (turn_progress - 2.5) / PHASES_PER_TURN
    )
    night_exposure = NIGHT_EXPOSURE_BY_TURN_DAY[moment.phase_of_turn - 1]

    return (
        region.base_temperature
        + region.seasonal_amplitude * seasonal_factor
        + region.light_cycle_temperature_amplitude * light_cycle_factor
        + region.elevation_temperature_per_1000m * region.elevation / 1000
        + region.ympha_temperature_influence
        * sky.ympha_visibility
        * night_exposure
        + region.season_light_temperature_influence
        * (sky.season_ympha_visibility - 0.5)
        * 2
        + rng.gauss(0, 2 * region.weather_volatility)
    )


def _choose_condition(
    rng,
    temperature,
    humidity,
    previous,
    persistence,
    *,
    campaign,
    season,
    precipitation_bias,
):
    if previous and rng.random() < persistence * 0.68:
        previous_condition = previous.condition
        can_persist = {
            WeatherState.Condition.SNOW: temperature <= 1 and humidity >= 45,
            WeatherState.Condition.RAIN: temperature > 0 and humidity >= 45,
            WeatherState.Condition.STORM: temperature > 0 and humidity >= 60,
            WeatherState.Condition.FOG: humidity >= 65,
            WeatherState.Condition.CLOUDY: humidity >= 48,
            WeatherState.Condition.CLEAR: humidity < 82,
        }
        if can_persist.get(previous_condition, False):
            return previous_condition

    precipitation_chance = clamp((humidity - 52) / 55, 0, 0.82)
    precipitation_chance += _season_weather_modifier(
        campaign,
        season,
        "precipitation",
    )
    precipitation_chance += precipitation_bias * 0.35
    if previous and previous.condition in PRECIPITATION_CONDITIONS:
        precipitation_chance += 0.2 * persistence
    precipitation_chance = clamp(precipitation_chance, 0, 0.92)

    fog_chance = 0.18
    if season == "Осень":
        fog_chance += 0.14
    if humidity > 88 and rng.random() < fog_chance:
        return WeatherState.Condition.FOG
    if rng.random() < precipitation_chance:
        if temperature <= 0:
            return WeatherState.Condition.SNOW
        storm_chance = 0.22 + (0.12 if season == "Осень" else 0)
        if humidity > 86 and rng.random() < storm_chance:
            return WeatherState.Condition.STORM
        return WeatherState.Condition.RAIN
    if humidity > 63:
        return WeatherState.Condition.CLOUDY
    return WeatherState.Condition.CLEAR


def generate_weather(region, world_minutes, previous=None, *, use_history=True):
    """Create one immutable weather snapshot at a scheduled simulation boundary."""
    existing = region.weather_history.filter(world_minutes=world_minutes).first()
    if existing:
        return existing

    if previous is None and use_history:
        previous = (
            region.weather_history.filter(world_minutes__lt=world_minutes)
            .order_by("-world_minutes")
            .first()
        )

    rng = random.Random(f"weather-v2:{region.pk}:{world_minutes}")
    persistence = clamp(region.weather_persistence, 0, 1)
    temperature_target = _target_temperature(region, world_minutes, rng)
    sky = describe_region_sky(region, world_minutes)
    moment = sky.local_moment
    humidity_target = clamp(
        region.humidity
        + _season_weather_modifier(campaign=region.campaign, season=moment.season, key="humidity")
        + rng.gauss(0, 12 * region.weather_volatility),
        0,
        100,
    )
    wind_target = max(0, rng.gauss(10, 5 * region.weather_volatility))

    if previous:
        temperature = (
            previous.temperature * persistence
            + temperature_target * (1 - persistence)
        )
        humidity = previous.humidity * persistence + humidity_target * (1 - persistence)
        wind_speed = previous.wind_speed * persistence + wind_target * (1 - persistence)
    else:
        temperature = temperature_target
        humidity = humidity_target
        wind_speed = wind_target

    temperature = clamp(temperature, -150, 150)
    humidity = clamp(humidity, 0, 100)
    condition = _choose_condition(
        rng,
        temperature,
        humidity,
        previous,
        persistence,
        campaign=region.campaign,
        season=moment.season,
        precipitation_bias=region.precipitation_bias,
    )

    precipitation = 0
    if condition == WeatherState.Condition.RAIN:
        precipitation = rng.uniform(0.5, 8)
    elif condition == WeatherState.Condition.STORM:
        precipitation = rng.uniform(8, 25)
    elif condition == WeatherState.Condition.SNOW:
        precipitation = rng.uniform(0.5, 10)

    return WeatherState.objects.create(
        region=region,
        world_minutes=world_minutes,
        temperature=round(temperature, 1),
        humidity=round(humidity, 1),
        wind_speed=round(wind_speed, 1),
        precipitation=round(precipitation, 1),
        condition=condition,
    )


def update_weather_for_period(region, old_time, new_time, *, force_initialize=False):
    """Advance weather only across the region's fixed simulation boundaries."""
    if new_time < old_time:
        raise ValueError("Погоду нельзя прокручивать назад этим сервисом.")

    interval = region.weather_update_interval_minutes
    previous = None
    if not force_initialize:
        previous = (
            region.weather_history.filter(world_minutes__lte=old_time)
            .order_by("-world_minutes")
            .first()
        )
    generated = []

    if previous is None:
        initial_boundary = old_time - (old_time % interval)
        previous = generate_weather(
            region,
            initial_boundary,
            use_history=not force_initialize,
        )
        generated.append(previous)

    next_boundary = (old_time // interval + 1) * interval
    transition_count = max(0, (new_time - next_boundary) // interval + 1)
    if transition_count > MAX_WEATHER_TRANSITIONS_PER_ADVANCE:
        raise ValueError(
            "Шаг времени пересекает слишком много интервалов погоды. "
            "Увеличьте интервал региона или продвигайте мир меньшими шагами."
        )

    for boundary in range(next_boundary, new_time + 1, interval):
        previous = generate_weather(region, boundary, previous=previous)
        generated.append(previous)

    return generated
