# PHASE C4.2 REPORT — Current Precipitation Persistence Audit

## Scope

C4.2 audited the existing exact precipitation lifecycle without changing
climate coefficients, cloud/fallout physics, random behavior, Region climate
parameters, fast-forward aggregation or snapshot format. C5, Leaflet, cyclone
entities, catastrophes and Travel were not started.

The repeatable read-only trace is:

```powershell
.\.venv\Scripts\python.exe scripts\audit_current_precipitation_c42.py CAMPAIGN_UUID
```

It advances the latest compatible grid by one 360-minute exact timestep only
in memory, chooses that step's wettest cell, serializes/deserializes the full
grid and samples the exact cell centre without creating a Region.

## 1. Root cause

The suspected lifecycle/persistence bug is **not present** in solver 7.
`precipitation_rate` is an explicit `AtmosphericGrid` field. Fallout writes the
surface mass flux to that field after removing the corresponding water from
`q_c`; serialization stores the field independently, and downstream samplers
read it directly. No stage reconstructs current precipitation from post-fallout
`q_c`.

The subsequent visual comparison did reveal a separate presentation diagnostic
bug: Region WeatherState used the documented bilinear coordinate sampler, while
the GM C4 panel used `coordinates_to_grid()` and displayed one nearest cell.
Both panels named their values as local Region values even though they were
sampling different spatial points. This fully explains the reported
`876.0 vs 1002.60 hPa` and `35.6% vs 22.5% RH` discrepancy.

A follow-up pressure-consistency audit found that the bilinear Region sampler
itself had a second, independent point-sampling bug. It interpolated the
already elevation-adjusted `pressure_hpa` of four cells while reporting the
nearest-cell Region elevation. Near a sharp raster transition this mixed air
pressure at `-15 m` with pressure at `6365 m`. The resulting `875.972 hPa` was
mathematically the old interpolation result, but it was not physically
compatible with the displayed local elevation. This was a sampling/diagnostic
error, not a pressure-solver or climate-coefficient error.

The reported «all current Regions are dry» observation has two measurable causes:

1. global rain at nearly every timestep does not imply rain at every fixed
   coordinate; and
2. the UI deliberately labels rates below the configurable visible-condition
   threshold `0.05 mm/h` as «без осадков», even though a tiny physical
   flux may be stored and included in integrated totals.

Real campaign evidence at the time of audit (`atmospheric_grid_v3` rows):

| Region | samples | physical rate > 0 | visible rate >= 0.05 | rain | snow | fog |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 | 3,298 | 0 | 0 | 0 | 0 | 0 |
| 16 | 3,298 | 120 | 96 | 96 | 0 | 24 |
| 17 (north, 81.995°) | 3,298 | 15 | 0 | 0 | 0 | 2,536 |
| 19 | 2,633 | 26 | 23 | 23 | 0 | 2 |
| 18 (south, -76.627°) | 3,298 | 24 | 7 | 0 | 7 | 69 |

Thus the frequent northern fog is real, while its 15 nonzero precipitation
samples were all below the visible threshold. At the same audit moment Region
16 was actively raining; its latest persisted current rate was `0.1939 mm/h`.

## 2. Exact wet-cell trace through every pipeline stage

Read-only trace from the real campaign, source snapshot minute 8,370,000 and
the next in-memory exact step at minute 8,370,360:

| stage/value | result |
| --- | ---: |
| grid size | 180×90 |
| wet cells in exact step | 2,290 |
| visible wet cells (`>=0.05 mm/h`) | 1,373 |
| selected cell | lat -73.0°, lon 23.0°, index 14,681 |
| pre-fallout `q_c` | 0.005725104 kg/kg |
| removed `q_c` | 0.003587350 kg/kg |
| post-fallout `q_c` | 0.002137754 kg/kg |
| raw microphysics precipitation | 3.866536310 mm/h |
| raw timestep amount | 23.199217860 mm |
| serialized snapshot round-trip | 3.866536379 mm/h |
| arbitrary-coordinate sampler | 3.866536310 mm/h |
| generated WeatherState | 3.8665 mm/h; 23.1992 mm |
| rain/snow fractions | 0.0 / 1.0 |
| condition | `snow` |
| environment summary | strong snowfall |

The tiny raw/round-trip difference is ordinary float32 representation, not
loss or recomputation. The whole exact step produced
`4.451307390183194e14 kg` of precipitation.

## 3. Was the diagnostic lost after fallout?

No. The operator lifecycle is:

1. `precipitation_fallout(q_c, ...)` computes `removed_q`;
2. it returns both `remaining q_c` and `rate_kg_m2_s`;
3. `simulate_step()` stores the remaining condensate in
   `cloud_condensate_specific_humidity`;
