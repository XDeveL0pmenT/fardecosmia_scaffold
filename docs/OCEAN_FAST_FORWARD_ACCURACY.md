# Ocean fast-forward accuracy refactor

Date: 2026-08-11. Phase C3 is not part of this change. The exact 360-minute
solver and C1 orbital equations were not weakened or recalibrated.

## Attribution profile

The profiler uses one unchanged exact two-year reference on 24×12. Each probe
changes only the skipped-period approximation. Sensitivity probes which turn a
physical flux off are diagnostic only and are not production settings.

| Probe | Season MAE | Year MAE | Interpretation |
|---|---:|---:|---|
| Legacy one-Vitok FF | 7.675°C | 9.058°C | Baseline |
| Legacy with 6-hour SST steps only | 7.646°C | 8.988°C | Large step was not the main error |
| Canonical stellar sampling only | 7.679°C | 9.048°C | Small MAE effect, but fixes longitude/canonical rotation |
| Spatial wind with legacy mean air | 11.276°C | 11.836°C | Wind cannot be corrected independently of air/q |
| Sensible disabled probe | 9.032°C | 10.878°C | Sensible exchange is important |
| Latent disabled probe | 5.910°C | 7.961°C | Legacy reset-RH latent approximation was biased |
| Deep relaxation disabled probe | 7.668°C | 10.675°C | Small seasonal, material annual contribution |
| Analytic deep only | 7.681°C | 9.048°C | Stable but not sufficient alone |
| New carried boundary surrogate | **1.665°C** | **1.089°C** | Air/q/wind must evolve together |

The probes are not additive. The dominant issue was the interaction between a
single mean ocean-air temperature, reset humidity and constant wind, rather
than one coefficient or the one-Vitok SST step by itself.

## Selected implementation

- The fine 180×90 SST remains the stored slow state.
- A 24×12 ocean boundary-layer surrogate carries temperature, specific
  humidity, pressure and spatial wind only for computing ocean fluxes.
- It advances at 360-minute substeps but does not run full `simulate_step`,
  cloud/precipitation generation, regional sampling, events, snapshots or DB
  writes across the skipped interval.
- C1 forcing is sampled without assuming an Earth-like 24-hour rotation. One
  full stellar light cycle remains the canonical 168-hour Vitok.
- Sensible and latent exchange are evaluated every boundary substep.
- Deep relaxation uses its analytic linear solution on the macro path.
- Fine-grid SST anomalies not represented by 24×12 are retained and decay on
  the configured deep-relaxation timescale.
- The final exact spin-up is unchanged.

## Accuracy and runtime

Accuracy is measured against sequential exact integration on 24×12. Runtime is
the complete transactional 180×90 advancement on the development machine,
including final exact spin-up, snapshots, WeatherState sampling and SQLite.

| Metric | Old FF | New FF |
|---|---:|---:|
| Season SST MAE | 7.675°C | **1.665°C** |
| Season maximum error | 33.917°C | **7.912°C** |
| Year SST MAE | 9.058°C | **1.089°C** |
| Year maximum error | 41.760°C | **6.327°C** |
| Season total runtime | 0.671 s | **0.847 s** |
| Year total runtime | 1.116 s | **1.514 s** |

The alternative 8-hour full-resolution surrogate reached 1.940/1.586°C MAE,
but retained 17.10/15.79°C local errors and took 3.46 s for a full-grid season.
One- to three-day full-resolution trials were faster per substep but diverged
to approximately 5–38°C MAE. The selected coarse boundary grid is therefore
the best measured accuracy/runtime trade-off.

## Ten worst season errors — old

| Latitude | Longitude | Abs error | Coastal | Band |
|---:|---:|---:|:---:|---|
| 52.5 | −97.5 | 33.917°C | yes | mid |
| 67.5 | 157.5 | 28.447°C | yes | polar |
| −67.5 | 97.5 | 26.785°C | yes | polar |
| −52.5 | 67.5 | 22.402°C | yes | mid |
| 82.5 | 172.5 | 21.006°C | yes | polar |
| 7.5 | 97.5 | 17.072°C | yes | equatorial |
| −7.5 | 22.5 | 16.388°C | no | equatorial/hot central ocean |
| −7.5 | −172.5 | 16.320°C | yes | equatorial |
| 67.5 | −82.5 | 16.307°C | yes | polar |
| −7.5 | 172.5 | 16.243°C | yes | equatorial |

## Ten worst season errors — new

| Latitude | Longitude | Abs error | Coastal | Band |
|---:|---:|---:|:---:|---|
| −22.5 | 67.5 | 7.912°C | yes | mid |
| 7.5 | 67.5 | 7.331°C | yes | equatorial |
| −22.5 | 82.5 | 7.022°C | yes | mid |
| −52.5 | 37.5 | 6.949°C | yes | mid |
| −37.5 | 52.5 | 6.578°C | yes | mid |
| −67.5 | 142.5 | 6.387°C | yes | polar |
| −37.5 | 142.5 | 6.385°C | yes | mid |
| −37.5 | 22.5 | 6.310°C | yes | mid |
| −52.5 | 127.5 | 6.258°C | yes | mid |
| −22.5 | 37.5 | 6.250°C | yes | mid |

## Ten worst year errors — old

| Latitude | Longitude | Abs error | Coastal | Band |
|---:|---:|---:|:---:|---|
| 82.5 | 172.5 | 41.760°C | yes | polar |
| 82.5 | −172.5 | 37.153°C | yes | polar |
| 67.5 | 157.5 | 32.649°C | yes | polar |
| 67.5 | 172.5 | 32.364°C | no | polar |
| 67.5 | −22.5 | 30.368°C | yes | polar |
| 67.5 | −172.5 | 26.206°C | no | polar |
| 52.5 | −97.5 | 26.191°C | yes | mid |
| −67.5 | 97.5 | 25.264°C | yes | polar |
| −52.5 | 67.5 | 23.635°C | yes | mid |
| −7.5 | 97.5 | 22.386°C | yes | equatorial |

## Ten worst year errors — new

| Latitude | Longitude | Abs error | Coastal | Band |
|---:|---:|---:|:---:|---|
| −67.5 | 142.5 | 6.327°C | yes | polar |
| −37.5 | 142.5 | 5.569°C | yes | mid |
| −67.5 | −52.5 | 5.553°C | yes | polar |
| −7.5 | 52.5 | 4.227°C | yes | equatorial |
| 7.5 | −67.5 | 4.209°C | yes | equatorial |
| 7.5 | 97.5 | 4.063°C | yes | equatorial |
| −52.5 | 127.5 | 3.949°C | yes | mid |
| −67.5 | −67.5 | 3.945°C | yes | polar |
| −22.5 | 67.5 | 3.724°C | yes | mid |
| 7.5 | 67.5 | 3.659°C | yes | equatorial |

At 24×12, 67.7% of ocean cells are classified as coastal, so coastal cells
are inherently common. The remaining worst errors are now all below 8°C and
span polar, middle and equatorial latitudes. The previous isolated hot central
ocean error no longer appears in the new top ten. Coastal approximation remains
the clearest residual limitation and is explicitly retained in diagnostics.
