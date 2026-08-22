from collections import defaultdict

from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber

from world.models import WeatherState
from world.services.astronomy import calculate_local_sky
from world.services.events import world_event_type_label
from world.services.orbital_climate import (
    astronomical_milestones_between,
    orbital_climate_state,
)


CONDITION_LABELS = dict(WeatherState.Condition.choices)
CONDITION_ORDER = [value for value, _label in WeatherState.Condition.choices]
PRECIPITATION = {
    WeatherState.Condition.RAIN,
    WeatherState.Condition.STORM,
    WeatherState.Condition.SNOW,
}
EPISODE_FAMILY = {
    WeatherState.Condition.CLEAR: "fair",
    WeatherState.Condition.CLOUDY: "fair",
    WeatherState.Condition.RAIN: "precipitation",
    WeatherState.Condition.STORM: "precipitation",
    WeatherState.Condition.SNOW: "snow",
    WeatherState.Condition.FOG: "fog",
}
NOTABLE_TEMPERATURE_RANGE_C = 10.0


def _precipitation_value(state):
    physical = getattr(state, "precipitation_rate_mm_h", None)
    return float(state.precipitation if physical is None else physical)


def _plural(value, forms):
    value = abs(int(value))
    if 11 <= value % 100 <= 14:
        return forms[2]
    if value % 10 == 1:
        return forms[0]
    if 2 <= value % 10 <= 4:
        return forms[1]
    return forms[2]


def format_requested_elapsed(amount, unit):
    forms = {
        "minutes": ("минута", "минуты", "минут"),
        "hours": ("час", "часа", "часов"),
        "phases": ("фаза Витка", "фазы Витка", "фаз Витка"),
        "turns": ("Виток", "Витка", "Витков"),
        "seasons": ("сезон", "сезона", "сезонов"),
        "years": ("год", "года", "лет"),
    }
    return f"{amount} {_plural(amount, forms[unit])}"


def dominant_condition(condition_minutes):
    if not condition_minutes:
        return None
    order = {condition: index for index, condition in enumerate(CONDITION_ORDER)}
    return max(
        condition_minutes,
        key=lambda condition: (condition_minutes[condition], -order.get(condition, 999)),
    )


def _latest_states_at(region_ids, world_minutes):
    if not region_ids:
        return {}
    states = (
        WeatherState.objects.filter(
            region_id__in=region_ids,
            world_minutes__lte=world_minutes,
        )
        .filter(
            Q(region_weather_revision=F("region__weather_geometry_revision"))
            | Q(
                region_weather_revision__isnull=True,
                region__weather_geometry_revision=0,
            )
        )
        .annotate(
            report_rank=Window(
                expression=RowNumber(),
                partition_by=[F("region_id")],
                order_by=F("world_minutes").desc(),
            )
        )
        .filter(report_rank=1)
    )
    return {state.region_id: state for state in states}


def _timeline(states, baseline, start, end):
    by_time = {}
    if baseline is not None:
        by_time[start] = baseline
    for state in states:
        if start <= state.world_minutes <= end:
            by_time[max(start, state.world_minutes)] = state
    points = sorted(by_time.items())
    segments = []
    for index, (segment_start, state) in enumerate(points):
        segment_end = points[index + 1][0] if index + 1 < len(points) else end
        if segment_end <= segment_start:
            continue
        segments.append(
            {
                "start": segment_start,
                "end": segment_end,
                "duration_minutes": segment_end - segment_start,
                "condition": state.condition,
                "temperature": float(state.temperature),
                "wind_speed": float(state.wind_speed),
                "precipitation": _precipitation_value(state),
                "state": state,
            }
        )
    samples = [state for _time, state in points]
    return segments, samples


def _merge_related_episodes(segments):
    episodes = []
    for segment in segments:
        family = EPISODE_FAMILY.get(segment["condition"], segment["condition"])
        if (
            episodes
            and episodes[-1]["kind"] == family
            and episodes[-1]["end"] == segment["start"]
        ):
            episode = episodes[-1]
            episode["end"] = segment["end"]
            episode["duration_minutes"] += segment["duration_minutes"]
            if segment["condition"] not in episode["conditions"]:
                episode["conditions"].append(segment["condition"])
            episode["minimum_temperature"] = min(
                episode["minimum_temperature"], segment["temperature"]
            )
            episode["maximum_temperature"] = max(
                episode["maximum_temperature"], segment["temperature"]
            )
            episode["maximum_wind_speed"] = max(
                episode["maximum_wind_speed"], segment["wind_speed"]
            )
            episode["peak_precipitation"] = max(
                episode["peak_precipitation"], segment["precipitation"]
            )
            continue
        episodes.append(
            {
                "kind": family,
                "start": segment["start"],
                "end": segment["end"],
                "duration_minutes": segment["duration_minutes"],
                "conditions": [segment["condition"]],
                "minimum_temperature": segment["temperature"],
                "maximum_temperature": segment["temperature"],
                "maximum_wind_speed": segment["wind_speed"],
                "peak_precipitation": segment["precipitation"],
            }
        )
    return episodes


