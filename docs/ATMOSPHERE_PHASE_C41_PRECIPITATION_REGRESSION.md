# Phase C4.1 — Precipitation Regression Audit & Hydrological Sanity Fix

## Scope and reproducibility

This phase audited the existing C4 physical chain without adding C5 entities,
random weather, biome precipitation bonuses, legacy Region precipitation
modifiers, Leaflet, Travel or WorldEvent-driven atmospheric forcing.

The primary diagnostic command is:

```powershell
.\.venv\Scripts\python.exe scripts\audit_precipitation_c41.py --duration vitok --width 24 --height 12 --top 10
.\.venv\Scripts\python.exe scripts\audit_precipitation_c41.py --duration season --width 24 --height 12 --top 10
.\.venv\Scripts\python.exe scripts\audit_precipitation_c41.py --duration year --width 24 --height 12 --top 10
```

The reduced reference uses real static World Data, a 24×12 equirectangular
grid, a 360-minute timestep, seed 202 and zero initial temperature/pressure
noise. A representative season is 13 Vitoks; one canonical year is 52 Vitoks.
All distributions below pool every cell of every exact timestep.

Implemented files:

- added `scripts/audit_precipitation_c41.py`;
- added `world/tests/test_atmosphere_c41.py`;
- added migration `world/migrations/0015_phase_c41_solver_version.py`;
- changed `world/services/atmosphere/circulation.py`, `orography.py` and
  `simulation.py`;
- changed `world/atmosphere_defaults.py` (solver 7, format remains 4);
- changed `world/services/time_reports.py`;
- changed `templates/campaigns/_time_advance_report.html` and
  `world/templates/world/region_detail.html`;
- extended `world/tests/test_time_reports.py` and `world/tests/test_views.py`.

## 1. Root cause

C4 did produce global evaporation, condensation and rain. The system was not
globally dry. Two independent problems made it look dry in actual play:

1. `w_orographic = u·∇h` already has the physical unit m/s, but C4 multiplied
   the combined vertical motion by `vertical_motion_coupling = 0.12`. That
   coefficient is needed only for the diagnosed single-layer convergence proxy.
   Consequently real terrain lift and its cooling were attenuated a second time;
   the effective terrain lapse response was only `4.5×0.12 = 0.54°C/km`.
2. Fixed Region coordinates can legitimately remain dry even while many other
   grid cells rain. The Region page displayed the final/current rate only, and
   `TimeAdvanceReport` did not integrate the physical per-step amounts. Rain
   earlier in a time advance therefore disappeared from the user-facing result.

The physical fix leaves every coefficient unchanged. It applies the coupling
only to `w_convergence`, keeps `w_orographic` physical, and corrects the solver
operator order so new wind and terrain cooling reach saturation adjustment in
the same timestep.

## 2. Classification: physics, sampling, persistence and UI

- A (insufficient vapor): **not the global failure**; ocean evaporation and
  transport are nonzero.
- B (condensate but no fallout): **not the failure**; `q_c` crosses the existing
  `0.00005 kg/kg` threshold and fallout is nonzero.
- C (wet grid but broken sampler): **not the failure**; raw and bilinear samples
  agree at exact cell centres.
- D (exact wet, fast-forward dry): **not the failure**; integrated FF rain remains
  close to exact.
- E (rain elsewhere but not at existing Regions): **observed** in the development
  campaign and compounded by current-vs-integrated UI semantics.
- Physical regression: the vertical-coupling unit/ownership error described in
  section 1 reduced terrain-triggered saturation at appropriate locations.

## 3. Exact hydrological statistics before the fix

Baseline C4, reduced 24×12:

| duration | evaporation kg | condensation kg | cloud evaporation kg | precipitation kg | wet cell-steps | wet timesteps | integrated wet cells | peak mm/h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vitok | 1.224e17 | 1.279e16 | 1.407e14 | 1.211e16 | 1,406 | 25/28 | 93 | 1.152 |
| season | 1.600e18 | 1.721e17 | 1.957e15 | 1.686e17 | 55,500 | 361/364 | 214 | 1.470 |
| year | 4.120e18 | 6.649e17 | 6.820e15 | 6.538e17 | 243,263 | 1,453/1,456 | 232 | 1.478 |

