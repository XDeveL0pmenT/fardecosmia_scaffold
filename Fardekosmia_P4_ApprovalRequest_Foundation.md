# ФАРДЕКОСМИЯ — P4
## ApprovalRequest Foundation
### Safe, auditable, human-readable approval workflows

> Перед началом перечитать `AGENTS.md`, `WORLD_HANDOFF_v2.md`, `ARCHITECTURE_GUARDRAILS.md`, `MASTER_ROADMAP.md`, P1/P2 report и P3 report.
>
> P4 создаёт общий безопасный механизм запросов на одобрение.
>
> НЕ начинать P5 WorldEvent, CharacterKnowledge, M2, Inventory/Purchases, Travel, Character/Fog, C5 и M1.5.

---

# 1. Главная схема

```text
REQUEST
  ↓
PENDING
  ↓
APPROVE / REJECT / CANCEL
  ↓
REGISTERED DOMAIN ACTION
  ↓
AUDITLOG
```

P4 НЕ является arbitrary model editor, JSON command executor, WorldEvent или универсальным workflow engine.

---

# 2. UX guardrail — обязательно

Главное требование P4:

```text
HUMAN FIRST
TECHNICAL SECOND
```

На detail page GM должен за 5 секунд понять:
- кто создал запрос;
- чего он хочет;
- что изменится при одобрении;
- какой сейчас статус;
- кто может принять решение.

Основной UI НЕ должен заставлять читать:
- `ContentType`;
- `GenericForeignKey`;
- raw JSON payload;
- UUID;
- internal enum names;
- handler keys;
- raw DB field names.

Технические данные показывать только в свёрнутом блоке:

```text
Технические данные
```

---

# 3. Нормальный вид detail page

Порядок:

```text
Заголовок запроса
Статус

Кто запросил
Кампания
Когда
Мировое время

Что запрашивается
...

Что произойдёт после одобрения
...

[Одобрить] [Отклонить]
[Отменить запрос] — если разрешено

Решение — если уже принято
...

История изменений
...

▼ Технические данные
```

Не строить экран вокруг таблицы внутренних полей.

---

# 4. Русские статусы

Internal:

```text
PENDING
APPROVED
REJECTED
CANCELLED
EXPIRED
```

UI:

```text
Ожидает решения
Одобрено
Отклонено
Отменено
Истекло
```

Не показывать raw enum обычному пользователю.


# 5. Семантика APPROVED

`APPROVED` означает одновременно:

```text
решение принято
+
domain action успешно применён
```

Не сохранять нормальное состояние:

```text
APPROVED, but application failed
```

Если executor не может применить действие:
- вся transaction rollback;
- request остаётся PENDING;
- normal success AuditLog не создаётся;
- GM получает человекочитаемую причину конфликта.

---

# 6. ApprovalRequest model

Recommended:

```text
id
campaign

request_type
status

requester nullable
requester_label_snapshot
requested_at
requested_world_minutes

title
summary

target_content_type nullable
target_object_id
target_label

payload JSON
payload_version

dedupe_key nullable
expires_at nullable

resolved_by nullable
resolved_by_label_snapshot
resolved_at nullable
resolved_world_minutes nullable
resolution_note

result JSON

operation_id UUID
```

Campaign в P4 обязателен.

Global-canon approval workflow сейчас не нужен.

---

# 7. Requester / resolver durability

Requester и resolver:

```text
FK settings.AUTH_USER_MODEL
SET_NULL
```

Плюс human-readable snapshots.

История должна оставаться понятной после удаления User.

Не создавать fake System User.

Future SYSTEM request может иметь requester=NULL.

---

# 8. World time snapshots

При создании:

```text
requested_world_minutes = campaign.world_minutes
```

При resolution:

```text
resolved_world_minutes = campaign.world_minutes
```

Не вычислять их позже из текущего Campaign.

UI по возможности использует существующий human-readable calendar formatter; raw minutes — только secondary/technical.


# 9. Request type registry

`request_type` — stable namespaced string, например будущие:

```text
inventory.purchase
travel.start
inventory.transfer
reward.accept
```

Не добавлять DB migration для каждого нового request type.

Все production request types регистрируются в whitelist registry.

---

# 10. Никаких arbitrary commands

Запрещено:

```json
{"model":"world.Region","method":"delete","pk":15}
```

