# PW2 — Live Character Ambience at Effective Location — Progress

Last updated: 2026-08-24

## Phase boundary

PW2 may connect the active Character Workspace to authoritative current
environment at the central effective location and reuse/extract the existing
Region ambience presentation path. It must not start Player Map, M2/V1, Travel,
Party, Notes, XP/Soul HUD, Inventory, Ledger, Quests, Roll20, Apotheosis or C5.

## Starting state

- Checkpoint created before implementation.
- PW1 and L1 are complete; the starting worktree contained only the untracked
  PW2 specification and this checkpoint.

## Completed work

- Created this resumable checkpoint immediately on starting PW2.
- Fully read `Fardecosmia_PW2_Live_Character_Ambience.md` and every mandatory
  architecture, handoff, roadmap and PW1/L1 report named by the specification.
- Completed the mandatory Phase 0 data-flow audit:
  - Region detail currently composes its background ad hoc in
    `world.views.region_detail` from `RegionalSky`, the latest current point
    `WeatherState.condition`, season classes and three CSS opacity variables;
  - Region clouds/precipitation are template/CSS presentation only; the
    existing implementation uses condition-class cloud opacity and animated
    rain/snow GIF backgrounds;
  - `calculate_local_sky()` is the reusable coordinate-aware RegionalSky path;
  - `sample_campaign_environment_state_at()` is the authoritative read-only
    arbitrary-point boundary and derives coherent point pressure using
    full-resolution World Data elevation;
  - current precipitation is the snapshot point field converted from kg/m2/s
    to mm/h, not interval accumulation;
  - authoritative fog support exists through solver `fog_potential()` and the
    existing `condition_from_cell()` classification;
  - Region `WeatherState` persistence is Region lifecycle data and must not be
    copied onto Character or used as a nearest-Region shortcut;
  - Player Workspace already resolves the active Character through P5.5 and
    location presence through the L1 central resolver, but has no environment.
- Recorded a rollback-only pre-PW2 Workspace benchmark: 7 queries, average
  5.771 ms render time over 20 warmed renders (min 4.712 ms, max 9.102 ms).
- Chosen implementation direction: extract one immutable shared ambient
  presentation adapter used by Region and Character, keep direct point
  interpretation server-side, and render one shared semantic layer template.
- Implemented the shared data/presentation boundaries:
  - `interpret_point_weather()` now centralizes the existing C4 point-to-current
    weather semantics and Region `WeatherState` construction consumes it;
  - `world.services.ambience` exposes immutable safe tokens,
    `build_region_ambience()` and `build_character_ambience()`;
  - Character ambience resolves coordinates only through
    `get_effective_character_location()`, samples the authoritative campaign
    snapshot once, and uses `calculate_local_sky()` at that exact point;
  - missing placement/config/snapshot or expected unavailable data produces a
    neutral read-only result without fallback coordinates or simulation;
  - current precipitation rate drives rain/snow; interval accumulation is not
    read by the adapter; fog is enabled only from the existing authoritative
    condition classifier.
- Refactored Region and Character onto one shared ambient layer template and
  CSS engine. Region retains its sky-only behavior while both surfaces now use
  proportional cloud state, CSS rain/snow, Ympha tint, day/night and existing
  thermal classification.
- Replaced animated precipitation GIFs in the shared layer with bounded CSS
  layers so the existing `prefers-reduced-motion` rule can actually stop rain,
  snow, fog, cloud and shimmer movement while retaining static tint.
- Connected both normal Player Workspace entry routes to the same Character
  ambience service; no Player endpoint or coordinate input was added.
- `python manage.py check` passes after the implementation block.
- Added focused PW2 coverage for all mandated data-flow/security/token cases,
  including a real compatible AtmosphericSnapshot read and active Character
  switch across different coordinates.
- Related PW1/L1/Region/environment-summary/weather-display/C4.2 regression:
  66 tests — OK, skipped=1.
- Expanded the focused suite to exactly 15 test methods so each mandatory
  coverage group is explicit, including absent config and reducible/no-GIF
  motion behavior; focused PW2 remains green.
- Recorded post-PW2 rollback-only performance:
  - neutral/unplaced: 7 queries, 5.872 ms average (4.783–7.871 ms);
  - authoritative live point: 12 queries, 28.728 ms average
    (24.457–32.596 ms).
  This is a bounded single point read with no per-frame or repeated sampling.
