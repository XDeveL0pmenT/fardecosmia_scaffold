# Фардекосмия — L1
# Character Location & Initial Placement Foundation

Дата подготовки: 2026-08-24  
Статус: implementation specification  
Рекомендуемый Codex Reasoning: **High / Высокий**

---

# 0. Phase goal

L1 вводит устойчивое физическое положение Character на планете Фардекосмия и
однократный setup начальной позиции.

L1 НЕ является Travel Engine, Player Map, системой исследования или live weather phase.

После L1 должно существовать:

```text
Character
↓
durable planetary position
↓
central effective-location resolver
```

Это позволит будущим системам использовать одну и ту же позицию:

```text
PW2 live ambience
M4 Player Map
Party / Travel
Weather-at-character-point
Quests
location-sensitive economy/jobs
future Visibility & Discovery
```

---

# 1. Mandatory pre-change audit

До migrations и изменений моделей Codex обязан перечитать:

- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Player_Experience_Architecture_v1.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- `P5_5_CHARACTER_IDENTITY_PLAYER_WORKSPACE_REPORT.md`
- `P5_6_CAMPAIGN_CREATION_GM_ELIGIBILITY_ALIGNMENT_REPORT.md`
- `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`

Затем провести аудит существующего `characters.Character`, Campaign relation,
active/archive/controller semantics, GM Character management UI, Player Workspace routing,
M1 map/Leaflet architecture, координатных helpers, Campaign world-time source,
AuditLog conventions, admin, tests/migrations и development DB Character rows.

Не создавать конкурирующую Character model или generic location system до аудита.

---

# 2. Canonical coordinate contract

Фардекосмия использует планетарные угловые координаты:

```text
latitude  ∈ [-90, +90]
longitude ∈ [-180, +180)
```

Longitude горизонтально wrap-around.

Это НЕ Earth geography. Нельзя использовать Earth-radius helpers или Earth distance assumptions.
M1 planetary circumference остаётся **72,500 km**.

Distance calculations не входят в L1, но будущие расстояния должны использовать параметры Фардекосмии.

---

# 3. Recommended storage design

Предпочтительно не добавлять `latitude`/`longitude` прямо в `Character`, если audit не найдёт
существующий подход, который логичнее продолжить.

Рекомендуемая модель:

```text
CharacterLocationState
----------------------
character        OneToOne -> Character
latitude
longitude
created_at
updated_at
```

Причины отдельной модели:

- Character остаётся identity anchor;
- location — отдельное world-facing state;
- проще расширить Travel/effective-location semantics;
- отсутствие row естественно означает «исходная позиция ещё не задана».

Не добавлять сейчас generic foreign key, Settlement FK, POI FK, Region FK как source of truth,
`location_name`, travel status, route, speed, destination, exploration, visibility или weather snapshot.

M2 позже вводит structured world entities. L1 coordinates должны оставаться совместимыми с ними без destructive migration.

---

# 4. Numeric precision

Предпочтительно:

```text
latitude:  DecimalField(max_digits=9, decimal_places=6)
longitude: DecimalField(max_digits=10, decimal_places=6)
```

Допустима эквивалентная точность после аудита project style.
DB constraints + service validation должны защищать диапазоны.

---

# 5. Initial placement semantics

Normal gameplay НЕ даёт GM свободно перемещать Character.

L1 реализует только:

```text
Character без position
↓
GM выбирает исходную точку
↓
preview
↓
explicit confirmation
↓
initial placement becomes durable
```

После успешного initial placement normal GM UI больше не предлагает reposition.

Нельзя реализовывать `Move Character`, `Teleport Character`, drag или edit coordinates как обычные GM actions.

---

# 6. Who may perform initial placement

Supported application flow:

- Campaign GM своей Campaign;
- superuser diagnostic override согласно существующим guardrails.

Не могут PLAYER, foreign GM, canon-editor-only User и ordinary authenticated User.
Character должен принадлежать той же Campaign.

Предпочтительно archived Character не получает новую initial placement через normal UI.
Assignment PLAYER не обязан быть предварительным условием: GM может подготовить позицию активного Character до назначения controller.

---

# 7. One-time rule and concurrency

Initial placement можно выполнить только при отсутствии location row.

После placement второй normal attempt отклоняется даже при тех же координатах.

Service должен использовать:

```text
transaction.atomic()
select_for_update()
authority validation
no-existing-location validation
create location
AuditLog
single commit
```

Два GM не должны одновременно создать две начальные позиции.
Если PostgreSQL доступен — добавить concurrency proof; SQLite skip допустим и документируется.

---

# 8. No normal manual correction

Ошибочная уже подтверждённая позиция не исправляется ordinary GM gameplay button.
Чтобы снизить риск ошибки, UI обязан иметь preview + explicit confirmation.

Technical emergency data repair относится к admin/recovery tooling и не является normal L1 workflow.
Не строить recovery UI без фактической необходимости.

