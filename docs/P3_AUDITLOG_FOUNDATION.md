# P3 AUDITLOG FOUNDATION REPORT

## 1. Changed files

- `world/models.py`, `world/migrations/0018_auditlog.py`
- `world/services/audit.py`, `world/services/canon.py`,
  `world/services/regions.py`, `world/services/map_layers.py`,
  `world/services/time.py`
- `world/views.py`, `world/urls.py`, `world/admin.py`, `campaigns/views.py`
- `world/templates/world/audit_list.html`,
  `world/templates/world/audit_detail.html`,
  `world/templates/world/global_world_entry_list.html`
- `world/templatetags/audit_json.py`, `templates/base.html`,
  `templates/campaigns/_campaign_quickbar.html`, `static/css/app.css`
- `world/tests/test_audit_p3.py`, `scripts/benchmark_audit_p3.py`
- `AGENTS.md`, `WORLD_HANDOFF_v2.md`,
  `Codex Handoff — Future Architecture Guardrails.md`,
  `Фардекосмия — Master Roadmap v1.0.md`

## 2. Migration

`world.0018_auditlog` creates the table and indexes. It contains no historical
backfill and has been applied to the local development database.

## 3. AuditLog model

The model stores the real timestamp, source, namespaced action, nullable live
Campaign and actor references, durable Campaign/actor snapshots, nullable world
minutes, generic target identity plus durable ID/label, deterministic summary,
nullable before/after JSON, metadata JSON and an indexed UUID operation ID.

## 4. Append-only enforcement

Instance `save()` rejects updates, instance `delete()` rejects deletion, and the
normal AuditLog QuerySet rejects `update()`/`delete()`. Admin has no add/change/
delete permissions, including for superuser. No purge, retention or pruning UI
exists. This is an application/ORM invariant; a database owner or raw SQL can
still perform emergency maintenance.

## 5. Global vs campaign scope semantics

Global rows have `campaign=NULL`, `campaign_id_snapshot=NULL` and
`world_minutes=NULL`. Campaign rows capture the live Campaign, string UUID/name
snapshots and current integer `Campaign.world_minutes`. A deleted Campaign is
not reclassified as global: global queries also require a null Campaign snapshot.

## 6. Actor model/snapshots

Actor is nullable `accounts.User`, `SET_NULL`. USER source requires an actor.
SYSTEM/INTEGRATION/IMPORT can use `actor=None`. `actor_label_snapshot` preserves
the display name/username after user deletion; no fake system user is created.

## 7. Source values

Stable choices are `USER`, `SYSTEM`, `INTEGRATION`, `IMPORT`.

## 8. Action naming convention

Lower-case namespaced identifiers are validated by the central writer. Current
actions are:

- `world_entry.created|updated|deleted`
- `campaign_override.created|updated|removed|suppressed|restored`
- `region.created|updated|deleted`
- `campaign.time_advanced`
- `campaign_biome.updated`, `global_biome.updated`
- `campaign.atmosphere_configured`
- `campaign.time_simulation_configured`

## 9. Target identity/snapshot strategy

`target_content_type` is nullable `SET_NULL`; `target_object_id` is a string and
`target_label` is copied at write time. GenericForeignKey is only a navigation
convenience. Audit details remain usable after target deletion.

## 10. operation_id

Every row gets an indexed UUID by default. Callers may provide a valid UUID for
future high-level grouping; no distributed tracing was introduced.

## 11. before/after/metadata schema

All components are JSON objects or null, JSON-round-tripped to stable plain data.
`changed_fields` is included for ordinary updates. Domain summaries do not copy
generated histories, request bodies or atmospheric grids.

## 12. Audit serializer architecture

`world.services.audit` contains the only supported writer plus explicit
serializers for WorldEntry, CampaignEntityOverride, Region, atmospheric/time
settings and compact biome diffs. `model_to_dict()` is not used.

## 13. Secret-redaction policy

Developer misuse is rejected rather than silently redacted. Recursive JSON keys
matching password, authorization, cookie, CSRF, token/OAuth, credential,
client-secret or session markers raise `ValidationError`. Views never pass
`request.POST`. GM lore values are allowed because protected lore is not a
technical credential.