Запрещено:
- arbitrary model name;
- arbitrary method;
- arbitrary Python;
- raw SQL;
- generic "set field X".

ApprovalRequest — intent, а не remote command API.

---

# 11. Handler registry

Создать central service, например:

```text
world/services/approvals.py
```

Concept:

```python
register_approval_handler(
    "travel.start",
    validator=...,
    presenter=...,
    can_request=...,
    can_approve=...,
    can_cancel=...,
    revalidate=...,
    apply=...,
)
```

Exact API можно адаптировать, но responsibilities должны сохраниться.

---

# 12. Presenter обязателен

Каждый production handler обязан иметь human presenter.

Presenter формирует DTO:

```text
request_type_label
title
summary
details
consequences
target_label
current_applicability_message
```

Normal templates не должны самостоятельно интерпретировать raw payload.

Это mandatory acceptance criterion.

---

# 13. Payload

Payload:
- validated;
- version-aware;
- deterministic;
- JSON serializable;
- bounded;
- без credentials.

Normal UI показывает понятные имена сущностей, а не IDs.

Например payload:

```json
{"origin_id":"42","destination_id":"81"}
```

UI:

```text
Из: Северный порт
В: Красные Врата
```

---

# 14. Payload limits and secrets

Concrete max size: выбрать разумный предел, рекомендовано 64 KiB.

No silent truncation.

Reuse/align with P3 secret safety.

Запрещены:
- passwords;
- auth tokens;
- Roll20 secrets;
- sessions;
- OAuth credentials;
- Authorization headers;
- DB secrets.

Не хранить request.POST целиком.


# 15. Target snapshot

Optional:

```text
target_content_type
target_object_id
target_label
```

Это контекст, а не разрешение на arbitrary mutation.

Если target удалён:
- detail page остаётся читаемой по snapshot;
- approve не падает 500;
- handler выдаёт human conflict.

---

# 16. Request-time validation

До создания PENDING row:

- handler существует;
- requester permission;
- campaign access;
- payload schema;
- target validity;
- current applicability;
- duplicate policy;
- expiry validity;
- size/security validation.

Invalid request не должен появляться в очереди.

---

# 17. Approval-time revalidation

Обязательно revalidate CURRENT state.

Flow:

```text
transaction.atomic
→ select_for_update(request)
→ status still PENDING?
→ expiry?
→ handler revalidate current state
→ apply
→ write domain audit(s)
→ status APPROVED
→ approval audit
→ commit
```

Не доверять только состоянию на момент request creation.

---

# 18. Optimistic conflict support

Handlers могут хранить expected values:

```text
expected_revision
expected_balance
expected_location
expected_quantity
```

Если current state изменился:
- blind overwrite запрещён;
- approval не применяется;
- request остаётся PENDING, если handler не решает явно expire;
- GM получает понятное сообщение.


# 19. Expiry

`expires_at` optional real timestamp.

GET не должен мутировать DB.

Поэтому:
- list/detail вычисляет effective "истёк" для отображения без save;
- approve истёкшего request transactionally переводит его в EXPIRED;
- optional maintenance task later.

Не добавлять generic world_minutes expiry без конкретного use case.

---

# 20. Cancel / reject

Requester может отменить собственный PENDING request, если handler разрешает.

GM может reject own-campaign PENDING request.

Resolution note:
- optional by default;
- handler может потребовать.

После terminal state request нельзя вернуть в PENDING generic способом.

---

# 21. Immutability after resolution

После:

```text
APPROVED
REJECTED
CANCELLED
EXPIRED
```

нельзя менять:
- payload;
- request_type;
- requester;
- target;
- resolution actor;
- status назад.

Generic "undo approval" не делать.

Compensation later = отдельное domain action.


# 22. Central state-transition service

Только services:

```text
create_approval_request(...)
approve_request(...)
reject_request(...)
cancel_request(...)
expire_request(...)
```

Views не делают:

```python
request.status = ...
request.save()
```

Все mutations atomic.

---

# 23. Concurrency

Два GM могут нажать "Одобрить" одновременно.

Use:

```text
select_for_update()
```

Expected:
- executor применяется один раз;
- domain mutation один раз;
- approval audit один раз;
- второй caller видит already resolved.

Concurrency tests обязательны.

---

# 24. Approval permissions

Default approver может быть Campaign GM через P2 access policy.