---

# 9. GM placement UI

Предпочтительно использовать существующую M1 planetary map architecture.

На GM Character detail для Character без location:

```text
[Установить исходное положение]
```

Placement page:

```text
Planet Atlas
↓
click point
↓
marker preview
↓
confirmation
↓
[Подтвердить исходное положение]
```

Requirements:

- local Leaflet assets;
- no CDN;
- M1 custom planetary CRS/map conventions;
- horizontal wrap only;
- no Earth distance/scale helpers;
- POST + CSRF for mutation;
- GET never mutates;
- server-side Campaign/Character authority revalidation;
- forged coordinates validated server-side.

Не делать Player Map в L1.

---

# 10. Player-facing semantics

L1 создаёт position как backend truth.

Player Workspace не показывает raw latitude/longitude по умолчанию.
Допустимо минимально изменить Map shell copy:

```text
Положение персонажа пока не отражено.
```

→ после placement:

```text
Ваше положение отражено.
```

или эквивалентно в diegetic-adjacent стиле.

Не показывать весь planetary atlas, неизвестные settlements/POI/Regions или hidden geography.
Player Map ждёт M2/V1/M4.

---

# 11. Central effective-location resolver

Future callers не должны читать location model напрямую по всему проекту.
Создать центральную boundary, концептуально:

```python
get_effective_character_location(character)
```

L1:

```text
no location → None / explicit unavailable result
location exists → canonical latitude + longitude
```

Можно использовать immutable dataclass/value object, если это соответствует project style.

Future resolver сможет учитывать Party Travel / active Travel / domain movement без переписывания PW2 и других callers.
Не реализовывать эти будущие ветки сейчас.

---

# 12. Future structured-location compatibility

M2 позже вводит Settlement/Road/POI/Country.
L1 не моделирует их заранее.

Physical coordinates остаются валидной точкой планеты даже при появлении structured place context.
Не делать generic FK или free-text `location_name` source of truth.

---

# 13. PW2 integration boundary

L1 готовит, но НЕ реализует:

```text
effective Character location
↓
C4.2 point environment sampler
+
RegionalSky
+
World Data / biome
↓
PW2 live ambience
```

L1 не вызывает AtmosphericGrid из Character Workspace.
Никаких temperature/rain/snow/cloud/fog/Ympha/day-night/biome ambience в этой фазе.

---

# 14. Travel integration boundary

Normal future movement:

```text
Character / Party
↓
Travel
↓
route simulation
↓
time advancement
↓
domain-controlled position changes
```

L1 не должен создавать generic public `set_character_location(...)`, который GM/view может вызывать свободно.
Если internal write boundary нужен, supported L1 operation должен быть initial-placement-only.
Future Travel добавит отдельный controlled movement service.

---

# 15. Party compatibility

P6 не начинается.
Не добавлять Party model, party location, party membership или party travel.
Resolver лишь должен быть расширяемым позже.

---

# 16. AuditLog

Initial placement — meaningful world mutation.

Предпочтительное action name:

```text
character.location_initialized
```

Audit включает Character, Campaign, coordinates, actor и existing world-time snapshot conventions.
Не логировать GET/no-op.
Location creation + AuditLog — одна transaction.

---

# 17. Admin

Django admin не должен становиться обходом policy.
Обычным staff/GM нельзя давать простой unaudited coordinate editor.
Предпочтительно location state read-only после creation.
Superuser recovery, если вообще нужен, документируется отдельно как diagnostic/recovery path.

---

# 18. Permission matrix

| Action | PLAYER | Campaign GM | Foreign GM | Canon Editor only | Superuser |
|---|---:|---:|---:|---:|---:|
| View own Workspace location-present state | yes | n/a | no | no | diagnostic |
| Raw exact coords in normal Player UI | no | n/a | no | no | diagnostic |
| Initial placement own Campaign Character | no | yes | no | no | yes |
| Re-place already positioned Character | no | no | no | no | recovery only |
| Forge foreign Character/Campaign | no | no | no | no | diagnostic override only |

---

# 19. Migration safety

Before migration:

- count Character rows;
- capture PK/campaign/owner/archive state without secrets;
- inspect any existing location-like data;
- capture Roll20 binding count.

Migration additive only.

After migration preserve:

- Character PKs;
- Campaign;
- owner/controller;
- archive state;
- Roll20 binding.

Не создавать fake location rows автоматически.

---

# 20. Development DB preservation

Никакого auto-placement:

```text
не ставить всех в 0,0
не использовать Region center
не использовать campaign default
не угадывать из biography
```

Если реальной позиции нет — Character остаётся unplaced до explicit GM setup.

---

# 21. Focused tests

Минимально покрыть:

1. GM initial placement succeeds.
2. AuditLog atomic.
3. PLAYER denied.
4. Foreign GM denied.
5. Canon Editor-only denied.
6. forged foreign Campaign/Character denied.
7. invalid latitude denied.
8. longitude canonicalization/validation.
9. GET does not mutate.
10. second placement denied.
11. concurrency semantics.
12. archived Character policy.
13. unassigned Character policy.
14. migration preserves Character/Roll20 binding.
15. resolver unavailable before placement.
16. resolver returns canonical coords after placement.
17. Player Workspace hides raw coords.
18. GM normal UI offers no re-place after success.
19. no Earth distance helper introduced.
20. bounded queries.

---

# 22. Browser/manual verification

Use isolated temporary data only.

Desktop GM flow:

```text
Character detail
↓
initial placement
↓
map click
↓
preview
↓
confirm
↓
persists
↓
placement action disappears / read-only state
```

PLAYER:

```text
Workspace
↓
Map shell reflects location exists
↓
no raw coords
↓
no GM atlas leakage
```

Also verify foreign GM denial, PLAYER direct URL denial, forged POST denial, refresh persistence,
no console errors, no horizontal overflow at 390×844, no accidental Player Map/Weather implementation.

Delete only isolated browser-test data afterward.

---

# 23. Performance

L1 should be cheap.
Resolver must not create N+1 behavior.
Use `select_related`/prefetch only where justified.
No atmosphere simulation/sampling in L1 performance tests.

---

# 24. Documentation updates

Update on completion:

- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`

Permanent rules:

```text
Character location is domain state, not User state.
Initial placement is one-time setup.
Normal GM free teleport does not exist.
Future movement happens through Travel/domain movement.
Player does not receive raw coordinate/GM atlas leakage.
All future Character-position consumers use central effective-location resolution.
```

Mark L1 complete and do not start next phase automatically.

---

# 25. Checkpoint protocol

Immediately create:

```text
docs/L1_PROGRESS.md
```

After every major milestone record completed work, changed files, migrations, tests,
current failures, browser state and exact next step.

Suggested checkpoints:

```text
Phase 0 audit
↓
Model + migration
↓
Location services + permissions
↓
GM initial-placement UI
↓
Focused tests
↓
Related regressions
↓
Browser verification
↓
Full suite + docs + report
```

---

# 26. Regression requirements

Current known PW1 completion baseline:

```text
422 tests
OK
skipped=8
```

Run focused L1 first.
Then affected regressions at minimum:

- P5.5 Character identity/control;
- P5.6 access/GM eligibility;
- PW1 Character Workspace;
- M1 map tests where relevant;
- R1/C4.2 only if their code is actually touched (prefer not to touch them).

Then full suite.

Final:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
git status
```

---

# 27. Required final report

Create:

```text
L1_CHARACTER_LOCATION_INITIAL_PLACEMENT_REPORT.md
```

Include at least:

1. baseline;
2. existing location audit;
3. storage design;
4. coordinate convention;
5. precision;
6. migration;
7. data preservation;
8. initial placement semantics;
9. permissions;
10. locking/concurrency;
11. GM placement UI;
12. Player disclosure behavior;
13. effective-location resolver;
14. M2 compatibility;
15. PW2 boundary;
16. Travel boundary;
17. AuditLog;
18. admin;
19. tests;
20. browser verification;
21. performance/query behavior;
22. docs;
23. known limitations;
24. confirmation that no next phase started.

---

# 28. Explicit out-of-scope

DO NOT START:

```text
PW2 live ambience/weather
N1 Notes
P6 Party
M2 Countries/Settlements/Roads/POI
V1 Visibility & Discovery
M4 Player Map
Travel Engine
Quests
XP mechanics
Soul HUD
Тиамана mechanics
Roll20 normalized sync
Ledger
Inventory
Economy
Apotheosis/Craft
C5
```

---

# 29. Acceptance criteria

L1 complete only if:

- [ ] Character durably has exact planetary position.
- [ ] Position absent until explicit initialization.
- [ ] Existing Characters preserved.
- [ ] Roll20 bindings preserved.
- [ ] GM can initialize once.
- [ ] PLAYER cannot initialize.
- [ ] Foreign Campaign denied.
- [ ] Second normal placement denied.
- [ ] GET never mutates.
- [ ] Mutation atomic + audited.
- [ ] Central effective-location resolver exists.
- [ ] Player does not see raw coordinates.
- [ ] No free normal GM movement/teleport UI.
- [ ] No accidental Player Map/Visibility implementation.
- [ ] No accidental weather/ambience implementation.
- [ ] No Earth-radius assumptions introduced.
- [ ] Browser desktop/mobile checks pass.
- [ ] Focused/related/full-suite tests pass.
- [ ] `manage.py check` passes.
- [ ] migration drift check passes.
- [ ] `git diff --check` passes.
- [ ] docs/report updated.
- [ ] next phase not started.

---

# 30. Stop condition

After completing L1, write the final report and STOP.
Do not begin N1, P6, M2, V1, PW2 or any other future phase automatically.
