# L1 — Character Location & Initial Placement Foundation — Report

Date: 2026-08-24

## 1. Baseline

L1 started from the completed P5.5/P5.6/PW1/M1 architecture. `Character` was
already the durable Campaign-scoped identity, control belonged to
`CampaignMembership`, active selection was centralized, M1 provided a local
Leaflet atlas/custom Fardecosmia CRS, and there was no Character location model
or table.

The development database baseline contained two durable Characters: PK 1 was
active/assigned and PK 4 archived/unassigned. Both belonged to Campaign
`5a47e46f-57bb-40af-a31f-4641949089fa`; there were no Roll20 bindings and no
location-like tables.

## 2. Existing-location audit

No location/position field, model, table, service, Player map marker or hidden
legacy coordinate existed. Region `map_latitude`/`map_longitude` describe Region
geometry and were not reinterpreted as Character position. Biography, Campaign
defaults, Region centers and the zero coordinate were rejected as sources.

## 3. Storage design

`characters.CharacterLocationState` is an additive OneToOne child of
`Character` (`related_name="location_state"`). It contains exact `latitude`,
`longitude`, `created_at` and `updated_at`. An absent row is the explicit
unplaced state. Location remains Character domain state and survives controller
reassignment because it is not stored on User or CampaignMembership.

## 4. Coordinate convention

Coordinates use the M1 Fardecosmia planetary/equirectangular convention:

- latitude: `[-90, 90]`;
- canonical longitude: `[-180, 180)`;
- input longitude `+180` canonicalizes to `-180`;
- longitude wraps horizontally; latitude does not wrap through a pole;
- no Earth CRS, radius, haversine or `distanceTo` helper was introduced.

## 5. Precision

Both coordinates use Decimal storage with six fractional digits. Latitude is
`DecimalField(max_digits=9, decimal_places=6)` and longitude is
`DecimalField(max_digits=10, decimal_places=6)`. Service validation rejects
booleans, non-numeric/non-finite values, excess precision and out-of-range
coordinates before persistence. Database check constraints independently bound
both fields.

## 6. Migration

`characters.0003_character_location_state_l1` performs only `CreateModel` for
the child state and its constraints. It has no data migration, no inferred
positions and no destructive operation. `makemigrations --check --dry-run`
reports no drift.

## 7. Data preservation

The migration test carries an existing User, CampaignMembership, Character and
Roll20 binding across 0002 → 0003 and verifies durable PK/owner/Campaign/active
state/binding plus zero generated locations. After applying 0003 to the actual
development DB, Character PK 1/4 and their captured fields were unchanged;
Roll20 bindings remained 0 and location rows remained 0.

## 8. Initial-placement semantics

`initialize_character_location()` is the sole supported L1 write. It accepts an
active, same-Campaign Character with no state, validates/canonicalizes the point,
creates exactly one state and audits it. Assigned and unassigned active
Characters are supported. Archived or already-placed Characters are rejected.
GET is read-only. There is deliberately no update/move/correction service or
normal UI.

## 9. Permissions and IDOR

Only a same-Campaign GM or superuser may initialize. PLAYER, foreign Campaign
GM and global-canon-editor-only accounts are denied. Both view lookup and the
locked service query bind the Character to the requested Campaign. Direct and
forged GET/POST paths are covered; foreign Campaign/Character combinations do
not cross boundaries.

## 10. Locking and concurrency

The service is `transaction.atomic`, locks the Campaign row, locks the target
Character row and checks the OneToOne state before creation. This serializes two
GM attempts on PostgreSQL. A PostgreSQL-only race test proves one success, one
domain conflict, one location and one audit; SQLite records the expected skip
because it has no row-level `SELECT FOR UPDATE` semantics.

## 11. GM placement UI

The Character detail card offers **Установить исходное положение** only for an
active unplaced Character. Its dedicated page uses bundled Leaflet 1.9.4, M1's
custom Fardecosmia CRS, local base tiles and planetary longitude wrap. A map
click places a marker and preview, fills hidden canonical coordinates and
enables explicit confirmation. Moving the marker clears confirmation. Submit is
disabled until both point and confirmation exist, while the backend enforces
the same requirements independently. After success the normal action disappears
and exact coordinates are read-only for GM.

## 12. Player disclosure

Player Workspace receives only `character_location_available`. It renders
**Ваше положение отражено.** or the corresponding absent-state copy. It receives
no raw latitude/longitude, atlas config, Leaflet asset, marker, environment or
Weather data. This keeps objective position, Character-facing disclosure and
GM-only setup information separate.

## 13. Effective-location resolver

`get_effective_character_location(character)` is the mandatory central read
boundary. It returns `None` for unplaced Characters or immutable
`EffectiveCharacterLocation(character_id, latitude, longitude,
source="initial_placement")`. Workspace queries select-related the child state,
so the resolver does not introduce N+1 behavior.

