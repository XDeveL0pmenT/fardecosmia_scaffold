# ФАРДЕКОСМИЯ — P3
## AuditLog Foundation
### Immutable meaningful-action history for global canon and campaign state

> Перед началом перечитать актуальные:
>
> - `AGENTS.md`
> - `WORLD_HANDOFF_v2.md`
> - `ARCHITECTURE_GUARDRAILS.md`
> - `MASTER_ROADMAP.md`
> - P1/P2 implementation report
> - M1 report
> - R1 report
>
> P1/P2 считается завершённой foundation.
>
> P3 добавляет **историю значимых изменений**, но НЕ является:
> - application log;
> - exception log;
> - event-sourcing rewrite;
> - WorldEvent;
> - WeatherState history;
> - ApprovalRequest.
>
> НЕ начинать:
> - P4 ApprovalRequest;
> - P5 WorldEvent;
> - CharacterKnowledge;
> - M2 Countries/Settlements/Roads;
> - Character/Fog;
> - Travel;
> - C5;
> - M1.5 analytical climate layers.

---

# 0. Главная цель

После P3 GM / Canon Editor должен иметь ответ на вопросы:

```text
КТО изменил состояние?
ЧТО именно было изменено?
КОГДА это произошло в реальном времени?
КАКОЕ было world time кампании?
К КАКОЙ кампании относилось действие?
КАКОЙ объект был затронут?
ЧТО было до?
ЧТО стало после?
ОТКУДА пришло изменение?
```

AuditLog нужен для debugging, GM history, понимания происхождения текущего state, будущих session recaps, P4 ApprovalRequest, P5 WorldEvent и контроля глобального канона.

# 1. Что P3 НЕ должна логировать

НЕ создавать AuditLog на:
- каждый `WeatherState`;
- каждый `RegionAreaWeatherState`;
- каждый `AtmosphericSnapshot`;
- каждый atmospheric timestep/grid cell/macro-step;
- каждый GET;
- открытие Region page;
- Leaflet pan/zoom/tile/hover/point inspection;
- internal cache update.

# 2. Что P3 должна логировать

Минимальная интеграция:

## Global canon
- global `WorldEntry` create/update/delete;
- global biome/shared atlas edit, если write path существует.

## Campaign state
- campaign-only `WorldEntry` create/update/delete;
- `CampaignEntityOverride` create/update/remove;
- suppression/restoration;
- Region create/update/delete;
- Campaign biome override edit;
- campaign world time advance.

Если существуют другие очевидные GM-authored write actions, сделать inventory и подключить только те, чей scope однозначен.

# 3. Один пользовательский action ≠ тысячи audit rows

Пример:

```text
GM нажал +1 Виток
```

Внутри могут создаться сотни/тысячи generated rows. AuditLog получает одну high-level запись:

```text
campaign.time_advanced
old_world_minutes
new_world_minutes
delta_minutes
exact / fast-forward
```

# 4. AuditLog vs WorldEvent

AuditLog отвечает: **кто/что изменило данные приложения?**

Future WorldEvent отвечает: **что произошло внутри мира?**

Не смешивать.

# 5. AuditLog vs Weather history

`WeatherState` / `RegionAreaWeatherState` — generated physical history.

AuditLog — meaningful authored/control change.

# 6. AuditLog model

Добавить model `AuditLog` (или `AuditEntry`, если naming проекта лучше).

Recommended fields:

```text
id
occurred_at
source
action
campaign nullable
campaign_id_snapshot nullable
campaign_label_snapshot
world_minutes nullable
actor nullable
actor_label_snapshot
target_content_type nullable
target_object_id
target_label
summary
before_state JSON nullable
after_state JSON nullable
metadata JSON
operation_id UUID
```

Prefer один real timestamp:

```text
occurred_at = auto_now_add
```

# 7. Scope semantics

Global audit:

```text
campaign = NULL
world_minutes = NULL
```

Campaign audit:

```text
campaign = Campaign
world_minutes = current Campaign.world_minutes
```

Не подставлять `0` для global world time.

# 8. Campaign durability

Рекомендуется:

```text
campaign FK nullable, SET_NULL
campaign_id_snapshot
campaign_label_snapshot
```

Audit остаётся читаемым после будущего удаления Campaign.

# 9. Actor

```text
actor FK -> settings.AUTH_USER_MODEL
nullable
SET_NULL
actor_label_snapshot
```

Actor nullable для будущих SYSTEM / INTEGRATION / IMPORT actions.

