# L1 — Character Location & Initial Placement Foundation — Progress

Last updated: 2026-08-24

## Phase boundary

L1 may add durable Character location, one-time initial placement, a central
effective-location resolver and the narrow UI/security needed for those
contracts. It must not implement normal GM teleport/reposition, PW2/live weather,
Travel, Party, M2, V1, Player Map, XP, Soul HUD, Inventory, Ledger, Quests or C5.

Planet coordinates are Fardecosmia world coordinates. Player-facing UI must not
expose raw latitude/longitude.

## Starting worktree

- Existing tracked worktree is clean.
- `Fardecosmia_L1_Character_Location_Initial_Placement.md` is the newly supplied
  untracked L1 specification.

## Completed work

- Created this checkpoint before implementation.
- Read `Fardecosmia_L1_Character_Location_Initial_Placement.md` in full.
- Re-read in full: `AGENTS.md`, `WORLD_HANDOFF_v2.md`, Architecture
  Guardrails, Player Experience Architecture, Master Roadmap, P5.5/P5.6
  reports and `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`.
- Completed mandatory Phase 0 audit:
  - the existing durable identity remains `characters.Character`;
  - Character control is `Character.owner -> CampaignMembership`, archive is
    nondestructive and active selection is Campaign-scoped;
  - no location/position model, field or database table exists;
  - M1 already provides local Leaflet 1.9.4 assets, custom equirectangular CRS,
    horizontal longitude wrap and canonical map helpers;
  - `world.services.map_geometry` already validates latitude, normalizes
    longitude and uses Fardecosmia's 72,500 km circumference;
  - C4.2 arbitrary point sampling exists but will not be called by L1;
  - `Campaign.world_minutes` and `world.services.audit.record_audit()` provide
    the required time/audit boundaries;
  - Character admin is already diagnostic-only and normal mutations use
    transactional services.
- Captured development DB preservation baseline:
  - 2 Character rows: PK 1 active/assigned, PK 4 archived/unassigned;
  - both belong to Campaign `5a47e46f-57bb-40af-a31f-4641949089fa`;
  - 0 Roll20 bindings and 0 bound Roll20 rows;
  - no location-like tables;
  - Characters migrations 0001/0002, Campaigns through 0011 and Roll20 0001
    are applied.
- Chosen additive design:
  - separate `CharacterLocationState` OneToOne, absent row = unplaced;
  - Decimal latitude/longitude at six decimal places with DB constraints;
  - no Region/Settlement/POI/name/travel/weather fields and no data migration;
  - one supported write service, initial-placement-only;
  - immutable central effective-location value returned by one resolver;
  - GM-only Leaflet placement page reuses M1 CRS/tiles;
  - Player Workspace receives only a location-present boolean.
- Completed model/migration milestone:
  - added `CharacterLocationState` OneToOne with six-decimal Decimal latitude/
    longitude, timestamps and DB latitude/longitude constraints;
  - added additive `characters.0003_character_location_state_l1` with no data
    migration and no generated location rows;
  - added strict finite/range/precision validation and `+180 -> -180`
    canonical seam handling;
  - added immutable `EffectiveCharacterLocation` and the central
    `get_effective_character_location()` resolver;
  - added the sole supported L1 write boundary
    `initialize_character_location()` with Campaign/Character row locks,
    same-Campaign GM authority, active-only and no-existing-row validation;
  - location creation and `character.location_initialized` AuditLog share one
    transaction and capture Campaign world time through existing audit semantics;
  - added diagnostic-only, read-only superuser admin; no normal recovery/editor
    path exists;
  - updated controlled/active Character loading to include location state without
    N+1 queries.
- Completed GM/Player UI milestone:
  - added a dedicated GM-only initial-placement route and POST flow;
  - the page reuses bundled Leaflet 1.9.4, the M1 Fardecosmia CRS, local base
    tiles and horizontal planetary longitude wrapping;
  - map click populates canonical hidden coordinates, resets explicit
    confirmation after every moved point and keeps submit disabled until both
    a point and confirmation are present;
  - Character detail shows the one-time action only for active, unplaced
    Characters and otherwise shows read-only coordinates to the GM;
  - archived and already-placed Characters cannot enter a placement editor;
  - Player Workspace receives only `character_location_available` and renders
    diegetic presence/absence copy without raw coordinates or a map;
  - no Region, weather, environment, Travel, Party or Player Map query was
    introduced;
  - `manage.py check` remains clean after the UI integration.
- Completed focused-test milestone:
  - added 21 focused tests covering every item in the L1 required matrix;
  - service, audit rollback, permissions, IDOR, range/precision, seam
    canonicalization, repeat denial, archived/unassigned policy, resolver,
    Player secrecy, GM UI, custom planetary CRS, bounded queries, admin and
    additive migration preservation all pass;
  - PostgreSQL two-GM race proof is present and expectedly skipped on SQLite;
  - focused result: `21 tests — OK, skipped=1`;
  - the first focused run had one locale-sensitive assertion expecting a dot
    while Russian rendering correctly uses a comma; no application defect was
    involved, and the test now also asserts persisted Decimal values directly;
  - updated the historical P5.5 migration test cleanup to restore the current
    migration leaf, preventing it from removing the newer L1 schema from later
    tests.
