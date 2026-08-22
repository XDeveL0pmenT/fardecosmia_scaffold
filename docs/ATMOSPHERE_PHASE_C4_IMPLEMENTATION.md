# Phase C4 — Atmospheric Circulation & Terrain Dynamics

## Scope and versions

C4 replaces the qualitative pressure/wind prototype with a deterministic,
single-layer circulation model. It does not implement C5, Leaflet, Travel,
Countries, Settlements, WorldEvent-driven catastrophes or cyclone entities.

- Grid: 180 × 90 by default; 360-minute exact timestep.
- World circumference: 72,500 km.
- Rotation period: 7.52 days.
- Gravity: 9.98 m/s².
- Snapshot: format 4, solver 6, payload magic `FATM4`.
- Circulation model version: 1.
- Stored float fields: 14; uncompressed 180 × 90 payload is 907,200 bytes.
- `rotation_direction_sign=+1` is a configurable technical working assumption,
  not settled world canon, and is included in the input fingerprint.

## Geometry and vector convention

`u` is eastward, `v` is northward. Longitude wraps periodically; latitude is
clamped at the polar rows. Planet radius is derived as `C / (2π)`. Cached grid
geometry contains latitude/longitude radians, `sin φ`, guarded `cos φ`, radius,
`dx = R cos(φ) Δλ`, `dy = R Δφ`, inverse distances, areas, angular velocity and
`f = 2 Ω sin(φ)`.

Semi-Lagrangian scalar and momentum transport uses those latitude-dependent
physical distances. Vector components stay in each cell's local east/north
basis during advection; parallel transport between bases is a documented
single-layer approximation.

## Pressure and wind

`circulation_pressure_hpa` is a prognostic reduced-pressure field. Each step:

1. semi-Lagrangian advection by previous `u/v`;
2. exponential relaxation toward a configurable thermodynamic target derived
   from virtual-temperature anomaly against the authored mean-temperature map;
3. bounded neighbor diffusion;
4. emergency min/max clamp with hit diagnostics.

No new pressure noise is added per timestep. A small deterministic perturbation
is applied only when the new solver branch is initialized.

`pressure_hpa` is a derived local surface pressure:

`p_surface = p_circulation × exp(-g z / (R_d T_virtual))`

Wind pressure-gradient acceleration uses only reduced pressure:

`a = -(1/ρ) ∇p`, where `ρ = p / (R_d T_virtual)`.

Momentum is advected, receives the pressure-gradient tendency, then exact
Coriolis rotation:

`u' = u cos(fΔt) + v sin(fΔt)`

`v' = v cos(fΔt) - u sin(fΔt)`

Land/ocean Rayleigh drag is integrated exponentially. Cached terrain slopes and
ruggedness provide smooth upslope and roughness damping. The global wind cap is
an emergency numerical safeguard only; the two-year benchmark recorded zero
hits.

## Terrain, convergence and microphysics

Terrain central gradients, directional upwind slopes and ruggedness use
spherical cell distances and are cached per static-grid/config combination.

- `w_orographic = u ∂h/∂x + v ∂h/∂y`, evaluated with upwind terrain slopes.
- `w_convergence = -H_effective × divergence`.
- `w_total` is their bounded sum.

The combined proxy applies one configurable adiabatic cooling/warming tendency.
Existing C3 saturation adjustment then creates/evaporates cloud condensate and
latent heat; there is no second orographic precipitation bonus. Divergence,
convergence, relative/absolute vorticity, Coriolis and pressure-gradient
accelerations are derived fields and are not persisted in snapshots.

The C3.5 24 × 12 boundary fast-forward carries the same reduced pressure,
prognostic wind, physical Coriolis, drag, coarse terrain vertical forcing and
q_v/q_c microphysics. It still ends in an exact one-Vitok spin-up.

## Coordinate sampling and diagnostics

`sample_environment_at(grid, static, settings, latitude, longitude)` is a pure,
renderer-independent service with no ORM dependency. It bilinearly samples all
continuous atmospheric fields and uses the nearest static cell for surface,
elevation and biome. Region WeatherState generation calls this same core.

