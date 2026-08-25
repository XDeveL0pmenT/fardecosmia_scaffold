# Фардекосмия
# Player Experience & Product Architecture v1.0

Дата фиксации: 2026-08-23

Статус: продуктовая архитектура. Документ задаёт направление интерфейса и будущих систем, но сам по себе не является phase implementation spec.

---

# 1. Главная идея Player Experience

Фардекосмия для игрока — не административная панель, не справочник и не интерфейс «что знает персонаж».

После входа в Campaign игрок взаимодействует с миром через **интерфейс своего персонажа**.

Нарративно персонаж способен устремить восприятие в промежуточную реальность и там воспринимать собственный «Лист»:

```text
аккаунт человека
↓
Campaign
↓
active Character
↓
Character Workspace
```

Character Workspace является отражением состояния персонажа, его развития, вещей, финансов, текущего положения, окружающей среды, квестов, команды, заметок и доступных ему действий.

Это всё ещё UI для реального игрока, но его формулировки и структура должны минимизировать метазнание.

---

# 2. Три пространства сайта

## 2.1 Platform Shell

Метауровень реального пользователя. Постоянные действия:

```text
Фардекосмия
Вернуться к кампаниям
Настройки
Выйти
```

Platform Shell не должен притворяться внутриигровой сущностью.

## 2.2 Character Workspace

Основной интерфейс Player после входа в Campaign.

**Player Campaign Index = Character Workspace активного персонажа.**

Campaign остаётся контекстом, а не главным объектом страницы.

## 2.3 GM Workspace

GM работает с объективным состоянием Campaign: настройками, Characters, WorldEvent, картой, регионами, симуляцией, AuditLog, ApprovalRequest queue, campaign/canon данными и будущими gameplay-системами.

GM Workspace не обязан быть diegetic.

---

# 3. Campaign creation / GM authority

Обычный новый User после регистрации и email verification:

```text
не может создать Campaign
не становится GM автоматически
может только получить приглашение
```

Только superuser может выдать пользователю право быть GM / создавать Campaign.

Не добавлять `User.is_gm`.

Предпочтительная архитектура:

```text
global permission / trusted GM eligibility
↓
выдаёт только superuser
↓
пользователь может создавать Campaign
↓
в созданной Campaign получает CampaignMembership.GM
```

CampaignMembership остаётся source of truth конкретной роли внутри конкретной Campaign.

Если политика проекта требует, что только superuser может повысить Campaign PLAYER до GM, это также закрепляется централизованно в access layer, а не отдельным role field на User.

---

# 4. Player entry flow

```text
Registration
↓
Email Verification
↓
Campaign list
↓
Campaign selected
↓
Active Character
↓
Character Workspace
```

Всегда должна оставаться возможность вернуться к списку Campaign.

Если Character не назначен — human-first empty state без fake Character.

Если Characters несколько — используется сохранённый active Character из P5.5.

---

# 5. Character Workspace — основной Index

Концептуальная композиция:

```text
┌────────────────────────────────────────────────────┐
│ Platform bar: Фардекосмия / Кампании / Settings   │
│                                                    │
│              LIVE CHARACTER AMBIENCE               │
│                                                    │
│ ┌───────────────────┐ ┌──────────────────────────┐ │
│ │ ТИАМАНА           │ │ АКТИВНЫЕ КВЕСТЫ         │ │
│ │ stats/progression │ │ личные + командные       │ │
│ └───────────────────┘ └──────────────────────────┘ │
│                                                    │
│ ┌───────────────────┐ ┌──────────────────────────┐ │
│ │ КАРТА             │ │ БЫТ / ОБЯЗАТЕЛЬСТВА     │ │
│ │ current position  │ │ lifestyle/housing/debt  │ │
│ └───────────────────┘ └──────────────────────────┘ │
│                                                    │
│ ┌───────────────────────────────────────────────┐  │
│ │ КОМАНДА                                       │  │
│ └───────────────────────────────────────────────┘  │
│                                                    │
│ ┌───────────────────┐ ┌──────────────────────────┐ │
│ │ ЗАМЕТКИ           │ │ APOTHEOSIS / CRAFT      │ │
│ └───────────────────┘ └──────────────────────────┘ │
│                                                    │
│ ИНВЕНТАРЬ: вещи при персонаже        [Подробнее]  │
│                                                    │
│ XP ███████████████░░░░░                 ◈ Деньги │
└────────────────────────────────────────────────────┘
```

