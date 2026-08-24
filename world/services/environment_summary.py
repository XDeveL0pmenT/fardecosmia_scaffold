"""Deterministic, localization-ready interpretation of one regional state.

This module never mutates atmosphere or stored weather.  Codes carry the
classification; Russian labels and sentence templates are presentation data.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from world.atmosphere_defaults import default_atmospheric_parameters
from world.biomes import Biome
from world.models import WeatherState
from world.services.atmosphere.thermodynamics import (
    saturation_vapor_pressure_pa,
    specific_humidity_from_relative_humidity,
    saturation_specific_humidity,
)


@dataclass(frozen=True)
class EnvironmentHazard:
    code: str
    severity: int
    title: str
    description: str


@dataclass(frozen=True)
class EnvironmentSummary:
    headline: str
    short_description: str
    thermal_label: str
    humidity_label: str
    wind_label: str
    precipitation_label: str
    pressure_label: str
    visibility_label: str
    apparent_temperature_c: float
    wet_bulb_temperature_c: float
    wind_chill_c: float | None
    hazards: tuple[EnvironmentHazard, ...]
    overall_severity: int
    magical_warnings: tuple[EnvironmentHazard, ...]
    heat_corruption_conditions: str
    oxygen_partial_pressure_hpa: float | None


WIND_LABELS = (
    (0.5, "WIND_CALM", "штиль"),
    (5.0, "WIND_LIGHT", "слабый ветер"),
    (10.0, "WIND_MODERATE", "умеренный ветер"),
    (17.0, "WIND_STRONG", "сильный ветер"),
    (25.0, "WIND_STORM", "очень сильный, штормовой ветер"),
    (33.0, "WIND_GALE", "буря"),
    (math.inf, "WIND_HURRICANE", "ураганный ветер"),
)
COMPASS_POINTS = ("С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ")


def _parameters(overrides):
    result = default_atmospheric_parameters()
    result.update(overrides or {})
    return result


def wet_bulb_temperature_c(temperature_c, relative_humidity, pressure_hpa):
    """Solve a bulk moist-enthalpy equality for wet-bulb temperature."""

    temperature = float(temperature_c)
    humidity = min(100.0, max(0.0, float(relative_humidity)))
    pressure = max(1.0, float(pressure_hpa))
    if humidity >= 99.999:
        return temperature
    cp = 1005.0
    latent_heat = 2_500_000.0
    q_actual = float(
        specific_humidity_from_relative_humidity(
            humidity,
            temperature,
            pressure,
            latent_heat_j_kg=latent_heat,
        )
    )
    target_enthalpy = cp * temperature + latent_heat * q_actual
    low = max(-120.0, temperature - 140.0)
    high = temperature
    for _iteration in range(60):
        midpoint = (low + high) * 0.5
        q_saturated = float(
            saturation_specific_humidity(
                midpoint,
                pressure,
                latent_heat_j_kg=latent_heat,
            )
        )
        saturated_enthalpy = cp * midpoint + latent_heat * q_saturated
        if saturated_enthalpy < target_enthalpy:
            low = midpoint
        else:
            high = midpoint
    return (low + high) * 0.5


def wind_chill_temperature_c(temperature_c, wind_speed_m_s):
    temperature = float(temperature_c)
    wind_km_h = max(0.0, float(wind_speed_m_s)) * 3.6
    if temperature > 10.0 or wind_km_h < 4.8:
        return None
    return (
        13.12
        + 0.6215 * temperature
        - 11.37 * wind_km_h**0.16
        + 0.3965 * temperature * wind_km_h**0.16
    )


def _compass(degrees):
    if degrees is None:
        return None
    return COMPASS_POINTS[round(float(degrees) / 45.0) % 8]


def _wind(speed, direction):
    for threshold, code, label in WIND_LABELS:
        if speed < threshold:
            compass = _compass(direction)
            phrase = label if compass is None else f"{label}, {compass}"
            return code, phrase
    raise AssertionError("unreachable")


def _thermal_state(temperature, wet_bulb):
    if temperature < -40:
        dry_label, dry_severity, dry_code = "экстремальный мороз", 4, "THERMAL_EXTREME_COLD"
    elif temperature < -25:
        dry_label, dry_severity, dry_code = "очень сильный мороз", 3, "THERMAL_SEVERE_COLD"
    elif temperature < -10:
        dry_label, dry_severity, dry_code = "сильный холод", 2, "THERMAL_COLD"
    elif temperature < 5:
        dry_label, dry_severity, dry_code = "холодно", 1, "THERMAL_COOL"
    elif temperature < 15:
        dry_label, dry_severity, dry_code = "прохладно", 0, "THERMAL_MILD_COOL"
    elif temperature < 27:
        dry_label, dry_severity, dry_code = "тепло", 0, "THERMAL_WARM"
    elif temperature < 35:
        dry_label, dry_severity, dry_code = "жарко", 1, "THERMAL_HOT"
    elif temperature < 45:
        dry_label, dry_severity, dry_code = "сильная жара", 2, "THERMAL_SEVERE_HEAT"
    elif temperature < 55:
        dry_label, dry_severity, dry_code = "экстремальная жара", 3, "THERMAL_EXTREME_HEAT"
    else:
        dry_label, dry_severity, dry_code = "смертельно опасная жара", 4, "THERMAL_LETHAL_HEAT"

    if wet_bulb > 33:
        humid_severity = 4
    elif wet_bulb >= 31:
        humid_severity = 4
    elif wet_bulb >= 28:
        humid_severity = 3
    elif wet_bulb >= 24:
        humid_severity = 2
    elif wet_bulb >= 18:
        humid_severity = 1
    else:
        humid_severity = 0
    return dry_code, dry_label, dry_severity, humid_severity


def temperature_presentation_band(temperature_c):
    """Return a stable cosmetic band from the existing thermal classifier.

    The band is presentation-only: it neither changes atmospheric values nor
    introduces a biome/season temperature correction.
    """

    thermal_code, _label, _severity, _humid_severity = _thermal_state(
        float(temperature_c),
        -273.15,
    )
    if thermal_code in {"THERMAL_EXTREME_COLD", "THERMAL_SEVERE_COLD"}:
        return "extreme-cold"
    if thermal_code in {"THERMAL_COLD", "THERMAL_COOL"}:
        return "cold"
    if thermal_code in {"THERMAL_HOT", "THERMAL_SEVERE_HEAT"}:
        return "hot"
    if thermal_code in {"THERMAL_EXTREME_HEAT", "THERMAL_LETHAL_HEAT"}:
        return "extreme-hot"
    return "temperate"


def _humidity_state(temperature, humidity, vapor_pressure_pa):
    if temperature >= 40 and humidity >= 85 and vapor_pressure_pa >= 7000:
        return "HUMIDITY_STEAM", "насыщенный горячим паром воздух"
    if temperature >= 28 and humidity >= 80:
        return "HUMIDITY_OPPRESSIVE", "душный воздух"
    if humidity >= 90:
        return "HUMIDITY_VERY_HIGH", "очень влажный воздух"
    if humidity >= 70:
        return "HUMIDITY_HIGH", "влажный воздух"
    if humidity >= 35:
        return "HUMIDITY_MODERATE", "умеренно влажный воздух"
    return "HUMIDITY_DRY", "сухой воздух"


def _cloud_label(cloud_cover):
    cloud = max(0.0, min(1.0, float(cloud_cover or 0.0)))
    if cloud < 0.1:
        return "ясно"
    if cloud < 0.3:
        return "почти ясно"
    if cloud < 0.6:
        return "переменная облачность"
    if cloud < 0.85:
        return "облачно"
    return "пасмурно, сплошная облачность"


def _precipitation_label(weather):
    rate = getattr(weather, "precipitation_rate_mm_h", None)
    if rate is None:
        if weather.condition == WeatherState.Condition.SNOW:
            return "снег"
        if weather.condition in {WeatherState.Condition.RAIN, WeatherState.Condition.STORM}:
            return "осадки (старая история без физических единиц)"
        return "без осадков"
    rate = max(0.0, float(rate))
    snow = float(getattr(weather, "snow_fraction", 0.0) or 0.0)
    rain = float(getattr(weather, "rain_fraction", 1.0 - snow) or 0.0)
    if rate < 0.05:
        return "без осадков"
    if 0.35 <= snow <= 0.65:
        return "мокрый снег, смешанные осадки"
    if snow > rain:
        if rate < 0.5:
            return "слабый снег"
        if rate < 2.5:
            return "снег"
        return "сильный снегопад"
    if rate < 0.5:
        return "морось или следы дождя"
    if rate < 2.5:
        return "слабый дождь"
    if rate < 7.5:
        return "умеренный дождь"
    if rate < 30:
        return "сильный дождь, ливень"
    return "очень сильный ливень"


def _pressure_label(pressure_hpa, reference):
    difference = float(pressure_hpa) - reference
    if difference < -120:
        return "очень низкое"
    if difference < -20:
        return "пониженное"
    if difference <= 20:
        return "обычное"
    if difference <= 120:
        return "повышенное"
    return "очень высокое"


def _visibility_label(weather, precipitation_label):
    if weather.condition == WeatherState.Condition.FOG:
        return "почти ничего не видно"
    rate = float(getattr(weather, "precipitation_rate_mm_h", 0.0) or 0.0)
    if rate > 30:
        return "очень плохая"
    if rate > 7.5:
        return "плохая"
    if rate > 0.5 or "снег" in precipitation_label:
        return "дымка"
    if float(weather.cloud_cover or 0.0) > 0.85:
        return "хорошая"
    return "отличная"


def build_environment_summary(
    weather,
    *,
    sky=None,
    biome=None,
    elevation_m=0.0,
    oxygen_fraction=None,
    parameters=None,
):
    if weather is None:
        return None
    values = _parameters(parameters)
    temperature = float(weather.temperature)
    humidity = max(0.0, min(100.0, float(weather.humidity)))
    pressure = float(weather.pressure_hpa or values["human_reference_pressure_hpa"])
    wind_speed = max(0.0, float(weather.wind_speed))
    wet_bulb = wet_bulb_temperature_c(temperature, humidity, pressure)
    wind_chill = wind_chill_temperature_c(temperature, wind_speed)
    vapor_pressure = float(saturation_vapor_pressure_pa(temperature)) * humidity / 100.0
    thermal_code, thermal_label, dry_severity, humid_severity = _thermal_state(
        temperature,
        wet_bulb,
    )
    if wind_chill is not None and wind_chill < -40.0:
        thermal_code = "THERMAL_EXTREME_COLD"
        thermal_label = "экстремальный мороз"
        dry_severity = 4
    humidity_code, humidity_label = _humidity_state(
        temperature,
        humidity,
        vapor_pressure,
    )
    wind_code, wind_label = _wind(wind_speed, weather.wind_direction_degrees)
    precipitation_label = _precipitation_label(weather)
    cloud_label = _cloud_label(weather.cloud_cover)
    pressure_label = _pressure_label(
        pressure,
        values["human_reference_pressure_hpa"],
    )
    visibility_label = _visibility_label(weather, precipitation_label)
    hazards = []
    thermal_severity = max(dry_severity, humid_severity)
    if thermal_severity:
        if temperature >= 27:
            title = (
                "Критическая жара"
                if thermal_severity >= 4
                else "Опасная жара"
                if thermal_severity >= 3
                else "Сильная жара"
                if thermal_severity >= 2
                else "Жара"
            )
            description = (
                "Горячий влажный воздух почти блокирует естественное охлаждение испарением."
                if humid_severity >= 4
                else "Жара и влажность заметно повышают тепловую нагрузку."
            )
            hazards.append(
                EnvironmentHazard(thermal_code, thermal_severity, title, description)
            )
        else:
            hazards.append(
                EnvironmentHazard(
                    thermal_code,
                    thermal_severity,
                    "Опасный холод" if thermal_severity >= 3 else "Холод",
                    "Ветер ускоряет потерю тепла." if wind_chill is not None else "Без утепления длительное пребывание опасно.",
                )
            )
    if humid_severity >= 2:
        hazards.append(
            EnvironmentHazard(
                humidity_code,
                humid_severity,
                "Удушающая духота" if humid_severity >= 3 else "Тяжёлая духота",
                "Причина — жара и высокая влажность, а не автоматически недостаток кислорода.",
            )
        )
    if wind_speed >= 10:
        wind_severity = 4 if wind_speed >= 33 else 3 if wind_speed >= 25 else 2 if wind_speed >= 17 else 1
        hazards.append(
            EnvironmentHazard(
                wind_code,
                wind_severity,
                "Ураганный ветер" if wind_severity == 4 else "Штормовой ветер" if wind_severity >= 3 else "Сильный ветер",
                f"Скорость ветра {wind_speed:.1f} м/с.",
            )
        )
    precipitation_rate = float(getattr(weather, "precipitation_rate_mm_h", 0.0) or 0.0)
    if precipitation_rate >= 7.5 or weather.condition == WeatherState.Condition.SNOW:
        precipitation_severity = 3 if precipitation_rate >= 30 else 2
        hazards.append(
            EnvironmentHazard(
                "PRECIP_HEAVY_SNOW" if "снег" in precipitation_label else "PRECIP_HEAVY_RAIN",
                precipitation_severity,
                "Сильный снегопад" if "снег" in precipitation_label else "Сильный ливень",
                "Осадки заметно ухудшают видимость и передвижение.",
            )
        )
    if weather.condition == WeatherState.Condition.FOG:
        hazards.append(
            EnvironmentHazard(
                "VISIBILITY_FOG",
                2,
                "Густой туман",
                "Ориентирование и дальняя видимость сильно затруднены.",
            )
        )

    magical = []
    if sky is not None and sky.star_intensity <= 0.1:
        if sky.ympha_visibility <= 0.2:
            magical.append(
                EnvironmentHazard(
                    "NOCTIS_DARK_NIGHT",
                    3,
                    "Тёмная ночь",
                    "Нет света Звезды и Ympha. Опасность Ноктиса повышена.",
                )
            )
        else:
            magical.append(
                EnvironmentHazard(
                    "YMPHA_LIGHT_NIGHT",
                    1,
                    "Светлая ночь Ympha",
                    "Ympha освещает ночь красным светом: Ноктис слабее, но ночь теплее обычного.",
                )
            )

    heat_corruption = "low"
    lowland = float(elevation_m or 0.0) <= values["heat_corruption_lowland_elevation_m"]
    light_summer = (
        sky is not None
        and sky.season_light_code == "light"
        and sky.local_moment.season == "Лето"
    )
    if temperature >= 35 and humidity >= 70 and lowland:
        heat_corruption = "highly_favorable" if wet_bulb >= 28 and light_summer else "favorable"
        magical.append(
            EnvironmentHazard(
                "HEAT_CORRUPTION_FAVORABLE",
                2 if heat_corruption == "highly_favorable" else 1,
                "Условия для Жарной Порчи",
                "Условия благоприятны для Жарной Порчи; это качественная оценка без вероятности заражения.",
            )
        )

    oxygen_partial_pressure = None
    if oxygen_fraction is not None:
        oxygen_partial_pressure = pressure * float(oxygen_fraction)

    if thermal_severity >= 4 and temperature >= 27:
        headline = (
            "Смертельно опасная сухая жара"
            if humidity < 30
            else "Смертельно опасная жара"
        )
        short_description = (
            "Воздух крайне горячий и насыщен влагой; естественное охлаждение испарением почти не работает. "
            "Длительное пребывание без защиты крайне опасно."
            if humid_severity >= 4
            else "Сухой воздух раскалён до экстремального уровня. Длительное пребывание без защиты крайне опасно."
        )
    elif thermal_severity >= 4:
        headline = "Смертельно опасный холод"
        short_description = "Открытая кожа быстро переохлаждается. Без утепления длительное пребывание крайне опасно."
        if wind_chill is not None:
            short_description += " Сильный ветер резко ускоряет потерю тепла."
    elif wind_speed >= 33:
        headline = "Ураганный ветер"
        short_description = f"{wind_label.capitalize()}; передвижение на открытой местности крайне опасно."
    elif precipitation_rate >= 30:
        headline = precipitation_label.capitalize()
        short_description = "Осадки резко ухудшают видимость и условия пути."
    elif weather.condition == WeatherState.Condition.FOG:
        headline = "Густой туман"
        short_description = "Воздух сырой, ориентирование и дальняя видимость сильно затруднены."
    elif temperature >= 27 and humid_severity >= 1:
        headline = f"{thermal_label.capitalize()} и душно"
        short_description = f"{humidity_label.capitalize()}. {wind_label.capitalize()} лишь частично облегчает тепловую нагрузку."
    elif temperature <= 8 and humidity >= 85:
        headline = f"{thermal_label.capitalize()} и сыро"
        short_description = f"{humidity_label.capitalize()}. {wind_label.capitalize()}."
    else:
        headline = f"{thermal_label.capitalize()} и {cloud_label}"
        short_description = f"{humidity_label.capitalize()}. {wind_label.capitalize()}."
        if precipitation_label != "без осадков":
            short_description += f" Сейчас: {precipitation_label}."

    # Biome contributes wording only when the measured state supports it.
    if biome == Biome.MISTY_MARSHES and humidity >= 85:
        short_description += " Топи наполнены тяжёлой сыростью."
    elif biome == Biome.RED_PLATEAUS and humidity < 35 and wind_speed >= 5:
        short_description += " Сухой ветер может нести пыль над плато."
    elif biome == Biome.MOUNTAINS and temperature <= 5 and wind_speed >= 5:
        short_description += " На высоте холод усиливается ветром."

    hazards.sort(key=lambda item: item.severity, reverse=True)
    overall = max([thermal_severity, *(item.severity for item in hazards)], default=0)
    apparent = wind_chill if wind_chill is not None else temperature + max(0.0, wet_bulb - 18.0) * 0.35
    return EnvironmentSummary(
        headline=headline,
        short_description=short_description,
        thermal_label=thermal_label,
        humidity_label=humidity_label,
        wind_label=wind_label,
        precipitation_label=precipitation_label,
        pressure_label=pressure_label,
        visibility_label=visibility_label,
        apparent_temperature_c=round(apparent, 1),
        wet_bulb_temperature_c=round(wet_bulb, 1),
        wind_chill_c=None if wind_chill is None else round(wind_chill, 1),
        hazards=tuple(hazards[:4]),
        overall_severity=overall,
        magical_warnings=tuple(magical),
        heat_corruption_conditions=heat_corruption,
        oxygen_partial_pressure_hpa=(
            None if oxygen_partial_pressure is None else round(oxygen_partial_pressure, 1)
        ),
    )