Не создавать fake System User.

# 10. Source

Stable choices:

```text
USER
SYSTEM
INTEGRATION
IMPORT
```

Django admin остаётся `USER`; optional metadata может хранить `channel=django_admin`.

# 11. Action identifiers

Action — namespaced string, не rigid Django choices enum с migration на каждый новый subsystem.

Examples:

```text
world_entry.created
world_entry.updated
world_entry.deleted
campaign_override.created
campaign_override.updated
campaign_override.removed
campaign_override.suppressed
campaign_override.restored
region.created
region.updated
region.deleted
campaign.time_advanced
campaign_biome.updated
global_biome.updated
```

# 12. Target identity

Audit должен переживать target deletion.

Хранить:

```text
target_content_type nullable SET_NULL
target_object_id string
target_label string
```

Optional GenericForeignKey допустим только как convenience navigation.

# 13. Target IDs

`target_object_id` хранить строкой, чтобы future UUID/int PK работали одинаково.

# 14. Summary

Каждая запись имеет краткий deterministic summary без LLM/API.

# 15. before_state / after_state

Хранить только meaningful audited fields.

НЕ делать blind `model_to_dict()` по произвольной модели.

# 16. Audit serializer architecture

Создать центральный механизм в `world/services/audit.py` или архитектурно подходящем месте.

Использовать explicit serializer whitelist для audited domains.

Goal:
- deterministic JSON;
- stable schema;
- no external credentials;
- no accidental giant payloads.

# 17. Technical secret safety

Никогда не хранить в audit payload:
- passwords;
- cookies;
- CSRF tokens;
- authorization headers;
- API/OAuth tokens;
- Roll20/extension credentials;
- DB credentials.

Не dump'ить request.POST целиком.

# 18. GM world secrets

GM-only lore не равно technical credential. Его можно хранить в global/campaign audit, потому что audit page сама защищена.

P3 не реализует CharacterKnowledge.

# 19. Payload size policy

Установить конкретный технический максимум serialized component/action, ориентир 64–128 KiB.

Не silently truncate arbitrary JSON.

Если domain может превысить лимит — использовать compact domain serializer/digest/summary или явную ошибку.

# 20. Region serializer

Для Region capture минимум:

```text
name
map_latitude
map_longitude
map_polygon
weather_geometry_revision
biome
base_temperature
humidity
elevation
use_manual_climate_overrides
```

Не включать WeatherState history.

# 21. Region update

Один user save → одна audit row.

Metadata желательно содержит:

```json
{"changed_fields": ["map_polygon", "map_latitude", "map_longitude"]}
```

# 22. WorldEntry serializer

Capture:

```text
scope
campaign id if campaign-only
kind
slug
title
summary
body
revision
```

# 23. CampaignEntityOverride serializer

Capture:

```text
campaign
target type/id/label
patch
is_suppressed
revision
base_revision_at_creation
```

# 24. Biome edit serializer

Не хранить full global/campaign biome layer before/after без необходимости.

Preferred compact metadata:

```text
scope
changed_cell_count
affected bbox/extent
old/new biome counts where practical
revision before/after if available
digest before/after
```

Если write request уже является небольшим explicit cell diff — diff можно сохранить.

# 25. Campaign time advance serializer

Одна audit row на explicit advance action.

Capture:

```text
old_world_minutes
new_world_minutes
delta_minutes
requested unit/action
exact vs fast-forward
atmospheric enabled?
optional compact TimeAdvanceReport summary
```

Не хранить full atmospheric grid/snapshot.

# 26. Time-advance world_minutes

Для `campaign.time_advanced`:

```text
AuditLog.world_minutes = new/current world time after successful advance
```

before_state хранит old, after_state — new.

# 27. Append-only semantics

Normal application exposes only create/read.

No normal update/delete UI/API.

Django admin для AuditLog:
- read-only;
- no add;
- no change;
- no delete;
- даже для superuser через обычный UI.

Future maintenance/archive — separate tool.

# 28. Model protection

Если practical, instance update/delete можно запрещать model-level guard'ом.

Не вводить сложные PostgreSQL-only triggers в P3; SQLite dev compatibility сохранить.

Документировать, что append-only invariant — application/service/admin layer.

# 29. No purge UI

Не добавлять clear history/TTL/pruning cron.

# 30. Central audit write API

Например:

```python
record_audit(
    *,
    action,
    source,
    actor=None,
    campaign=None,
    world_minutes=None,
    target=None,
    target_label=None,
    summary,
    before_state=None,
    after_state=None,
    metadata=None,
    operation_id=None,
)
```

