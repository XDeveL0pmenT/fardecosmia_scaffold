"""Canonical annual orbit and deterministic astronomical climate state.

The climate year is deliberately normalized to the confirmed 364-day game
calendar.  Kepler's equation controls *where* the system is on its ellipse;
the unusual central mass is not used to derive a conflicting orbital period
or luminosity.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


MINUTES_PER_HOUR = 60
HOURS_PER_CALENDAR_DAY = 24
CALENDAR_DAYS_PER_YEAR = 364
CANONICAL_YEAR_MINUTES = (
    CALENDAR_DAYS_PER_YEAR * HOURS_PER_CALENDAR_DAY * MINUTES_PER_HOUR
)
ORBITAL_FORCING_VERSION = 1

EARTH_SOLAR_CONSTANT_W_M2 = 1361.0

CENTRAL_OBJECT_MASS_SOLAR = 1681.0
CENTRAL_OBJECT_RADIUS_SOLAR = 4.0
CENTRAL_OBJECT_SURFACE_TEMPERATURE_K = 12_621.0
CENTRAL_OBJECT_LUMINOSITY_SOLAR = 282.0
CENTRAL_OBJECT_DENSITY_G_CM3 = 37.1

STAR_ORBIT_PERICENTER_AU = 10.2
STAR_ORBIT_APOCENTER_AU = 14.2
STAR_ORBIT_SEMI_MAJOR_AU = (
    STAR_ORBIT_PERICENTER_AU + STAR_ORBIT_APOCENTER_AU
) / 2.0
STAR_ORBIT_ECCENTRICITY = (
    STAR_ORBIT_APOCENTER_AU - STAR_ORBIT_PERICENTER_AU
) / (STAR_ORBIT_APOCENTER_AU + STAR_ORBIT_PERICENTER_AU)

YMPHA_MASS_JUPITER = 78.4
YMPHA_RADIUS_JUPITER = 1.0
YMPHA_AVERAGE_TEMPERATURE_K = 2834.0
YMPHA_REPORTED_INFRARED_EMISSIVITY = 0.192

PLANET_YMPHA_ORBIT_PERIOD_MINUTES = round(7.05 * 24 * 60)
PLANET_YMPHA_SEMI_MAJOR_AU = 0.0300
PLANET_YMPHA_PERICENTER_AU = 0.0288
PLANET_YMPHA_APOCENTER_AU = 0.0313
PLANET_YMPHA_ECCENTRICITY = 0.0414

PHYSICAL_ROTATION_PERIOD_MINUTES = round(7.52 * 24 * 60)
AXIAL_TILT_DEG = 8.79
CANONICAL_TILT_DIRECTION_DEG = 109.0
SPIN_AXIS_LATITUDE_DEG = -73.2
SPIN_AXIS_LONGITUDE_DEG = 292.0

SEASON_CODES = ("summer", "autumn", "winter", "spring")
SEASON_LABELS = {
    "summer": "Лето",
    "autumn": "Осень",
    "winter": "Зима",
    "spring": "Весна",
}


def _normalize_radians(value: float) -> float:
    return value % (2.0 * math.pi)


def _eccentric_anomaly_from_true(true_anomaly_rad: float, eccentricity: float) -> float:
    return 2.0 * math.atan2(
        math.sqrt(1.0 - eccentricity) * math.sin(true_anomaly_rad / 2.0),
        math.sqrt(1.0 + eccentricity) * math.cos(true_anomaly_rad / 2.0),
    )


def _mean_anomaly_from_true(true_anomaly_rad: float, eccentricity: float) -> float:
    eccentric = _eccentric_anomaly_from_true(true_anomaly_rad, eccentricity)
    return eccentric - eccentricity * math.sin(eccentric)


def solve_kepler(
    mean_anomaly_rad: float,
    eccentricity: float,
    *,
    max_iterations: int = 12,
    tolerance: float = 1e-13,
) -> float:
    """Solve ``M = E - e sin(E)`` with a bounded deterministic iteration."""
    mean = _normalize_radians(mean_anomaly_rad)
    eccentric = mean if eccentricity < 0.8 else math.pi
    for _ in range(max_iterations):
        residual = eccentric - eccentricity * math.sin(eccentric) - mean
        derivative = 1.0 - eccentricity * math.cos(eccentric)
        delta = residual / derivative
        eccentric -= delta
        if abs(delta) <= tolerance:
            break
    return _normalize_radians(eccentric)


# Calendar year starts at true anomaly -45 degrees.  The unwrapped boundary
# means below make season lengths emerge from orbital geometry, not constants.
MEAN_ANOMALY_AT_EPOCH_RAD = _mean_anomaly_from_true(
    math.radians(-45.0),
    STAR_ORBIT_ECCENTRICITY,
)


def _unwrapped_mean_for_true_degrees(true_degrees: float) -> float:
    signed_degrees = ((true_degrees + 180.0) % 360.0) - 180.0
    mean = _mean_anomaly_from_true(
        math.radians(signed_degrees),
        STAR_ORBIT_ECCENTRICITY,
    )
    while mean < MEAN_ANOMALY_AT_EPOCH_RAD - 1e-12:
        mean += 2.0 * math.pi
    if true_degrees >= 315.0 and mean <= MEAN_ANOMALY_AT_EPOCH_RAD + 1e-12:
        mean += 2.0 * math.pi
    return mean


_SEASON_TRUE_BOUNDARIES_DEG = (-45.0, 45.0, 135.0, 225.0, 315.0)
_SEASON_MEAN_BOUNDARIES = tuple(
    _unwrapped_mean_for_true_degrees(value)
    for value in _SEASON_TRUE_BOUNDARIES_DEG
)
_SEASON_YEAR_FRACTIONS = tuple(
    (value - MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi)
    for value in _SEASON_MEAN_BOUNDARIES
)


def annual_mean_stellar_flux_w_m2() -> float:
    """Time-mean inverse-square flux over the canonical ellipse."""
    return (
        EARTH_SOLAR_CONSTANT_W_M2
        * CENTRAL_OBJECT_LUMINOSITY_SOLAR
        / (
            STAR_ORBIT_SEMI_MAJOR_AU**2
            * math.sqrt(1.0 - STAR_ORBIT_ECCENTRICITY**2)
        )
    )


ANNUAL_MEAN_STELLAR_FLUX_W_M2 = annual_mean_stellar_flux_w_m2()


@dataclass(frozen=True)
class OrbitalClimateState:
    world_minutes: int
    year_index: int
    year_fraction: float
    mean_anomaly_rad: float
    eccentric_anomaly_rad: float
    true_anomaly_rad: float
    star_distance_au: float
    stellar_flux_w_m2: float
    stellar_flux_earth_ratio: float
    annual_mean_flux_w_m2: float
    flux_anomaly_ratio: float
    global_season: str
    global_season_label: str
    season_progress: float
    season_start_world_minutes: float
    season_end_world_minutes: float
    season_duration_minutes: float
    solar_declination_rad: float

    @property
    def true_anomaly_degrees(self) -> float:
        return math.degrees(self.true_anomaly_rad) % 360.0

    @property
    def solar_declination_degrees(self) -> float:
        return math.degrees(self.solar_declination_rad)

    @property
    def season_duration_days(self) -> float:
        return self.season_duration_minutes / (24.0 * 60.0)

    @property
    def year_progress_percent(self) -> float:
        return self.year_fraction * 100.0

    @property
    def season_progress_percent(self) -> float:
        return self.season_progress * 100.0


def orbital_climate_state(
    world_minutes: int | float,
    *,
    axial_tilt_deg: float = AXIAL_TILT_DEG,
    axial_phase_deg: float = CANONICAL_TILT_DIRECTION_DEG,
) -> OrbitalClimateState:
    if isinstance(world_minutes, bool) or not math.isfinite(float(world_minutes)):
        raise ValueError("Игровое время орбиты должно быть конечным числом минут.")
    year_index, minute_of_year = divmod(float(world_minutes), CANONICAL_YEAR_MINUTES)
    year_index = int(year_index)
    year_fraction = minute_of_year / CANONICAL_YEAR_MINUTES
    unwrapped_mean = MEAN_ANOMALY_AT_EPOCH_RAD + 2.0 * math.pi * year_fraction
    mean = _normalize_radians(unwrapped_mean)
    eccentric = solve_kepler(mean, STAR_ORBIT_ECCENTRICITY)
    true = _normalize_radians(
        2.0
        * math.atan2(
            math.sqrt(1.0 + STAR_ORBIT_ECCENTRICITY)
            * math.sin(eccentric / 2.0),
            math.sqrt(1.0 - STAR_ORBIT_ECCENTRICITY)
            * math.cos(eccentric / 2.0),
        )
    )
    distance = STAR_ORBIT_SEMI_MAJOR_AU * (
        1.0 - STAR_ORBIT_ECCENTRICITY * math.cos(eccentric)
    )
    earth_ratio = CENTRAL_OBJECT_LUMINOSITY_SOLAR / distance**2
    stellar_flux = EARTH_SOLAR_CONSTANT_W_M2 * earth_ratio

    season_index = len(SEASON_CODES) - 1
    for index in range(len(SEASON_CODES)):
        if _SEASON_YEAR_FRACTIONS[index] <= year_fraction < _SEASON_YEAR_FRACTIONS[index + 1]:
            season_index = index
            break
    start_fraction = _SEASON_YEAR_FRACTIONS[season_index]
    end_fraction = _SEASON_YEAR_FRACTIONS[season_index + 1]
    season_progress = (year_fraction - start_fraction) / (end_fraction - start_fraction)
    year_start = year_index * CANONICAL_YEAR_MINUTES
    season_start = year_start + start_fraction * CANONICAL_YEAR_MINUTES
    season_end = year_start + end_fraction * CANONICAL_YEAR_MINUTES

    # Universe Sandbox's tilt-direction coordinate cannot yet be mapped more
    # precisely to the atlas.  This isolated axial phase is the documented,
    # configurable working mapping for C1; it does not invent precession.
    solar_declination = math.asin(
        math.sin(math.radians(axial_tilt_deg))
        * math.sin(true - math.radians(axial_phase_deg))
    )
    season = SEASON_CODES[season_index]
    return OrbitalClimateState(
        world_minutes=int(round(float(world_minutes))),
        year_index=year_index,
        year_fraction=year_fraction,
        mean_anomaly_rad=mean,
        eccentric_anomaly_rad=eccentric,
        true_anomaly_rad=true,
        star_distance_au=distance,
        stellar_flux_w_m2=stellar_flux,
        stellar_flux_earth_ratio=earth_ratio,
        annual_mean_flux_w_m2=ANNUAL_MEAN_STELLAR_FLUX_W_M2,
        flux_anomaly_ratio=stellar_flux / ANNUAL_MEAN_STELLAR_FLUX_W_M2,
        global_season=season,
        global_season_label=SEASON_LABELS[season],
        season_progress=max(0.0, min(1.0, season_progress)),
        season_start_world_minutes=season_start,
        season_end_world_minutes=season_end,
        season_duration_minutes=season_end - season_start,
        solar_declination_rad=solar_declination,
    )


def canonical_season_durations() -> dict[str, float]:
    return {
        code: (
            _SEASON_YEAR_FRACTIONS[index + 1] - _SEASON_YEAR_FRACTIONS[index]
        )
        * CANONICAL_YEAR_MINUTES
        for index, code in enumerate(SEASON_CODES)
    }


def canonical_orbital_fingerprint_data() -> dict:
    """Stable canonical inputs included in AtmosphericSnapshot branching."""
    return {
        "forcing_version": ORBITAL_FORCING_VERSION,
        "year_minutes": CANONICAL_YEAR_MINUTES,
        "earth_solar_constant_w_m2": EARTH_SOLAR_CONSTANT_W_M2,
        "star_luminosity_solar": CENTRAL_OBJECT_LUMINOSITY_SOLAR,
        "star_semi_major_au": STAR_ORBIT_SEMI_MAJOR_AU,
        "star_pericenter_au": STAR_ORBIT_PERICENTER_AU,
        "star_apocenter_au": STAR_ORBIT_APOCENTER_AU,
        "star_eccentricity": STAR_ORBIT_ECCENTRICITY,
        "mean_anomaly_at_epoch_rad": MEAN_ANOMALY_AT_EPOCH_RAD,
        "axial_tilt_deg": AXIAL_TILT_DEG,
        "tilt_direction_source_deg": CANONICAL_TILT_DIRECTION_DEG,
        "planet_ympha_period_minutes": PLANET_YMPHA_ORBIT_PERIOD_MINUTES,
        "planet_ympha_semi_major_au": PLANET_YMPHA_SEMI_MAJOR_AU,
        "planet_ympha_eccentricity": PLANET_YMPHA_ECCENTRICITY,
    }


def shift_orbital_seasons(world_minutes: int, seasons: int) -> int:
    """Move to the same fractional position in a later orbital season."""
    if seasons < 1:
        raise ValueError("Число сезонов должно быть положительным.")
    state = orbital_climate_state(world_minutes)
    current_index = SEASON_CODES.index(state.global_season)
    target_ordinal = state.year_index * len(SEASON_CODES) + current_index + seasons
    target_year, target_index = divmod(target_ordinal, len(SEASON_CODES))
    target_start = (
        target_year + _SEASON_YEAR_FRACTIONS[target_index]
    ) * CANONICAL_YEAR_MINUTES
    target_end = (
        target_year + _SEASON_YEAR_FRACTIONS[target_index + 1]
    ) * CANONICAL_YEAR_MINUTES
    target = target_start + state.season_progress * (target_end - target_start)
    return max(1, int(round(target - world_minutes)))


def astronomical_milestones_between(start: int, end: int) -> list[dict]:
    """Return deterministic season/periapsis/apoapsis events in ``(start, end]``."""
    if end <= start:
        return []
    first_year = math.floor(start / CANONICAL_YEAR_MINUTES) - 1
    last_year = math.floor(end / CANONICAL_YEAR_MINUTES) + 1
    peri_fraction = (-MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi)
    apo_fraction = (math.pi - MEAN_ANOMALY_AT_EPOCH_RAD) / (2.0 * math.pi)
    events = []
    for year in range(first_year, last_year + 1):
        for index, code in enumerate(SEASON_CODES):
            event_time = round(
                (year + _SEASON_YEAR_FRACTIONS[index]) * CANONICAL_YEAR_MINUTES
            )
            if start < event_time <= end:
                events.append(
                    {
                        "kind": "season_transition",
                        "world_minutes": event_time,
                        "season": code,
                        "title": f"Началось {SEASON_LABELS[code]}",
                    }
                )
        for kind, fraction, title in (
            ("periapsis", peri_fraction, "Система прошла перицентр"),
            ("apoapsis", apo_fraction, "Система прошла апоцентр"),
        ):
            event_time = round((year + fraction) * CANONICAL_YEAR_MINUTES)
            if start < event_time <= end:
                events.append(
                    {
                        "kind": kind,
                        "world_minutes": event_time,
                        "title": title,
                    }
                )
    events.sort(key=lambda event: (event["world_minutes"], event["kind"]))
    return events