Но final permission принадлежит handler, чтобы future request type мог сузить/изменить правило.

Не создавать `can_approve_anything` как универсальный GM bypass за исключением superuser central policy.


# 25. Permission boundaries

Campaign GM A:
- видит queue A;
- может решать allowed requests A;
- не видит B.

Canon Editor без CampaignMembership:
- не получает Campaign queue;
- не approve Campaign request.

Player:
- видит только свои requests;
- не видит чужие requests;
- не видит GM controls.

Superuser:
- central diagnostic bypass.

---

# 26. My Requests

Добавить:

```text
Мои запросы
```

Authenticated campaign member видит свои requests.

Не создавать generic форму:

```text
request_type
payload JSON
```

Request creation later идёт из domain UI:
- Купить;
- Начать путешествие;
- Передать предмет.

P4 может не иметь production create button, пока нет настоящего request type.

---

# 27. GM queue

Campaign page:

```text
Запросы на одобрение
```

Default:
```text
Ожидают решения
```

Filters/tabs:

```text
Ожидают
Одобрены
Отклонены
Отменены
Истёкшие
Все
```

Human labels only.

---

# 28. Queue row/card

Show:
- status badge;
- title;
- requester;
- short summary;
- requested time;
- target/person if relevant.

Do not show:
- UUID;
- payload_version;
- ContentType;
- raw object ID;
- dedupe key.


# 29. Detail actions

Authorized GM:
```text
Одобрить
Отклонить
```

Requester when allowed:
```text
Отменить запрос
```

Resolved:
- no active decision buttons;
- clearly show resolver, time, note and result.

---

# 30. Consequences section

Every production handler must explain:

```text
Что произойдёт после одобрения
```

This is mandatory.

GM should never need to infer effect from payload.

---

# 31. Conflict messages

Main UI uses human messages:

```text
Запрос нельзя одобрить: исходный объект уже удалён.
```

```text
Запрос основан на устаревшем состоянии.
```

Future:
```text
Предмет уже недоступен.
Персонаж уже находится в путешествии.
```

Internal exception names/tracebacks do not belong in normal UI.

---

# 32. Empty states

Use readable messages:

```text
Сейчас нет запросов, ожидающих решения.
```

```text
У вас пока нет запросов.
```

No blank table.


# 33. P3 AuditLog integration

Lifecycle actions:

```text
approval_request.created
approval_request.approved
approval_request.rejected
approval_request.cancelled
approval_request.expired
```

All share request `operation_id`.

---

# 34. Human-readable audit summaries

Required:

```text
Создан запрос «...».
GM одобрил запрос «...».
Запрос «...» отклонён.
Запрос «...» отменён.
```

Not acceptable as primary summary:

```text
ApprovalRequest #124 PENDING -> APPROVED
```

Technical transition code can live in metadata/detail.

---

# 35. Domain audit on approval

Approval must NOT suppress normal P3 audit of applied domain action.

Future example:

```text
operation_id X

approval_request.approved
inventory.purchase
ledger.transaction_created
```

Same `operation_id`.

---

# 36. Atomic approval + audit

Transaction:

```text
lock request
revalidate
apply domain action
domain audit
resolve request
approval audit
commit
```

Any failure:
- all rollback;
- request remains PENDING;
- no false successful audit.


# 37. Human snapshots

Store `title` and `summary` at request creation.

Reason:
- target may be renamed/deleted;
- handler presentation can evolve;
- historical request should remain understandable.

Presenter may additionally show current applicability.

---

# 38. Structured result

Recommended:

```text
result JSON
```

Only written on APPROVED.

Example future:
```json
{"travel_id":17}
```

Normal UI:
```text
Путешествие создано.
```

Result also:
- bounded;
- validated;
- secret-safe.

`resolution_note` is human text from approver.
`result` is structured executor output.

---

# 39. Dedupe

Optional `dedupe_key`.

Handler can prevent duplicate PENDING requests for same intent.

Do not expose dedupe key in normal UI.

Service-level validation acceptable.


# 40. Production proof strategy

Не придумывать fake gameplay subsystem.

Codex должен выбрать минимально искусственный вариант:

A. test-only registered handler for full backend/concurrency tests, while production UI provides queue/detail infrastructure without generic create form;

OR

B. narrow existing-domain proposal handler only if it naturally fits current permissions and semantics.