## 14. M2 compatibility

The stored point is pure planetary latitude/longitude and has no dependency on
Country, Settlement, Road, POI, Region name or future vector feature IDs. M2 can
relate named geography later without rewriting the durable point or inventing a
location during L1.

## 15. PW2 boundary

L1 does not call `sample_environment_at`, C4.2 atmosphere sampling or Weather
services. The Workspace map card only reflects position presence. PW2 may later
resolve the effective point and sample real current environment, but no live
ambience, sky, biome, weather or fake baseline was added here.

## 16. Travel boundary

No free GM teleport/reposition exists. Future Travel/Party/domain movement must
become an effective-position source through the central resolver, with its own
authority, time and audit semantics. Callers must not edit
`CharacterLocationState` directly.

## 17. AuditLog

Creation and `character.location_initialized` audit share one transaction.
Audit failure rolls back the state. The row records actor, Campaign, Character
target, Campaign `world_minutes`, before `{location: null}`, exact canonical
coordinate strings, source and Fardecosmia coordinate-system metadata. It
contains no request dump or secret.

## 18. Admin

`CharacterLocationStateAdmin` is superuser-visible diagnostic state only.
Add/change/delete are disabled. It is not a recovery editor or an alternate
movement boundary.

## 19. Tests

- focused L1: **21 tests — OK, skipped=1** (PostgreSQL race proof on SQLite);
- related P5.5/P5.6/PW1/M1: **69 tests — OK, skipped=2**;
- full suite: **443 tests — OK, skipped=9**.

Final validation also passed: `manage.py check` reports no issues,
`makemigrations --check --dry-run` reports no changes, and
`git diff --check` is clean. Line-ending notices are Git's existing Windows
LF/CRLF normalization warnings, not whitespace errors.

The focused matrix covers all 20 requirements from the L1 specification,
including migration preservation, Player secrecy, no Earth helper and bounded
queries. The full total is the previous 422-test baseline plus 21 L1 tests.

## 20. Browser verification

Isolated desktop and mobile verification completed on the real Django app:

- GM detail → placement page → map click → preview → confirmation → save;
- moving a selected point reset confirmation;
- refresh preserved the saved coordinates;
- the placement action disappeared and direct repeat URL redirected read-only;
- Player saw only the location-present statement and no coordinates/GM atlas;
- PLAYER and foreign GM direct URLs returned 403;
- desktop and `390×844` Player UI had no horizontal overflow;
- the `390×844` GM map remained usable and had no horizontal overflow;
- browser console had no warnings/errors;
- no Player Map or Weather feature appeared.

The temporary viewport was reset, the tab closed, the temporary server stopped,
and only isolated `l1-browser-*` users/Campaigns were removed. The original
development rows were rechecked afterward.

## 21. Performance and query behavior

No atmosphere/static-grid/environment sampling runs in placement or Workspace
reads. Controlled and active Character queries select-related location state.
The 20-Character Player Workspace remains within the existing 12-query bound.

## 22. Documentation

Updated `AGENTS.md`, `WORLD_HANDOFF_v2.md`, Architecture Guardrails and Master
Roadmap with only completed L1 invariants: Character-owned location, one-time
setup, no free GM teleport, effective resolver, Player secrecy and future
Travel/PW2 boundaries. The Roadmap marks L1 complete.

## 23. Known limitations

- SQLite cannot execute the PostgreSQL row-lock race proof; the test is present
  and skipped only on unsupported backends.
- L1 stores an exact point but intentionally has no named place, region binding,
  movement history, location correction workflow or Player map.
- Environment/weather, discovery/visibility and travel semantics are deferred
  rather than approximated.

## 24. Scope confirmation

L1 did not start PW2/weather, Travel, Party, M2, V1, Player Map, Notes, XP, Soul
HUD, Inventory, Ledger, Quests, Roll20 sync, Apotheosis or C5. No next phase was
started automatically.

## Changed files

- `characters/models.py`
- `characters/migrations/0003_character_location_state_l1.py`
- `characters/services.py`
- `characters/forms.py`
- `characters/admin.py`
- `characters/views.py`
- `characters/urls.py`
- `characters/templates/characters/character_detail.html`
- `characters/templates/characters/character_workspace.html`
- `characters/templates/characters/character_initial_placement.html`
- `campaigns/views.py`
- `static/js/atlas/character_initial_placement.js`
- `static/css/app.css`
- `characters/tests/test_character_location_l1.py`
- `characters/tests/test_character_identity_p55.py`
- `docs/L1_PROGRESS.md`
- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- `L1_CHARACTER_LOCATION_INITIAL_PLACEMENT_REPORT.md`
