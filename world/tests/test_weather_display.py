from types import SimpleNamespace

from django.test import SimpleTestCase

from world.models import WeatherState
from world.services.weather_display import build_weather_summary


class WeatherDisplayTests(SimpleTestCase):
    def test_wind_has_units_plain_language_and_direction(self):
        weather = SimpleNamespace(
            wind_speed=12.7,
            wind_direction_degrees=225.0,
            pressure_hpa=1002.4,
            cloud_cover=0.72,
            precipitation=0.8,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V1,
        )

        summary = build_weather_summary(weather)

        self.assertIn("12.7 м/с", summary["wind"])
        self.assertIn("46 км/ч", summary["wind"])
        self.assertIn("сильный", summary["wind"])
        self.assertIn("ЮЗ", summary["wind"])
        self.assertEqual(summary["pressure"], "1002.4 гПа")
        self.assertEqual(summary["clouds"], "72% · облачно")
        self.assertIn("умеренные", summary["precipitation"])

    def test_zero_precipitation_is_explained_as_none(self):
        weather = SimpleNamespace(
            wind_speed=0,
            wind_direction_degrees=None,
            pressure_hpa=None,
            cloud_cover=None,
            precipitation=0,
            source=WeatherState.Source.LEGACY_V2,
        )

        summary = build_weather_summary(weather)

        self.assertIn("штиль", summary["wind"])
        self.assertEqual(summary["precipitation"], "нет")

    def test_c3_physical_precipitation_does_not_reinterpret_legacy_index(self):
        physical = SimpleNamespace(
            wind_speed=4,
            wind_direction_degrees=0,
            pressure_hpa=995,
            cloud_cover=0.9,
            precipitation=0.0,
            precipitation_rate_mm_h=8.25,
            precipitation_amount_mm=49.5,
            rain_fraction=1.0,
            snow_fraction=0.0,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V2,
        )
        legacy = SimpleNamespace(
            wind_speed=4,
            wind_direction_degrees=0,
            pressure_hpa=995,
            cloud_cover=0.9,
            precipitation=8.25,
            source=WeatherState.Source.ATMOSPHERIC_GRID_V1,
        )

        physical_summary = build_weather_summary(physical)
        legacy_summary = build_weather_summary(legacy)

        self.assertIn("8.25 мм/ч", physical_summary["precipitation"])
        self.assertIn("49.50 мм за шаг", physical_summary["precipitation"])
        self.assertNotIn("индекс", physical_summary["precipitation"])
        self.assertIn("индекс 8.25", legacy_summary["precipitation"])