Это направление, а не обязательная pixel-perfect сетка.

---

# 6. Persistent HUD

Два элемента закреплены в Character Workspace:

```text
XP BAR
MONEY
```

Они должны сохранять своё место при переходе по Character-facing разделам, если layout позволяет.

---

# 7. XP и развитие

Fardecosmia является source of truth для XP, level progression, class progression и choices развития.

XP не должен быть просто редактируемым integer без истории. Предпочтительно использовать `ExperienceTransaction` или эквивалентный append-oriented progression ledger.

Источники первой версии:

- Quest reward;
- GM вручную;
- будущие доменные события только когда их правила определены.

---

# 8. Level Up experience

```text
XP reward
↓
частицы/эффект летят в XP bar
↓
bar заполняется
↓
звуковой сигнал Level Up
↓
визуальный transition
↓
автоматический переход в Тиаману
↓
интерфейс прокачки
```

Дополнительно игрок получает email о доступной/произошедшей прокачке.

Если XP уже легитимно выдан, дополнительный GM approval для достижения threshold не требуется.

---

# 9. Тиамана

Тиамана — отдельный Character module:

```text
stats
class
level
progression
abilities/features
future spells/mechanics
level-up choices
```

P5.5 Character остаётся identity anchor, а Тиамана строится поверх future normalized character/progression state.

---

# 10. Fardecosmia / Roll20 authority split

## Fardecosmia authoritative

Фардекосмия — ядро persistent character/world-facing state:

```text
XP
level/progression
class choices
features
currency
Ledger
Inventory
Equipment
Purchases
Craft / Apotheosis
Quests
Party
Travel
Location
Lifestyle
Housing
Debt
Notes
```

## Roll20 authoritative

Roll20 преимущественно хранит и исполняет battle-runtime/combat representation:

```text
current HP
temporary HP
death saves
combat attacks/macros
battle-use resources where appropriate
combat sheet representation
```

Точный список двухсторонних полей должен быть отдельно проаудирован перед Roll20 integration phase.

Основное направление синхронизации:

```text
Fardecosmia
↓
normalized Character state
↓
Roll20 adapter
↓
Roll20 sheet
```

Обратно идут только реальные Roll20-authoritative battle-runtime изменения.

Не делать generic bidirectional last-write-wins sync.

---

# 11. Character ambience

Character Workspace визуально отражает реальное окружение персонажа.

Источник:

```text
effective Character position
↓
World Data
+
AtmosphericGrid/C4.2 point sampler
+
RegionalSky
↓
Character ambience
```

Учитывать:

- день/ночь;
- Light/Dark Night;
- Ympha;
- облачность;
- дождь;
- снег;
- туман;
- температуру/ощущение жары/холода;
- biome/terrain ambience, где уместно.

Никакой декоративной случайной погоды.

PW2 implementation status:

- ambient state is derived on each Workspace render from the active Character's
  centralized effective location;
- the current compatible AtmosphericSnapshot is sampled at that exact point and
  combined with RegionalSky at Campaign world time;
- Region and Character pages share one safe presentation adapter and one visual
  layer component rather than maintaining separate weather/sky engines;
- current rain/snow, cloud fraction and authoritative fog condition are used;
  interval accumulation is never presented as current precipitation;
- missing placement or environment produces neutral ambience without hidden
  simulation, fallback coordinates or technical Player output;
- raw coordinates, pressure/grid/provenance diagnostics and arbitrary-coordinate
  Player weather queries remain unavailable;
- ambience is derived presentation, not persisted Character state, and active
  Character switching rebuilds it for the newly selected point;
- heat/cold and optional stable biome keys are cosmetic only and do not patch C5
  physics or add gameplay consequences.

---

# 12. Ambient effects

Примеры:

```text
день → фон светлее
ночь → фон темнее
Ympha → красное внешнее освещение
дождь → ненавязчивые rain effects
снег → snow particles
туман → мягкое снижение контраста
жара → лёгкое heat shimmer
мороз → холодное визуальное ощущение
```

Эффекты не должны мешать чтению интерфейса и должны иметь accessibility/performance fallback.

---

# 13. Character location

Normal gameplay не позволяет GM произвольно перетаскивать Character по карте.

Position меняется через доменные действия мира:

```text
Travel
other explicit future movement services
```

## Initial placement

Character нуждается в исходной точке. Начальная позиция задаётся как Campaign setup при создании/подключении Character, пока location ещё отсутствует.

