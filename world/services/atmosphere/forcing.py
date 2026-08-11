"""Vectorized stellar and Ympha climate forcing for AtmosphericGrid."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Protocol

import numpy as np

from world.services.astronomy import STAR_INTENSITY_BY_PHASE
from world.services.calendar import PHASES_PER_TURN, TURNS_PER_FACE_CIRCLE
from world.services.orbital_climate import (
    ANNUAL_MEAN_STELLAR_FLUX_W_M2,
    CANONICAL_YEAR_MINUTES,
    PLANET_YMPHA_ECCENTRICITY,
    PLANET_YMPHA_ORBIT_PERIOD_MINUTES,
    PLANET_YMPHA_SEMI_MAJOR_AU,
    OrbitalClimateState,
    orbital_climate_state,
    solve_kepler,
)


class RadiativeForcingProvider(Protocol):
    is_zero: bool

    def temperature_adjustment_grid(self, geometry, world_minutes): ...


@dataclass(frozen=True)
class RadiativeForcingGrid:
    orbital_state: OrbitalClimateState
    stellar_direct_w_m2: np.ndarray
    stellar_flux_anomaly_w_m2: np.ndarray
    stellar_normalized_anomaly: np.ndarray
    stellar_temperature_anomaly_c: np.ndarray
    ympha_visibility_factor: np.ndarray
    ympha_distance_factor: float
    ympha_forcing_factor: np.ndarray
    ympha_temperature_anomaly_c: np.ndarray
    total_radiative_anomaly_c: np.ndarray
    solar_zenith_cosine: np.ndarray


@dataclass(frozen=True)
class OceanMacroForcingGrid:
    stellar_flux_anomaly_w_m2: np.ndarray
    ympha_temperature_anomaly_c: np.ndarray
    air_temperature_anomaly_c: np.ndarray


class ZeroRadiativeForcing:
    is_zero = True

    def temperature_adjustment(self, latitude, longitude, world_minutes):
        return 0.0

    def temperature_adjustment_grid(self, geometry, world_minutes):
        return np.zeros_like(geometry.latitude, dtype=np.float64)


def stellar_occlusion_factor(campaign, world_minutes, latitude, longitude):
    """Future eclipse hook; C1 deliberately creates no random occlusions."""
    del campaign, world_minutes, latitude, longitude
    return 1.0


def _wrapped_longitude_delta(longitude, reference):
    return (longitude - reference + 180.0) % 360.0 - 180.0


def _local_turn_progress(campaign, world_minutes, longitude):
    delta = _wrapped_longitude_delta(longitude, campaign.star_reference_longitude)
    return (
        world_minutes / campaign.calendar_minutes_per_turn
        - campaign.star_motion_direction * delta / 360.0
    ) % 1.0


def _local_hour_angle(campaign, world_minutes, longitude):
    progress = _local_turn_progress(campaign, world_minutes, longitude)
    angle = 2.0 * math.pi * (progress - 2.0 / PHASES_PER_TURN)
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _visual_star_intensity(campaign, world_minutes, longitude):
    scaled = _local_turn_progress(campaign, world_minutes, longitude) * PHASES_PER_TURN
    index = np.floor(scaled).astype(np.int64) % PHASES_PER_TURN
    fraction = scaled - np.floor(scaled)
    values = np.asarray(STAR_INTENSITY_BY_PHASE, dtype=np.float64)
    return values[index] * (1.0 - fraction) + values[(index + 1) % PHASES_PER_TURN] * fraction


def _ympha_visibility(campaign, world_minutes, longitude):
    delta = _wrapped_longitude_delta(
        longitude,
        campaign.ympha_peak_longitude_at_epoch,
    )
    local_face_progress = (
        TURNS_PER_FACE_CIRCLE / 2.0
        + world_minutes / campaign.calendar_minutes_per_turn
        - campaign.ympha_motion_direction
        * delta
        / 360.0
        * TURNS_PER_FACE_CIRCLE
    ) % TURNS_PER_FACE_CIRCLE
    visibility = 1.0 - np.abs(
        local_face_progress - TURNS_PER_FACE_CIRCLE / 2.0
    ) / (TURNS_PER_FACE_CIRCLE / 2.0)
    return np.clip(visibility, 0.0, 1.0)


def planet_ympha_distance_au(world_minutes):
    mean = 2.0 * math.pi * (
        (world_minutes % PLANET_YMPHA_ORBIT_PERIOD_MINUTES)
        / PLANET_YMPHA_ORBIT_PERIOD_MINUTES
    )
    eccentric = solve_kepler(mean, PLANET_YMPHA_ECCENTRICITY)
    return PLANET_YMPHA_SEMI_MAJOR_AU * (
        1.0 - PLANET_YMPHA_ECCENTRICITY * math.cos(eccentric)
    )


@lru_cache(maxsize=64)
def _annual_reference_for_latitudes(
    latitudes: tuple[float, ...],
    axial_tilt_deg: float,
    axial_phase_deg: float,
    samples: int = 720,
):
    """Annual/time mean direct-insolation ratio for each latitude.

    Subtracting this reference prevents the static mean-temperature map from
    receiving the world's mean stellar energy a second time.
    """
    latitude = np.radians(np.asarray(latitudes, dtype=np.float64))[:, None]
    total = np.zeros((len(latitudes), 1), dtype=np.float64)
    for sample in range(samples):
        # The mean is sampled uniformly in canonical time, not true anomaly.
        state = orbital_climate_state(
            (sample + 0.5) / samples * CANONICAL_YEAR_MINUTES,
            axial_tilt_deg=axial_tilt_deg,
            axial_phase_deg=axial_phase_deg,
        )
        declination = state.solar_declination_rad
        argument = -np.tan(latitude) * math.tan(declination)
        sunset_angle = np.where(
            argument <= -1.0,
            math.pi,
            np.where(argument >= 1.0, 0.0, np.arccos(np.clip(argument, -1.0, 1.0))),
        )
        daily_geometry = (
            sunset_angle * np.sin(latitude) * math.sin(declination)
            + np.cos(latitude) * math.cos(declination) * np.sin(sunset_angle)
        ) / math.pi
        total += state.flux_anomaly_ratio * np.maximum(0.0, daily_geometry)
    return tuple((total[:, 0] / samples).tolist())


def _daily_mean_geometry(latitude_rad, declination_rad):
    argument = -np.tan(latitude_rad) * math.tan(declination_rad)
    sunset_angle = np.where(
        argument <= -1.0,
        math.pi,
        np.where(
            argument >= 1.0,
            0.0,
            np.arccos(np.clip(argument, -1.0, 1.0)),
        ),
    )
    return np.maximum(
        0.0,
        (
            sunset_angle * np.sin(latitude_rad) * math.sin(declination_rad)
            + np.cos(latitude_rad)
            * math.cos(declination_rad)
            * np.sin(sunset_angle)
        )
        / math.pi,
    )


class CampaignSkyForcing:
    """C1 forcing adapter shared by initialization and every solver step."""

    def __init__(self, campaign, settings):
        self.campaign = campaign
        self.stellar_response_c = float(
            np.clip(settings.value("stellar_response_c"), -100.0, 100.0)
        )
        self.ympha_response_c = float(
            np.clip(settings.value("ympha_response_c"), 0.0, 10.0)
        )
        self.axial_tilt_deg = float(
            np.clip(settings.value("axial_tilt_deg"), -90.0, 90.0)
        )
        self.axial_phase_deg = settings.value("axial_phase_deg") % 360.0
        stellar_bounds = sorted(
            (
                float(
                    np.clip(settings.value("stellar_anomaly_min_c"), -100.0, 100.0)
                ),
                float(
                    np.clip(settings.value("stellar_anomaly_max_c"), -100.0, 100.0)
                ),
            )
        )
        total_bounds = sorted(
            (
                float(
                    np.clip(
                        settings.value("total_radiative_anomaly_min_c"),
                        -120.0,
                        120.0,
                    )
                ),
                float(
                    np.clip(
                        settings.value("total_radiative_anomaly_max_c"),
                        -120.0,
                        120.0,
                    )
                ),
            )
        )
        self.stellar_min_c, self.stellar_max_c = stellar_bounds
        self.ympha_max_c = float(
            np.clip(settings.value("ympha_anomaly_max_c"), 0.0, 20.0)
        )
        self.total_min_c, self.total_max_c = total_bounds
        self.is_zero = self.stellar_response_c == 0 and self.ympha_response_c == 0

    def _forcing_for_coordinates(self, latitude, longitude, world_minutes):
        latitude = np.asarray(latitude, dtype=np.float64).reshape(-1)
        longitude = np.asarray(longitude, dtype=np.float64).reshape(-1)
        state = orbital_climate_state(
            world_minutes,
            axial_tilt_deg=self.axial_tilt_deg,
            axial_phase_deg=self.axial_phase_deg,
        )
        latitude_rad = np.radians(latitude)
        hour_angle = _local_hour_angle(self.campaign, world_minutes, longitude)
        cos_zenith = (
            np.sin(latitude_rad) * math.sin(state.solar_declination_rad)
            + np.cos(latitude_rad)
            * math.cos(state.solar_declination_rad)
            * np.cos(hour_angle)
        )
        daylight_cosine = np.maximum(0.0, cos_zenith)
        occlusion = stellar_occlusion_factor(
            self.campaign,
            world_minutes,
            latitude,
            longitude,
        )
        direct = state.stellar_flux_w_m2 * daylight_cosine * np.asarray(
            occlusion,
            dtype=np.float64,
        )
        unique_latitudes, latitude_inverse = np.unique(latitude, return_inverse=True)
        reference_unique = np.asarray(
            _annual_reference_for_latitudes(
                tuple(float(value) for value in unique_latitudes),
                self.axial_tilt_deg,
                self.axial_phase_deg,
            ),
            dtype=np.float64,
        )
        reference = reference_unique[latitude_inverse]
        stellar_flux_anomaly = direct - reference * ANNUAL_MEAN_STELLAR_FLUX_W_M2
        normalized_anomaly = direct / ANNUAL_MEAN_STELLAR_FLUX_W_M2 - reference
        stellar_temperature = np.clip(
            self.stellar_response_c * normalized_anomaly,
            self.stellar_min_c,
            self.stellar_max_c,
        )

        visibility = _ympha_visibility(self.campaign, world_minutes, longitude)
        night_exposure = 1.0 - _visual_star_intensity(
            self.campaign,
            world_minutes,
            longitude,
        )
        distance = planet_ympha_distance_au(world_minutes)
        distance_factor = (PLANET_YMPHA_SEMI_MAJOR_AU / distance) ** 2
        ympha_factor = np.clip(visibility * night_exposure * distance_factor, 0.0, 2.0)
        ympha_temperature = np.clip(
            self.ympha_response_c * ympha_factor,
            0.0,
            self.ympha_max_c,
        )
        total = np.clip(
            stellar_temperature + ympha_temperature,
            self.total_min_c,
            self.total_max_c,
        )
        return RadiativeForcingGrid(
            orbital_state=state,
            stellar_direct_w_m2=direct,
            stellar_flux_anomaly_w_m2=stellar_flux_anomaly,
            stellar_normalized_anomaly=normalized_anomaly,
            stellar_temperature_anomaly_c=stellar_temperature,
            ympha_visibility_factor=visibility,
            ympha_distance_factor=distance_factor,
            ympha_forcing_factor=ympha_factor,
            ympha_temperature_anomaly_c=ympha_temperature,
            total_radiative_anomaly_c=total,
            solar_zenith_cosine=cos_zenith,
        )

    def ocean_macro_forcing_grid(
        self,
        geometry,
        world_minutes,
        interval_minutes,
        *,
        ympha_samples=7,
        legacy_rotation_mean=False,
    ):
        """Average the unchanged C1 forcing across one slow SST interval.

        A Fardecosmia light cycle lasts 168 hours, so an Earth-style 24-hour
        daily mean is not valid for one- to three-day ocean substeps.  Sampling
        the exact C1 field preserves longitude and the canonical rotation.
        """
        latitude = np.asarray(geometry.latitude, dtype=np.float64).reshape(-1)
        longitude = np.asarray(geometry.longitude, dtype=np.float64).reshape(-1)
        samples = max(1, int(ympha_samples))
        span = max(1.0, float(interval_minutes))
        sample_times = world_minutes + (
            (np.arange(samples, dtype=np.float64) + 0.5) / samples - 0.5
        ) * span
        if legacy_rotation_mean:
            state = orbital_climate_state(
                world_minutes,
                axial_tilt_deg=self.axial_tilt_deg,
                axial_phase_deg=self.axial_phase_deg,
            )
            unique_latitudes, latitude_inverse = np.unique(
                latitude,
                return_inverse=True,
            )
            latitude_rad = np.radians(unique_latitudes)
            direct_mean = state.stellar_flux_w_m2 * _daily_mean_geometry(
                latitude_rad,
                state.solar_declination_rad,
            )
            reference_unique = np.asarray(
                _annual_reference_for_latitudes(
                    tuple(float(value) for value in unique_latitudes),
                    self.axial_tilt_deg,
                    self.axial_phase_deg,
                ),
                dtype=np.float64,
            )
            stellar_anomaly = (
                direct_mean - reference_unique * ANNUAL_MEAN_STELLAR_FLUX_W_M2
            )[latitude_inverse]
            stellar_temperature = np.clip(
                self.stellar_response_c
                * (
                    direct_mean / ANNUAL_MEAN_STELLAR_FLUX_W_M2
                    - reference_unique
                )[latitude_inverse],
                self.stellar_min_c,
                self.stellar_max_c,
            )
            visibility = _ympha_visibility(
                self.campaign,
                sample_times[:, None],
                longitude[None, :],
            )
            night_exposure = 1.0 - _visual_star_intensity(
                self.campaign,
                sample_times[:, None],
                longitude[None, :],
            )
            distance_factor = np.asarray(
                [
                    (
                        PLANET_YMPHA_SEMI_MAJOR_AU
                        / planet_ympha_distance_au(sample_time)
                    )
                    ** 2
                    for sample_time in sample_times
                ],
                dtype=np.float64,
            )[:, None]
            ympha_temperature = np.clip(
                self.ympha_response_c
                * np.clip(visibility * night_exposure * distance_factor, 0.0, 2.0),
                0.0,
                self.ympha_max_c,
            )
            mean_ympha = np.mean(ympha_temperature, axis=0)
            return OceanMacroForcingGrid(
                stellar_flux_anomaly_w_m2=stellar_anomaly,
                ympha_temperature_anomaly_c=mean_ympha,
                air_temperature_anomaly_c=np.clip(
                    stellar_temperature + mean_ympha,
                    self.total_min_c,
                    self.total_max_c,
                ),
            )
        stellar_samples = []
        ympha_temperature_samples = []
        air_temperature_samples = []
        for sample_time in sample_times:
            sampled = self._forcing_for_coordinates(
                latitude,
                longitude,
                sample_time,
            )
            stellar_samples.append(sampled.stellar_flux_anomaly_w_m2)
            ympha_temperature_samples.append(sampled.ympha_temperature_anomaly_c)
            air_temperature_samples.append(sampled.total_radiative_anomaly_c)
        return OceanMacroForcingGrid(
            stellar_flux_anomaly_w_m2=np.mean(
                np.asarray(stellar_samples),
                axis=0,
            ),
            ympha_temperature_anomaly_c=np.mean(
                np.asarray(ympha_temperature_samples),
                axis=0,
            ),
            air_temperature_anomaly_c=np.mean(
                np.asarray(air_temperature_samples),
                axis=0,
            ),
        )

    def forcing_grid(self, geometry, world_minutes):
        return self._forcing_for_coordinates(
            geometry.latitude,
            geometry.longitude,
            world_minutes,
        )

    def temperature_adjustment_grid(self, geometry, world_minutes):
        if self.is_zero:
            return np.zeros_like(geometry.latitude, dtype=np.float64)
        return self.forcing_grid(geometry, world_minutes).total_radiative_anomaly_c

    def temperature_adjustment(self, latitude, longitude, world_minutes):
        if self.is_zero:
            return 0.0
        result = self._forcing_for_coordinates(
            np.asarray([latitude]),
            np.asarray([longitude]),
            world_minutes,
        )
        return float(result.total_radiative_anomaly_c[0])

    def diagnostics(self, latitude, longitude, world_minutes):
        result = self._forcing_for_coordinates(
            np.asarray([latitude]),
            np.asarray([longitude]),
            world_minutes,
        )
        cosine = float(np.clip(result.solar_zenith_cosine[0], -1.0, 1.0))
        return {
            "orbital_state": result.orbital_state,
            "solar_zenith_degrees": math.degrees(math.acos(cosine)),
            "stellar_direct_w_m2": float(result.stellar_direct_w_m2[0]),
            "stellar_flux_anomaly_w_m2": float(
                result.stellar_flux_anomaly_w_m2[0]
            ),
            "stellar_normalized_anomaly": float(
                result.stellar_normalized_anomaly[0]
            ),
            "stellar_temperature_anomaly_c": float(
                result.stellar_temperature_anomaly_c[0]
            ),
            "ympha_distance_factor": result.ympha_distance_factor,
            "ympha_forcing_factor": float(result.ympha_forcing_factor[0]),
            "ympha_temperature_anomaly_c": float(
                result.ympha_temperature_anomaly_c[0]
            ),
            "total_radiative_anomaly_c": float(
                result.total_radiative_anomaly_c[0]
            ),
        }