For the pre-fix year, mean `q_v/RH/q_sat/q_c` were respectively
`0.039908 / 89.180% / 0.048534 / 0.00004875`. The important finding was that
none of these values was zero: the first broken assumption was not the ocean or
cloud pathway, but the interpretation of terrain vertical velocity and then
the user-facing temporal aggregation.

## 4. Exact hydrological statistics after the fix

| duration | evaporation kg | condensation kg | cloud evaporation kg | precipitation kg | wet cell-steps | visible wet cell-steps | wet timesteps | wet cells | peak mm/h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vitok | 1.225e17 | 8.843e15 | 1.156e14 | 8.337e15 | 1,185 | 1,001 | 25/28 | 81 | 0.813 |
| season | 1.646e18 | 1.455e17 | 2.023e15 | 1.424e17 | 48,176 | 20,608 | 361/364 | 197 | 1.541 |
| year | 4.242e18 | 5.987e17 | 7.331e15 | 5.883e17 | 219,398 | 75,757 | 1,453/1,456 | 213 | 1.572 |

The fix is spatial/physical, not a global-rain amplifier. Full physical descent
warming now also participates, strengthening rain shadows and reducing the
global total by about 10% relative to the incorrectly attenuated baseline.

## 5. q_v, RH and q_sat distributions

| duration | q_v mean / p50 / p90 / p99 / max | RH mean / p50 / p90 / p99 / max % | q_sat mean / min / max |
| --- | --- | --- | --- |
| Vitok | .053284 / .036485 / .147752 / .237130 / .301466 | 76.505 / 79.466 / 100.000 / 100.084 / 101.000 | .068559 / 8.73e-8 / .570408 |
| season | .043970 / .032860 / .116610 / .174293 / .301466 | 85.482 / 99.990 / 100.004 / 100.147 / 101.000 | .054751 / 8.73e-8 / .570570 |
| year | .039685 / .030263 / .102191 / .152331 / .301466 | 86.616 / 100.000 / 100.007 / 100.184 / 101.000 | .050637 / 8.16e-8 / .570570 |

Vitok/season/year counts of cell-steps with RH ≥90% are
2,330 / 66,463 / 293,166; with RH ≥100% they are
1,047 / 34,212 / 160,506. `q_v` and `q_sat` are specific-humidity mass
fractions (kg/kg); RH is percent.

## 6. q_c distribution versus fallout threshold

The unchanged autoconversion threshold is `q_c = 0.00005 kg/kg`.

| duration | q_c mean / p50 / p90 / p99 / max | q_c>0 cell-steps | q_c>threshold cell-steps |
| --- | --- | ---: | ---: |
| Vitok | 1.849e-5 / ~0 / 8.263e-5 / 2.391e-4 / 3.397e-4 | 4,810 | 1,185 |
| season | 4.091e-5 / 2.372e-5 / 9.385e-5 / 2.633e-4 / 6.452e-4 | 78,421 | 48,176 |
| year | 4.495e-5 / 5.020e-5 / 9.524e-5 / 2.747e-4 / 6.565e-4 | 322,002 | 219,398 |

The threshold lies within the resolved distribution, below p90, rather than
orders of magnitude above it. Lowering it was neither necessary nor done.

## 7. Condensation statistics

Total masses are in section 4. Active condensation cell-steps are
1,625 / 51,726 / 227,762 for Vitok/season/year. Peak local condensation fluxes
are `2.605e-4 / 4.327e-4 / 4.423e-4 kg m⁻² s⁻¹`.
Saturation adjustment occurs after the new terrain cooling and before fallout;
its maximum iterative solve count was 4, below the configurable maximum 6.

## 8. Evaporation statistics

