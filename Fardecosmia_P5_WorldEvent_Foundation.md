# ФАРДЕКОСМИЯ — P5
## WorldEvent Foundation
### Definitions, world-time triggering, immutable occurrences, effects boundary and readable world history

> **Рекомендуемый уровень Codex Reasoning / Intelligence: ОЧЕНЬ ВЫСОКИЙ.**
>
> Причина: P5 пересекает Campaign world time, `advance_world()`, fast-forward,
> TimeAdvanceReport, AuditLog, будущие Travel/Quest/Economy/Character systems
> и уже существующие исторические WorldEvent traces. Ошибка здесь может создать
> дублирующую event architecture или нарушить причинность world state.
>
> Перед началом обязательно перечитать:
>
> - `AGENTS.md`
> - `WORLD_HANDOFF_v2.md`
> - `ARCHITECTURE_GUARDRAILS.md`
> - `MASTER_ROADMAP.md`
> - P3 AuditLog implementation report
> - P4 ApprovalRequest implementation report
> - P4.5 Account/Email/Campaign implementation report
> - `TIME_ADVANCE_REPORTS.md`
> - `WEATHER_SYSTEM.md`
> - C4 / C4.1 / C4.2 reports
>
> **НЕЛЬЗЯ начинать миграции P5 до выполнения Phase 0 Existing WorldEvent Audit.**
>
> P5 НЕ начинает CharacterKnowledge, M2, Travel, Inventory/Ledger/Purchases,
> Quest engine, faction simulation, catastrophe engine, C5, cyclone entities,
> player Fog of War или WorldEvent atmospheric forcing.

---

# 0. EXISTING WORLDEVENT AUDIT — BLOCKING STEP

В старой документации уже существуют упоминания `WorldEvent` в `advance_world()`
и `TimeAdvanceReport`. Поэтому перед любым новым model/schema design:

1. Найти ВСЕ существующие `WorldEvent` models, migrations, services,
   managers/querysets, admin, forms/views/URLs/templates, references в
   `advance_world()`, `TimeAdvanceReport`, tests, fixtures/dev rows, generic
   relations и world-minute crossing logic.
2. Зафиксировать семантику каждого поля: schedule, occurrence, mutable status,
   trigger time, created time, description, effects, target/location.
3. Проверить development DB: число rows, заполненные поля, authored/fired rows,
   использование в report history.
4. Классифицировать existing model как definition/schedule, occurrence/history,
   смешанную модель или legacy-заготовку.
5. До окончания аудита запрещено создавать второй `WorldEvent`, переименовывать
   table, удалять rows, делать destructive migration или менять event semantics
   `advance_world()`.
6. Implementation report начинается разделом `EXISTING WORLDEVENT AUDIT`.

---

# 1. Главная концептуальная граница

P5 окончательно разделяет:

```text
WORLD EVENT DEFINITION / SCHEDULE
«что может/должно произойти и при каком trigger»
                ↓
WORLD EVENT OCCURRENCE
«это конкретное событие реально произошло в мире»
```

Definition можно изменить/отключить до срабатывания. Occurrence — immutable
исторический факт.

---

# 2. Не навязывать имена моделей до аудита

Желаемая семантика — `WorldEventDefinition` + `WorldEventOccurrence`, но existing
model может уже занимать одну роль. Допустимы стратегии:

- existing occurrence-like → сохранить и добавить definition/schedule;
- existing schedule-like → сохранить и добавить occurrence;
- mixed with real data → additive split preserving IDs/data;
- truly empty legacy → clean evolution только после proof.

В отчёте объяснить выбранную стратегию. Не создавать конкурирующую систему.

---

# 3. WorldEvent != AuditLog != ApprovalRequest != TimeAdvanceReport

```text
AuditLog
«кто/какая система изменила приложение»

ApprovalRequest
«намерение/запрос на разрешение»

WorldEvent
«что произошло внутри мира»

TimeAdvanceReport
«что произошло за конкретное действие прокрутки времени»
```

WorldEventOccurrence — самостоятельная permanent history row. Report может
содержать compact snapshot/reference, но не становится источником истории.

---

# 4. Scope P5

P5 реализует foundation:

