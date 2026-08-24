"""Shared, read-only ambient presentation for Region and Character pages."""

from __future__ import annotations

from dataclasses import dataclass
import math

from characters.services import get_effective_character_location
from world.atmosphere_defaults import default_atmospheric_parameters
from world.biomes import Biome
from world.models import AtmosphericConfig, WeatherState
from world.services.astronomy import calculate_local_sky
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.persistence import (
    sample_campaign_environment_state_at,
)
from world.services.atmosphere.sampling import interpret_point_weather
from world.services.environment_summary import temperature_presentation_band


SEASON_VISUAL_KEYS = {
    "Лето": "summer",
    "Осень": "autumn",
    "Зима": "winter",
    "Весна": "spring",
}
LIGHT_LEVELS = frozenset(
    {"dawn", "day", "bright", "sunset", "night", "deep-night", "predawn"}
)
WEATHER_CODES = frozenset(value for value, _label in WeatherState.Condition.choices)
BIOME_KEYS = frozenset(Biome.values)


def _unit(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class AmbientPresentation:
    """Player-safe cosmetic tokens derived from authoritative current state."""

    has_environment: bool
    location_available: bool
    light_level: str
    is_dark: bool
    star_light_strength: float
    darkness_strength: float
    ympha_light_strength: float
    ympha_tint_strength: float
    cloud_fraction: float
    precipitation_kind: str
    precipitation_intensity: float
    rain_intensity: float
    snow_intensity: float
    fog_or_haze_strength: float
    temperature_band: str
    biome_visual_key: str
    weather_code: str
    season_code: str
    turn_type_code: str
    season_light_code: str

    @property
    def css_classes(self):
        if not self.has_environment:
            return "ambient-scene--neutral"
        return " ".join(
            (
                "ambient-scene--active",
                f"ambient-scene--{self.light_level}",
                f"weather--{self.weather_code}",
                f"season--{self.season_code}",
                f"turn--{self.turn_type_code}",
                f"season-light--{self.season_light_code}",
                f"temperature--{self.temperature_band}",
                f"precipitation--{self.precipitation_kind}",
            )
        )

    @property
    def css_variables(self):
        warm_strength = (
            0.16
            if self.temperature_band == "extreme-hot"
            else 0.08
            if self.temperature_band == "hot"
            else 0.0
        )
        cold_strength = (
            0.15
            if self.temperature_band == "extreme-cold"
            else 0.08
            if self.temperature_band == "cold"
            else 0.0
        )
        cloud_opacity = (
            0.0
            if self.cloud_fraction <= 0.0
            else 0.12 + self.cloud_fraction * 0.78
        )
        rain_opacity = (
            0.0
            if self.rain_intensity <= 0.0
            else 0.22 + math.sqrt(self.rain_intensity) * 0.5
        )
        snow_opacity = (
            0.0
            if self.snow_intensity <= 0.0
            else 0.22 + math.sqrt(self.snow_intensity) * 0.54
        )
        values = {
            "star-opacity": 0.04 + self.star_light_strength * 0.96,
            "ympha-opacity": self.ympha_light_strength,
            "dark-opacity": self.darkness_strength * 0.99,
            "cloud-opacity": _unit(cloud_opacity),
            "rain-opacity": _unit(rain_opacity),
            "snow-opacity": _unit(snow_opacity),
            "fog-opacity": _unit(self.fog_or_haze_strength * 0.72),
            "warm-opacity": warm_strength,
            "cold-opacity": cold_strength,
        }
        return "".join(
            f"--ambient-{name}:{value:.4f};" for name, value in values.items()
        )


def neutral_ambience(*, location_available=False):
    return AmbientPresentation(
        has_environment=False,
        location_available=location_available,
        light_level="neutral",
        is_dark=False,
        star_light_strength=0.0,
        darkness_strength=0.0,
        ympha_light_strength=0.0,
        ympha_tint_strength=0.0,
        cloud_fraction=0.0,
        precipitation_kind="none",
        precipitation_intensity=0.0,
        rain_intensity=0.0,
        snow_intensity=0.0,
        fog_or_haze_strength=0.0,
        temperature_band="neutral",
        biome_visual_key="",
        weather_code=WeatherState.Condition.CLEAR,
        season_code="neutral",
        turn_type_code="neutral",
        season_light_code="neutral",
    )


def _precipitation_tokens(weather, parameters):
    condition = getattr(weather, "condition", WeatherState.Condition.CLEAR)
    rate = getattr(weather, "precipitation_rate_mm_h", None)
    snow_fraction = _unit(getattr(weather, "snow_fraction", 0.0))
    rain_fraction = _unit(getattr(weather, "rain_fraction", 1.0 - snow_fraction))
    if rate is None:
        if condition not in {
            WeatherState.Condition.RAIN,
            WeatherState.Condition.STORM,
            WeatherState.Condition.SNOW,
        }:
            return "none", 0.0, 0.0, 0.0
        intensity = _unit(float(getattr(weather, "precipitation", 0.0) or 0.0) / 8.0)
        intensity = max(0.55, intensity)
        if condition == WeatherState.Condition.SNOW:
            snow_fraction, rain_fraction = 1.0, 0.0
        elif snow_fraction <= 0.0:
            snow_fraction, rain_fraction = 0.0, 1.0
    else:
        rate = max(0.0, float(rate))
        threshold = max(
            0.0001,
            float(parameters["condition_precipitation_rate_mm_h"]),
        )
        if rate < threshold:
            return "none", 0.0, 0.0, 0.0
        strong_rate = max(
            threshold,
            float(parameters["condition_storm_precipitation_rate_mm_h"]),
        )
        intensity = _unit(rate / strong_rate)

    fraction_total = rain_fraction + snow_fraction
    if fraction_total > 0.0:
        rain_fraction /= fraction_total
        snow_fraction /= fraction_total
    if 0.35 <= snow_fraction <= 0.65:
        kind = "mixed"
    elif snow_fraction > rain_fraction:
        kind = "snow"
    else:
        kind = "rain"
    return (
        kind,
        intensity,
        _unit(intensity * rain_fraction),
        _unit(intensity * snow_fraction),
    )


def build_ambient_presentation(
    *,
    sky,
    weather,
    parameters=None,
    biome=None,
    location_available=True,
    allow_sky_only=False,
):
    """Normalize Region/Character weather and sky into one visual contract."""

    has_environment = sky is not None and (weather is not None or allow_sky_only)
    if not has_environment:
        return neutral_ambience(location_available=location_available)

    parameters = {**default_atmospheric_parameters(), **(parameters or {})}
    light_level = (
        sky.star_phase_code if sky.star_phase_code in LIGHT_LEVELS else "neutral"
    )
    condition = getattr(weather, "condition", WeatherState.Condition.CLEAR)
    weather_code = condition if condition in WEATHER_CODES else WeatherState.Condition.CLEAR
    cloud_fraction = _unit(getattr(weather, "cloud_cover", 0.0))
    precipitation = _precipitation_tokens(weather, parameters) if weather else (
        "none",
        0.0,
        0.0,
        0.0,
    )
    fog_strength = 1.0 if weather_code == WeatherState.Condition.FOG else 0.0
    temperature_band = (
        temperature_presentation_band(weather.temperature)
        if weather is not None
        else "neutral"
    )
    biome_key = str(biome or "")
    if biome_key not in BIOME_KEYS:
        biome_key = ""
    ympha_strength = _unit(
        (1.0 - float(sky.star_intensity)) * float(sky.ympha_visibility)
    )
    return AmbientPresentation(
        has_environment=True,
        location_available=location_available,
        light_level=light_level,
        is_dark=float(sky.star_intensity) <= 0.1,
        star_light_strength=_unit(sky.star_intensity),
        darkness_strength=_unit(sky.darkness),
        ympha_light_strength=ympha_strength,
        ympha_tint_strength=ympha_strength,
        cloud_fraction=cloud_fraction,
        precipitation_kind=precipitation[0],
        precipitation_intensity=precipitation[1],
        rain_intensity=precipitation[2],
        snow_intensity=precipitation[3],
        fog_or_haze_strength=fog_strength,
        temperature_band=temperature_band,
        biome_visual_key=biome_key,
        weather_code=weather_code,
        season_code=SEASON_VISUAL_KEYS.get(sky.local_moment.season, "neutral"),
        turn_type_code=sky.turn_type_code,
        season_light_code=sky.season_light_code,
    )


def build_region_ambience(weather, sky, *, parameters=None, biome=None):
    """Preserve Region sky behavior while using the shared token adapter."""

    return build_ambient_presentation(
        sky=sky,
        weather=weather,
        parameters=parameters,
        biome=biome,
        location_available=bool(sky and sky.location_known),
        allow_sky_only=True,
    )


def build_character_ambience(character, campaign):
    """Build ambience at the active Character's centrally resolved location."""

    location = get_effective_character_location(character)
    if location is None:
        return neutral_ambience(location_available=False)

    config = AtmosphericConfig.objects.filter(
        campaign=campaign,
        enabled=True,
    ).first()
    if config is None:
        return neutral_ambience(location_available=True)

    latitude = float(location.latitude)
    longitude = float(location.longitude)
    try:
        sampled = sample_campaign_environment_state_at(
            campaign,
            latitude,
            longitude,
            config=config,
        )
        if sampled is None:
            return neutral_ambience(location_available=True)
        settings = AtmosphericSettings.from_model(config, campaign)
        weather = interpret_point_weather(
            sampled.point,
            settings,
            parameters=settings.parameters,
        )
        sky = calculate_local_sky(
            campaign,
            campaign.world_minutes,
            longitude,
            latitude,
            location_known=True,
        )
        return build_ambient_presentation(
            sky=sky,
            weather=weather,
            parameters=settings.parameters,
            biome=sampled.point.biome,
            location_available=True,
        )
    except (LookupError, OSError, ValueError):
        return neutral_ambience(location_available=True)