Ocean evaporation was active in 3,812 / 51,946 / 205,798 cell-steps.
The maximum resolved flux in all three runs was `1.120e-3 kg m⁻² s⁻¹`,
below the emergency `0.003` cap. Water enters the atmospheric `q_v` field and
is transported by the same advection operator as heat; no regional humidity or
biome rain injection was added.

## 9. Precipitation statistics

Positive-rate p50/p90/p99 in mm/h:

| duration | p50 | p90 | p99 | mean over wet cell-steps |
| --- | ---: | ---: | ---: | ---: |
| Vitok | 0.139 | 0.428 | 0.675 | 0.187 |
| season | 0.040 | 0.215 | 0.577 | 0.082 |
| year | 0.023 | 0.210 | 0.576 | 0.074 |

`precipitation_rate` in the grid is kg m⁻² s⁻¹, numerically equivalent
to mm/s of water. Region persistence converts it to mm/h. The visible weather
condition threshold remains the configurable `0.05 mm/h`; sub-threshold
physical fallout is still accumulated in the timestep amount.

## 10. Vertical-motion unit audit

For horizontal wind `u,v [m/s]` and terrain gradients `∂h/∂x,∂h/∂y
[m/m]`:

`w_orographic = u ∂h/∂x + v ∂h/∂y [m/s]`.

For horizontal divergence `[1/s]` and effective mixing depth `[m]`:

`w_convergence_raw = -H_effective divergence [m/s]`.

Only the inferred convergence term is coupled:

`w_total = clamp(w_orographic + coupling * w_convergence_raw) [m/s]`.

Temperature tendency for one exact step is:

`ΔT = -w_total * Δt_seconds * lapse_rate_C_per_m [K per timestep]`.

There is no degrees/radians term here, no km/m ambiguity (`4.5°C/km` is
divided by 1,000 exactly once), and no hours/seconds ambiguity (360 minutes is
converted to 21,600 seconds exactly once).

After-fix extrema in m/s for Vitok are:
`w_orographic [-0.017715, 0.008032]`, raw convergence
`[-0.003332, 0.006126]`, effective total `[-0.017808, 0.007809]`.
Maximum terrain-linked cooling is 0.759°C per step. Across a year it reaches
1.688°C, well below the 8°C emergency clamp.

## 11. Operator-order audit

The exact step now executes:

1. advect temperature, `q_v`, `q_c`, reduced pressure and `u/v`;
2. apply optional explicit external tendencies;
3. surface/radiative exchange;
4. ocean sensible/latent exchange and evaporation;
5. advance reduced pressure and derive local surface pressure;
6. solve wind from the new pressure state, Coriolis, drag and terrain;
7. diagnose terrain/convergence motion and apply cooling/warming;
8. saturation adjustment, condensation/cloud evaporation and latent heat;
9. refresh diagnostic surface pressure from the final T/q state without
   advancing prognostic reduced pressure twice;
10. condensate fallout/autoconversion;
11. cloud cover, RH and numerical safety checks.

Thus condensation sees current-step cooling, fallout sees current-step `q_c`,
and no later pressure/wind operation overwrites temperature or humidity.

## 12. C3.5 versus C4 comparison

The repository history contains a single `C3 Weather system` commit rather than
a complete committed C3.5 tree; C3.5 support files are present only in the dirty
working tree. A controlled historical comparison was therefore reconstructed
by loading the committed pre-C4 simulation/orography/wind/pressure modules over
the same current support data and deterministic Vitok scenario. It is useful
diagnostically but is not claimed as a byte-identical historical checkout.

| metric after one Vitok | reconstructed C3.5 | C4 pre-fix |
| --- | ---: | ---: |
| mean q_v | 0.07752 | 0.05321 |
| mean RH | 88.30% | 77.65% |
| mean/max q_c | 4.591e-4 / 4.125e-3 | 2.392e-5 / 4.609e-4 |
| precipitation mass | 1.828e17 kg | 1.211e16 kg |
| peak / wet mean | 8.585 / 2.052 mm/h | 1.152 / 0.226 mm/h |
| mean/max wind | 32.03 / 80 m/s | physical, below cap |
| maximum terrain cooling | 8°C cap | 0.201°C pre-fix |

