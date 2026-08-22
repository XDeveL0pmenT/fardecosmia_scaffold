from types import SimpleNamespace

from django.test import SimpleTestCase

from world.models import WeatherState
from world.services.environment_summary import build_environment_summary


def weather(
    temperature,
    humidity,
    *,
    wind=0.0,
    direction=315.0,
    pressure=1000.0,
    cloud=0.0,
    condition=WeatherState.Condition.CLEAR,
    precipitation_rate=0.0,
    rain_fraction=1.0,
    snow_fraction=0.0,
):
    return SimpleNamespace(
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind,
        wind_direction_degrees=direction,
        pressure_hpa=pressure,
        cloud_cover=cloud,
        condition=condition,
        precipitation=0.0,
        precipitation_rate_mm_h=precipitation_rate,
        precipitation_amount_mm=precipitation_rate * 6.0,
        rain_fraction=rain_fraction,
        snow_fraction=snow_fraction,
    )


def sky(*, dark=False, light=False):
    return SimpleNamespace(
        star_intensity=0.0 if (dark or light) else 1.0,
        ympha_visibility=0.0 if dark else 0.8 if light else 0.0,
        season_light_code="mixed",
        local_moment=SimpleNamespace(season="Осень"),
    )


class EnvironmentSummaryTests(SimpleTestCase):
    def test_current_region_is_warm_clear_and_windy_not_lethal(self):
        summary = build_environment_summary(
            weather(23.6, 52, wind=12.3, pressure=970.7),
        )

        self.assertIn("Тепло", summary.headline)
        self.assertIn("ясно", summary.headline)
        self.assertIn("сильный ветер", summary.wind_label)
        self.assertLess(summary.overall_severity, 4)
        self.assertEqual(summary.pressure_label, "пониженное")
        self.assertIsNone(summary.oxygen_partial_pressure_hpa)
        self.assertNotIn("смерт", summary.short_description.lower())

    def test_extreme_humid_heat_is_severity_four(self):
        summary = build_environment_summary(weather(48, 90, wind=1.0))

        self.assertEqual(summary.overall_severity, 4)
        self.assertEqual(summary.headline, "Смертельно опасная жара")
        self.assertIn("насыщен", summary.short_description)
        self.assertIn("испарением", summary.short_description)

    def test_extreme_dry_heat_is_not_called_steam(self):
        summary = build_environment_summary(weather(60, 10, wind=1.0))

        self.assertEqual(summary.overall_severity, 4)
        self.assertEqual(summary.headline, "Смертельно опасная сухая жара")
        self.assertNotIn("пар", summary.short_description.lower())
        self.assertNotIn("пар", summary.humidity_label.lower())

    def test_cool_saturated_air_is_cold_and_damp_not_oppressive(self):
        summary = build_environment_summary(weather(8, 100, wind=1.0))

        self.assertIn("сыро", summary.headline)
        self.assertNotIn("духот", summary.headline.lower())
        self.assertNotIn("духот", summary.short_description.lower())

    def test_extreme_cold_and_wind_are_emphasized(self):
        summary = build_environment_summary(weather(-35, 60, wind=20.0))

        self.assertEqual(summary.overall_severity, 4)
        self.assertEqual(summary.headline, "Смертельно опасный холод")
        self.assertIn("ветер", summary.short_description.lower())
        self.assertIsNotNone(summary.wind_chill_c)

    def test_unknown_oxygen_never_creates_hypoxia_claim(self):
        summary = build_environment_summary(weather(20, 50, pressure=970.0))

        self.assertIsNone(summary.oxygen_partial_pressure_hpa)
        combined = " ".join(
            [summary.headline, summary.short_description]
            + [hazard.description for hazard in summary.hazards]
        ).lower()
        self.assertNotIn("кислород", combined)
        self.assertNotIn("гипокс", combined)

    def test_dark_and_light_night_use_existing_sky_state(self):
        dark_summary = build_environment_summary(weather(20, 50), sky=sky(dark=True))
        light_summary = build_environment_summary(weather(20, 50), sky=sky(light=True))

        self.assertEqual(dark_summary.magical_warnings[0].code, "NOCTIS_DARK_NIGHT")
        self.assertIn("Ноктис", dark_summary.magical_warnings[0].description)
        self.assertEqual(light_summary.magical_warnings[0].code, "YMPHA_LIGHT_NIGHT")
        self.assertIn("Ympha", light_summary.magical_warnings[0].description)