Business services используют его вместо прямого `.objects.create()`.

# 31. operation_id

Добавить UUID `operation_id`, indexed.

Нужен для будущей группировки нескольких meaningful mutations одного high-level operation и интеграции P4/P5.

Не строить distributed tracing.

# 32. Transaction semantics

Audit должен commit/rollback вместе с mutation.

Preferred:
- same `transaction.atomic()`;
- audit after successful mutation but before commit;
- rollback removes both.

Не отправлять audit в external queue.

# 33. Не использовать Django signals как primary mechanism

`post_save` / `post_delete` плохо знают actor/scope/summary и дают double/bulk issues.

Primary integration — explicit domain services.

Signals допустимы только для narrow justified gap и должны быть описаны в report.

# 34. P1/P2 integration

Instrument фактические P1/P2 write services:

```text
create/update/delete global WorldEntry
create/update/delete campaign WorldEntry
set/remove CampaignEntityOverride
suppress/restore override
```

# 35. Global delete

Audit только successful delete.

Capture before state + durable target snapshots.

Сохранить P1/P2 protection от удаления global object с active overrides.

# 36. Override removal

Removal означает `return to inheriting global canon`.

before = previous override.
after может быть `{ "inherits_global": true }`.

# 37. Region integration

Audit Region create/update/delete.

Если current view сохраняет Region напрямую, небольшой refactor в domain service разрешён.

Не сломать C3.5 autoconfig, R1 revision, M1 contour flow.

Audit должен фиксировать final server-authoritative state.

# 38. Region create ordering

Concept:

```text
validate
→ calculate center/climate server-side
→ Region save
→ R1 lifecycle
→ one region.created audit
→ commit
```

No WeatherState child audit.

# 39. Region update ordering

Capture before → perform authoritative save/revision → capture final after → one audit.

# 40. Region delete

Capture state/label before delete.

Cascade child generated data must NOT create child audit spam.

# 41. Campaign time advancement integration

Audit at high-level campaign advancement boundary.

Если `advance_world()` не знает actor — добавить clean wrapper/context, но НЕ прокидывать actor через атмосферные solver functions.

# 42. Failed actions

Permission/validation/transaction failure не создаёт success AuditLog.

Security-attempt logging — не P3.

# 43. Global biome integration

Global shared biome edit by Canon Editor:

```text
global_biome.updated
campaign=NULL
```

Tile rebuild/view не является canon edit и не audit'ится.

# 44. Campaign biome integration

Campaign sparse override edit by own GM:

```text
campaign_biome.updated
```

Capture compact diff/summary.

# 45. Admin mutations

P1/P2 allows Canon Editor some admin writes. Они тоже должны audit'иться.

Preferred route через same domain services или carefully instrumented ModelAdmin hooks.

One admin edit → exactly one AuditLog.

# 46. Superuser

Superuser mutations audit'ятся как обычный actual actor.

# 47. SYSTEM future compatibility

Audit API supports:

```text
actor=None
source=SYSTEM
```

P3 не должна invent automatic system audit spam.

# 48. INTEGRATION future compatibility

Support `source=INTEGRATION` для будущего Roll20/connectors, но не логировать raw secrets/payload noise.

# 49. Campaign audit permissions

Campaign Audit page:
- own Campaign GM — allowed;
- superuser — allowed;
- Canon Editor without membership — denied;
- player — denied;
- other Campaign GM — denied.

Use P2 access helpers.

# 50. Global audit permissions

Global Audit page:
- Canon Editor — allowed;
- superuser — allowed;
- ordinary GM — denied;
- player — denied.

# 51. No leakage

Campaign A audit page не содержит B/global rows.

Global page не раскрывает campaign logs.

# 52. Audit UI

Server-rendered minimal UI.

Suggested:

```text
Campaign → История изменений
Global Canon → История изменений
```

No frontend framework.

# 53. Audit list columns

At minimum:

```text
Real timestamp
World time if campaign
Actor
Summary/action
Target
Source
```

# 54. Audit detail

Показывать:

```text
summary
actor
source
real timestamp
campaign
world time
target
operation_id
before
after
metadata
```

JSON escaped/preformatted safely.

# 55. Diff

No large diff library required.

Minimum:
- before/after blocks;
- changed_fields where available.

# 56. Pagination

Server-side, ориентир 50 rows/page.

# 57. Filtering