## 14. Payload-size policy

Each of `before_state`, `after_state` and `metadata` is capped at 128 KiB of
canonical UTF-8 JSON. Summary and target label are capped at 500 characters.
Oversize/non-finite/non-serializable data fails explicitly; nothing is truncated.

## 15. Transaction/rollback behavior

The writer deliberately opens no independent transaction. Every integration is
called inside the domain mutation's `transaction.atomic()`. Audit serialization
or DB failure therefore rolls back both rows. Forced rollback, denied permission,
validation failure and oversized WorldEntry tests prove no success audit remains.

## 16. Signals

No signals are used. Explicit service boundaries know actor, scope, summary and
operation semantics, and avoid duplicate/bulk/generated-data rows.

## 17. P1/P2 WorldEntry integration

All six global/campaign create/update/delete services record final revision-aware
snapshots. Blocked global deletion with active overrides writes no audit.

## 18. CampaignEntityOverride integration

Create, meaningful patch update, suppress, restore and remove each produce one
distinct action. Removal records `after_state={"inherits_global": true}`. No-op
updates do not create rows and global base objects remain unchanged.

## 19. Region create/update/delete integration

Direct view writes were moved to `world.services.regions`. Creation follows
validation → server-side center/climate → save → R1 initialization → audit in one
transaction. Update locks the Region, captures before state, lets `Region.save()`
produce the final R1 revision, then audits final state. Cascade-generated weather
children do not produce audit rows. Admin Region writes use the same services.

## 20. Region serializer

Captured fields: name, latitude, longitude, contour, weather geometry revision,
biome, baseline temperature, humidity, elevation and manual-climate flag. No
WeatherState/RegionAreaWeatherState history is copied.

## 21. Campaign time-advance integration

The high-level end of `advance_world()` records old/new world minutes, delta,
requested amount/unit, exact/fast-forward mode, atmosphere enabled flag, coverage
kinds and TimeAdvanceReport ID. `AuditLog.world_minutes` is the successful new
time. Actor is not passed into atmospheric solver functions.

## 22. Proof one advance = one audit

Regression tests cover +10 minutes, +1 Vitok, exact and fast-forward. Each
explicit call with an actor creates exactly one `campaign.time_advanced` row.

## 23. Proof generated weather does not spam audit

Region initialization and exact advancement may create WeatherState and
RegionAreaWeatherState children, but tests assert only the one domain/time row.
AtmosphericSnapshot and six-hour steps never call the audit writer.

## 24. Global biome audit

`update_global_biome_layer()` requires Canon Editor/superuser authority and stores
only scope, authored-cell counts, SHA-256 before/after digests, changed-cell count,
geographic bbox, changed old/new biome counts and grid dimensions. The full layer
is never copied into AuditLog. Global layer admin routes biome writes through it.

## 25. Campaign biome audit

`update_campaign_biome_layer()` requires GM membership in that exact campaign,
validates land/codes, saves the sparse override and creates one compact campaign
row. Forged cross-campaign POST and read-only Leaflet GET are tested.

## 26. Admin mutation audit

WorldEntry admin create/update/delete routes through P1 services and is tested via
real Django admin requests for exact one-row behavior. Region and biome admin
writes route through audited services. Generic override, legacy map layer and
AtmosphericConfig admin paths are read-only to prevent bypass. AuditLog admin is
strictly read-only.

## 27. Campaign audit permissions

Allowed: that campaign's GM or superuser. Denied: other campaign GM, player and
Canon Editor without membership. List and detail both enforce the same scoped
query, including IDOR tests.

## 28. Global audit permissions

Allowed: `world.manage_global_canon` or superuser. Denied: ordinary GM/player.
Orphaned deleted-campaign rows cannot leak into global history.

## 29. Final access matrix

| Scope | Superuser | Canon Editor | Own GM | Other GM | Player |
|---|---:|---:|---:|---:|---:|
| Global audit | yes | yes | no | no | no |
| Campaign audit | yes | membership required | yes | no | no |

## 30. Campaign Audit UI

Server-rendered list/detail pages are linked from the campaign quickbar and retain
the existing universal time control.