def _periods(segments, conditions):
    periods = []
    current = None
    for segment in segments:
        if segment["condition"] not in conditions:
            current = None
            continue
        if current is not None and current["end"] == segment["start"]:
            current["end"] = segment["end"]
            current["duration_minutes"] += segment["duration_minutes"]
            current["peak_precipitation"] = max(
                current["peak_precipitation"], segment["precipitation"]
            )
            continue
        current = {
            "start": segment["start"],
            "end": segment["end"],
            "duration_minutes": segment["duration_minutes"],
            "peak_precipitation": segment["precipitation"],
        }
        periods.append(current)
    return periods


def _human_summary(dominant, shares, precipitation=None):
    if dominant is None:
        return "Недостаточно подробно рассчитанных состояний погоды."
    leading = {
        WeatherState.Condition.CLEAR: "Преимущественно ясно",
        WeatherState.Condition.CLOUDY: "Преимущественно облачно",
        WeatherState.Condition.RAIN: "Преимущественно дождливо",
        WeatherState.Condition.STORM: "Преобладают грозы",
        WeatherState.Condition.SNOW: "Преимущественно снежно",
        WeatherState.Condition.FOG: "Преимущественно туманно",
    }[dominant]
    secondary_phrases = {
        WeatherState.Condition.CLEAR: ("временами прояснения", "редкие прояснения"),
        WeatherState.Condition.CLOUDY: ("временами облачно", "редкая облачность"),
        WeatherState.Condition.RAIN: ("временами дожди", "редкие дожди"),
        WeatherState.Condition.STORM: ("временами грозы", "редкие грозы"),
        WeatherState.Condition.SNOW: ("временами снег", "редкий снег"),
        WeatherState.Condition.FOG: ("временами туманы", "редкие туманы"),
    }
    secondary = sorted(
        (
            (condition, percent)
            for condition, percent in shares.items()
            if condition != dominant
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:2]
    phrases = []
    for condition, percent in secondary:
        if percent <= 0:
            continue
        phrases.append(secondary_phrases[condition][0 if percent >= 15 else 1])
    summary = ", ".join([leading, *phrases]) + "."
    if precipitation is not None:
        amount = precipitation["integrated_amount_mm"]
        if amount > 0.0:
            summary += f" За рассчитанный период выпало {amount:.2f} мм осадков."
        else:
            summary += " За рассчитанный период осадки не зафиксированы."
    return summary


def _integrated_physical_precipitation(states, start, end):
    """Aggregate completed atmospheric steps, never the current-rate proxy.

    ``precipitation_rate_mm_h`` describes the instantaneous/final rate stored
    on a WeatherState. ``precipitation_amount_mm`` is the water-equivalent
    amount produced by the completed solver timestep ending at that state.
    TimeAdvanceReport therefore sums only the latter.
    """

    physical = [
        state
        for state in states
        if start < state.world_minutes <= end
        and state.precipitation_amount_mm is not None
    ]
    if not physical:
        return None
    amount = sum(max(0.0, float(state.precipitation_amount_mm)) for state in physical)
    rain_amount = sum(
        max(0.0, float(state.precipitation_amount_mm))
        * max(0.0, min(1.0, float(state.rain_fraction or 0.0)))
        for state in physical
    )
    snow_amount = sum(
        max(0.0, float(state.precipitation_amount_mm))
        * max(0.0, min(1.0, float(state.snow_fraction or 0.0)))
        for state in physical
    )
    maximum_rate = max(
        max(0.0, float(state.precipitation_rate_mm_h or 0.0))
        for state in physical
    )
    return {
        "integrated_amount_mm": round(amount, 4),
        "rain_amount_mm": round(rain_amount, 4),
        "snow_water_equivalent_mm": round(snow_amount, 4),
        "maximum_rate_mm_h": round(maximum_rate, 4),
        "sampled_steps": len(physical),
        "wet_steps": sum(
            1
            for state in physical
            if float(state.precipitation_amount_mm or 0.0) > 0.0
        ),
    }


def summarize_region_weather(region, states, baseline, start, end):
    segments, samples = _timeline(states, baseline, start, end)
    integrated_precipitation = _integrated_physical_precipitation(
        states,
        start,
        end,
    )
    condition_minutes = defaultdict(int)
    for segment in segments:
        condition_minutes[segment["condition"]] += segment["duration_minutes"]
    observed_minutes = sum(condition_minutes.values())
    dominant = dominant_condition(condition_minutes)
    shares = {
        condition: round(minutes * 100 / observed_minutes, 1)
        for condition, minutes in condition_minutes.items()
        if observed_minutes
    }
    weighted_temperature = sum(
        segment["temperature"] * segment["duration_minutes"] for segment in segments
    )
    temperatures = [float(state.temperature) for state in samples]
    winds = [float(state.wind_speed) for state in samples]
    minimum_temperature = min(temperatures) if temperatures else None
    maximum_temperature = max(temperatures) if temperatures else None
    average_temperature = (
        weighted_temperature / observed_minutes
        if observed_minutes
        else (sum(temperatures) / len(temperatures) if temperatures else None)
    )
    maximum_wind = max(winds) if winds else None
    episodes = _merge_related_episodes(segments)
    notable_episodes = []
    for episode in episodes:
        if episode["kind"] not in {"precipitation", "snow", "fog"}:
            continue
        if WeatherState.Condition.STORM in episode["conditions"]:
            title = "Грозовой эпизод"
            score = 100
        elif episode["kind"] == "snow":
            title = "Снегопад"
            score = 80
        elif episode["kind"] == "precipitation":
            title = "Период осадков"
            score = 60
        else:
            title = "Период тумана"
            score = 40
        notable_episodes.append(
            {
                **episode,
                "duration_hours": round(episode["duration_minutes"] / 60, 1),
                "title": title,
                "score": score + episode["duration_minutes"] / 60,
            }
        )

    temperature_extremes = []
    if (
        minimum_temperature is not None
        and maximum_temperature is not None
        and maximum_temperature - minimum_temperature >= NOTABLE_TEMPERATURE_RANGE_C
    ):
        min_state = min(samples, key=lambda state: state.temperature)
        max_state = max(samples, key=lambda state: state.temperature)
        temperature_extremes = [
            {
                "kind": "temperature_low",
                "title": "Заметное похолодание",
                "value": round(minimum_temperature, 1),
                "world_minutes": min_state.world_minutes,
                "score": 50 + maximum_temperature - minimum_temperature,
            },
            {
                "kind": "temperature_high",
                "title": "Заметное потепление",
                "value": round(maximum_temperature, 1),
                "world_minutes": max_state.world_minutes,
                "score": 50 + maximum_temperature - minimum_temperature,
            },
        ]

    return {
        "region_id": str(region.pk),
        "region_name": region.name,
        "summary": _human_summary(dominant, shares, integrated_precipitation),
        "dominant_condition": dominant,
        "dominant_condition_label": CONDITION_LABELS.get(dominant),
        "condition_shares": [
            {
                "condition": condition,
                "label": CONDITION_LABELS[condition],
                "percent": percent,
            }
            for condition, percent in sorted(
                shares.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "observed_minutes": observed_minutes,
        "temperature": {
            "minimum": (
                None if minimum_temperature is None else round(minimum_temperature, 1)
            ),
            "maximum": (
                None if maximum_temperature is None else round(maximum_temperature, 1)
            ),
            "average": (
                None if average_temperature is None else round(average_temperature, 1)
            ),
        },
        "maximum_wind_speed": None if maximum_wind is None else round(maximum_wind, 1),
        "periods": {
            "precipitation": _periods(segments, PRECIPITATION),
            "fog": _periods(segments, {WeatherState.Condition.FOG}),
            "snow": _periods(segments, {WeatherState.Condition.SNOW}),
            "storms": _periods(segments, {WeatherState.Condition.STORM}),
        },
        "integrated_precipitation": integrated_precipitation,
        "notable_episodes": [
            {key: value for key, value in episode.items() if key != "score"}
            for episode in notable_episodes
        ],
        "temperature_extremes": [
            {key: value for key, value in extreme.items() if key != "score"}
            for extreme in temperature_extremes
        ],
        "_highlights": notable_episodes + temperature_extremes,
    }


def _climate_summary(campaign, start, end):
    start_sky = calculate_local_sky(campaign, start, 0, location_known=True)
    end_sky = calculate_local_sky(campaign, end, 0, location_known=True)
    start_label = f"год {start_sky.local_moment.year}, {start_sky.season_label}"
    end_label = f"год {end_sky.local_moment.year}, {end_sky.season_label}"
    if start_label == end_label:
        text = f"Период остался в пределах: {start_label}."
    else:
        text = f"Период прошёл от «{start_label}» до «{end_label}»."
    start_orbit = orbital_climate_state(start)
    end_orbit = orbital_climate_state(end)
    forcing_change = (
        end_orbit.stellar_flux_w_m2 / start_orbit.stellar_flux_w_m2 - 1.0
    ) * 100.0
    milestones = astronomical_milestones_between(start, end)
    crossed_seasons = [
        event["season"]
        for event in milestones
        if event["kind"] == "season_transition"
    ]
    return {
        "start": start_label,
        "end": end_label,
        "text": text,
        "start_global_season": start_orbit.global_season,
        "end_global_season": end_orbit.global_season,
        "crossed_seasons": crossed_seasons,
        "stellar_flux_change_percent": round(forcing_change, 1),
    }


def build_time_advance_summary(
    campaign,
    regions,
    weather_states,
    world_events,
    *,
    start,
    end,
    amount,
    unit,
    simulation_mode,
    weather_coverage_start,
    atmospheric_summary=None,
):
    regions = list(regions)
    weather_states = list(weather_states)
    states_by_region = defaultdict(list)
    for state in weather_states:
        states_by_region[state.region_id].append(state)
    baselines = _latest_states_at(
        [region.pk for region in regions],
        weather_coverage_start,
    )
    regional = [
        summarize_region_weather(
            region,
            states_by_region[region.pk],
            baselines.get(region.pk),
            weather_coverage_start,
            end,
        )
        for region in regions
    ]
    highlights = []
    for item in regional:
        for highlight in item.pop("_highlights"):
            highlights.append(
                {
                    **highlight,
                    "region_id": item["region_id"],
                    "region_name": item["region_name"],
                }
            )
    highlights.sort(key=lambda item: item["score"], reverse=True)
    highlights = [
        {key: value for key, value in item.items() if key != "score"}
        for item in highlights[:10]
    ]

    regions_with_temperature = [
        item for item in regional if item["temperature"]["minimum"] is not None
    ]
    regions_with_wind = [
        item for item in regional if item["maximum_wind_speed"] is not None
    ]
    extremes = {
        "temperature_minimum": None,
        "temperature_maximum": None,
        "wind_maximum": None,
        "precipitation_maximum": None,
    }
    if regions_with_temperature:
        coldest = min(
            regions_with_temperature,
            key=lambda item: item["temperature"]["minimum"],
        )
        hottest = max(
            regions_with_temperature,
            key=lambda item: item["temperature"]["maximum"],
        )
        extremes["temperature_minimum"] = {
            "region_name": coldest["region_name"],
            "value": coldest["temperature"]["minimum"],
        }
        extremes["temperature_maximum"] = {
            "region_name": hottest["region_name"],
            "value": hottest["temperature"]["maximum"],
        }
    if regions_with_wind:
        windiest = max(regions_with_wind, key=lambda item: item["maximum_wind_speed"])
        extremes["wind_maximum"] = {
            "region_name": windiest["region_name"],
            "value": windiest["maximum_wind_speed"],
        }
    regions_with_precipitation = [
        item
        for item in regional
        if item["integrated_precipitation"] is not None
    ]
    if regions_with_precipitation:
        wettest = max(
            regions_with_precipitation,
            key=lambda item: item["integrated_precipitation"]["integrated_amount_mm"],
        )
        extremes["precipitation_maximum"] = {
            "region_name": wettest["region_name"],
            "value": wettest["integrated_precipitation"]["integrated_amount_mm"],
        }

    astronomical_events = astronomical_milestones_between(start, end)
    return {
        "elapsed_label": format_requested_elapsed(amount, unit),
        "global_highlights": highlights,
        "regional_weather": regional,
        "extremes": extremes,
        "world_events": [
            {
                # ``id`` and ``trigger_at`` remain for old report consumers;
                # P5 fields identify the immutable occurrence explicitly.
                "id": event.definition_id or event.pk,
                "occurrence_id": event.pk,
                "title": event.title,
                "trigger_at": event.occurred_world_minutes,
                "occurred_world_minutes": event.occurred_world_minutes,
                "event_type": event.event_type_snapshot,
                "type_label": world_event_type_label(event.event_type_snapshot),
                "location_label": event.region_label_snapshot or event.target_label,
                "region_name": event.region_label_snapshot or None,
            }
            for event in world_events
        ],
        "astronomical_events": astronomical_events,
        "climate_summary": _climate_summary(campaign, start, end),
        "ocean_summary": atmospheric_summary,
        "weather_scope": (
            "exact" if simulation_mode == "exact" else "final_spinup"
        ),
    }