4. independently, it stores the diagnostic flux in `precipitation_rate`;
5. no later operation in the step overwrites that rate.

The trace proves partial condensate removal and a simultaneous nonzero current
rate. The mandatory inverse case also holds: zero `q_c` returns zero rate and
zero timestep amount.

## 4. AtmosphericSnapshot persistence behavior

Snapshot format 4 serializes all fourteen float32 grid fields in fixed order.
`precipitation_rate` is field 9 and is compressed into the same payload as
temperature, vapor and condensate. Solver-version/fingerprint checks prevent an
incompatible payload from being silently loaded.

Current precipitation representation by layer:

| value | AtmosphericGrid / Snapshot | WeatherState |
| --- | --- | --- |
| current rate | explicit `precipitation_rate`, kg m⁻² s⁻¹ | explicit `precipitation_rate_mm_h` |
| amount this step | exactly derived as `rate × step_seconds` | explicit `precipitation_amount_mm` |
| rain fraction | deterministically derived from current temperature | explicit `rain_fraction` |
| snow fraction | deterministically derived from current temperature | explicit `snow_fraction` |

Amount and phase do not need separate snapshot arrays because the compatible
snapshot fingerprint fixes the timestep/config and temperature is already
persisted. Most importantly, none of them is reconstructed from post-fallout
`q_c`.

## 5. Sampler behavior

`sample_environment_at()` bilinearly samples the explicit
`precipitation_rate` field like the other continuous fields. At an exact cell
centre, the read-only wettest-cell check returned
`3.866536310 mm/h`, identical to the in-memory raw value within float tolerance.

For point pressure, the corrected sampler bilinearly samples prognostic
`circulation_pressure_hpa`, temperature and water-vapor specific humidity,
then derives local `pressure_hpa` hydrostatically at the same continuous local
elevation. The old bilinear interpolation of already elevation-dependent
surface pressure is retained only as a GM diagnostic comparison value and is
never used for new WeatherState pressure or RH.

The C4.2 regression also runs a fresh reduced real-World-Data exact Vitok,
selects the wettest cell of the final step, serializes/deserializes it and
samples its exact latitude/longitude without creating a Region. The value stays
nonzero and numerically equal at all three stages.

## 6. WeatherState behavior

`_weather_from_grid_at_time()` reads `point.values["precipitation_rate"]`,
converts kg m⁻² s⁻¹ to mm/h with `×3600`, and stores:

- current rate in `precipitation_rate_mm_h`;
- exact completed-step water equivalent in `precipitation_amount_mm`;
- temperature-derived rain/snow fractions;
- a human condition based on the current rate and configured thresholds.

The legacy dimensionless `WeatherState.precipitation` remains zero for new
physical rows and is not consulted as the C4 source of truth.

An existing real Region at the latest audited snapshot demonstrated:

`snapshot sample 0.193896 mm/h → WeatherState 0.1939 mm/h → 1.1634 mm
for the six-hour step → condition rain`.

## 7. Region UI behavior

`region_detail` selects the latest WeatherState at or before campaign time. It
passes that same row to `build_weather_summary()` and
`build_environment_summary()`; neither reads `q_c` or the global grid.

The authenticated real Region page returned HTTP 200 and rendered:

`морось / следы · 0.19 мм/ч · 1.16 мм за шаг`.

The automated exact integration test additionally creates a Region exactly on
a wet final-step cell, persists its snapshot and WeatherState, builds the
environment summary and renders the full Region view. The rendered current
rate remains nonzero.

### Visual addendum: snapshot minute 8,368,560

The non-checkpoint snapshot had already been pruned after later advancement, so
the state was deterministically reconstructed from compatible checkpoint minute
8,366,400 through six exact steps. The reconstructed bilinear values reproduce
the persisted WeatherState exactly after its documented rounding:

| field | old nearest-cell diagnostics | Region bilinear sample | WeatherState/card |
| --- | ---: | ---: | ---: |
| temperature | 39.292°C | 38.135°C | 38.1°C |
| surface pressure | 1002.604 hPa | 875.972 hPa | 876.0 hPa |
| circulation pressure | 1000.942 hPa | 1000.745 hPa | not shown in weather card |
| `wind u/v` | -0.988 / -0.792 m/s | -0.798 / -1.429 m/s | speed 1.6 m/s, from 29.2° |
| `q_v` | 10.379 g/kg | 17.728 g/kg | converted to RH |
| RH | 22.461% | 35.592% | stored 35.6%, rendered 36% |
| `q_c` | ~0 | ~0 | cloud 0% |
| precipitation | 0 mm/h | 0 mm/h | none |

