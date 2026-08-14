"""Human-readable presentation helpers for stored weather snapshots.

The labels below explain technical values; they do not add physical laws or
canonical thresholds to Fardecosmia's simulation.
"""

from world.models import WeatherState


_COMPASS_POINTS = ("С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ")


def _wind_strength(speed_m_s):
    # Compact UI bands close to familiar terrestrial wording.  They describe
    # the number already produced by the solver and do not affect simulation.
    if speed_m_s < 0.5:
        return "штиль"
    if speed_m_s < 5.0:
        return "лёгкий"
    if speed_m_s < 10.0:
        return "умеренный"
    if speed_m_s < 17.0:
        return "сильный"
    if speed_m_s < 25.0:
        return "штормовой"
    if speed_m_s < 33.0:
        return "буря"
    return "ураганный"


def _compass_direction(degrees):
    if degrees is None:
        return None
    return _COMPASS_POINTS[round(float(degrees) / 45) % len(_COMPASS_POINTS)]


def _cloud_description(cloud_cover):
    if cloud_cover is None:
        return None
    percent = max(0, min(100, round(float(cloud_cover) * 100)))
    if percent < 15:
        label = "почти ясно"
    elif percent < 45:
        label = "переменная"
    elif percent < 75:
        label = "облачно"
    else:
        label = "плотная облачность"
    return f"{percent}% · {label}"


def _precipitation_description(weather):
    physical_rate = getattr(weather, "precipitation_rate_mm_h", None)
    if physical_rate is not None:
        rate = max(0.0, float(physical_rate))
        amount = max(0.0, float(getattr(weather, "precipitation_amount_mm", 0.0) or 0.0))
        snow_fraction = float(getattr(weather, "snow_fraction", 0.0) or 0.0)
        rain_fraction = float(getattr(weather, "rain_fraction", 1.0 - snow_fraction) or 0.0)
        if rate < 0.05:
            return "нет"
        if 0.35 <= snow_fraction <= 0.65:
            label = "мокрый снег / смешанные осадки"
        elif snow_fraction > rain_fraction:
            label = "слабый снег" if rate < 0.5 else "снег" if rate < 2.5 else "сильный снегопад"
        else:
            label = (
                "морось / следы"
                if rate < 0.5
                else "слабый дождь"
                if rate < 2.5
                else "умеренный дождь"
                if rate < 7.5
                else "сильный дождь / ливень"
                if rate < 30.0
                else "очень сильный ливень"
            )
        return f"{label} · {rate:.2f} мм/ч · {amount:.2f} мм за шаг"
    value = max(0.0, float(weather.precipitation))
    if value <= 0:
        return "нет"
    if weather.source == WeatherState.Source.ATMOSPHERIC_GRID_V1:
        if value < 0.15:
            label = "следы осадков"
        elif value < 0.6:
            label = "слабые"
        elif value < 1.5:
            label = "умеренные"
        else:
            label = "интенсивные"
    elif value < 2:
        label = "слабые"
    elif value < 8:
        label = "умеренные"
    else:
        label = "сильные"
    return f"{label} · индекс {value:.2f}"


def build_weather_summary(weather):
    if weather is None:
        return None
    speed = max(0.0, float(weather.wind_speed))
    compass = _compass_direction(weather.wind_direction_degrees)
    direction = ""
    if compass is not None:
        direction = f", откуда: {compass} ({weather.wind_direction_degrees:.0f}°)"
    wind = (
        f"{speed:.1f} м/с ({speed * 3.6:.0f} км/ч) · "
        f"{_wind_strength(speed)}{direction}"
    )
    pressure = (
        None
        if weather.pressure_hpa is None
        else f"{float(weather.pressure_hpa):.1f} гПа"
    )
    return {
        "wind": wind,
        "clouds": _cloud_description(weather.cloud_cover),
        "pressure": pressure,
        "precipitation": _precipitation_description(weather),
        "is_atmospheric": weather.source in {
            WeatherState.Source.ATMOSPHERIC_GRID_V1,
            WeatherState.Source.ATMOSPHERIC_GRID_V2,
            WeatherState.Source.ATMOSPHERIC_GRID_V3,
        },
        "has_physical_precipitation": getattr(
            weather, "precipitation_rate_mm_h", None
        ) is not None,
    }