## 31. Global Audit UI

Server-rendered list/detail pages are linked only for Canon Editors/superusers and
from the global canon page.

## 32. Pagination/filtering

Pagination is 50 rows. Filters: exact action, actor snapshot substring, target
`app_label.model`, source, and campaign world-time range or global real-date range.
Ordering is `occurred_at DESC, id DESC`; select_related prevents N+1 reads.

## 33. Deleted target behavior

ID/label/content type remain visible after target deletion; tests open the detail
page successfully after deleting a Region.

## 34. Deleted actor behavior

Actor FK becomes null while the label snapshot remains. UI renders the snapshot.

## 35. Example WorldEntry audit

Create: before null, after contains global scope, kind/slug/title/summary/body and
revision 1. Update: before revision 1, after revision 2 plus changed fields.

## 36. Example Region geometry audit

One update captures old/new contour and anchor coordinates; after state contains
the final incremented `weather_geometry_revision`.

## 37. Example +1 Vitok audit

One row records old 0, new 10080, delta 10080 minutes, requested amount 1/unit
`turns`, exact mode, atmosphere flag and new world time 10080.

## 38. Database indexes

Indexes cover campaign+real timestamp, campaign+world minutes, actor+timestamp,
action, source, content-type+object ID and operation ID. JSON is not indexed.

## 39. Query count/performance

Local SQLite rollback-only benchmark, 12 repetitions:

- WorldEntry raw median 2.40 ms; audited 4.48 ms; increment 2.08 ms.
- Region rename raw median 1.02 ms; audited 2.12 ms; increment 1.10 ms.
- Empty-campaign exact Vitok without user report boundary 4.07 ms; with
  TimeAdvanceReport+audit 5.46 ms (combined increment 1.39 ms).
- Materializing an audit list with all three relations selected used one query
  for the available 25 rows.

The audit call remains outside atmospheric cell/timestep loops.

## 40. Tests added

`world.tests.test_audit_p3` covers model/snapshots, append guards, secret and size
rejection, transaction rollback, each domain lifecycle, exact/fast-forward,
admin integration, access matrix/IDOR, orphan scope, filters, pagination, escaping,
deleted actor/target and GET/no-spam behavior.

## 41. Full test result

Final result: 269 tests passed (246 baseline + 23 P3 tests).

## 42. manage.py check

Passed with zero issues.

## 43. makemigrations --check --dry-run

Passed: no changes detected.

## 44. M1 regression status

Leaflet routes, atlas GET behavior and map editor flow remain intact. M1 was not
redesigned.

## 45. R1 regression status

Region revision, current weather selection, initial physical/legacy lifecycle and
area/point separation remain intact. Region services audit the final R1 revision.

## 46. Atmosphere regression/scope confirmation

No climate equations, coefficients, timestep, snapshot format or fast-forward
physics changed. Atmospheric and generated weather rows are outside AuditLog.

## 47–50. Persistent documentation

`WORLD_HANDOFF_v2.md`, `AGENTS.md`, Architecture Guardrails and Master Roadmap now
record P3 invariants/status. The future CharacterSheet-log item remains unchecked
because CharacterSheet is not implemented.

## 51. Known limitations

- Append-only protection is application/ORM/admin-level, not a PostgreSQL trigger.
- No export/archive/prune UI and no retroactive backfill by design.
- Diff UI shows escaped before/after JSON rather than a semantic diff library.
- Existing admin-only domains outside the explicitly integrated P3 boundaries are
  not retroactively modeled as events.
- SYSTEM/INTEGRATION/IMPORT are supported by the writer but no automatic sources
  were invented.

## 52. Future P4 integration path

ApprovalRequest may later store/propagate one operation ID; approval decisions and
their resulting mutations can share that operation ID without changing AuditLog.
P4 was not implemented.

## 53. Future P5 integration path

WorldEvent remains world-state/event semantics. A future WorldEvent service can
record one meaningful SYSTEM/USER audit at its mutation boundary, not solver spam.
P5 was not implemented.

## 54. Scope stop confirmation

P4, P5, CharacterKnowledge, M2, Travel and C5 were not started.