No demo lore/request rows in production DB.

Document choice.

---

# 41. Admin

ApprovalRequest admin is diagnostic, not a status bypass.

Safe default:
```text
superuser read-only
```

No arbitrary editing of payload/status/resolver.

GM resolves through campaign UI.

---

# 42. IDOR

Raw request URL must enforce:
- campaign scope;
- requester ownership;
- GM membership.

Player A cannot see Player B.
GM A cannot see Campaign B.
Canon Editor-only cannot see Campaign A queue.

Use project-consistent 403/404.


# 43. UI readability tests — mandatory

Tests/manual checks must confirm normal detail:

1. raw payload not visible by default;
2. internal `PENDING` not displayed;
3. `ContentType` not displayed;
4. operation UUID only technical;
5. human status present;
6. human request type present;
7. "Что запрашивается" present;
8. "Что произойдёт после одобрения" present;
9. actions visible only to authorized actor;
10. resolved state clearly shows who/when/result;
11. technical JSON escaped;
12. empty states readable.

---

# 44. Browser/manual readability acceptance

Check as GM and requester.

GM:
- empty queue;
- pending queue;
- detail;
- approve;
- reject;
- resolved state;
- narrow/mobile width.

Requester:
- My Requests;
- own detail;
- cancel when allowed;
- no GM controls.

Mandatory subjective acceptance:

```text
За 5 секунд понятно:
что это?
кто просит?
чего хочет?
что произойдёт?
какой статус?
что нужно сделать?
```

Если нет — P4 не закрывать, даже если tests green.


# 45. Style consistency

Use existing Fardecosmia:
- typography;
- cards;
- buttons;
- badges;
- spacing;
- responsive layout.

Do NOT introduce:
- React;
- Tailwind;
- Bootstrap;
- new design system

unless already project-standard.

---

# 46. Reusable technical-details component

Создать/reuse standard collapsed pattern:

```text
Технические данные
```

It can later be reused by:
- ApprovalRequest;
- AuditLog;
- weather debug;
- WorldEvent.

Если P3 сейчас показывает raw технические данные слишком заметно, допустимо сделать **небольшое presentation-only улучшение** P3 с этим reusable component.

Не переписывать P3 business logic.


# 47. Pagination / filters

GM queue:
- 50/page or smaller reasonable value.
- default PENDING.

My Requests:
- 25–50/page.

Minimum filters:
- status;
- request type;
- requester for GM;
- date if simple.

Human labels only.

Optional efficient pending count badge.

---

# 48. Database indexes

Recommended:
```text
campaign + status + requested_at
requester + requested_at
request_type
status
expires_at
operation_id
target_content_type + target_object_id
```

Do not index payload JSON.

---

# 49. Migration

P4 authorizes next normal migration, expected around:

```text
world.0019_approvalrequest
```

Apply locally.

No data migration.
No fake approval rows.


# 50. Required tests

Model:
- campaign required;
- PENDING default;
- requester/resolver snapshots;
- target snapshot;
- operation_id;
- world-time snapshots;
- payload/result limits;
- secret rejection;
- terminal immutability;
- invalid transition rejection.

Registry:
- unknown type rejected;
- payload validation;
- requester permission;
- approver permission;
- human presenter;
- version mismatch safe;
- target conflict safe.

Concurrency:
- double approve applies exactly once.

Revalidation:
- state changes after request → no blind apply.

Audit:
- create/approve/reject/cancel lifecycle;
- same operation_id;
- failed approve no success audit;
- GET no audit.

Permissions:
- requester/GM/cross-campaign/Canon Editor/superuser matrix.

UI:
- readability requirements from section 43.


# 51. Performance

Report:
- create request;
- queue query count;
- detail query count;
- approval framework overhead excluding domain action;
- P3 audit interaction.

Avoid N+1.

P4 must not touch atmospheric timestep loops.

---

# 52. Regression baseline

P3 baseline:

```text
269 tests passed
```

All existing tests must remain passing.

No change to:
- AtmosphericGrid;
- WeatherState;
- RegionAreaWeatherState;
- C1–C4.2;
- R1;
- M1 Leaflet;
- Region geometry lifecycle.


# 53. Future integrations

Inventory/Purchase:

```text
Buy
→ inventory.purchase request
→ GM approve
→ Ledger
→ Inventory
→ AuditLog
```

Travel:

