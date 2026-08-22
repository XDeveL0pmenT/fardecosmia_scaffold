# ФАРДЕКОСМИЯ — P1/P2
## Canon, Campaign Overrides & Roles Foundation
### Global world canon, campaign-scoped lore, strict override resolution, centralized access policy

> Перед началом обязательно прочитать:
>
> - `AGENTS.md`
> - актуальный `WORLD_HANDOFF.md` v2
> - Master Roadmap / Architecture Guardrails, если они находятся в репозитории
> - M1 Leaflet Planetary Atlas report
> - R1 Region Weather Semantics & Lifecycle report
>
> Эта фаза объединяет:
>
> - **P1 — Global Canon & Campaign Override Foundation**
> - **P2 — Roles & Access Policy Foundation**
>
> Это архитектурная фаза.
>
> НЕ начинать:
>
> - P3 AuditLog;
> - P4 ApprovalRequest;
> - P5 WorldEvent;
> - CharacterKnowledge;
> - Countries/Settlements/Roads;
> - M1.5 analytical climate layers;
> - Character/Fog;
> - Travel;
> - C5.

---

# 0. Главная проблема

После M1 карта уже является полноценной платформой.

Перед добавлением стран, городов, дорог, энциклопедии и player-visible мира нужно формально ответить:

```text
Что является глобальным каноном Фардекосмии?

Что принадлежит только конкретной кампании?

Что GM кампании может изменить только у себя?

Кто имеет право менять сам глобальный канон?

Как получить effective entity для конкретной кампании?

Как не дать GM одной кампании случайно изменить мир для всех?
```

Архитектурное правило:

```text
GLOBAL CANON
      ↓
CAMPAIGN OVERRIDE
      ↓
CHARACTER KNOWLEDGE / PLAYER VISIBILITY
```

P1/P2 реализует первые два слоя и role boundary.

CharacterKnowledge пока НЕ реализуется.



# 1. Роли и границы доступа

## Global world canon

Может изменять:

```text
superuser
OR
user with explicit global-canon permission
```

Campaign GM НЕ становится canon editor автоматически.

## Campaign state

Может изменять:

```text
GM соответствующей Campaign
```

Campaign GM не получает права менять другую Campaign.

## Player

Не получает GM/canon write access.

---

# 2. Не добавлять глобальный `is_gm` / `is_player` / `is_canon_editor` на User

Сохранить правило `AGENTS.md`.

Campaign role:

```text
CampaignMembership
```

Global Canon Editor:

```text
Django permission
```

а НЕ boolean field на `accounts.User`.

Superuser использует стандартный Django superuser bypass.

---

# 3. Global Canon Editor permission

Добавить одно явно именованное permission, например:

```text
world.manage_global_canon
```

Название можно адаптировать к conventions проекта, но оно должно быть:
- одно;
- понятное;
- проверяемое центральным helper;
- не привязанное к Campaign.

Не создавать автоматически production group через data migration без необходимости.

Permission можно назначать через Django admin.

Optional future group `World / Canon Editors` допустим, но P1/P2 не обязана делать его канонической ролью в БД.

---

# 4. Centralized access service

Создать policy module, например:

```text
world/services/access.py
```

Минимальные helpers:

```python
can_manage_global_canon(user) -> bool
can_view_global_atlas(user) -> bool
can_view_campaign(user, campaign) -> bool
can_manage_campaign(user, campaign) -> bool
require_global_canon_editor(...)
require_campaign_member(...)
require_campaign_gm(...)
```

Не размазывать `is_staff`, `is_superuser` и membership checks по views.

Superuser behavior централизовать там же.

CampaignMembership остаётся source of truth. Если текущие role choices уже подходят, не делать unnecessary migration.



# 5. WorldEntry — минимальная реальная сущность для проверки foundation

Добавить модель:

```text
WorldEntry
```

Это generic encyclopedic/lore record, а НЕ универсальная сущность всех будущих domain objects.

## Critical prohibition

НЕ заставлять будущие:
- Country;
- Settlement;
- Race;
- Item;
- NPC;
- Road;
- Quest;

храниться внутри одного JSON `WorldEntry`.

