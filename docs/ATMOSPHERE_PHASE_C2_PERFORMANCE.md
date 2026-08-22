# Phase C2 atmospheric performance and stability

> The original one-Vitok ocean fast-forward measurements below are retained as
> the before-baseline. The current accuracy refactor and old/new comparison are
> documented in `docs/OCEAN_FAST_FORWARD_ACCURACY.md`.

Date: 2026-08-11. Development machine, SQLite, grid 180×90, atmospheric
timestep 360 game minutes. Database writes in `benchmark_atmosphere.py` are
rolled back. Timings are development measurements, not production guarantees.

## Full-grid before / after

| Scenario | Before C2 wall | After C2 wall | C2 simulated steps |
|---|---:|---:|---:|
| 1 atmospheric step | 0.134 s | 0.124 s | 1 |
| 1 Vitok / 28 steps | 0.471 s | 0.517 s | 28 |
| 1 season fast-forward | 0.461 s | 0.671 s | 28 + ocean macro |
| 1 canonical year fast-forward | 0.463 s | 1.116 s | 28 + ocean macro |

The final year measurement spends about 0.590 s in bounded SST macro stepping;
the final exact spin-up remains 28 ordinary atmospheric steps. Peak working set
was about 82.0 MiB, DB time 0.007 s, two snapshots were written, and snapshot
payload bytes were about 1.00 MiB. One exact Vitok stayed below the C2 hard
target of one second. Season fast-forward stayed below one second; the year is
close to, but above, the desirable one-second target.

## Two-year reduced-grid stability

`python scripts/benchmark_atmosphere_c2.py` uses the real static maps on 24×12
and performs two sequential canonical years (2912 exact six-hour steps), then
repeats the run and compares fast-forward.

- deterministic compressed payload: yes;
- SST range: −25.211…78.486 °C;
- maximum q_v: 0.385566 kg/kg;
- stellar peak phase/day index: 33;
- SST peak phase/day index: 100;
- observed SST lag: 67 phases (no exact canonical lag is hardcoded);
- year-to-year daily SST-pattern MAE: 1.065 °C;
- largest numerical-cap frequency: 1.069% of cell-steps.

Cap counts across the exact two-year run:

- evaporation cap: 118 cell-hits;
- SST per-step cap: 23;
- air sensible cap: 826;
- temporary supersaturation safety cap: 8966.

No NaN/Inf, absolute SST cap, or q_v runaway occurred in the accepted run.

## Fast-forward accuracy

Comparison is exact six-hour integration versus one-Vitok SST macro steps plus
one final exact Vitok of spin-up on the same 24×12 world:

| Interval | SST spatial MAE | Maximum cell error | Exact / FF mean SST |
|---|---:|---:|---:|
| Season | 7.675 °C | 33.917 °C | 56.383 / 51.527 °C |
| Year | 9.058 °C | 41.760 °C | 50.443 / 46.129 °C |

This does not meet the desirable 1–2 °C target from the C2 brief. The measured
regression limits are therefore explicitly 8 °C for a season and 10 °C for a
year. The main remaining error is spatial: the exact C1 wind solver frequently
reaches its 80 m/s safeguard and transports heat into cold ocean cells, while
the bounded slow-state approximation deliberately does not simulate a full
historical atmosphere. The macro path remains deterministic, stateful and
fast; it does not invent skipped weather. Improving this approximation is a
known follow-up, not hidden as false precision.
