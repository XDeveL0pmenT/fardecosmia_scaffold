# PW2 — Live Character Ambience at Effective Location — Final Report

Date: 2026-08-24
Status: **COMPLETE**

## 1. Baseline

PW2 started from the completed PW1/L1 baseline:

- Player Campaign detail already rendered the active Character Workspace;
- active Character selection was Campaign-scoped;
- L1 stored optional exact Character coordinates and exposed the mandatory
  `get_effective_character_location()` resolver;
- C4.2 already provided coherent arbitrary-point atmosphere sampling;
- known full-suite baseline was 443 tests, OK, skipped=9;
- pre-PW2 warmed neutral Workspace benchmark: 7 queries, 5.771 ms average
  render time over 20 rollback-only iterations (4.712–9.102 ms).

No prior schema or routing work was restarted or replaced.

## 2. Region ambience audit

The existing Region detail page was audited before implementation.

- `world.views.region_detail()` read the latest current Region point
  `WeatherState` and `describe_region_sky()`.
- The template built an ad hoc fixed background from star phase, condition,
  season, turn and season-light classes plus three opacity variables.
- Clouds were selected mostly by discrete weather condition rather than the
  current cloud fraction.
- Rain and snow used animated GIF backgrounds.
- Darkness and Ympha tint already came from `RegionalSky` values.
- Region Weather cards and `build_environment_summary()` were presentation of
  persisted current Region rows; Region diagnostics remained GM-only.
- No separate JavaScript sky/weather engine existed.

The audit confirmed that Region presentation could be safely extracted into a
shared adapter/component rather than copied into Character Workspace.

## 3. Shared/reused design and changed files

The implementation now has one server-rendered path:

```text
authoritative point weather + RegionalSky
                 ↓
world.services.ambience immutable safe tokens
                 ↓
world/_ambient_layers.html + shared CSS
                 ↓
       Region UI / Character Workspace
```

Core files:

- `world/services/ambience.py` — shared ambient adapter, Region wrapper and
  Character exact-point read service;
- `world/services/atmosphere/sampling.py` — shared immutable
  `AtmosphericPointWeather` and `interpret_point_weather()` used by both direct
  point presentation and Region `WeatherState` construction;
- `world/services/environment_summary.py` — cosmetic temperature band derived
  from the existing thermal classifier;
- `world/templates/world/_ambient_layers.html` — shared safe ambient layers;
- `world/templates/world/region_detail.html`, `world/views.py` — Region moved to
  the shared adapter/component;
- `characters/templates/characters/character_workspace.html`,
  `campaigns/views.py`, `characters/views.py` — Player Workspace integration;
- `static/css/app.css`, `templates/base.html` — common ambient engine and cache
  version;
- `characters/tests/test_character_ambience_pw2.py` — focused PW2 tests;
- `scripts/benchmark_pw2_workspace.py` — rollback-only benchmark;
- mandatory architecture/handoff/roadmap documents and this report.

## 4. Effective-location integration

`build_character_ambience(character, campaign)` always calls
`get_effective_character_location(character)` first.

- It does not read `character.location_state` directly.
- Decimal L1 coordinates are converted to floats only at the established
  sampler/astronomy boundary; L1 precision is six decimal places.
- An absent resolver result returns neutral ambience before querying config or
  calling the sampler.
- Region center, Campaign center, biography and `(0, 0)` are never fallbacks.

## 5. Authoritative atmosphere point path

For a placed Character with enabled atmosphere:

1. load the Campaign's enabled `AtmosphericConfig`;
2. call `sample_campaign_environment_state_at()` exactly once with the resolved
   Character point and Campaign world time;
3. let the C4.2 sampler select the latest compatible snapshot, deserialize the
   grid, bilinearly sample continuous fields, use World Data elevation and
   derive coherent local surface pressure;
4. interpret the point through `interpret_point_weather()` using the existing
   humidity, rain/snow, fog and condition logic;
5. discard technical provenance before presentation.

No nearest-Region approximation is used. Region persistence now consumes the
same `interpret_point_weather()` function, preserving C4 semantics.

## 6. RegionalSky path

Local sky uses `calculate_local_sky(campaign, campaign.world_minutes,
longitude, latitude)` at the exact effective Character point.

It remains the source of:

- local stellar phase and intensity;
- darkness;
- Ympha visibility;
- red/black turn presentation;
- local seasonal-light classification.

Browser local time and real-world Earth time are not used.