- Applied the additive migration to the development DB and verified preservation:
  - Characters PK 1 and 4 retain the same Campaign, owner and active/archive
    state captured before migration;
  - Roll20 bindings remain 0;
  - `CharacterLocationState` rows remain 0, so no location was guessed or
    auto-created.
- Completed mandatory related regression:
  - P5.5 Character identity/control;
  - P5.6 GM eligibility/access;
  - PW1 Character Workspace;
  - M1 Leaflet atlas;
  - combined result: `69 tests — OK, skipped=2`.
- Completed isolated browser/manual verification:
  - desktop GM Character detail exposed initial placement exactly once;
  - the local Leaflet/Fardecosmia atlas loaded, map click populated preview,
    confirmation enabled only after a point, and moving the point reset the
    confirmation before submit;
  - successful submit persisted the selected point, redirected to read-only GM
    detail, survived refresh and removed the normal placement action;
  - direct repeat URL redirected to detail with an already-established notice;
  - Player Workspace rendered only `Ваше положение отражено.` with no raw
    coordinates, GM atlas configuration, Leaflet asset or Weather UI;
  - PLAYER and a GM from another Campaign received 403 on the placement URL;
    forged POST denial is also covered in the focused suite;
  - desktop and mobile `390×844` Player Workspace had no horizontal overflow;
  - mobile `390×844` GM placement page had no horizontal overflow and retained
    a usable 303 px-wide map with disabled submit before selection;
  - browser console contained no warnings or errors;
  - the temporary viewport was reset, the browser tab was closed and the local
    server was confirmed stopped;
  - only three `l1-browser-*` accounts and the two isolated browser Campaigns
    were deleted; the original development baseline is again exactly Characters
    PK 1/4, zero locations and zero Roll20 bindings.
- Completed final regression/documentation milestone:
  - full suite: `443 tests — OK, skipped=9` (the 422-test PW1 baseline plus 21
    L1 tests; the extra skip is the PostgreSQL-only race proof);
  - `manage.py check`: no issues;
  - `makemigrations --check --dry-run`: no changes detected;
  - `git diff --check`: clean; Windows LF/CRLF notices are normalization
    warnings only;
  - updated `AGENTS.md`, `WORLD_HANDOFF_v2.md`, Architecture Guardrails and
    Master Roadmap with completed L1 invariants and marked L1 complete;
  - created `L1_CHARACTER_LOCATION_INITIAL_PLACEMENT_REPORT.md` with all 24
    required report sections;
  - no out-of-scope phase was started.

## Changed files

- `docs/L1_PROGRESS.md` — resumable L1 checkpoint.
- `characters/models.py` — additive durable location state.
- `characters/migrations/0003_character_location_state_l1.py` — additive schema.
- `characters/services.py` — validation, initial placement and resolver.
- `characters/forms.py` — strict placement confirmation form.
- `characters/admin.py` — read-only diagnostic registration.
- `characters/views.py` — GM placement endpoint and resolver-backed view context.
- `characters/urls.py` — narrow initial-placement route.
- `characters/templates/characters/character_initial_placement.html` — GM map,
  preview and explicit confirmation.
- `characters/templates/characters/character_detail.html` — one-time action or
  GM-only read-only location state.
- `characters/templates/characters/character_workspace.html` — Player-safe
  location-presence copy.
- `campaigns/views.py` — resolver-backed Player Workspace boolean.
- `static/js/atlas/character_initial_placement.js` — Fardecosmia map selection.
- `static/css/app.css` — placement layout, marker and mobile presentation.
- `characters/tests/test_character_location_l1.py` — focused L1 matrix.
- `characters/tests/test_character_identity_p55.py` — migration-test cleanup
  restores current leaf after the historical preservation scenario.

## Tests

- Model milestone: `manage.py check` passes.
- Model/migration milestone: `makemigrations --check --dry-run` reports
  `No changes detected`.
- UI milestone: `manage.py check` passes.
- Focused L1: `21 tests — OK, skipped=1` (PostgreSQL-only concurrency proof).
- Related P5.5/P5.6/PW1/M1: `69 tests — OK, skipped=2`.
- Browser desktop/mobile: complete, no defects, console clean, no overflow.
- Full suite: `443 tests — OK, skipped=9`.
- Final check/migration-drift/diff validation: clean.

## Known issues

- The first DB audit command used the wrong Roll20 import/app label; it made no
  writes. The audit was immediately repeated with `integrations.roll20` /
  `roll20` and completed successfully.

## Exact next step

L1 is complete. Stop and wait for a separate explicit instruction; do not begin
N1, Party, M2/V1, PW2/M4, Travel, Roll20, economy, C5 or any other next phase.