Они будут иметь собственные structured models.

`WorldEntry` нужен для:
- generic lore/encyclopedic records;
- проверки scope architecture;
- первой реальной override-capable сущности.

Structured entities later могут ссылаться на WorldEntry для описательного lore, но не обязаны.

---

# 6. WorldEntry fields

Recommended:

```text
id
scope
campaign nullable
kind
slug
title
summary
body
created_at
updated_at
created_by nullable
updated_by nullable
revision
```

No production demo entries.

`scope`:

```text
GLOBAL
CAMPAIGN
```

Semantics:

```text
GLOBAL
→ объективный global canon record
→ campaign = NULL

CAMPAIGN
→ существует только в одной Campaign
→ campaign != NULL
```

DB CheckConstraint обязателен.

---

# 7. Identity / uniqueness

`kind` — technical namespace string.

Тесты могут использовать `lore`, `location`, `concept`, но production fixtures с выдуманным каноном не создавать.

`slug` — stable identifier внутри scope.

Uniqueness:

Global:
```text
(scope=GLOBAL, kind, slug)
```

Campaign:
```text
(scope=CAMPAIGN, campaign, kind, slug)
```

Use conditional DB constraints.

Campaign-only WorldEntry не должен иметь тот же effective `(kind, slug)`, что уже существующий GLOBAL entry. Такой collision service должен отклонять и предлагать использовать override.

---

# 8. Revision / provenance

`WorldEntry.revision` увеличивается при meaningful content change.

Не увеличивать на GET/view.

Store:
```text
created_by
updated_by
created_at
updated_at
```

Это lightweight provenance.

Полный immutable AuditLog — P3, не реализовывать сейчас.

Scope и campaign assignment считать immutable в normal UI/service.



# 9. CampaignEntityOverride

Добавить generic model:

```text
CampaignEntityOverride
```

Purpose:

```text
campaign-specific patch over a GLOBAL registered entity
```

Recommended fields:

```text
campaign
content_type
object_id
patch JSON
is_suppressed
created_by
updated_by
created_at
updated_at
revision
base_revision_at_creation nullable
```

Django ContentType / GenericForeignKey допустим.

Но target должен быть строго whitelisted через override-policy registry.

---

# 10. Override — не arbitrary JSON mutation

Запрещено принимать arbitrary patch на arbitrary model.

Каждая override-capable model регистрирует:
- allowed fields;
- validators;
- optional custom resolver.

Concept:

```python
register_override_policy(
    WorldEntry,
    allowed_fields={"title", "summary", "body"},
)
```

Forbidden by default:

```text
id
pk
scope
campaign
kind
slug
created_by
updated_by
revision
```

Future concrete models регистрируют свои поля отдельно.

---

# 11. Patch semantics

Default patch — shallow field override.

```json
{
  "title": "Campaign-specific title",
  "summary": "Campaign-specific summary"
}
```

Field absent → inherit global value.

Field present → override global value.

`null` разрешён только когда policy/field допускает null.

Не внедрять JSON Patch language.

Nested relation editing не входит в P1.

Relations вроде country/ruler/capital/race не хранить как arbitrary raw FK IDs в generic JSON. Для structured future models relationship overrides делаются model-specific, когда реально понадобятся.



# 12. Suppression

`is_suppressed=True`:

```text
global entity excluded from effective Campaign view
```

Это Campaign override, а не удаление глобального канона.

Не путать с player visibility / CharacterKnowledge.

---

# 13. Override target constraints

CampaignEntityOverride может target только:

```text
registered
GLOBAL
override-capable
existing entity
```

Reject:
- campaign-scoped target;
- non-whitelisted model;
- missing target;
- malformed object id.

One current override per:

```text
campaign + target content type + target object id
```

DB UniqueConstraint.

Do not create chains of active override rows.

---

# 14. Override revision / base provenance

Override revision увеличивается на meaningful patch/suppression change.

Если target имеет `revision`, store optional:

```text
base_revision_at_creation
```

или эквивалент.

Это позволит позже показать, что global canon изменился после создания override.

P1 не обязана автоматически разрешать такие conflicts.