```text
definition/schedule
manual event
world-time trigger
crossing detection
occurrence history
safe effect boundary
audit integration
time-report integration
GM event UI
human-readable presentation
```

Не реализовывать weather-trigger rules, arbitrary conditions, recurrence,
faction turns, quest state machine, travel progress, economic ticks или
catastrophe simulation.

---

# 5. Initial trigger types

Только:

```text
MANUAL
WORLD_TIME
```

Architecture может позже поддержать registered `DOMAIN_SIGNAL`, `CONDITION`,
`RECURRING`, `TRAVEL_PROGRESS`, `QUEST_STATE`, `WEATHER_THRESHOLD`, но P5 их не
реализует.

Никакого `eval()`, `exec()` или arbitrary expression language в БД.

---

# 6. Definition / schedule semantics

После existing audit schedule/definition должна иметь эквивалент:

```text
id
campaign

event_type
title
summary/description

trigger_type
trigger_config JSON
trigger_version

effect_type nullable
effect_payload JSON
effect_version nullable

enabled
one_shot

target_content_type nullable
target_object_id
target_label

optional Region / lat / lon

created_by nullable
created_by_label_snapshot
created_at
updated_at
revision

scheduled_world_minutes / indexed due-time field
```

Не обязательно использовать ровно эти названия.

---

# 7. Occurrence semantics

Historical occurrence должна хранить durable snapshots:

```text
id
campaign
definition nullable

event_type_snapshot
title
summary

occurred_world_minutes
scheduled_world_minutes nullable
occurred_at real timestamp

source
actor nullable
actor_label_snapshot

trigger_type_snapshot
trigger_snapshot JSON

target_content_type nullable
target_object_id
target_label

optional Region/location snapshot

effect_type_snapshot nullable
effect_result JSON

operation_id UUID
```

Если existing `WorldEvent` уже играет эту роль — эволюционировать его.

---

# 8. Immutability

Occurrence после успешного creation immutable. Normal application code не
может менять occurred time/title/summary/trigger/effect result и удалять row.
Admin occurrence — read-only.

Definition до occurrence можно create/update/disable. Later edits definition не
переписывают occurrence snapshots. Не cascade-delete history.

---

# 9. Campaign scope and visibility

P5 campaign-scoped. Every definition/occurrence belongs to exactly one Campaign.

До CharacterKnowledge/player publication:

```text
WorldEventDefinition = GM-only
WorldEventOccurrence = GM-only objective history
```

Occurrence НЕ означает, что все персонажи знают о событии.

---

# 10. Event types and human presentation

Use stable namespaced strings, future examples:

```text
travel.departed
travel.arrived
settlement.captured
quest.started
character.died
weather.catastrophe
narrative.event
```

P5 может использовать `narrative.event` как production-safe no-effect type.

Structured event types should have human presenters. Normal templates never
require raw JSON.

---

# 11. Safe effect registry

Если event applies domain effects, effect type must be registered:

```python
register_world_event_effect(
    "some.domain.effect",
    validator=...,
    presenter=...,
    apply=...,
)
```

Запрещён generic JSON model mutation engine.

P5 не придумывает fake Travel/Inventory/Settlement effects. Effect boundary
можно доказать test-only handler. Narrative event may have `effect_type=null`.

---

# 12. Effect atomicity and operation_id

```text
trigger detected
↓
lock/revalidate
↓
registered effect apply
↓
domain audit(s)
↓
create occurrence
↓
world_event.occurred audit
↓
commit
```

Если effect fails: no occurrence, no partial mutation, no success audit.

One occurrence gets one operation UUID reused by all resulting domain audits.

Source semantics should align with P3:

```text
manual GM → USER + actor
WORLD_TIME → SYSTEM + actor=NULL
```

No fake System User.

---

# 13. WORLD_TIME trigger

Initial one-shot schedule uses explicit indexed integer game minutes. If existing
model already has trigger time field, preserve/evolve it.

Critical crossing invariant when time moves `T1 → T2`:

```text
T1 < scheduled_world_minutes <= T2
```

- event exactly at T2 fires;
- event at T1 does not re-fire;
- zero-minute advance fires none.

Multiple due events ordered deterministically:

