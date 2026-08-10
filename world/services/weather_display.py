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
    if speed_m_s < 3.4:
        return "лёгкий"
    if speed_m_s < 8.0:
        return "умеренный"
    if speed_m_s < 13.9:
        return "сильный"
    if speed_m_s < 20.8:
        return "штормовой"
    return "крайне сильный"


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
        "is_atmospheric": weather.source == WeatherState.Source.ATMOSPHERIC_GRID_V1,
    }