# 15. Resolver

Создать:

```text
resolve_for_campaign(instance, campaign)
```

Он возвращает immutable/read-only projection/dataclass, НЕ mutated ORM object.

Metadata:

```text
base object
effective values
source
override nullable
is_suppressed
base_revision
override_revision
```

Sources:

```text
GLOBAL
GLOBAL_OVERRIDDEN
CAMPAIGN_ONLY
```

Forbidden:

```python
entry.title = override.patch["title"]
return entry
```

потому что такой ORM instance можно случайно save обратно в global canon.

---

# 16. Effective list

Для WorldEntry:

```text
effective_world_entries(campaign, kind=None)
```

Возвращает:
1. GLOBAL entries;
2. с campaign overrides;
3. suppressed entries исключены по умолчанию;
4. CAMPAIGN entries только этой Campaign.

Optional:
```text
include_suppressed=True
```

для GM diagnostics.

Не смешивать rows других campaigns.

Prefetch/load overrides одной query, без N+1.



# 17. Core resolution regression

Base:

```text
title=A
summary=A
```

Campaign override:

```text
summary=B
```

Resolved:
```text
title=A
summary=B
```

Global title потом меняется на C.

Resolved:
```text
title=C
summary=B
```

Если Campaign override позже задаёт title=D:

Resolved:
```text
title=D
summary=B
```

Base ORM row должен оставаться C + base summary, никогда не D.

---

# 18. Sparse patch cleanup

Если override field равен current base:
- service может удалить этот key.

Если patch становится пустым и `is_suppressed=False`:
- service может удалить пустую override row.

Выбрать точное поведение и задокументировать в report.

Goal:
```text
store only actual campaign differences
```



# 19. Write services

Не помещать всю policy в model `save()`.

Preferred:

```text
create_global_world_entry(...)
update_global_world_entry(...)
delete_global_world_entry(...)

create_campaign_world_entry(...)
update_campaign_world_entry(...)
delete_campaign_world_entry(...)

set_campaign_override(...)
remove_campaign_override(...)
set_campaign_suppression(...)
```

Each:
- actor permission;
- target/scope validation;
- transaction;
- provenance;
- revision.

Views thin.

Use `transaction.atomic()`.

При override update cheap `select_for_update()` допустим.

DB uniqueness должна предотвращать duplicate overrides.



# 20. Global vs Campaign permissions

## Global WorldEntry create/update/delete

Requires:

```text
can_manage_global_canon(user)
```

Campaign GM without global permission cannot write global canon.

## Campaign WorldEntry

Requires GM membership in that same Campaign.

## Campaign override

Requires GM membership in that same Campaign.

## Canon Editor only

Canon editor без membership:
- может edit global canon;
- НЕ может edit Campaign override;
- НЕ может advance Campaign time;
- НЕ может edit Region Campaign.

## Superuser

Central bypass.

---

# 21. Campaign GM vs Canon Editor invariants

Campaign A GM:
- can manage Campaign A;
- can create Campaign A override;
- cannot modify global canon unless also canon editor;
- cannot manage Campaign B.

Canon Editor only:
- can manage global canon;
- cannot manage Campaign A state without membership.

Canon Editor + GM A:
- both respective scopes.

Do not conflate these roles.



# 22. Global atlas after P2

Recommended final access:

## View global objective atlas

Allowed:
- superuser;
- canon editor;
- user who is GM in at least one campaign.

Player denied for now because atlas exposes objective GM truth.

## Edit global atlas/world canon

Allowed only:
- superuser;
- canon editor.

Ordinary Campaign GM may VIEW global atlas but cannot mutate shared global canon.

---

# 23. Campaign map after P2

Campaign GM may:
- create/edit Regions in own Campaign;
- create/edit campaign biome overrides;
- inspect GM world data;
- use M1 tools.

Campaign GM must not:
- alter shared global biome layer;
- alter base World Data rasters;
- alter global WorldEntry.

Server authorizes; frontend flags are UX only.



# 24. Existing specialized map override stays specialized

Current:

```text
GlobalWorldMapLayer
CampaignWorldMapOverride
```