```text
scheduled_world_minutes ASC
stable ID ASC
```

---

# 14. Exact vs fast-forward truthfulness

WORLD_TIME events MUST fire across fast-forward skipped intervals even though
no detailed WeatherState exists there.

For safe narrative WORLD_TIME events:

```text
exact T1→T2
```

and

```text
fast-forward T1→T2
```

must yield the same ordered occurrence set/times.

Do not tie event firing to AtmosphericGrid timesteps.

---

# 15. Simulation-coupled effects boundary

If an effect should influence simulation after its event time, true chronological
integration may require splitting advancement at event boundaries.

P5 MUST NOT pretend to solve this generically.

Initial production WORLD_TIME effects are limited to effects safe under current
high-level scheduling semantics. Do not add effects that change climate during
fast-forward.

C4 `apply_external_tendencies()` exists for future forcing, but P5 MUST NOT call
it in production.

---

# 16. advance_world() integration

Audit existing implementation first. Preserve one transaction and Campaign row
locking.

Required semantics:

- query due events at high-level advancement, not per cell;
- occurrence stores scheduled world minute, not merely final T2;
- no duplication at exact/spin-up/FF boundaries;
- TimeAdvanceReport sees actual occurrences;
- failed due event must not silently disappear.

If safe event execution fails, preferred behavior is rollback of enclosing
advance transaction rather than committing world time past an unapplied event.
Document final behavior.

---

# 17. One-shot idempotency and concurrency

Initial WORLD_TIME definitions are one-shot.

Need DB/service invariant preventing duplicate occurrence, preferably uniqueness
on one-shot definition plus `select_for_update()`.

Two concurrent GM advances/manual triggers must not double-fire.

PostgreSQL race tests required; SQLite may explicitly skip row-lock proof.

---

# 18. Manual events

GM can manually trigger MANUAL definitions with explicit POST.

Also provide human-friendly way to record a one-off narrative event at CURRENT
Campaign world time without requiring raw JSON. Choose clean architecture after
existing audit; do not force awkward reusable definition UX for one-off history.

No arbitrary historical backdating in P5. Scheduling into past/current should
be rejected with human message; suggest recording event now.

GET never creates/fires events.

---

# 19. Targets and location

Optional generic target is context/navigation only, not permission to mutate.
Store durable `target_label`; occurrence remains readable after target deletion.

P5 may support optional existing Region and/or lat/lon. Do not invent Settlement
or M2 models.

No full WorldEvent map overlay in P5.

---

# 20. Versioning and payload safety

Definition has revision. Occurrence snapshots the definition revision used.

Trigger/effect handlers have stored versions. Unknown/incompatible due handler
must NOT silently execute under new semantics.

JSON components:
- plain deterministic objects;
- recommended 64 KiB limit each;
- reuse P3/P4 secret validation;
- reject password/token/session/OAuth/SMTP/Auth headers/request.POST;
- no silent truncation.

---

# 21. AuditLog integration

Recommended actions:

```text
world_event_definition.created
world_event_definition.updated
world_event_definition.disabled
world_event_definition.removed
world_event.occurred
```

Human summaries:

```text
Запланировано событие «Прибытие каравана».
Событие «Прибытие каравана» произошло.
```

P3 invariant remains:

```text
one explicit advance_world()
→ exactly one campaign.time_advanced AuditLog
```

Additional meaningful `world_event.occurred` rows are valid and are NOT weather
spam.

---

# 22. TimeAdvanceReport integration

Report should include compact references/snapshots of actual occurrences:

```text
occurrence_id
title
occurred_world_minutes
type label
location label
```

Do not copy full trigger/effect payload.

Historical TimeAdvanceReport JSON/templates must remain readable. Inspect old
schema before changing it. Fast-forward report may truthfully contain events
from skipped interval while weather remains macro/final-spinup only.

---

# 23. GM UI — human first

Campaign page:

```text
События мира
```

Tabs/filters:

```text
Предстоящие
Произошедшие
Отключённые
Все
```

Upcoming card/row:

```text
[Запланировано]
Название
Когда по мировому времени
Через сколько игрового времени
Место
Краткое описание
```

Occurrence:

```text
[Произошло]
Название
Мировое время
Реальное время фиксации — secondary
Место
Причина
```

No raw JSON columns.

---

# 24. Definition detail UI

Order:

```text
Название
Статус

Что должно произойти
Когда / как сработает
Где
Что произойдёт после срабатывания

[Запустить сейчас] — MANUAL when allowed
[Изменить]
[Отключить]

История срабатываний

▼ Технические данные
```

---

# 25. Occurrence detail UI

Order:

```text
Название события
Произошло: <world date/time>
Место
Что произошло
Почему произошло
Какие последствия применены
Источник

Связанные изменения AuditLog operation group

▼ Технические данные
```

Internal `MANUAL`, `WORLD_TIME`, UUID, versions and JSON are collapsed technical
information only.

Human cause examples:

```text
Событие было запланировано на это мировое время.
Событие зафиксировал Game Master Руслан.
```

---

# 26. Scheduling form

Human fields:

```text
Название
Описание
Когда произойдёт
Место optional
```

For narrative event consequence may simply be:

```text
Событие будет добавлено в историю мира.
```

Reuse existing world/calendar formatter/input helpers. Do not force normal GM to
calculate raw integer minutes.

---

# 27. Empty states and mobile

```text
Предстоящих событий пока нет.
В истории кампании пока нет событий мира.
```

GM actions:

```text
[Запланировать событие]
[Записать событие сейчас]
```

Responsive/narrow UI; no horizontal raw-table overflow.

---

# 28. Permissions

Campaign GM:
- manage definitions;
- manual trigger;
- view occurrence history.

Player:
- no objective event pages in P5.

GM B:
- no Campaign A events.

Canon Editor only:
- no Campaign event authority.

Superuser:
- central diagnostic override.

All raw URLs must be campaign-scoped and IDOR-safe.

---

# 29. No email / ApprovalRequest overuse

P5 does not automatically email players on occurrence. P4.5 email foundation is
future notification infrastructure only.

GM scheduling does not require ApprovalRequest. Future player proposal may be an
ApprovalRequest whose approved handler creates a domain event, but not by default.

---

# 30. Query/performance strategy

Due-event lookup should use indexed fields:

```text
campaign
enabled/active
trigger_type
scheduled_world_minutes
```

Prefer one interval query `(T1,T2]`, not scans inside atmospheric timestep/cell
loops.

Measure:
- zero due events;
- 10 upcoming;
- advance crossing 10 narrative events;
- list/detail query counts.

P5 overhead should be negligible relative to atmosphere for normal campaigns.

---

# 31. Current baseline

Before modifying P5 run full suite AFTER P4.5.1 patch and record exact:

```text
passed
skipped
runtime
```

Do not assume old 334 baseline if patch added tests.

P5 final suite must preserve that baseline.

Explicitly confirm P4.5.1 resend countdown remains intact.

---

# 32. Required tests — existing behavior baseline

Before migration, document/test current behavior where possible:
- existing event crossing;
- TimeAdvanceReport capture;
- transaction semantics.

These tests become migration safety baseline.

---

# 33. Required crossing tests

1. T1 < event < T2 fires.
2. event == T2 fires.
3. event == T1 does not re-fire.
4. event < T1 does not fire.
5. event > T2 does not fire.
6. zero advance does not fire.
7. multiple events deterministic order.
8. one-shot never fires twice.

---

# 34. Required exact/FF tests

Same safe narrative setup:

```text
exact T1→T2
fast-forward T1→T2
```

Expected same occurrence identity/type/time/order. Weather histories need not
match.

Report tests:
- exact report contains actual occurrences;
- FF report contains crossed occurrences;
- no invented detailed weather;
- old report JSON renders;
- history readable after definition rename/delete.

---

# 35. Required effect tests

With test-only registered effect:
- validation;
- apply exactly once;
- effect failure rollback;
- domain audit + event audit same operation_id;
- no occurrence on failure;
- unregistered effect cannot execute.

---

# 36. Required manual/permission tests

- own GM can trigger;
- player denied;
- foreign GM denied;
- Canon Editor-only denied;
- current world minute stored;
- GET no mutation;
- POST one occurrence;
- cross-campaign IDOR blocked.