Это не normal gameplay teleport.

После initial placement обычное перемещение должно идти через Travel/domain movement.

Emergency data-repair tooling, если понадобится, является техническим admin recovery, а не GM gameplay control.

---

# 14. Travel

Player выбирает желаемую цель/маршрут.

Travel engine позже рассчитывает маршрут, длину, terrain, roads, biome, weather, transport, speed, provisions, time, checks и consequences.

Travel action может требовать ApprovalRequest, но Player UI не говорит «Отправить запрос DM».

Он видит действие мира:

```text
Отправиться в путь
```

Backend сам решает, нужен ли ApprovalRequest.

---

# 15. ApprovalRequest visibility

Player НЕ имеет отдельной очереди ApprovalRequest и не видит «Мои запросы» как постоянный Player module.

ApprovalRequest является backend/GM workflow.

Player взаимодействует с исходным действием:

```text
Отправиться
Купить
Присоединиться
Сделать
```

Состояние конкретного действия может отображаться контекстно, но не как техническая ApprovalRequest queue.

GM queue остаётся GM-only.

---

# 16. Party / Команда

Character может состоять максимум в одной active Party:

```text
Character → 0..1 active Party
```

История прошлых Party может существовать позже.

---

# 17. Party card на Index

Блок «Команда» показывает только:

```text
портрет
имя
```

Не показывать HP, AC, деньги, inventory, spell slots и другие sheet values.

---

# 18. Party full module

Party — отдельный future domain. Он может включать:

- участников;
- invitations;
- shared/current location;
- Travel;
- party map;
- team quests;
- team notes;
- future shared storage при необходимости.

Invite flow использует domain action + ApprovalRequest/consent infrastructure, но Player видит именно приглашение в команду.

---

# 19. Quests on Character Index

На Index показываются только активные:

```text
Личные
Командные
```

Completed quests не занимают основной экран.

Full Quest page:

```text
Активные
Завершённые
future failed/abandoned if rules need them
```

---

# 20. Notes

Отдельного CharacterKnowledge раздела не требуется.

Сюжетные сведения, слухи, подозрения и память остаются частью RP. Player сам ведёт Notes.

---

# 21. Personal Notes

```text
CharacterNote belongs to Character
```

Личные заметки видит только текущий controller этого Character.

GM не имеет обычного права читать личные Notes.

Нарративно Notes являются отражением мыслей/памяти персонажа в промежуточной реальности.

При reassignment Character личные Notes остаются с Character.

N1 implementation status:

- private state is `characters.CharacterNote` with an opaque UUID, optional
  short memo, required escaped plain-text body and technical-only timestamps;
- access is only through Campaign-scoped routes for the current active
  controller; GM, superuser diagnostic UI and other Players cannot browse it;
- access follows Character reassignment, while unassignment/archive/User
  deletion preserve the thoughts without exposing them;
- create/edit/release does not create Campaign AuditLog records;
- Workspace shows at most three thoughts; the full surface paginates and never
  displays dates, IDs, author or privacy metadata;
- creation and editing use the held-thought two-question experience, focused
  presentation and confirmed release, with no-JS and reduced-motion support;
- N1 surfaces reuse the live PW2 ambience without creating new weather state.

---

# 22. Party Notes

Отдельные Team/Party Notes:

```text
belongs to Party
visible to current Party members
```

Они не являются копией personal notes.

---

# 23. Visibility & Discovery вместо CharacterKnowledge

Полноценный generic CharacterKnowledge с Unknown/Rumor/Partial/Known сейчас не является основной продуктовой моделью.

Вместо него позже нужен узкий foundation:

```text
Visibility & Discovery
```

Он отвечает за системно необходимую видимость:

- открыт ли location;
- показывается ли POI;
- исследована ли карта;
- доступен ли Quest;
- публичен/открыт ли WorldEvent;
- обнаружен ли объект.

Он НЕ пытается моделировать всё содержимое головы Character.

Слухи/догадки/разговоры остаются RP + Notes.

---

# 24. Anti-meta UI rule

Player UI не должен сообщать само существование скрытых данных.

Плохо:

```text
Правитель: ???
Тайный культ: ???
Секретный вход: ???
```

Правильно: показывать только уже доступные Character-facing сведения.

Неизвестный объект может полностью отсутствовать на Player карте/поиске.

---

# 25. Map

Player Map отличается от GM Atlas.

В будущем она использует:

```text
Visibility / Discovery
+
exploration
+
current visibility
+
Character/Party position
```