At that coordinate the bilinear point was grid `(96.2463, 32.2496)` and the
nearest discrete surface cell was index 5,856. The first discrepancy was
therefore nearest-neighbor versus bilinear spatial sampling. The follow-up
audit below shows why the old bilinear surface-pressure value was itself not a
valid local point pressure.

### Point-pressure consistency addendum

The same deterministically reconstructed minute `8,368,560` state has these
four atmospheric neighbours (`q_v` is shown in g/kg):

| cell/index | elevation | circulation pressure | surface pressure | T | q_v | bilinear weight | contribution to old pressure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `(96,32)` / 5,856 | -15 m | 1000.9423 hPa | 1002.6038 hPa | 39.2918°C | 10.3786 | 0.5655950 | 567.0677 hPa |
| `(97,32)` / 5,857 | -15 m | 1002.0308 hPa | 1003.6885 hPa | 40.8191°C | 8.0623 | 0.1848450 | 185.5268 hPa |
| `(96,33)` / 6,036 | 6365 m | 999.2202 hPa | 496.4622 hPa | 34.9802°C | 43.8706 | 0.1880895 | 93.3793 hPa |
| `(97,33)` / 6,037 | 6365 m | 999.7314 hPa | 488.0066 hPa | 29.0761°C | 34.4222 | 0.0614705 | 29.9980 hPa |

The old result is exactly:

```text
567.0677 + 185.5268 + 93.3793 + 29.9980 = 875.9718 hPa
```

It mixed two near-sea-level cell pressures with two 6365-m cell pressures.
The same weights produce the valid point primitives:

```text
Pc = 1000.745178 hPa
T  = 38.135185°C
qv = 0.017727893 kg/kg
```

For the Region's persisted local elevation `z = -15 m`, the unchanged C4
hydrostatic formula is:

```text
Tv = 314.651428 K
Ps = Pc × exp(-g × z / (Rd × Tv))
   = 1000.745178 × exp(0.001657428)
   = 1002.405216 hPa
```

The full-resolution World Data elevation audit sampled four authoritative
`360×180` raster cells with values `-15, 225, -15, -15 m` and weights
`0.0000065, 0.0008735, 0.0073625, 0.9917575`. Their continuous elevation is
`-14.790356 m`, which gives `1002.381996 hPa`. The existing Region row stores
the earlier rounded sample `-15 m`; both answers are physically consistent and
differ by only `0.023 hPa`.

World Data semantics after the audit are therefore:

- surface type and biome: nearest/discrete;
- elevation: bilinear over four valid authoritative raster/GM-correction
  samples;
- if any elevation neighbour is `UNKNOWN`, retain the nearest value rather
  than extrapolating land into ocean or the hidden source strip;
- atmosphere at an arbitrary point: bilinear `Pc/T/q/wind/...`, then derive
  surface pressure from that point's elevation.

### Field provenance used after the fix

| Region weather value | AtmosphericSnapshot | coordinate sampler | WeatherState | view/context | rendered value |
| --- | --- | --- | --- | --- | --- |
| temperature | `temperature` (°C) | bilinear `values["temperature"]` | `temperature`, rounded 0.1°C | `weather.temperature`; diagnostics `temperature_c` | card heading, 0.1°C |
| humidity | `water_vapor_specific_humidity`, `temperature`, `circulation_pressure_hpa` plus static elevation | `q/T/Pc` bilinear, local surface pressure hydrostatically derived, RH calculated from the coherent local T/q/P | `humidity`, rounded 0.1% | `weather.humidity`; diagnostics recompute RH from the same point values | weather card, whole percent; diagnostics, 0.1% |
| surface pressure | grid-cell `pressure_hpa` remains persisted for solver cells | output is re-derived from bilinear `Pc/T/q` and local continuous elevation; raw bilinear grid pressure is diagnostic only | `pressure_hpa`, rounded 0.1 hPa | `weather_summary.pressure`; diagnostics `surface_pressure_hpa` | weather 0.1 hPa; diagnostics 0.01 hPa |
| circulation pressure | `circulation_pressure_hpa` | bilinear continuous field | not stored in WeatherState | diagnostics only | diagnostics, 0.01 hPa |
| wind u/v | `wind_u`, `wind_v` | both bilinear | u/v not duplicated; converted to `wind_speed` and `wind_direction_degrees` | `weather_summary.wind`; diagnostics keep sampled u/v and speed | speed/direction card plus u/v diagnostics |
| cloud | `cloud_cover` | bilinear `values["cloud_cover"]` | `cloud_cover`, rounded 0.001 | `weather_summary.clouds`; diagnostics `cloud_cover_fraction` | percent/label plus raw diagnostic fraction |
| precipitation | `precipitation_rate` (kg m⁻² s⁻¹) | bilinear continuous flux | `precipitation_rate_mm_h`, `precipitation_amount_mm`, rain/snow fractions | `weather_summary.precipitation`, environment summary; diagnostics current flux | current mm/h and one-step mm |