must NOT be replaced by generic CampaignEntityOverride.

Reason:
- sparse spatial data;
- performance;
- M1 rendering;
- specialized semantics.

Generic override framework is for structured global entities.

Map cell override remains specialized.

---

# 25. Existing Region stays campaign state

Do NOT migrate `Region` to global canon.

Region:
- manually drawn inside Campaign;
- simulation area;
- owns R1 weather semantics.

Future Country/Settlement/Canonical Geography are different entities.

Do not conflate them.

---

# 26. M1/R1/Atmosphere no-regression

P1/P2 must not modify:
- Leaflet CRS;
- tile system;
- world wrap;
- Region contour storage;
- RegionAreaWeatherState;
- WeatherState lifecycle;
- atmospheric solver;
- snapshot format;
- timestep;
- precipitation physics;
- Region geometry revision.

No climate migration.



# 27. Minimal management UI

Add only enough UI to prove architecture.

Do NOT build full encyclopedia shell.

Recommended:

## Global World Entries
- list/detail;
- ordinary GM read-only;
- canon editor gets create/edit/delete controls.

## Campaign World Entries
- effective entries;
- badges:
  - `Глобальный канон`
  - `Изменено в кампании`
  - `Только эта кампания`
  - `Скрыто в кампании`
- create campaign-only entry;
- override selected global entry;
- suppress/restore.

Player-facing publication is not part of this phase.

---

# 28. Scope must be obvious in UI

Global edit warning:

```text
Изменение глобального канона влияет на все кампании,
если конкретная кампания не переопределяет это поле.
```

Campaign override form shows:
```text
Базовое значение
Campaign override
```

Blank/inherit means:
```text
inherit current global value
```

Only changed fields should be stored.



# 29. Player access

Because CharacterKnowledge/visibility is not implemented:

```text
WorldEntry management/effective-canon pages remain GM/canon-only
```

Do not publish objective canon to players automatically.

Do not add `known_by` JSON to WorldEntry.

Future player resolution:

```text
global/campaign effective truth
↓
CharacterKnowledge / visibility
↓
player-safe representation
```



# 30. Delete semantics

## Global delete

Canon editor only.

If active CampaignEntityOverride exists:
- prevent normal hard delete;
- report affected campaign count/list;
- do not leave orphan override.

GenericForeignKey means DB PROTECT may be unavailable, so normal UI/service delete must explicitly check.

Admin deletion must be hardened/documented.

## Campaign WorldEntry delete

GM of same Campaign only.

## Override delete

Means:
```text
return to inheriting current global canon
```

Must not delete base.



# 31. Admin boundary

If models are registered in Django admin:
- customize add/change/delete permissions;
- filter querysets where required.

Superuser full access.

Canon editor may manage GLOBAL WorldEntry.

Campaign GM should use campaign UI, not unrestricted admin.

Do not expose all CampaignEntityOverride rows to unrelated users.

If project intentionally limits admin to superuser only, document it and keep simpler.



# 32. ContentType safety

If GenericForeignKey is used:
- never trust arbitrary `content_type_id` from POST;
- route/service resolves model through whitelist;
- server fetches target;
- object_id validated.

Do not expose a generic endpoint able to mutate arbitrary models.



# 33. Permission audit before changes

Inventory current endpoints and classify:
- global canon read;
- global canon write;
- campaign read;
- campaign write;
- player read.

At minimum audit:
- global atlas;
- global biome edit;
- campaign world map;
- CampaignWorldMapOverride save;
- Region create/edit;
- Region detail GM diagnostics;
- map point inspector;
- Campaign time advance.

Do not perform massive unrelated refactor.



# 34. Access matrix

Test roles:

```text
Anonymous
Player in Campaign A
GM in Campaign A
GM in Campaign B
Canon Editor only
Canon Editor + GM A
Superuser
```

Operations:

```text
View global atlas
Edit global canon
View Campaign A
Edit Campaign A
Create override in Campaign A
Edit Campaign B
View GM point inspector
Advance Campaign A time
```

Implementation report must include final matrix.

---

# 35. IDOR/security