`sample_campaign_environment_at(...)` is a read-only wrapper around the latest
compatible checkpoint. It never advances simulation. New C4 regional rows use
source `atmospheric_grid_v3`; old C1/C3 rows remain intact.

The GM-only region diagnostics panel now exposes reduced and local pressure,
pressure anomaly, `u/v`, pressure-gradient acceleration, `f`, surface drag,
divergence, vorticity, terrain slope/ruggedness and combined vertical-motion
proxies alongside the existing ocean/cloud diagnostics.

`apply_external_tendencies()` is an optional in-memory service boundary for
future temperature, reduced-pressure, u/v and moisture tendencies. C4 does not
read any future event/catastrophe database model.

## Benchmarks

Development campaign, 180 × 90, exact one Vitok (28 steps), rolled back:

| Metric | before C4 | after C4 |
| --- | ---: | ---: |
| wall | 0.864 s | 0.755 s |
| CPU | 0.797 s | 0.719 s |
| peak RAM | 87.54 MiB | 89.79 MiB |
| bytes written | 1,335,572 | 1,179,986 |

After-C4 stage attribution: advection 0.074 s, pressure 0.039 s, wind 0.080 s,
terrain/vertical forcing 0.022 s, microphysics 0.046 s, ocean exchange 0.079 s,
serialization 0.044 s, region sampling 0.031 s and DB time 0.006 s.

Full-size fast-forward including final exact Vitok and DB/report pipeline:

- one season: 1.224 s;
- one year: 3.011 s (hard-warning threshold is 3.0 s; observed excess 0.011 s).

The year runtime is dominated by the inherited C3.5 ocean/boundary fast-forward
(2.048 s). The C4 circulation code was not weakened to hide this 11 ms excess.

Reduced 24 × 12, two exact canonical years (2,912 steps): deterministic payload,
no NaN/Inf, no pressure-cap hits, no wind-cap hits, final wind median/p90/p95/
p99/max = 0.632/1.813/2.255/4.112/6.243 m/s. Final reduced pressure is
984.36–1008.94 hPa; surface pressure is 402.62–1008.94 hPa. Checkerboard
pressure fraction is 0.0372. Supersaturation safety corrections occurred 4,926
times over 838,656 cell-steps (0.59%); they are the existing C3 safeguard.

Reduced-grid exact versus fast-forward after final spin-up:

| Field | season error | year error |
| --- | ---: | ---: |
| SST MAE / max | 0.082 / 0.598 °C | 0.053 / 0.346 °C |
| air T MAE | 0.494 °C | 0.368 °C |
| local pressure MAE | 0.421 hPa | 0.302 hPa |
| reduced pressure MAE | 0.181 hPa | 0.147 hPa |
| wind vector MAE | 0.139 m/s | 0.110 m/s |
| q_v MAE | 0.000500 | 0.000320 |
| q_c MAE | 0.00000462 | 0.00000438 |
| integrated precipitation error | 2.28% | 0.95% |

Profiler traces: `ATMOSPHERE_PHASE_C4_BEFORE_VITOK.prof` and
`ATMOSPHERE_PHASE_C4_AFTER_VITOK.prof`. Repeatable diagnostics are in
`scripts/benchmark_atmosphere_c4.py`.

## Tests and known approximations

The suite covers physical radius/metrics, polar finiteness and longitude wrap;
rotation magnitude/sign and exact speed conservation; reduced-vs-surface
pressure separation; gradient direction, prognostic pressure, advection and
drag; convergence/vorticity; terrain ascent/descent; rain shadow; deterministic
snapshots; region-free coordinate sampling and integration with persisted
regional weather.

Known approximations remain configurable and are not world canon: one bulk
atmospheric layer, technical dry-air constant/composition, thermodynamic target
coefficient, effective mixing depth/lapse coupling, coarse 2-degree terrain,
local-basis vector advection and 24 × 12 skipped-period boundary atmosphere.
No hardcoded Earth wind belts, biome wind direction, cyclone switch or storm
pressure bonus was added.