## 7. Day/night

Safe `light_level`, `is_dark`, stellar-strength and darkness tokens come from
`RegionalSky`. The common component maps them to light and darkness layers.
Bright/day phases are visibly lighter; deep night is visibly darker. These are
presentation tokens and do not alter Campaign time or solver forcing.

## 8. Ympha

Ympha light/tint strength is derived from existing stellar intensity and Ympha
visibility. Red-turn classes preserve the Region saturation treatment. No
random red overlay or separate Character astronomy formula was introduced.

## 9. Clouds

Cloud opacity now follows the normalized current point `cloud_cover` value for
both surfaces. Weather condition still adjusts visual filtering for storm,
snow and fog, but does not invent clouds or change the atmospheric field.

## 10. Rain

Rain is rendered only when the current physical `precipitation_rate_mm_h`
crosses the existing configured current-precipitation threshold. Visual
intensity is normalized against the existing storm-rate presentation boundary.

`precipitation_amount_mm` and fast-forward/interval totals are not consulted by
the ambience adapter. A focused regression explicitly supplies a large
accumulated amount with zero current rate and obtains no rain.

## 11. Snow

Snow and mixed precipitation use the existing current rain/snow fractions
produced by C4 point interpretation. No new PW2 temperature threshold was
introduced. Snow and rain can share the same bounded layer for mixed current
precipitation through their separate normalized intensities.

## 12. Fog/haze decision

Fog is supported because Phase 0 confirmed an existing authoritative path:

```text
point q_v/q_c/T/pressure/wind/elevation
→ fog_potential()
→ condition_from_cell()
→ WeatherState.Condition.FOG
```

The visual adapter enables fog only for that condition. It does not synthesize
fog from an arbitrary PW2 humidity threshold.

## 13. Heat/cold

The cosmetic band (`extreme-cold`, `cold`, `temperate`, `hot`,
`extreme-hot`) is derived from the existing human thermal classifier in
`environment_summary.py`. It controls only subtle warm/cold tint and shimmer.

No biome, season or UI correction changes sampled temperature. No gameplay
penalty or Heat Corruption rule was added.

## 14. Biome decision

The shared token contract can carry only a validated stable `Biome` identifier
from the sampled point. PW2 intentionally adds no strong biome-specific visual
or climate override. Sky, current weather, clouds and temperature remain higher
priority. This avoids turning optional cosmetic context into C5 physics or
revealing Settlement/POI/Country knowledge.

## 15. Security and no Player oracle

- No Player weather/environment endpoint was added.
- Workspace ignores arbitrary latitude/longitude query parameters.
- Sampling coordinates are server-side values from the active controlled
  Character resolver.
- Foreign Campaign and foreign/other Character access remains denied by the
  existing membership/ownership boundaries.
- Player HTML exposes only safe semantic data attributes/classes.
- Raw coordinates, pressure, circulation pressure, grid coordinates/indexes,
  snapshot time/version/fingerprint, diagnostic JSON and GM atlas controls are
  absent.

## 16. No world mutation

Workspace GET does not call time advancement, simulation, spin-up or repair.
It does not write:

- Campaign world time;
- AtmosphericSnapshot;
- WeatherState;
- CharacterLocationState;
- Character ambience fields;
- AuditLog.

A real compatible snapshot integration test verifies payload/count stability.

## 17. Accessibility and motion

The shared engine replaces Region's animated rain/snow GIFs with bounded CSS
layers for rain, snow, clouds, fog and thermal shimmer. The existing global
`prefers-reduced-motion: reduce` rule reduces all animation to a single
0.01 ms iteration and retains static light/tint.

Focused tests lock the media rule and absence of the old GIF references. The
browser CSSOM confirmed that the rule was loaded. The in-app browser's active
OS preference was not reduced and did not expose media emulation, so no system
setting was changed merely for the test.

## 18. Performance and query counts

All measurements used 20 warmed rollback-only development renders.

| Mode | Queries | Average | Min | Max |
|---|---:|---:|---:|---:|
| Before PW2, neutral Workspace | 7 | 5.771 ms | 4.712 ms | 9.102 ms |
| After PW2, neutral/unplaced | 7 | 5.872 ms | 4.783 ms | 7.871 ms |
| After PW2, authoritative live point | 12 | 28.728 ms | 24.457 ms | 32.596 ms |

The live path is bounded: one config lookup, one compatible snapshot read, the
existing fingerprint/static World Data reads and one point sample per render.
There are no N+1 loops, per-frame server calls, WebSockets or giant video/raster
backgrounds.

