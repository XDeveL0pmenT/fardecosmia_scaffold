from dataclasses import dataclass
from typing import Protocol

from world.services.astronomy import calculate_local_sky


CONFIRMED_ORBITAL_DISTANCE_SPAN_AU = 5.0


class RadiativeForcingProvider(Protocol):
    def temperature_adjustment(self, latitude, longitude, world_minutes): ...


class ZeroRadiativeForcing:
    def temperature_adjustment(self, latitude, longitude, world_minutes):
        return 0.0


class CampaignSkyForcing:
    """Adapter to the established local-sky model with configurable heat gains."""

    def __init__(self, campaign, settings):
        self.campaign = campaign
        self.star_heating = settings.value("star_heating_c")
        self.ympha_heating = settings.value("ympha_heating_c")
        self.is_zero = self.star_heating == 0 and self.ympha_heating == 0

    def temperature_adjustment(self, latitude, longitude, world_minutes):
        # The default prototype deliberately asserts no unknown canonical heat
        # contribution. Avoid thousands of full sky/calendar calculations per
        # atmospheric step when both configurable hooks are disabled.
        if self.is_zero:
            return 0.0
        sky = calculate_local_sky(
            self.campaign,
            world_minutes,
            longitude,
            latitude,
        )
        return (
            sky.star_intensity * self.star_heating
            + sky.effective_night_visibility_percent / 100.0 * self.ympha_heating
        )


class OrbitalDistanceProvider(Protocol):
    """Future hook: absolute orbital scale/period remain configurable."""

    def distance_au(self, world_minutes): ...


@dataclass(frozen=True)
class ConfigurableOrbit:
    """Prototype orbit with configurable absolute scale and confirmed 5 AU span."""

    periapsis_au: float
    period_minutes: int
    phase_at_epoch: float = 0.0

    def __post_init__(self):
        if self.periapsis_au <= 0:
            raise ValueError("Абсолютную ближнюю границу орбиты нужно задать явно.")
        if self.period_minutes <= 0:
            raise ValueError("Период орбиты должен быть задан положительным числом минут.")

    @property
    def apoapsis_au(self):
        return self.periapsis_au + CONFIRMED_ORBITAL_DISTANCE_SPAN_AU

    def distance_au(self, world_minutes):
        import math

        progress = (world_minutes / self.period_minutes + self.phase_at_epoch) % 1.0
        blend = (1.0 - math.cos(2.0 * math.pi * progress)) / 2.0
        return self.periapsis_au + (self.apoapsis_au - self.periapsis_au) * blend