---

# 37. Required immutability/migration/security tests

- occurrence update/delete rejected;
- admin occurrence read-only;
- definition update through service;
- later definition edit does not rewrite history;
- deleted target history remains readable;
- missing required target gives safe conflict;
- secrets/oversize/non-JSON rejected;
- old WorldEvent rows preserved according to audited semantics.

---

# 38. PostgreSQL concurrency tests

At minimum:
1. concurrent time advancement cannot double-fire scheduled event;
2. concurrent manual one-shot trigger cannot double-fire.

Explicit SQLite skip is acceptable. Do not weaken locking because local DB is
SQLite.

---

# 39. Browser/manual verification

GM:
1. events empty state;
2. schedule narrative event;
3. inspect human detail;
4. advance to before event — no occurrence;
5. advance crossing — occurrence;
6. TimeAdvanceReport shows it;
7. history shows it;
8. occurrence detail readable;
9. schedule and disable another;
10. record manual current event.

Player:
11. event URLs denied/not exposed.

Mobile:
12. upcoming/history/detail readable;
13. no horizontal overflow;
14. no console errors.

---

# 40. Human-first 5-second acceptance

Upcoming event: immediately clear
- what;
- when;
- where;
- whether it applies an effect;
- whether active.

Occurrence: immediately clear
- what happened;
- when in world time;
- where;
- why;
- what consequences applied.

If not, P5 is not complete even with green backend tests.

---

# 41. Regression scope

P5 must not change:
- C1–C4.2 equations;
- solver 7;
- snapshot format;
- precipitation semantics;
- point pressure sampling;
- R1 area/point weather lifecycle;
- M1 Leaflet CRS/tiles;
- P4 ApprovalRequest semantics;
- P4.5 account/email/campaign lifecycle;
- P4.5.1 resend countdown.

No atmospheric coefficients. No external tendencies wiring.

---

# 42. Future paths — document only

Travel:
```text
Travel starts → departure occurrence
Travel progresses in Travel domain
Arrival → arrival occurrence
```

Quest:
- quest transition may create/react to occurrences later.

CharacterKnowledge:
```text
objective occurrence
↓ publication/propagation
CharacterKnowledge
↓ player-safe history
```

Recurrence:
- separate future phase.

Simulation-coupled event:
- needs split-at-event-boundary design before atmosphere effects.

WorldEvent is NOT a generic pub/sub bus and does NOT convert application to event
sourcing.

---

# 43. Documentation updates after success

## WORLD_HANDOFF

Mark:
```text
P5 WorldEvent completed
next: CharacterKnowledge
```

Add:
- definition/schedule != occurrence;
- occurrence immutable objective campaign history;
- WORLD_TIME crossing `(old,new]`;
- exact/FF cannot miss deterministic scheduled events;
- WorldEvent != AuditLog != ApprovalRequest != TimeAdvanceReport;
- player visibility requires CharacterKnowledge/publication.

## AGENTS

Add concise permanent rules:
- audit existing WorldEvent before replacement;
- no eval/arbitrary JSON model mutation;
- occurrences immutable;
- explicit crossing semantics;
- no atmosphere coupling without simulation-boundary design;
- objective event != player knowledge.

## Guardrails

Add:
- definition and occurrence distinct semantics;
- WorldEvent not application event bus/event sourcing;
- effects through registered domain services;
- occurrence/effects/audits atomic;
- FF must not skip world-time events;
- simulation-coupled effects future phase.

Update Roadmap only after acceptance.

---

# 44. Acceptance Criteria

P5 complete when:

