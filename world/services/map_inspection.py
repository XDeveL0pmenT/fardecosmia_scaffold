"""Read-only arbitrary-point inspection for the GM planetary atlas."""

from __future__ import annotations

from world.models import AtmosphericConfig, Region, WeatherState
from world.services.atmosphere.config import AtmosphericSettings
from world.services.atmosphere.microphysics import (
    fog_potential,
    rain_and_snow_fraction,
)
from world.services.atmosphere.persistence import (
    sample_campaign_environment_state_at,
)
from world.services.atmosphere.sampling import condition_from_cell
from world.services.atmosphere.thermodynamics import relative_humidity_percent
from world.services.map_geometry import normalize_longitude, validate_latitude
from world.services.region_climate import (
    climatological_humidity_at,
    region_climate_at,
)
from world.services.world_data import WorldData


def inspect_map_point(latitude, longitude, *, campaign=None):
    latitude = validate_latitude(latitude)
    longitude = normalize_longitude(longitude)
    if campaign is None:
        world_data = WorldData()
        surface = world_data.surface_at(latitude, longitude)
        biome = world_data.biome_at(latitude, longitude)
        biome_labels = dict(Region.Biome.choices)
        static_data = {
            "surface_type": surface.value,
            "surface_label": "Суша" if surface.value == "land" else "Океан",
            "elevation": world_data.elevation_at(latitude, longitude),
            "biome": biome or "",
            "biome_label": biome_labels.get(biome, "Не задан"),
            "biome_source": "global_atlas" if biome else "unknown",
            "base_temperature": world_data.mean_temperature_at(latitude, longitude),
            "humidity": climatological_humidity_at(
                latitude,
                longitude,
                world_data=world_data,
            ),
        }
    else:
        static_data = region_climate_at(campaign, latitude, longitude)

    payload = {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "static": {
            **static_data,
            "elevation": (
                None
                if static_data["elevation"] is None
                else round(float(static_data["elevation"]), 3)
            ),
            "base_temperature": round(float(static_data["base_temperature"]), 3),
            "humidity": round(float(static_data["humidity"]), 3),
        },
        "weather_available": False,
        "weather": None,
    }
    if campaign is None:
        return payload

    config = AtmosphericConfig.objects.filter(campaign=campaign, enabled=True).first()
    if config is None:
        return payload
    sampled = sample_campaign_environment_state_at(
        campaign,
        latitude,
        longitude,
        config=config,
    )
    if sampled is None:
        return payload

    point = sampled.point
    values = point.values
    settings = AtmosphericSettings.from_model(config, campaign)
    humidity = float(
        relative_humidity_percent(
            values["water_vapor_specific_humidity"],
            values["temperature"],
            values["pressure_hpa"],
            latent_heat_j_kg=settings.value("latent_heat_vaporization_j_kg"),
        )
    )
    humidity = max(0.0, min(200.0, humidity))
    rain_fraction, snow_fraction = rain_and_snow_fraction(
        values["temperature"],
        settings,
    )
    precipitation_rate_mm_h = max(0.0, values["precipitation_rate"]) * 3600.0
    fog_probability = float(
        fog_potential(
            values["water_vapor_specific_humidity"],
            values["cloud_condensate_specific_humidity"],
            values["temperature"],
            values["pressure_hpa"],
            point.wind_speed_m_s,
            point.elevation_m,
            settings,
        )
    )
    condition = condition_from_cell(
        values["temperature"],
        humidity,
        point.wind_speed_m_s,
        values["cloud_cover"],
        0.0,
        parameters=settings.parameters,
        precipitation_rate_mm_h=precipitation_rate_mm_h,
        snow_fraction=float(snow_fraction),
        fog_probability=fog_probability,
    )
    payload["weather_available"] = True
    payload["weather"] = {
        "snapshot_world_minutes": sampled.snapshot_world_minutes,
        "age_minutes": sampled.age_minutes,
        "solver_version": sampled.solver_version,
        "temperature_c": round(values["temperature"], 3),
        "relative_humidity_percent": round(humidity, 3),
        "surface_pressure_hpa": round(values["pressure_hpa"], 3),
        "circulation_pressure_hpa": round(
            values["circulation_pressure_hpa"],
            3,
        ),
        "wind_u_m_s": round(values["wind_u"], 3),
        "wind_v_m_s": round(values["wind_v"], 3),
        "wind_speed_m_s": round(point.wind_speed_m_s, 3),
        "wind_direction_degrees": (
            None
            if point.wind_direction_degrees is None
            else round(point.wind_direction_degrees, 3)
        ),
        "cloud_cover": round(values["cloud_cover"], 4),
        "precipitation_rate_mm_h": round(precipitation_rate_mm_h, 4),
        "rain_fraction": round(float(rain_fraction), 4),
        "snow_fraction": round(float(snow_fraction), 4),
        "condition": condition,
        "condition_label": dict(WeatherState.Condition.choices)[condition],
        "q_v_g_kg": round(values["water_vapor_specific_humidity"] * 1000.0, 4),
        "q_c_g_kg": round(values["cloud_condensate_specific_humidity"] * 1000.0, 4),
    }
    return payload