Direct access by raw URL/pk to:
- Campaign B override;
- Campaign B campaign-only entry;
- Campaign B Region;
- unauthorized global POST;

must be denied with project-consistent 403/404.

Do not rely on hidden buttons.



# 36. Model tests

WorldEntry:
1. GLOBAL requires campaign NULL.
2. CAMPAIGN requires campaign.
3. global kind/slug unique.
4. campaign campaign/kind/slug unique.
5. different campaigns may reuse campaign-only slug.
6. campaign-only collision with global effective identity rejected.
7. normal service cannot change scope.
8. normal service cannot move Campaign A entry to B.
9. revision increments on meaningful change.
10. GET/view does not increment.

---

# 37. Override tests

1. global WorldEntry can be overridden.
2. campaign WorldEntry cannot.
3. non-whitelisted model rejected.
4. forbidden field rejected.
5. malformed patch rejected.
6. null validation works.
7. one override per campaign/target.
8. override does not mutate base.
9. remove override restores base.
10. suppression excludes effective row.
11. restore returns row.
12. sparse patch cleanup documented/tested.
13. missing target rejected.



# 38. Isolation tests

Campaign A override:
- affects A;
- not B;
- not base.

Campaign-only A:
- in A;
- absent B.

GM A:
- cannot mutate B.

---

# 39. Role tests

Player A denied:
- global write;
- Campaign write;
- GM inspector;
- Campaign B.

GM A allowed:
- Campaign A write;
- A override.

GM A denied:
- global write;
- Campaign B.

Canon Editor only allowed:
- global write.

Canon Editor only denied:
- Campaign override;
- Campaign time advance.

Canon Editor + GM A:
- both respective scopes.

Superuser:
- all management.



# 40. Global atlas / map regression tests

1. GM A can view global atlas.
2. Player A cannot view objective global atlas.
3. GM A without canon permission cannot POST global canon/biome change.
4. Canon Editor can mutate allowed global canon.
5. Campaign biome override stays editable by GM A.
6. Campaign override does not alter global biome.
7. Region create/edit still works for own GM.
8. point inspector stays read-only.
9. view does not mutate DB.
10. R1 history unaffected.
11. Leaflet map contract remains valid.



# 41. Minimal UI tests

Global list:
- edit controls absent for ordinary GM;
- present for canon editor.

Campaign effective list:
- source badges correct;
- campaign-only create works;
- override stores only changed fields;
- suppression visible.

Forged POST must still be denied server-side.



# 42. Query/performance

At tabletop scale:
- resolve effective lists with bulk queries;
- no N+1.

Report query strategy/count for representative list.

P1/P2 should not measurably affect M1 map or atmosphere performance.

No climate benchmark required unless climate code was accidentally touched.



# 43. Migration

This phase explicitly authorizes schema migration.

Create next normal Django migration for:
- WorldEntry;
- CampaignEntityOverride;
- constraints;
- indexes;
- custom permission as required.

Apply to local development DB.

Do NOT add production lore data migration.
Do NOT create demo canon.

Run:

```bash
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```



# 44. Suggested indexes

WorldEntry:
- scope;
- campaign + kind;
- kind + slug.

CampaignEntityOverride:
- campaign;
- content_type + object_id;
- unique campaign + content_type + object_id.

Do not over-index blindly.



# 45. Documentation update

After success:

## WORLD_HANDOFF.md

Update only relevant status/architecture sections:
- P1/P2 completed;
- WorldEntry GLOBAL/CAMPAIGN scope;
- CampaignEntityOverride;
- canon permission;
- global vs campaign edit rule.

Do not rewrite astronomy/climate unnecessarily.

## AGENTS.md

Add concise technical rule if useful:

```text
Global canon writes use centralized canon permission.
Campaign authority comes from CampaignMembership.
Campaign-effective entities must resolve through the override resolver.
```

Keep AGENTS concise.

## Architecture Guardrails

If present, add:
```text
Global canon != campaign state.
Campaign override never mutates base canon.
Player visibility is later CharacterKnowledge.
Generic overrides are whitelist-validated.
Future structured domains remain structured models.
```



# 46. Future M2 compatibility