1. Existing WorldEvent implementation audited before migration.
2. Existing DB rows/history preserved.
3. Definition/schedule separate from occurrence semantics.
4. No competing duplicate event architecture.
5. MANUAL works.
6. WORLD_TIME works.
7. Crossing exactly `(old,new]`.
8. Deterministic due ordering.
9. One-shot cannot fire twice.
10. Exact and FF produce same safe event set.
11. FF does not invent WeatherState.
12. Occurrence stores exact world minute.
13. Durable human snapshots stored.
14. Occurrence immutable.
15. Definition safely manageable before occurrence.
16. Definition edits do not rewrite history.
17. Trigger types registered/versioned.
18. No eval/arbitrary conditions.
19. Effects whitelisted/registered.
20. No arbitrary model mutation payload.
21. Effect + occurrence + audits atomic.
22. Failed effect creates no successful occurrence.
23. operation_id groups mutations.
24. P3 integration works.
25. One-time-advance audit invariant remains.
26. TimeAdvanceReport contains actual events.
27. Historical reports remain readable.
28. GM event UI exists.
29. Upcoming/occurrence pages human-readable.
30. Technical JSON collapsed/secondary.
31. Player cannot see objective history.
32. Canon Editor-only gets no campaign authority.
33. Cross-campaign IDOR blocked.
34. Existing calendar formatter reused.
35. No raw minute requirement in normal UI if avoidable.
36. No atmospheric physics changed.
37. No event atmospheric tendencies enabled.
38. P4/P4.5/P4.5.1 regressions pass.
39. Full pre-P5 baseline remains passing.
40. PostgreSQL double-fire tests exist.
41. Browser/manual flow passes.
42. 5-second readability passes.
43. CharacterKnowledge/M2/Travel/Inventory/Quest/C5 not started.

---

# 45. P5 IMPLEMENTATION REPORT

After implementation STOP and return:

```text
P5 WORLDEVENT FOUNDATION REPORT

1. Pre-P5 full-suite baseline
2. Existing WorldEvent audit
3. Existing model fields/semantics
4. Existing migrations/services/usages
5. Existing DB row audit
6. Existing TimeAdvanceReport integration
7. Chosen migration/evolution strategy
8. Changed files
9. Migrations
10. Old-data preservation proof
11. Definition/schedule model semantics
12. Occurrence model semantics
13. Campaign scope
14. Event type strategy
15. Trigger registry
16. MANUAL trigger
17. WORLD_TIME trigger
18. Crossing `(old,new]` proof
19. Deterministic ordering
20. One-shot/idempotency strategy
21. Definition revision/versioning
22. Trigger versioning
23. Effect registry
24. Effect versioning
25. Generic narrative event
26. Effect atomicity
27. Failed-effect rollback proof
28. operation_id propagation
29. Occurrence immutability
30. Definition update/disable/delete behavior
31. Target/location strategy
32. Deleted-target history behavior
33. Source/actor snapshots
34. World-time vs real-time semantics
35. advance_world integration
36. Exact-mode event behavior
37. Fast-forward event behavior
38. Exact-vs-FF equivalence proof
39. Simulation-coupled-effect limitation
40. TimeAdvanceReport integration
41. Historical report compatibility
42. P3 AuditLog integration
43. Human audit summaries
44. P4 boundary confirmation
45. CharacterKnowledge visibility boundary
46. GM events list
47. Upcoming events UI
48. Occurrence history UI
49. Definition detail
50. Occurrence detail
51. Manual event UI
52. Human trigger/cause presentation
53. Collapsed technical details
54. Mobile/responsive behavior
55. Permission matrix
56. Player denial
57. Canon Editor boundary
58. IDOR tests
59. Secret/payload limits
60. Event crossing tests
61. Manual trigger tests
62. Effect tests
63. Immutability tests
64. TimeAdvanceReport tests
65. Existing-data migration tests
66. PostgreSQL concurrency tests/skips
67. Browser/manual verification
68. 5-second readability acceptance
69. Query counts
70. Performance
71. Tests added
72. Full test result
73. manage.py check
74. makemigrations --check --dry-run
75. git diff --check
76. P3 regression
77. P4 regression
78. P4.5 regression
79. P4.5.1 resend-countdown regression
80. M1 regression
81. R1 regression
82. Atmosphere/C4.2 regression
83. Confirmation external atmospheric tendencies unused
84. WORLD_HANDOFF update
85. AGENTS update
86. Guardrails update
87. Master Roadmap update
88. Known limitations
89. Future Travel path
90. Future Quest path
91. Future CharacterKnowledge path
92. Future recurrence path
93. Future simulation-coupled event path
94. Confirmation no CharacterKnowledge/M2/Travel/Inventory/Quest/C5 was started
```

Stop after report.