Campaign audit minimum:
- action;
- actor;
- target type;
- source;
- world time from/to if practical.

Global:
- action;
- actor;
- target type;
- real date range if practical.

No Elasticsearch.

# 58. Ordering

Default:

```text
occurred_at DESC, id DESC
```

Не сортировать только по world_minutes.

# 59. Real vs world time UI

Явно различать:

```text
Реальное время изменения
Мировое время кампании
```

Не интерпретировать world_minutes как Gregorian datetime.

# 60. Indexes

Recommended:

```text
campaign + occurred_at
campaign + world_minutes
actor + occurred_at
action
source
target_content_type + target_object_id
operation_id
```

Не index JSON payloads в P3.

# 61. Migration

P3 авторизует next normal migration для AuditLog/indexes.

Apply local development DB.

Не делать retroactive data migration.

# 62. Existing history

Audit history начинается с P3 deployment.

НЕ создавать fake audit rows из старых WeatherState/Regions/P1/P2 history.

# 63. Baseline

До P3:

```text
246 tests passed
```

Сохранить все.

# 64. Model tests

Required:
1. service creates AuditLog.
2. global campaign/world time nullable.
3. campaign captures Campaign/world time.
4. actor nullable for SYSTEM.
5. actor deletion preserves snapshot.
6. target deletion preserves id/label.
7. operation_id exists.
8. metadata default safe.
9. update rejected if append guard implemented.
10. normal delete rejected if guard implemented.

# 65. Transaction tests

1. mutation + audit commit together.
2. forced rollback → neither persists.
3. audit serialization failure → required business mutation rolls back.
4. denied permission → no success audit.
5. validation failure → no success audit.

# 66. WorldEntry audit tests

Global create/update/delete each produce exactly one row with correct before/after/revision/actor and campaign NULL.

Campaign-only entries capture Campaign/world_minutes.

# 67. Override audit tests

Create/update/suppress/restore/remove each produce one audit row, no base mutation, no duplicates.

# 68. Region audit tests

1. create → one audit.
2. geometry edit → one audit.
3. meaningful rename → one audit.
4. final R1 revision captured.
5. GET → zero audits.
6. edit cancel → zero audits.
7. delete → one audit.
8. WeatherState children → zero audits.

# 69. Time advance tests

Critical:
1. +10min → exactly one audit.
2. +1 Vitok → exactly one audit.
3. exact → one audit.
4. fast-forward → one audit.
5. generated weather does not create audit spam.
6. old/new/delta correct.
7. AuditLog.world_minutes = new value.
8. rollback → no change/no audit.

# 70. Biome audit tests

Global:
- Canon Editor edit → one compact global audit.
- ordinary GM forged global edit → denied, no audit.

Campaign override:
- own GM → one campaign audit.
- other GM denied.
- view → zero audit.

# 71. Admin audit tests

If admin writes remain supported:
- Canon Editor create/update/delete audited;
- exactly one each;
- no double logging;
- unauthorized denied;
- superuser audited.

# 72. Secret tests

Audit must never contain password/token/cookie/auth headers/integration credentials.

Developer misuse through metadata should be rejected or redacted according to documented policy.

# 73. Payload limit tests

1. normal Region contour fits.
2. oversized metadata rejected.
3. no silent truncation.

# 74. Permission tests

Campaign A audit:
- GM A yes;
- GM B no;
- player no;
- Canon Editor-only no;
- superuser yes.

Global:
- Canon Editor yes;
- superuser yes;
- GM-only no;
- player no.

Audit detail IDOR checks required.

# 75. UI tests

1. pagination.
2. escaped before/after.
3. filters scope-safe.
4. no Campaign B leak.
5. deleted target audit remains readable.
6. deleted actor audit remains readable.
7. real/world time distinction.

# 76. Performance

Report:
- WorldEntry write overhead;
- Region edit overhead;
- +1 Vitok with/without audit if easy;
- audit list query count.

Avoid N+1 (`select_related` where appropriate).

# 77. Atmosphere performance guardrail

Audit must NOT run per atmospheric timestep.

If Vitok simulation significantly slows because audit is inside solver loop — implementation is wrong.

# 78. Cross-app future support

Audit target strategy must work later for:
- Character;
- Quest;
- Settlement;
- InventoryTransaction.

Do not hardcode only `world` models.

# 79. Future P4

ApprovalRequest can later reuse:

```text
operation_id
actor
campaign
target
```

P3 does not implement approvals.

# 80. Future P5