Static surface type and biome intentionally remain values of the nearest
authored cell. Elevation is continuous. Every continuous atmospheric and
derived diagnostic now uses the same physically coherent Region point as
WeatherState.

## 8. Fix

No precipitation lifecycle bug was found, so solver physics, persistence,
WeatherState and climate coefficients remain unchanged. The separate GM-panel
bug was fixed in the read-only diagnostic path:

- `latest_atmospheric_cell_diagnostics()` now obtains the same
  `AtmosphericPointSample` as Region weather;
- `cell_ocean_diagnostics()` consumes that point for continuous snapshot
  fields and bilinearly samples derived circulation arrays at the same x/y;
- surface type and biome remain nearest-cell while elevation is continuous;
- point pressure is re-derived from interpolated `Pc/T/q` and local elevation;
- the Region sampler uses the Region's World Data/explicit GM elevation, while
  the Region-independent campaign sampler obtains elevation from World Data;
- the GM panel exposes local elevation, nearest atmospheric-cell elevation and
  the rejected old pressure interpolation side by side;
- the GM template states this sampling rule and now shows sampled temperature,
  wind speed and cloud fraction alongside pressure/RH/u/v/precipitation;
- the obsolete hardcoded «solver v6» empty-state text was made version-neutral.

Changing physics or turning an integrated amount into current rain would have
introduced the bug the phase explicitly forbids and was not done.

C4.2 instead adds two durable safeguards:

- `scripts/audit_current_precipitation_c42.py`, a read-only real-campaign
  exact-step trace;
- `world/tests/test_atmosphere_c42.py`, regression coverage across fallout,
  serialization, arbitrary-coordinate sampling, WeatherState, summaries and
  rendered HTML.

This is the smallest valid correction to the previous coverage gap: the C4.1
test constructed a wet grid manually and therefore did not prove that a real
exact `simulate_step()` diagnostic survived snapshot serialization.

## 9. Tests

Added eight tests:

1. positive `q_c` partially falls out while the independently stored current
   precipitation rate remains nonzero after payload round-trip;
2. `q_c = 0` produces zero rate and zero amount;
3. the final wettest cell of a real exact reduced-grid Vitok survives
   grid→payload→arbitrary-coordinate sampling without a Region;
4. real exact precipitation survives snapshot→sampler→WeatherState→
   environment/weather summaries→authenticated Region HTML;
5. deliberately different nearest and bilinear cells prove that GM diagnostics,
   WeatherState, view context and rendered HTML all use the bilinear Region
   sample for temperature, RH, both pressure fields, u/v, speed, clouds and
   precipitation;
6. a synthetic `0↔6000 m` cliff proves that point pressure is re-derived at an
   explicit local `-15 m` rather than interpolated between grid-cell pressures;
7. the no-ORM sampler fallback first interpolates elevation and then applies
   the same hydrostatic formula;
8. authoritative World Data elevation is bilinear between four valid raster
   cell centres while surface type remains discrete.

The initial focused C4.1+C4.2 run passed 9/9 tests. The final point-sampling
focused run passed 31/31 tests, and the final project run passed
**185/185 tests** in 34.249 seconds. `manage.py check` reported no issues,
`makemigrations --check --dry-run` reported `No changes detected`, and
`git diff --check` found no whitespace errors (only the repository's existing
Windows line-ending warnings).

## 10. Exact/current precipitation demonstration

The exact diagnostic and fast-forward aggregate retain different semantics:

- snapshot/Region current weather: the rate from the latest completed exact
  360-minute atmospheric step;
- `WeatherState.precipitation_amount_mm`: that one completed step only;
- exact TimeAdvanceReport: sum of actual sampled timestep amounts in coverage;
- fast-forward TimeAdvanceReport: accumulated macro precipitation plus detailed
  WeatherState only for final exact spin-up coverage;
- cumulative interval precipitation is never displayed as «дождь сейчас».

At the audited wettest exact cell, current snow was `3.8665 mm/h` and the
six-hour amount was `23.1992 mm`. At real Region 16, current rain was
`0.1939 mm/h` and its six-hour amount was `1.1634 mm`. Both are current-step
diagnostics, not seasonal accumulation.

## 11. No physics/random change and scope stop

Confirmed:

- no climate coefficient changed;
- no precipitation threshold changed;
- no random rain chance was added;
- no biome/Region rain bonus was added;
- no legacy precipitation bias was restored;
- no cumulative value was reused as current rain;
- fast-forward aggregate semantics were left unchanged;
- C5, Leaflet/Core and every later roadmap phase were not started.