The reconstructed C3.5 state was regulated by the 80 m/s wind and 8°C cooling
emergency caps. Its nearly continuous heavy rain was therefore a numerical
artifact and was not restored as a target. C4's first meaningful divergence is
the new physical circulation/terrain pathway, specifically the extra coupling
applied to already physical `u·∇h`.

## 13. Required ocean-to-mountain rain-shadow scenario

`HydrologicalSanityScenarioTests` runs the real `simulate_step()` for 28 exact
steps on a deterministic 36×2 domain: twelve hot/moist ocean columns, persistent
eastward flow, a 1,500→3,000→1,500 m mountain belt, then a lee interior.
It verifies all required links:

- ocean evaporation mass > 0;
- downstream `q_v` increases;
- condensation mass > 0;
- maximum `q_c` > 0;
- precipitation mass > 0;
- integrated windward precipitation > integrated lee precipitation.

The scenario failed before the vertical ownership fix and passes after it.

## 14. Wettest-coordinate diagnostic

Top ten integrated cells after the reduced exact year:

| lat | lon | surface | integrated mm | peak mm/h | current raw/sampler mm/h |
| ---: | ---: | --- | ---: | ---: | ---: |
| 22.5 | 82.5 | land | 10,925.97 | 1.572 | 1.447 / 1.447 |
| -7.5 | -82.5 | land | 3,256.22 | 0.684 | 0 / 0 |
| -22.5 | -112.5 | land | 3,138.90 | 0.643 | 0.217 / 0.217 |
| 22.5 | 67.5 | land | 2,744.56 | 0.455 | 0.414 / 0.414 |
| -82.5 | 127.5 | land | 2,682.42 | 0.963 | 0.158 / 0.158 |
| -82.5 | -157.5 | land | 2,523.82 | 0.617 | 0.279 / 0.279 |
| 37.5 | 82.5 | ocean | 2,504.32 | 0.426 | 0.264 / 0.264 |
| 37.5 | 67.5 | ocean | 2,486.75 | 0.340 | 0.325 / 0.325 |
| -82.5 | -112.5 | land | 2,172.21 | 0.526 | 0.257 / 0.257 |
| -82.5 | -127.5 | land | 2,152.23 | 0.704 | 0.190 / 0.190 |

This is a development diagnostic, not new geography or rainfall canon.

## 15. Raw grid, coordinate sampler and Region agreement

At cell centres, `sample_environment_at()` reproduces the raw current
precipitation rate within floating-point tolerance, as shown in section 14.
The end-to-end regression constructs a `1.0 mm/h` wet cell and verifies:

- raw grid: 1.0 mm/h;
- arbitrary-coordinate sampler: 1.0 mm/h;
- Region sample: condition `rain`, rate 1.0 mm/h;
- persisted six-hour WeatherState amount: 6.0 mm;
- `build_weather_summary`: mentions rain;
- `build_environment_summary`: is not `без осадков`;
- rendered Region view exposes the same physical rate and unit semantics.

The existing real campaign also explains the original symptom: solver-6's
latest raw 180×90 snapshot contained 755 visible wet cells (peak 3.917 mm/h),
while all five Region coordinates happened to sample dry at that exact minute.

## 16. WeatherState persistence and UI fixes

For `atmospheric_grid_v3` rows:

- `precipitation_rate_mm_h`: current/final physical intensity;
- `precipitation_amount_mm`: water-equivalent amount produced by the completed
  atmospheric timestep ending at this row;
- `rain_fraction` and `snow_fraction`: phase partition of that physical amount;
- `precipitation`: legacy dimensionless index, deliberately stored as 0 for new
  physical rows and retained only for historical sources;
- `condition`: derived from physical rate, snow fraction, clouds, fog and wind.

The Region card is now explicitly labelled **«Осадки сейчас»** and
explains that it is the current rate/last-step amount. `TimeAdvanceReport` sums
`precipitation_amount_mm` once over completed states in `(start, end]`, reports
rain, snow water equivalent, peak rate, sampled steps and wet steps, and renders
the result both in regional details and global extremes. It does not copy full
WeatherState history into the report.