## 19. Character switch behavior

The POST switch still persists active Character through the P5.5 service and
redirects to the normal Campaign Workspace. The redirected render resolves and
samples the newly active Character. No ambience cache is keyed only by User or
Campaign.

Focused and browser tests switched between distinct coordinates and observed a
hot bright rainy state change to a cold deep-night Ympha snow state.

## 20. Graceful fallback

Neutral ambience is returned for:

- no active Character;
- unplaced Character;
- disabled/missing AtmosphericConfig;
- missing compatible snapshot;
- expected unavailable/corrupt point input represented by the sampler's normal
  `LookupError`, `OSError` or `ValueError` boundary.

Location-presence wording remains accurate even if atmosphere is unavailable.
No technical error is shown to Player and no hidden initialization occurs.

## 21. Focused tests

Command:

```text
python manage.py test characters.tests.test_character_ambience_pw2 -v 1
```

Result: **15 tests — OK**.

Coverage includes all required data-flow, resolver, single-sample, IDOR,
mutation, shared-adapter, current precipitation, diagnostic-leak, fallback,
snapshot, no-persistence, visual-token and motion contracts.

## 22. Related regressions

PW1 Workspace, L1 location/resolver, Region views, environment summary, weather
display and C4.2 point sampling were run together.

Result: **66 tests — OK, skipped=1**.

## 23. Full suite

Command:

```text
python manage.py test -v 1
```

Result: **458 tests — OK, skipped=9**, in 629.463 seconds.

The increase from the known 443-test baseline is exactly the 15 focused PW2
tests.

## 24. Browser desktop/mobile verification

Isolated data contained one temporary Campaign, one Player, two placed
Characters at different points, one unplaced Character and one compatible
snapshot. It was deleted afterward by exact Campaign/User identifiers and zero
remaining matches were confirmed.

Verified:

- desktop 1280-class viewport: day, heavy clouds, current rain, hot tint and
  readable Workspace content;
- active switch: deep night, strong red Ympha, snow, cold tint;
- unplaced switch: neutral hidden ambient layers and honest location wording;
- mobile 390x844 override: no horizontal overflow and readable controls/cards;
- no coordinates, debug/provenance, GM atlas or Player point-query controls;
- loaded reduced-motion rule and CSS-only bounded weather motion;
- no console warnings/errors;
- no fake gameplay state.

Viewport override was reset, the agent-created tab was closed and the temporary
server was stopped.

## 25. Schema and migration status

PW2 adds no model field/table and persists no ambience.

```text
python manage.py makemigrations --check --dry-run
No changes detected
```

No migration was created.

## 26. Documentation

Updated with implemented facts only:

- `AGENTS.md`;
- `WORLD_HANDOFF_v2.md`;
- `Codex Handoff — Future Architecture Guardrails.md`;
- `Fardecosmia_Player_Experience_Architecture_v1.md`;
- `Fardecosmia_Master_Roadmap_v1_1.md`;
- `docs/PW2_PROGRESS.md`;
- this report.

`python manage.py check` is clean and `git diff --check` reports no whitespace
errors (only the repository's Windows LF/CRLF notices).

## 27. Known limitations, including C5

- “Live” means render/refresh against the latest compatible Campaign snapshot;
  PW2 does not add realtime push.
- If that snapshot is older than Campaign time, PW2 presents that authoritative
  latest state without exposing age/provenance or silently simulating forward.
- C5 land-surface/diurnal deficits remain exactly as produced by the solver;
  PW2 does not correct them with biome/season/UI temperature hacks.
- Biome flavor remains a safe stable token without strong theme rules.
- Player Map, named Location, POI/Settlement, Visibility/Discovery and Travel
  context are intentionally absent.
- The in-app browser could verify the loaded reduced-motion CSS contract but
  did not expose a media-preference emulator; automated CSS tests provide the
  regression boundary without changing the user's OS setting.

## 28. Scope confirmation and stop

PW2 did not start or implement:

- M4 Player Map;
- M2/V1 Geography or Visibility/Discovery;
- Travel or Party;
- Notes backend;
- XP, Soul HUD or Тиамана mechanics;
- Inventory, Ledger, Quests or Economy;
- Roll20 normalized sync;
- Apotheosis/Craft;
- C5/C6/C7.

PW2 is complete. Work stops here pending a separate explicit instruction.