WorldEvent may later trigger audited SYSTEM writes sharing operation_id.

P3 does not implement WorldEvent.

# 81. Future CharacterKnowledge

Knowledge changes may later become meaningful audit entries, but AuditLog remains GM-only.

# 82. Documentation updates

After success update:

## WORLD_HANDOFF_v2.md
- P3 completed;
- AuditLog = meaningful append-only action history;
- Weather history remains separate;
- AuditLog != WorldEvent;
- one explicit time advance = one high-level audit.

## AGENTS.md
Concise rules:
- meaningful mutations use audited domain services;
- no secrets;
- no primary signal-based audit;
- no audit on GET/per-step weather.

## ARCHITECTURE_GUARDRAILS.md
- AuditLog != WorldEvent;
- AuditLog != WeatherState history;
- append-only;
- same transaction;
- global/campaign audit scopes separate.

## MASTER_ROADMAP.md
Mark P3 complete only after acceptance, P4 next.

# 83. Non-goals

P3 does NOT implement:
- approvals;
- WorldEvent;
- player knowledge;
- countries/cities/roads;
- Travel;
- Character markers;
- C5;
- analytical climate layers;
- event sourcing;
- log retention/export system.

# 84. Acceptance Criteria

P3 complete when:

1. AuditLog model exists.
2. Real timestamp preserved.
3. Campaign entries capture campaign/world_minutes.
4. Global entries use NULL campaign/world time.
5. Actor can be User or SYSTEM/null.
6. Actor snapshot survives User deletion.
7. Target snapshot survives target deletion.
8. operation_id exists.
9. Action names stable/searchable.
10. Explicit audit serializers used.
11. Technical secrets are excluded.
12. Payload limits exist; no silent truncation.
13. Audit is application-level append-only.
14. Audit admin is read-only.
15. Audit shares transaction with mutation.
16. P1/P2 WorldEntry writes audited.
17. P1/P2 override writes audited.
18. Region create/update/delete audited.
19. One time advance = one high-level audit row.
20. WeatherState/RegionAreaWeatherState/snapshots do not spam audit.
21. Global biome edits audited compactly.
22. Campaign biome overrides audited compactly.
23. GET/Leaflet interaction creates zero rows.
24. Global/campaign audit permissions isolated.
25. Global Audit UI exists.
26. Campaign Audit UI exists.
27. Pagination exists.
28. Useful filters exist.
29. Existing 246-test baseline remains passing.
30. New transaction/security/secret tests pass.
31. M1 intact.
32. R1 intact.
33. Atmosphere physics/snapshot/timestep unchanged.
34. No fake historical backfill.
35. P4/P5/CharacterKnowledge/M2/C5 not started.

# 85. P3 IMPLEMENTATION REPORT

After implementation STOP and return:

```text
P3 AUDITLOG FOUNDATION REPORT

1. Changed files
2. Migration
3. AuditLog model
4. Append-only enforcement
5. Global vs campaign scope semantics
6. Actor model/snapshots
7. Source values
8. Action naming convention
9. Target identity/snapshot strategy
10. operation_id
11. before/after/metadata schema
12. Audit serializer architecture
13. Secret-redaction policy
14. Payload-size policy
15. Transaction/rollback behavior
16. Why signals were/weren't used
17. P1/P2 WorldEntry integration
18. CampaignEntityOverride integration
19. Region create/update/delete integration
20. Region serializer
21. Campaign time-advance integration
22. Proof one advance = one audit
23. Proof WeatherState/RegionAreaWeatherState do not spam audit
24. Global biome audit
25. Campaign biome audit
26. Admin mutation audit
27. Campaign audit permissions
28. Global audit permissions
29. Final access matrix
30. Campaign Audit UI
31. Global Audit UI
32. Pagination/filtering
33. Deleted target behavior
34. Deleted actor behavior
35. Example WorldEntry audit
36. Example Region geometry audit
37. Example +1 Vitok audit
38. Database indexes
39. Query count/performance
40. Tests added
41. Full test result
42. manage.py check
43. makemigrations --check --dry-run
44. M1 regression status
45. R1 regression status
46. Atmosphere regression/scope confirmation
47. WORLD_HANDOFF update
48. AGENTS update
49. Architecture Guardrails update
50. Master Roadmap status
51. Known limitations
52. Future P4 integration path
53. Future P5 integration path
54. Confirmation no P4/P5/CharacterKnowledge/M2/Travel/C5 was started
```

Stop after report.