## 17. Fast-forward behavior

Fast-forward still uses the C3.5 boundary atmosphere plus a final exact one-
Vitok spin-up. It does not create detailed regional weather for the skipped
interval. Report integration is restricted to the exact/spin-up coverage, so
no rain is invented inside a skipped period.

Reduced-grid precipitation agreement after final spin-up:

| target | exact kg | fast-forward kg | relative error |
| --- | ---: | ---: | ---: |
| season | 1.424228e17 | 1.412682e17 | 0.8107% |
| year | 5.883307e17 | 5.881746e17 | 0.0265% |

The same benchmark remains payload-deterministic.

## 18. Performance before and after

Development campaign, default 180×90 grid, 360-minute exact timestep, changes
rolled back after each measurement:

| operation | C4 before | C4.1 after |
| --- | ---: | ---: |
| exact one Vitok / 28 steps | 0.755 s | 0.669 s |
| production season fast-forward + spin-up/report | 1.224 s | 1.102 s |
| production year fast-forward + spin-up/report | 3.011 s | 2.963 s |

The final Vitok measurement used 0.641 CPU seconds, 87.52 MiB peak working set,
1,187,584 snapshot payload bytes, 140 WeatherStates, 18 SQL queries and 6
writes. The final year FF used 2.83 CPU seconds, 89.63 MiB peak working set,
23 queries/7 writes and 1,286,996 snapshot bytes; 2.075 seconds remain in the
inherited ocean/boundary fast-forward. C4.1 introduces no pathological
performance regression.

## 19. Tests added

- unattenuated physical orographic velocity;
- real ocean→land→mountain→lee hydrological integration scenario;
- reduced real-World-Data annual hydrology;
- raw grid→coordinate sampler→WeatherState→human summaries persistence chain;
- mandatory `q_c=0 → precipitation=0`;
- current dry rate versus accumulated past timestep amount;
- fast-forward report excludes an unsimulated wet state and sums only spin-up;
- Region-view rendering of C4 physical rain labels and units;
- report rendering of integrated precipitation after redirect.

Existing C1–C4 circulation, ocean, cloud, report and UI regressions remain in
the ordinary suite.

## 20. Full test result

Final verification commands:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

The focused C4.1/report/view run completed 28 tests successfully. The final
project run completed **177 tests successfully** in 30.704 seconds. Django
reported no system-check issues, and `makemigrations --check --dry-run`
reported `No changes detected`.

## 21. Known approximations

- single bulk atmospheric layer and diagnosed, not resolved, vertical motion;
- coarse equirectangular grid and upwind terrain faces;
- convergence ascent uses an effective mixing-depth proxy;
- one effective adiabatic lapse coefficient handles ascent and descent in C4;
- microphysics is bulk-column saturation adjustment and threshold fallout;
- precipitation phase is a temperature transition, not resolved ice physics;
- the annual audit's 24×12 grid is a regression reference, not a local forecast;
- fixed Regions are point samples and may remain dry while nearby cells rain;
- fast-forward reports only final detailed spin-up weather for skipped periods;
- solver safety still records rare supersaturation corrections (2,769 over
  419,328 annual reduced cell-steps); pressure and wind caps had zero hits.

All numerical coefficients remain configurable technical values, not newly
declared Fardecosmia canon.

## 22. No legacy/random/biome rain hack

Confirmed: this phase did not lower the condensate threshold, raise global or
regional humidity to force rain, add random rain probability, revive Region
`precipitation_bias`, add biome wet/dry bonuses, or add a second orographic
precipitation source. Physical fallout still requires cloud condensate; the
explicit zero-condensate test enforces this boundary.

## 23. Scope stop

C5, Leaflet/Core, cyclone entities, catastrophes, Travel Engine and new
WorldEvent atmospheric behavior were not started. Phase C4.1 stops at the
diagnosis, hydrological sanity correction, persistence/UI semantics, regression
tests and this report.
