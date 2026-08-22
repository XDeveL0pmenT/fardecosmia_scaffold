# Fardecosmia Phase C3.5 Implementation Report

Phase C4 was not started.

## A. Fast-forward

### 1. Profiler before

The required pre-change trace is stored in `docs/ATMOSPHERE_PHASE_C35_BEFORE.prof`.
It contains a full C3 reduced-grid run plus season/year fast-forward comparisons.
The two fast-forward calls spent 3.205 s cumulative in
`advance_ocean_fast_forward`; the largest shared costs were saturation
adjustment, saturation vapor pressure/specific humidity, C1 forcing, pressure,
wind and precipitation fallout.

### 2. Bottlenecks

- Newton saturation adjustment evaluated every originally active cell again on
  every iteration, including cells that had already converged.
- Full-grid saturation diagnostics were evaluated for cloud evaporation even
  where no cloud water existed.
- Fallout built air-column, cell-area and phase arrays for non-precipitating
  cells.
- Cell areas were allocated repeatedly although grid geometry is immutable.
- C1 forcing repeatedly rebuilt latitude trigonometry and annual-reference
  arrays for the same geometry.

### 3. Optimizations

- Condensation, cloud evaporation and precipitation use explicit vector masks.
- Newton iterations now operate only on unresolved cells.
- Air-column mass and cell-area arrays are shared inside a solver step.
- Cell areas are part of cached `GridGeometry`.
- Rain/snow phase arrays are skipped in the boundary solver where their return
  value is not consumed. Physical fallout mass is unchanged.
- `CampaignSkyForcing` caches geometry-only latitude/reference terms.
- No coefficient in condensation, latent heat, evaporation, precipitation,
  pressure, wind or C1 orbit was changed.

### 4. Active-cell strategy

The focused benchmark reports the following year-run fractions:

- saturation adjustment: 0.749020 of seen cells;
- cloud evaporation candidates: 0.215931;
- precipitation fallout: 0.710890.

Inactive cells bypass the corresponding expensive work. Within saturation
adjustment, already-converged cells also leave subsequent Newton iterations.

### 5. Thermodynamic reuse/cache

`GridGeometry.cell_areas_m2` is immutable and cached with the rest of grid
geometry. A step computes pressure-dependent air-column mass once for
saturation diagnostics/condensation rates and once after the pressure update
for fallout, preserving the original pressure ordering. The boundary loop
passes these arrays to microphysics instead of rebuilding them.

### 6. Adaptive timestep tests

A 12-hour boundary step was tested and rejected. Although it halved the macro
steps, it changed the result too much:

| 12-hour probe | Season | Year |
|---|---:|---:|
| SST MAE | 1.581225°C | 3.077708°C |
| SST maximum error | 20.266441°C | 33.362427°C |
| precipitation mass error | 17.6315% | 18.5920% |

The production default remains the accurate 360-minute boundary substep.

### 7. Performance before/after

Comparable unprofiled reduced-boundary measurements:

| Interval | Phase C3 baseline | Phase C3.5 clean run |
|---|---:|---:|
| Season | 1.142 s | 0.482 s |
| Year | 2.947 s | 1.911 s |

The development machine showed substantial transient contention in repeated
later runs: focused year samples ranged from 2.072 s to 4.704 s. The focused
benchmark records min/median/max rather than hiding this variance. The clean
single-run comparison meets the 2.0–2.2 s desired target; even under contention
the implementation performs the same number of physical steps and produces an
identical payload. The final validation run under the same contention measured
1.246 s for a season and 4.949 s for a year; it retained all accuracy figures
below. Wall-time conclusions should therefore use repeated quiet-machine runs,
not one loaded sample.

The reusable focused benchmark is
`scripts/benchmark_atmosphere_c35.py`. The after trace is
`docs/ATMOSPHERE_PHASE_C35_AFTER.prof`.

### 8. Accuracy before/after

Physical accuracy is unchanged:

| Interval | SST MAE | maximum SST error |
|---|---:|---:|
| Season | 0.145860°C | 1.526943°C |
| Year | 0.143172°C | 1.790962°C |

Air temperature, q_v, q_c, wind and SST payload values in the C3 regression
remain unchanged. Diagnostic saturation-cap counts are lower because inactive
cells are no longer evaluated merely for bookkeeping.

### 9. Precipitation mass error

- Season: 0.4342%.
- Year: 0.0740%.

Both remain below 1%. There is still no precipitation without condensate.

### 10. Determinism

Repeated exact and fast-forward runs serialize to identical payloads for equal
inputs. The focused benchmark checks determinism for every requested interval.

## B. Region autoconfiguration

### 11. Existing Region fields audit

The six audited values remain stored for compatibility, but their provenance
is now explicit. New regions default to World Data; pre-migration regions are
marked manual because the origin of their old numbers cannot be proven.

### 12. Consumers field-by-field

| Field | Source in automatic mode | Current consumers | AtmosphericGrid v5 | Final role |
|---|---|---|---|---|
| `base_temperature` | `mean_temperature_at` | legacy `_target_temperature`, UI | no | map climatology snapshot / legacy fallback |
| `seasonal_amplitude` | model legacy default | legacy `_target_temperature` | no | legacy orbital-response control only |
| `humidity` | shared initialization baseline | legacy weather-v2, UI | no | initial climatology snapshot, not current RH |
| `elevation` | `elevation_at` | legacy lapse rate, regional fog diagnostic, UI | no evolution input | derived location metadata; global solver reads static World Data directly |
| `weather_volatility` | model legacy default | legacy random T/RH/wind | no | deprecated legacy control |
| `precipitation_bias` | model legacy default | legacy condition choice | no | deprecated legacy control |

