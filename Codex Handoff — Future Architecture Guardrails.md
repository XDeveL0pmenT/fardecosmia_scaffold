# CODEX HANDOFF — FUTURE ARCHITECTURE GUARDRAILS
## Проект «Фардекосмия»

Это **НЕ задача на реализацию всего roadmap**.

Это архитектурные ограничения для следующих фаз разработки. Их необходимо учитывать, начиная с **Phase C4**, чтобы сегодняшние изменения не блокировали будущие системы.

---

# 1. Ближайшая задача

Следующей отдельной задачей будет:

**Phase C4 — Atmospheric Circulation & Terrain Dynamics.**

При выполнении C4:

- НЕ начинай Leaflet migration;
- НЕ начинай Core Platform;
- НЕ реализуй страны/города;
- НЕ начинай катаклизмы;
- НЕ начинай Travel Engine;
- НЕ начинай CharacterKnowledge.

Но архитектура C4 не должна делать эти будущие этапы сложнее.

После выполнения C4 остановись и верни implementation report.

---

# 2. Карта будет перенесена на Leaflet

Текущая реализация карты является временной.

Планируется полноценная миграция на **Leaflet**:

```text
Planet
→ deep zoom
→ layers
→ regions
→ countries
→ settlements
→ roads
→ characters
→ routes
→ events
```

Поэтому:

- не связывай climate/services с текущим DOM/canvas/image implementation карты;
- климатические данные должны быть доступны через backend/service/API-friendly интерфейсы;
- source of truth географии — `latitude/longitude`;
- не создавай новые игровые сущности, существующие только в pixel coordinates;
- учитывать wrap через `-180° / +180°`;
- будущие страны, регионы, дороги и поселения будут векторными сущностями;
- карта будет tile/slippy-map.

---

# 3. Размер Фардекосмии

Окружность планеты:

```text
72 500 км
```

Не использовать земной радиус или земную окружность в новой географической логике.

Если уже существует world-geometry helper — использовать его.

Будущая система путешествий будет рассчитывать расстояния непосредственно по lat/lon.

---

# 4. Главная будущая модель данных

Архитектура проекта будет строиться как:

```text
GLOBAL CANON
      ↓
CAMPAIGN OVERRIDE
      ↓
CHARACTER KNOWLEDGE / CHARACTER STATE
```

Следствия:

- campaign model не должен становиться единственным source of truth глобального канона;
- не копировать весь канонический объект в campaign без необходимости;
- campaign хранит отличия/overlay;
- не хардкодить campaign-specific изменения в глобальные World Data;
- оставить возможность будущих overrides.

После P1/P2 foundation:

- global/campaign encyclopedic scope проверяется через `WorldEntry`;
- `CampaignEntityOverride` хранит только whitelist-validated sparse patch;
- campaign override никогда не мутирует global base;
- player visibility остаётся отдельным будущим `V1 Visibility & Discovery`
  layer; не возвращать старый широкий K1 CharacterKnowledge как ближайшую фазу;
- будущие Country/Settlement/Race и другие structured domains остаются
  отдельными structured models, а не JSON внутри `WorldEntry`.

C4 не реализует эту систему, но не должен ей мешать.

---

# 5. Будущие роли

Планируются:

```text
Superuser
World / Canon Editor
Campaign GM
Player
возможно Assistant GM
```

Не создавать новую бизнес-логику, которая принципиально зависит только от:

```python
user.is_staff
user.is_superuser
```

если существует или может использоваться нормальный permission/service layer.

---

# 6. Visibility & Discovery и Fog of War

Позже игрок будет видеть только сведения, известные его персонажу.

Для карты:

```text
unknown
explored
currently visible
```

Следовательно:

- не предполагай, что любой authenticated user имеет право получать полный world state;
- новые GM/debug endpoints должны быть отделимы от player-safe данных;
- climate debug information не должна автоматически становиться публичной.

---

# 7. WorldEvent

P5 foundation реализован:

- `WorldEvent` — mutable campaign definition/schedule;
- `WorldEventOccurrence` — immutable objective history;
- WORLD_TIME one-shot crossing — строго `(old, new]` с deterministic order;
- exact и fast-forward не пропускают safe scheduled events;
- triggers/effects registered, versioned, bounded и secret-safe;
- effect, occurrence и связанные audits атомарны и имеют общий `operation_id`;
- failed effect не оставляет occurrence/partial mutation и откатывает advance;
- objective occurrences GM-only до explicit Visibility/Discovery publication.

WorldEvent не является application event bus, event sourcing, AuditLog,
ApprovalRequest или TimeAdvanceReport. Запрещены `eval`, arbitrary JSON field
mutation и создание конкурирующей event architecture.

Будущие расширения:

- глобальные события;
- локальные события;
- катаклизмы;
- войны;
- магические аномалии;
- временные модификаторы

будут объединены через `WorldEvent` или архитектурный эквивалент.

Simulation-coupled effects пока не подключены: если событие должно влиять на
атмосферу внутри пропущенного периода, будущая фаза обязана разделить simulation
на event boundaries. Нельзя молча применять такое effect только в конце advance.

Solver должен позволять позже подключить явно спроектированные external
forcing/effect hooks.

Не создавать без необходимости множество permanent DB flags вида:

```text
is_global_storm_active
is_heatwave_active
is_magic_weather_active
```

как отдельные несвязанные системы.

---

# 8. AuditLog

P3 foundation реализована. Общий `AuditLog` является append-only историей
значимых действий, а не application log, WorldEvent или event-sourcing store.

Обязательные правила для новых доменов:

- запись через `world.services.audit.record_audit()`;
- одна осмысленная операция пользователя, а не row на каждый внутренний шаг;
- audit и mutation находятся в одной `transaction.atomic()`;
- explicit domain serializer, без `request.POST` и технических секретов;
- global и campaign scope не смешиваются;
- normal update/delete/purge AuditLog запрещены.

В будущем этот foundation будет использоваться для:

- CharacterSheet;
- экономики;
- inventory;
- quests;
- campaign edits;
- approvals;
- world edits.

Внутренние solver steps, WeatherState и AtmosphericSnapshot не логируются.

Новые user-driven destructive/edit actions должны подключаться на границе
доменного сервиса и создавать ровно одну или явно сгруппированную запись.

---

# 9. ApprovalRequest

P4 foundation реализован как campaign-scoped workflow зарегистрированных
намерений. Он пока не создаёт выдуманные gameplay-действия, но является
единственной общей основой для будущих:

- покупки;
- путешествия;
- согласия других игроков;
- GM approval;
- награды;
- других подтверждаемых действий.

Обязательные правила:

- `ApprovalRequest != WorldEvent`;
- `ApprovalRequest` не является arbitrary command queue;
- request type должен иметь зарегистрированный versioned handler;
- handler валидирует payload при создании и повторно проверяет актуальность
  состояния непосредственно перед применением;
- normal UI получает человекочитаемые intent/consequences от presenter, а raw
  payload остаётся вторичной свёрнутой диагностикой;
- `APPROVED` означает, что доменное действие успешно выполнено;
- domain mutation, resolution/result и P3 audit выполняются атомарно с общим
  `operation_id`;
- concurrent decision использует row lock и не может применить действие дважды;
- resolved requests неизменяемы через normal application paths;
- payload/result ограничены по размеру и не могут содержать технические секреты;
- campaign GM authority не смешивается с Global Canon Editor authority.

Не создавать ad-hoc approval architecture в будущих feature stubs. Покупки,
travel, rewards и multi-party consent должны подключать собственные handlers к
этому foundation, когда их канон и доменные модели будут определены.

---

# 9.5 Account onboarding and Campaign lifecycle

P4.5 and P5.6 foundations are implemented. Future account/Campaign work must
preserve:

- verification code and invitation token are different credentials with
  separate lifecycles;
- plaintext verification codes, invitation tokens and reset tokens are never
  persisted or copied into AuditLog;