M2 Countries/Settlements/Roads should be able to register concrete models with the foundation.

Future entity may be:

```text
GLOBAL canonical entity
CAMPAIGN-only entity
GLOBAL + Campaign override
```

Do not force M2 data into WorldEntry JSON.

---

# 47. Future CharacterKnowledge compatibility

Later:

```text
effective objective truth
↓
CharacterKnowledge / visibility
↓
player representation
```

P1/P2 must not collapse truth and knowledge.

---

# 48. Future P3/P4/P5 hooks

Write services should have clean future hook points for:

P3 AuditLog:
```text
actor / action / target / campaign / before / after
```

P4 ApprovalRequest:
- not used for every canon/GM edit.

P5 WorldEvent:
- authored WorldEntry edits are not automatically world events.

Do not implement these systems now.



# 49. Non-goals

P1/P2 does NOT:
- create countries;
- create cities;
- create roads;
- create race pages;
- expose encyclopedia to players;
- implement knowledge/rumors;
- implement AuditLog;
- implement ApprovalRequest;
- implement WorldEvent;
- modify climate;
- redesign Leaflet;
- add Travel;
- add Character markers;
- add precipitation/hazard/habitability layers.



# 50. Acceptance Criteria

P1/P2 complete when:

1. Global canon and Campaign scope are explicitly modeled.
2. `WorldEntry` foundation exists.
3. GLOBAL/CAMPAIGN DB constraints are valid.
4. Campaign-only entries do not leak across campaigns.
5. `CampaignEntityOverride` exists.
6. Override targets are whitelist-restricted.
7. Patch fields are validated.
8. Identity/scope fields cannot be patched.
9. Resolver returns immutable effective projection.
10. Resolver never mutates base ORM row.
11. Suppression works per Campaign.
12. Base changes flow through inherited fields.
13. Campaign overrides remain isolated.
14. Campaign GM cannot edit global canon.
15. Canon Editor cannot edit Campaign state without membership.
16. Superuser can manage both.
17. CampaignMembership remains campaign-role source of truth.
18. Global canon permission is centralized.
19. Global atlas write access is canon-editor-only.
20. Campaign biome override remains GM-editable.
21. Specialized map override is not replaced.
22. Region remains campaign-local.
23. M1 and R1 remain intact.
24. No player-visible canon leakage introduced.
25. Existing tests pass.
26. New access/security/resolution tests pass.
27. No production demo lore is created.
28. P3/P4/P5/CharacterKnowledge/M2/C5 are not started.



# 51. P1/P2 IMPLEMENTATION REPORT

After implementation STOP and return:

```text
P1/P2 CANON, CAMPAIGN OVERRIDES & ROLES REPORT

1. Changed files
2. Migration(s)
3. Current CampaignMembership role model
4. Global canon permission
5. Central access-policy module
6. Final access matrix
7. WorldEntry model
8. GLOBAL/CAMPAIGN constraints
9. WorldEntry uniqueness/identity
10. WorldEntry revision/provenance
11. CampaignEntityOverride model
12. Generic target implementation
13. Override whitelist registry
14. Patch validation rules
15. Suppression semantics
16. Override uniqueness
17. Base revision provenance
18. Effective resolver design
19. Proof resolver does not mutate base
20. Effective list query strategy
21. Campaign-only entity behavior
22. Global base-change + override example
23. Campaign isolation example
24. Global edit UI
25. Campaign override UI
26. Source badges
27. Global atlas permission changes
28. Campaign map permission behavior
29. Global biome vs campaign biome behavior
30. Existing Region behavior
31. M1 regression status
32. R1 regression status
33. Admin permission behavior
34. Security/IDOR tests
35. Query count/performance
36. Tests added
37. Full test result
38. manage.py check
39. makemigrations --check --dry-run
40. WORLD_HANDOFF update
41. AGENTS update if changed
42. Known limitations
43. Future M2 registration path
44. Future CharacterKnowledge path
45. Confirmation no AuditLog/ApprovalRequest/WorldEvent was started
46. Confirmation no M2/Character/Travel/C5 was started
```

Stop after report.