- Completed isolated browser verification using a temporary Campaign, Player,
  three Characters and one compatible snapshot:
  - desktop 1280-class viewport: bright/day, heavy cloud, current rain and hot
    tint rendered together and remained readable;
  - switching to the second Character rebuilt ambience at its different exact
    point as deep night, strong red Ympha, cloud, current snow and cold tint;
  - switching to the unplaced Character produced hidden neutral layers and did
    not sample/fabricate a coordinate;
  - mobile 390x844 override had no horizontal overflow and retained readable
    modules/switch controls;
  - no raw coordinates, GM atlas/debug strings, coordinate inputs or Player
    arbitrary-weather links were present;
  - no browser console warnings/errors;
  - the loaded CSSOM contains the reduced-motion override, all shared motion is
    CSS animation, and no animated rain/snow GIF remains in the engine; the
    focused test also locks this contract;
  - browser viewport was reset and the agent-created tab was closed.
- Deleted only the isolated browser Campaign UUID
  `d27d04c8-1a86-4b79-8bd5-ed4272c68ae2` and User ID 22, confirmed both exact
  selectors now return zero, and confirmed the temporary server is no longer
  listening.
- A replacement `AGENTS.md` instruction set arrived during browser cleanup;
  its L1 location-domain/resolver/GM-only-coordinate rules were reviewed and
  the current PW2 implementation already conforms.
- Full regression suite: 458 tests — OK, skipped=9, 629.463 seconds.
- Final validation:
  - `python manage.py check` — OK;
  - `python manage.py makemigrations --check --dry-run` — No changes detected;
  - `git diff --check` — no whitespace errors (Windows LF/CRLF notices only).
- Updated AGENTS, WORLD_HANDOFF_v2, Architecture Guardrails, Player Experience
  Architecture and Master Roadmap with implemented PW2 facts only.
- Created `PW2_LIVE_CHARACTER_AMBIENCE_REPORT.md` with all 28 required report
  sections and explicit scope/stop confirmation.
- Final read-only review confirmed all 28 report sections, no trailing whitespace
  in new files, no stale “PW2 not started” statements in the maintained
  architecture documents, and a worktree containing only intended PW2 source,
  test, style, documentation, specification and benchmark files.

## Changed files

- `docs/PW2_PROGRESS.md` — resumable PW2 checkpoint.
- `scripts/benchmark_pw2_workspace.py` — rollback-only render/query benchmark
  used for the required before/after measurement.
- `world/services/atmosphere/sampling.py` — shared current point-weather
  interpretation, reused by Region persistence.
- `world/services/environment_summary.py` — public cosmetic temperature band
  derived from the existing thermal classifier.
- `world/services/ambience.py` — immutable shared Region/Character ambient
  presentation and Character exact-point read path.
- `world/templates/world/_ambient_layers.html` — shared safe ambient layers.
- `world/templates/world/region_detail.html` — Region now consumes the shared
  layer component.
- `world/views.py` — Region ambient adapter integration.
- `campaigns/views.py`, `characters/views.py` — Player Workspace ambience
  integration through the active Character.
- `characters/templates/characters/character_workspace.html` — shared ambient
  layer include.
- `static/css/app.css`, `templates/base.html` — common ambient engine,
  reduced-motion-compatible effects and cache version.
- `characters/tests/test_character_ambience_pw2.py` — focused PW2 contract,
  security, mutation, shared-adapter, visual token and integration tests.
- `AGENTS.md`, `WORLD_HANDOFF_v2.md`,
  `Codex Handoff — Future Architecture Guardrails.md`,
  `Fardecosmia_Player_Experience_Architecture_v1.md`,
  `Fardecosmia_Master_Roadmap_v1_1.md` — completed PW2 contracts/status.
- `PW2_LIVE_CHARACTER_AMBIENCE_REPORT.md` — final PW2 handoff report.

## Tests

- `python manage.py check` — OK.
- Focused PW2: 13 tests — OK.
- Focused PW2 final: 15 tests — OK.
- Related combined regression: 66 tests — OK, skipped=1.
- Full suite: 458 tests — OK, skipped=9.
- Final `manage.py check` — OK.
- Migration dry-run — no changes detected.
- `git diff --check` — clean apart from line-ending notices.

## Known issues

- There is no active PLAYER membership in the development database, so the
  benchmark creates isolated rows inside a transaction and rolls them back.

## Exact next step

PW2 is complete. Stop. Do not begin any subsequent roadmap phase without a new
explicit instruction.