`seasonal_amplitude`, `weather_volatility` and `precipitation_bias` are hidden
from the ordinary automatic flow. They appear only in explicit manual/legacy
settings.

### 13. Biome source

The default is `WorldData.biome_at(latitude, longitude)`. A sparse
`CampaignWorldMapOverride` at the same cell takes precedence and the preview
returns `biome_source="campaign_override"`. An unpainted cell remains the empty
unknown value; no biome is invented.

### 14. Base-temperature source

`WorldData.mean_temperature_at(latitude, longitude)` supplies the stored
climatological mean. UI labels explicitly distinguish it from current
AtmosphericGrid temperature.

### 15. Elevation source

`WorldData.elevation_at(latitude, longitude)` supplies the value. `Region.elevation`
is nullable so a source pixel hidden by the raster legend remains unknown
instead of becoming a fictional zero.

### 16. Mean-humidity source/helper

`climatological_humidity_at(...)` calls the same
`initial_relative_humidity_percent(...)` helper now used by
`initialize_atmosphere`. Today the configured initializer distinguishes land
and ocean only. Latitude, temperature, elevation and biome are deliberately not
added because the existing initialization physics does not use them.

### 17. Orbital-response final role

`Region.seasonal_amplitude` remains only in weather-v2. AtmosphericGrid v5 gets
C1 distance, flux, zenith and radiative anomalies directly and never receives
this Region field, preventing a second seasonal bonus.

### 18. Weather-volatility final role

`Region.weather_volatility` remains only in deterministic legacy weather-v2
random targets. It is not passed to AtmosphericGrid and creates no second
random climate layer.

### 19. Precipitation-modifier final role

`Region.precipitation_bias` remains only in legacy weather-v2 condition choice.
C3 precipitation remains evaporation → q_v → transport/uplift/cooling → q_c →
fallout. There is no biome-specific Red Plateau precipitation hardcode.

### 20. Manual override architecture

`Region.use_manual_climate_overrides` is one explicit aggregate GM switch,
default OFF. When OFF, biome/temperature/humidity/elevation are recomputed at
save/placement and legacy controls reset to their technical defaults. When ON,
all posted manual values are preserved. Refresh does not overwrite manual
values; a separate explicit “switch to World Data” action is required.

### 21. Form/UI changes

The ordinary form asks for a name and map contour. It displays read-only auto
values for biome, climatic mean temperature, climatic mean humidity, elevation
and surface type. Manual mode enables those controls and reveals legacy
settings with clear warnings that solver v5 ignores them.

### 22. Coordinate-change behavior

Repositioning an automatic region recalculates derived values from the new
cell. Name and historical `WeatherState` rows are untouched. Future sampling
uses the new latitude/longitude. A manual region preserves its explicit values.

### 23. Preview endpoint / backend source of truth

`region_climate_preview` is a GM-protected GET endpoint. The browser sends the
polygon; the backend calculates the same canonical polygon centre used by POST,
then calls `region_climate_at`. POST repeats the calculation and never trusts
preview values. The endpoint does not initialize or advance the atmosphere.

### 24. Legacy compatibility

Weather-v2 still uses the old fields for disabled AtmosphericConfig or
unplaced regions. Existing database rows are marked manual by the migration,
so their authored/unknown provenance is preserved. Nullable unknown elevation
uses a neutral technical zero only inside the legacy lapse/fog fallback; the
database and UI continue to show it as unknown.

### 25. Double-count protections

Regression tests create colocated regions with opposite base temperature,
orbital response, humidity, volatility and precipitation bias. Their sampled
AtmosphericGrid physical fields are identical. Global solver construction
continues to read World Data, not Region climate fields.

### 26. Tests added

`world/tests/test_region_climate.py` covers:

1. biome from World Data;
2. temperature from the raster;
3. elevation from the raster;
4. shared climatological humidity;
5. POST without manual climate fields;
6. preview/save parity;
7. coordinate recomputation;
8. name preservation;
9. manual override preservation;
10. no legacy controls in AtmosphericGrid;
11. campaign biome override provenance;
12. no Red Plateau humidity/precipitation hardcode;
13. preview does not run atmosphere initialization;
14. current weather still has AtmosphericGrid C3 source;
15. safe World Data refresh semantics.

## C. Final

### 27. Full test result

`python manage.py test`: **155 tests passed** in 29.303 s.

`python manage.py check`: no issues.

`python manage.py makemigrations --check --dry-run`: no changes detected.

### 28. Migrations

`world/0013_region_climate_autoconfiguration.py` adds the manual override flag,
allows unknown biome/elevation, and safely marks all pre-existing regions as
manual. It was applied successfully to the local development database.

### 29. Known approximations

- Baseline RH currently has only configured land/ocean differentiation because
  that is all AtmosphericGrid initialization currently implements.
- Manual overrides use one aggregate switch rather than per-field provenance.
- Region fields remain stored snapshots for UI/legacy compatibility; the global
  atmosphere itself continues to read static World Data.
- The 24×12 boundary surrogate and 360-minute substep remain unchanged.
- OS contention makes wall-clock benchmarks variable; physical step counts and
  serialized results are stable.

### 30. Remaining questions for C4

No C4 code was implemented. Canonical atmospheric composition remains unknown
unless configured; unknown elevation/biome cells remain unresolved World Data;
and the current single-reservoir q_c phase split remains the documented C3
model. These are factual boundaries of the present implementation, not new
canon assumptions.