- accepting an invitation is a direct, email-bound membership operation, not an
  ApprovalRequest;
- normal onboarding must not require Django Admin;
- email delivery goes through the centralized accounts service and configured
  Django backend;
- Campaign authority remains CampaignMembership-scoped;
- invitation authorship, verified email, Canon Editor and staff flags do not
  grant Campaign GM rights;
- global trusted-GM eligibility is the direct individual permission
  `campaigns.create_campaign_as_gm`; group-derived permission does not count;
- only superuser can grant/revoke that eligibility through the audited service;
- Campaign creation requires eligibility (or superuser) plus verified email;
- PLAYER -> GM promotion requires the target User to be eligible;
- revocation preserves an existing Campaign GM membership but blocks new
  Campaign creation and a later promotion after demotion;
- every Campaign must retain at least one GM, enforced under transaction/locking;
- security/authentication telemetry remains outside world AuditLog, while
  meaningful Campaign creation/invitation/membership mutations use P3 audit.

Do not introduce reusable/public invitations, assistant-GM roles, social login
or notification infrastructure without a separate phase and permission model.

---

# 10. Character и Roll20

P5.5 Character Identity & Player Workspace foundation реализован.

Обязательные границы:

- `Character != User`;
- Character identity принадлежит Campaign и имеет durable PK;
- Character assignment/controller не является Campaign role;
- Campaign authority остаётся в `CampaignMembership`;
- Character identity != CharacterSheet;
- Roll20 binding/control assignment — независимые отношения;
- gameplay knowledge/state не хранится на User;
- future gameplay knowledge/Visibility & Discovery state follows Character on
  reassignment rather than User;
- player-facing выборки показывают только controlled active Characters той же
  Campaign;
- normal hard-delete Character не вводить: использовать archive/deactivate;
- не заменять существующую Character model и не менять Roll20 binding semantics
  без отдельного data-preserving audit/migration proof.

Будущая цепочка:

```text
Character identity
↓
Normalized Character State / CharacterSheet
↓
Roll20 Adapter
```

Roll20 остаётся source of truth combat-sheet mechanics. Fardecosmia хранит
campaign/world state и стабильный normalized mirror. Не связывать по имени и не
протаскивать raw Roll20 attributes в Character domain/UI.

---

# 10.5 Player Character Workspace

PW1 реализован как server-rendered shell и routing contract, а не как новая
доменная модель.

- Для `PLAYER` normal Campaign destination — Workspace активного Character.
- Для GM сохраняется отдельный objective Campaign landing; Player Workspace не
  является источником объективной истины мира.
- Active Character определяется и переключается только через P5.5
  Campaign-scoped control/selection services.
- Старый Player Character detail URL остаётся compatibility redirect после
  проверки доступа, а не вторым расходящимся экраном.
- “Мои запросы” и ApprovalRequest terminology не должны возвращаться в normal
  Player navigation. ApprovalRequest backend и GM decision queue сохраняются.
- Workspace скрывает GM-only state, raw Roll20 attributes,
  `CharacterKnowledge`/«Что знает персонаж» и developer-roadmap wording.
- Тиамана, Quests, Map, Быт/Обязательства, Party, Notes, Apotheosis, Inventory,
  XP и money представлены только стабильными UI slots/anchors. До профильных
  фаз запрещено наполнять их fake values или baseline world data.
- PW1 не определяет Location, live Weather, Notes ownership, Party, XP,
  Inventory, Quests, Economy, Travel, Roll20 sync или Apotheosis mechanics.

Любое дальнейшее наполнение Workspace должно подключаться к явно определённому
source of truth и соблюдать разделение objective truth, Character perception и
GM-only information.

---

# 11. Travel Engine — критически важное требование

Будущий Travel Engine будет учитывать:

- координаты;
- расстояния;
- terrain;
- elevation;
- biome;
- weather;
- roads;
- hazards;
- transport;
- buffs;
- provisions;
- world time.