```text
Propose route
→ travel.start request
→ approval
→ Travel
→ AuditLog
```

Future multi-party consent can add separate `ApprovalDecision`/participants later.

Do NOT add multi-party schema before concrete need.

Future SYSTEM proposals may use requester=NULL.

P5 WorldEvent remains separate.


# 54. Documentation update

After success:

## WORLD_HANDOFF

Mark:
```text
P4 completed
next P5 WorldEvent
```

Add:
- ApprovalRequest is registered intent, not arbitrary JSON command.
- APPROVED means successfully applied.
- approval-time revalidation mandatory.
- lifecycle audited through P3.
- UI human-first.

## AGENTS

Concise:
```text
Approval workflows use registered handlers.
Never execute arbitrary model operations from payload.
Revalidate at approval time.
Production approval UI must present human-readable intent/consequences.
```

## Guardrails

Add:
```text
ApprovalRequest != WorldEvent.
ApprovalRequest != arbitrary command queue.
Resolved requests immutable.
Approval + domain mutation atomic.
Human presenter required.
```

Update Master Roadmap only after acceptance.


# 55. Acceptance Criteria

P4 complete when:

1. ApprovalRequest exists.
2. Campaign scope enforced.
3. Lifecycle validated.
4. APPROVED means action successfully applied.
5. Atomic approval.
6. Double approval cannot double-apply.
7. request_type whitelist registry exists.
8. Unknown handler cannot execute.
9. Payload validated/version-aware.
10. Payload/result bounded and secret-safe.
11. Request-time validation exists.
12. Approval-time revalidation exists.
13. Stale request cannot blind-write.
14. Snapshots survive user/target deletion.
15. operation_id propagated.
16. request/resolution world times stored.
17. terminal requests immutable.
18. cancel/reject/expiry work.
19. P3 lifecycle audits work.
20. domain audits can share operation_id.
21. GM queue exists.
22. My Requests exists.
23. IDOR/cross-campaign isolation works.
24. Canon Editor-only has no Campaign approval authority.
25. No generic raw JSON create UI.
26. Normal UI hides internal implementation details.
27. Human intent is obvious.
28. Consequences are obvious.
29. Status/resolution are readable.
30. Technical data is collapsed/secondary.
31. Empty/narrow/mobile states are readable.
32. Manual 5-second readability review passes.
33. Existing 269 tests pass.
34. New concurrency/security/audit/UI tests pass.
35. M1/R1/Atmosphere unchanged.
36. P5/CharacterKnowledge/M2/Inventory/Travel/C5 not started.


# 56. P4 IMPLEMENTATION REPORT

After implementation STOP and return:

```text
P4 APPROVALREQUEST FOUNDATION REPORT

1. Changed files
2. Migration
3. ApprovalRequest model
4. Campaign scope
5. Status lifecycle
6. APPROVED semantics
7. Requester/resolver snapshots
8. World-time snapshots
9. Target snapshot
10. operation_id
11. Payload version/size/security
12. Handler registry
13. Handler contract
14. Human presenter contract
15. Request-time validation
16. Approval-time revalidation
17. Stale/conflict behavior
18. dedupe
19. Expiry
20. Cancel/reject
21. Result storage
22. Terminal immutability
23. Transactions
24. select_for_update / concurrency
25. Double-approval proof
26. P2 access integration
27. Final permission matrix
28. GM queue
29. My Requests
30. Request detail
31. Human status labels
32. Human request presentation
33. Consequences presentation
34. Collapsed technical data
35. Empty/mobile states
36. P3 AuditLog integration
37. Audit summary readability
38. operation_id propagation
39. Admin behavior
40. IDOR/security tests
41. Secret/payload tests
42. Registry tests
43. UI readability tests
44. Browser/manual verification
45. 5-second readability acceptance
46. Query counts
47. Performance
48. Tests added
49. Full test result
50. manage.py check
51. makemigrations --check --dry-run
52. M1 regression
53. R1 regression
54. Atmosphere scope confirmation
55. WORLD_HANDOFF update
56. AGENTS update
57. Guardrails update
58. Master Roadmap status
59. Known limitations
60. Future Inventory/Purchase path
61. Future Travel path
62. Future multi-party extension
63. Future P5 path
64. Confirmation no P5/CharacterKnowledge/M2/Inventory/Travel/C5 was started
```

Stop after report.