Character current position является центральным элементом.

---

# 26. Economy / Money HUD

Money HUD показывает текущий доступный баланс Character.

По нажатию:

```text
Финансы
Баланс
Доходы
Расходы
История
Предстоящие обязательства
Долги
```

Source of truth — Ledger, не одно вручную редактируемое число.

---

# 27. Быт / Обязательства card

На Index кратко:

```text
Уровень жизни
Жильё
Долги
Регулярные услуги
следующее списание
стоимость за период
```

Полный module позже реализует E3 Recurring Economy & Lifestyle.

---

# 28. Inventory on Index

На основной Character странице показывается только то, что находится **при Character**.

Пример:

```text
ИНВЕНТАРЬ

Меч
Зелье ×2
Факел ×4
Карта

[Подробнее]
```

Не показывать домашний склад в quick list.

---

# 29. Inventory storage model

Inventory персонажа является абстрактным пространственным хранилищем «при себе».

Не требуется автоматически делать каждый рюкзак/сундук/мешок отдельным Container.

Такие предметы могут влиять на capacity/weight/storage rules без появления отдельного inventory-location.

---

# 30. Separate storages

Отдельные физически значимые хранилища могут существовать:

```text
Character Inventory
House Storage
Party Storage
Vehicle Storage
Shop Storage
```

В full Inventory screen:

```text
При себе
Домашний склад — если существует
Транспорт — если существует
другие реальные storage domains
```

Сундук в доме может быть capacity upgrade домашнего склада, а не обязательным отдельным storage location.

---

# 31. Item model direction

Future:

```text
ItemInstance
↓
meaningful Storage/Ownership context
```

Не создавать granular container hierarchy без gameplay необходимости.

---

# 32. Apotheosis

Apotheosis — future Craft-like gameplay mechanic.

Механику необходимо отдельно обсудить и спроектировать до реализации.

На Character Workspace можно резервировать module slot, но не fake functionality.

---

# 33. Requests/actions wording

Player не должен видеть техническое:

```text
ApprovalRequest
Request ID
Отправить запрос GM
```

Он видит действие мира:

```text
Отправиться в путь
Купить
Присоединиться к команде
Создать предмет
```

Backend ApprovalRequest остаётся скрытой orchestration layer.

---

# 34. WorldEvent visibility

Objective WorldEventOccurrence не становится автоматически Player-visible.

Future Visibility/Discovery/publication rules решают, что проявляется в Player-facing world.

Отдельного generic Knowledge page не требуется.

---

# 35. Product principle: perception, not omniscience

Character Workspace должен ощущаться как отражение:

```text
того, где Character находится
того, что с ним происходит
того, чем он владеет
того, что он делает
того, что он сам записал
```

Он не должен быть window into GM database.

---

# 36. Accessibility / reduced effects

Живой ambient UI должен поддерживать reduced motion, reduced particles, performance fallback и readability overrides.

Состояние мира остаётся тем же; отключаются только декоративные effects.

---

# 37. Near-term implementation direction

После фиксации этой архитектуры:

```text
P5.6 — Campaign Creation & GM Eligibility Alignment
PW1  — Character Workspace Shell
L1   — Character Location / Initial Placement
PW2  — Live Character Ambience at Effective Location
N1   — Notes Foundation
P6   — Party Foundation
M2   — Geography
V1   — Visibility & Discovery
```

Точный порядок M2/V1 может корректироваться при phase design.

---

# 38. Important invariants

```text
Player Campaign Index = active Character Workspace.
User != Character.
Character Workspace is diegetic-adjacent.
Platform bar is explicitly meta.
Ordinary new User cannot create Campaign.
Only superuser grants GM eligibility.
Player never gets a global ApprovalRequest inbox.
Normal Character movement happens through Travel/domain movement.
Initial placement is setup, not gameplay teleport.
Character can belong to only one active Party.
Party card reveals only names and portraits.
Personal Notes are private from GM.
Party Notes belong to Party.
No generic CharacterKnowledge UI.
Visibility/Discovery only controls system visibility.
Fardecosmia owns progression/economy/inventory/world-facing state.
Roll20 owns battle-runtime/combat representation where appropriate.
XP and money have transaction/history foundations.
Index Inventory shows only items currently with Character.
House/Vehicle/Party storages are separate meaningful stores.
Backpacks/chests do not automatically become nested storage locations.
Ambient UI is driven by real Character-location weather/sky data.
```