Поэтому атмосферная система должна позволять получать состояние мира **в произвольной точке**, а не только для заранее созданного Region ORM object.

Желательное концептуальное API:

```python
sample_environment_at(
    campaign,
    world_minutes,
    latitude,
    longitude,
)
```

или архитектурный эквивалент.

Будущая система должна уметь sample'ить погоду вдоль маршрута.

Не создавать зависимость:

```text
нет Region row → нельзя получить погоду
```

---

# 12. Region после C3.5

Region теперь концептуально:

```text
location
+ identity
+ optional explicit GM override
```

Region НЕ является отдельным source of climate physics.

Не возвращать в AtmosphericGrid:

- legacy orbital response;
- legacy precipitation bias;
- legacy weather volatility.

C1–C4 физика должна оставаться глобальной.

---

# 13. Детерминизм

Сохранить:

```text
Campaign.world_minutes
```

как source of truth времени.

Сохранить:

- deterministic seeded evolution;
- одинаковые результаты эквивалентных exact advances;
- корректный snapshot resume;
- fast-forward не выдумывает детальные weather events пропущенного периода.

---

# 14. Snapshot / persistence

Если C4 меняет состояние solver:

- bump version/fingerprint;
- old snapshots не удалять без причины;
- incompatible snapshots не принимать молча;
- migration должна быть backward-safe;
- WeatherState history не переписывать задним числом.

---

# 15. Performance

Перед C4 снять baseline.

Требования:

- NumPy/vectorization;
- no ORM per grid cell;
- no Python loop per grid cell;
- cache static latitude/longitude/terrain geometry;
- benchmark exact Vitok;
- benchmark Season FF;
- benchmark Year FF;
- profiler перед arbitrary simplification.

Не ухудшать физику только для красивого benchmark без измеренного trade-off.

---

# 16. Будущие катаклизмы

C4 НЕ реализует катаклизмы.

Позже цепочка должна быть способна выглядеть так:

```text
Climate / Geology simulation
        ↓
WorldEvent
        ↓
Map
        ↓
Country / Settlement
        ↓
Travel
        ↓
Quest / Economy / Character consequences
```

Поэтому severe-weather состояние не должно существовать только как UI string.

Физические diagnostics/state должны оставаться доступны будущему event engine.

---

# 17. Human-readable conditions

C3 уже реализовал `environment_summary`.

Правило:

```text
scientific physical state
        ↓
derived human interpretation
```

Human labels никогда не являются входом solver.

C4 не должен смешивать textual conditions и физику.

---

# 18. Канонические системы, которые C4 не переписывает

Без отдельной задачи не менять:

- 364-дневный Великий Круг;
- C1 normalized star orbit;
- текущие неравные сезоны;
- RegionalSky;
- Красные/Чёрные Витки;
- Круг Лика;
- C2 dynamic SST;
- C2 physical `q_v`;
- C3 physical `q_c`;
- C3 precipitation water removal;
- C3 environment summary;
- C3.5 Region climate autoconfiguration.

---

# 19. Future Leaflet requirement для climate layers

Климатические слои позже будут отображаться в Leaflet:

- current temperature;
- wind;
- pressure;
- humidity;
- clouds;
- precipitation;
- storms;
- hazards.

Поэтому C4 output должен быть пригоден для:

```text
grid → raster/tile/API overlay
```

без зависимости от текущего frontend renderer.

Не реализовывать Leaflet в C4.

---

# 20. После C4

Вернуть отдельный:

```text
PHASE C4 IMPLEMENTATION REPORT
```

с:

- changed files;
- models;
- migrations;
- circulation equations;
- Coriolis implementation;
- pressure-gradient implementation;
- terrain coupling;
- convergence/divergence;
- integration with q_v/q_c/latent heating;
- fast-forward changes;
- snapshot/version changes;
- tests;
- performance;
- long-run stability;
- known approximations;
- future compatibility;
- подтверждением, что Leaflet/Core/Travel/Catastrophes не начинались.

После отчёта остановиться.
