# Фардекосмия — PW1 Character Workspace Shell

Дата подготовки: 2026-08-24

Статус: implementation specification.

## 0. Обязательное чтение перед работой

Перед изменениями перечитать полностью:

- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Player_Experience_Architecture_v1.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- `P5_5_CHARACTER_IDENTITY_PLAYER_WORKSPACE_REPORT.md`
- `P5_6_CAMPAIGN_CREATION_GM_ELIGIBILITY_ALIGNMENT_REPORT.md`

Не начинать L1, N1, P6, M2, V1, CH1, XP1, T1, I1, E1, Q1, TR1, Apotheosis/Craft, C5.

Reasoning: HIGH.

---

# 1. Цель PW1

Перестроить Player-facing Campaign experience вокруг **active Character Workspace**.

Для PLAYER:

```text
Campaign list
    ↓
Open Campaign
    ↓
resolve active Character
    ↓
Character Workspace
```

Campaign больше не имеет отдельного Player dashboard между списком Campaign и Character Workspace.

PW1 — это shell/layout/foundation. Он НЕ реализует будущие gameplay systems и НЕ создаёт fake data.

---

# 2. Нарративный UX принцип

Character Workspace — интерфейс, который персонаж воспринимает через промежуточную реальность.

Он должен ощущаться как отражение:

- персонажа;
- его состояния;
- его вещей;
- его развития;
- мира вокруг него;
- его действий.

Не использовать в Player UI техническую/developer лексику вроде:

- `ApprovalRequest`;
- «Мои запросы»;
- «после этапа CharacterKnowledge»;
- «появится после Ledger»;
- «normalized CharacterSheet»;
- database IDs / permission names / implementation notes.

Platform-level элементы допустимы только как минимальный meta shell:

```text
Все кампании
Настройки
Выйти
```

---

# 3. Campaign list для PLAYER

Сохранить Campaign cards как platform-level navigation.

Для PLAYER card содержит:

- Campaign title;
- description;
- PLAYER badge/status if already used;
- primary action `Открыть кампанию`.

Удалить из нормального Player UX:

```text
Мои запросы
```

со всех Campaign cards и player navigation surfaces.

Не удалять P4 ApprovalRequest backend/GM queue только ради PW1.

---

# 4. Player Campaign open behavior

PLAYER `Открыть кампанию` не должен вести на старый промежуточный dashboard.

Алгоритм:

## 4.1 Нет контролируемого Character

Показать human-first empty state:

```text
Персонаж ещё не назначен.
```

С возможностью вернуться ко всем Campaign.

Не создавать placeholder Character.

## 4.2 Один доступный Character

Использовать существующую P5.5 semantics `get_active_character(user, campaign)`.

Не дублировать active-character resolution.

Если helper возвращает single-character fallback без GET mutation — сохранить эту семантику.

## 4.3 Несколько Characters

Использовать persisted `CampaignMembership.active_character` и существующий P5.5 switch flow.

Если active Character отсутствует/invalid и Characters несколько — показать выбор Character, не угадывать.

## 4.4 Active Character найден

Рендерить Character Workspace как Player Campaign Index.

---

# 5. Character Workspace composition

Основной shell ориентируется на утверждённый UX-макет, но не обязан быть pixel-perfect копией sketch.

Desktop conceptual layout:

```text
┌──────────────────────────────────────────────────────┐
│ ← Все кампании                     Settings / Logout │
│                                                      │
│                CHARACTER WORLDSPACE                  │
│                                                      │
│ ┌────────────────────┐ ┌───────────────────────────┐ │
│ │ ТИАМАНА            │ │ АКТИВНЫЕ КВЕСТЫ          │ │
│ └────────────────────┘ └───────────────────────────┘ │
│                                                      │
│ ┌────────────────────┐ ┌───────────────────────────┐ │
│ │ КАРТА              │ │ БЫТ / ОБЯЗАТЕЛЬСТВА      │ │
│ └────────────────────┘ └───────────────────────────┘ │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ КОМАНДА                                          │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌────────────────────┐ ┌───────────────────────────┐ │
│ │ ЗАМЕТКИ            │ │ APOTHEOSIS               │ │
│ └────────────────────┘ └───────────────────────────┘ │
│                                                      │
│ ИНВЕНТАРЬ — вещи при персонаже           [Подробнее] │
│                                                      │
│ [reserved XP soul HUD]                  [Money HUD]  │
└──────────────────────────────────────────────────────┘
```

---

# 6. Тиамана card

PW1 не реализует CharacterSheet/normalized state/level-up.

Карточка должна существовать как будущий primary progression module.

Разрешено показывать только уже существующие безопасные identity сведения Character, если это помогает композиции.

Не писать:

```text
Появится после normalized CharacterSheet и Roll20 adapter
```

Предпочтительно human empty/locked state без developer roadmap wording.

Не читать raw Roll20 attributes.

---

# 7. Quests card

PW1 не создаёт Quest models.

Карточка резервирует место для:

- active personal quests;
- active party quests.

Completed quests в будущем смотрятся отдельно, не захламляют Index.

Пока данных нет — clean empty state без fake quests и без roadmap terminology.

---

# 8. Map card

PW1 не реализует L1 Character Location, Travel или Player Map.

Карточка является integration surface.

Не придумывать координаты Character.

Не использовать Region centroid как fake Character position.

Не подключать C4.2 weather ambience без реальной effective Character location.

---

# 9. Быт / Обязательства card

PW1 не реализует Ledger/E3.

Будущий content contract:

- lifestyle;
- housing;
- debts;
- recurring services;
- amount per billing period;
- next billing boundary.

Пока — clean empty/unavailable state без fake money.

---

# 10. Party card

PW1 не создаёт Party model.

Будущий compact card показывает только:

```text
portrait + Character name
```

Никаких HP/AC/money/inventory/combat stats других Characters.

Пока Party не существует — human empty state.

---

# 11. Notes card

PW1 не реализует N1.

Зарезервировать module entry.

Не использовать старую карточку `Что знает персонаж`.

Полностью убрать Player-facing CharacterKnowledge placeholder/terminology.

Будущая semantics:

- Personal Notes — принадлежат Character, private from GM in ordinary UI;
- Party Notes — принадлежат Party.

---

# 12. Apotheosis card

PW1 создаёт только visual module slot.

Не реализует механику.

Не связывать с XP/corruption автоматически.

Не выдумывать crafting data.

---

# 13. Inventory quick section

PW1 не реализует I1 Item/Inventory models.

Но shell должен соответствовать будущему contract:

- на Index показываются только вещи **при Character**;
- домашний склад/transport/party storage не должны появляться в quick list;
- full Inventory позже показывает отдельные meaningful storages;
- backpacks/chests не обязаны становиться nested storage locations.

Пока Item system отсутствует — clean empty state.

---

# 14. XP soul HUD integration point

PW1 НЕ реализует финальный XP HUD/animation.

Не внедрять сейчас Soul assets, GIF/WebP fill, particles, level-up burst, sound или XP transactions.

Подготовить только устойчивый layout/integration anchor для будущего HUD.

Будущий HUD должен поддерживать:

- soul-shaped XP visualization instead of plain progress bar;
- animated fill;
- XP particles flying toward soul;
- subtle glint just before level-up transition;
- level-up full-screen transition to Тиамана;
- sound;
- reduced-motion/accessibility fallback.

Это future XP1/T1/HUD work, не PW1.

---

# 15. Money HUD integration point

PW1 НЕ реализует Ledger.

Подготовить layout anchor для persistent Character money HUD.

Не показывать fake balance / `0` как будто это реальное состояние.

Future source of truth = Ledger.

---

# 16. ApprovalRequest / «Мои запросы»

Обязательное PW1 изменение.

Удалить Player-facing navigation to `Мои запросы` из:

- Campaign cards;
- Player Campaign landing/dashboard;
- Character workspace;
- player nav/quick actions.

Сам ApprovalRequest backend, handlers, GM queue, audit и tests не удалять.

Если старый Player route существует и его удаление создаёт regression risk — можно оставить compatibility route, но он не должен быть discoverable из normal Player UX.

Future Player actions показывают состояние domain action, а не generic request queue.

---

# 17. Старый Character detail

Текущий P5.5 Player Character detail с карточками вроде:

```text
Игровой лист
Что знает персонаж
Предметы и снаряжение
История приключений
```

не является финальным Player Workspace.

PW1 должен заменить/перенаправить normal Player navigation так, чтобы основной Character-facing экран был новым Workspace.

Не оставлять `Что знает персонаж` в normal Player UX.

Если отдельный technical Character detail нужен для compatibility/tests, он не должен быть primary Player destination.

---

# 18. Character identity presentation

Player Workspace должен ясно показывать, каким Character сейчас играет User, но не превращаться в database detail page.

Допустимо:

- Character name;
- biography/short visual identity where existing data supports it;
- portrait if already supported safely;
- active-character selector when multiple.

Не показывать:

- DB IDs;
- owner FK;
- GM notes;
- raw Roll20 data;
- permission/debug state.

---

# 19. Multiple Character switching

Сохранить P5.5 switching semantics.

Switcher должен быть доступен Character controller при multiple controlled Characters.

POST + CSRF only.

Switch должен приводить обратно в Character Workspace выбранного Character.

Не создавать новый selection store.

---

# 20. Player vs GM routing

Не ломать GM Campaign dashboard/workspace.

Для GM существующий objective Campaign management остаётся отдельным.

PLAYER `Open Campaign` → Character Workspace.

GM `Open Campaign` → GM workspace согласно существующей архитектуре, если уже реализовано.

Если User одновременно GM и имеет controlled Character, не смешивать автоматически два режима; использовать текущий role/access contract и задокументировать фактическое решение.

---

# 21. Mobile

Обязательная проверка 390×844.

- no horizontal overflow;
- cards stack naturally;
- persistent HUD anchors do not cover content;
- Character switch controls usable by touch;
- module labels readable;
- platform navigation remains reachable.

---

# 22. Accessibility

PW1 должен подготовить архитектуру для future ambient/HUD effects, но сам shell должен быть usable без animations.

Не вводить critical interaction, доступный только через hover/animation.

---

# 23. Security / IDOR

Сохранить/расширить tests:

- Player cannot open another Player's Character Workspace;
- cross-Campaign Character cannot be selected via forged URL/POST;
- archived/unowned Character cannot become active;
- foreign Campaign cannot be accessed by changing IDs;
- GM-only data absent from Player response;
- raw Roll20 payload absent;
- Player-facing hidden ApprovalRequest navigation absent.

Reuse P5.5 central services/helpers.

---

# 24. Query/performance guardrail

Не создавать N+1 при resolving Character/controller/portrait/basic display.

PW1 не должен вызывать atmosphere solver or expensive map processing.

---

# 25. Tests

Добавить focused PW1 test module, покрывающий минимум:

1. Player Campaign card no longer shows `Мои запросы`.
2. PLAYER Open Campaign with active Character renders Workspace.
3. No intermediate old Player campaign dashboard in normal flow.
4. No Character → human empty state.
5. Multiple Characters → valid active selection/switch.
6. No `Что знает персонаж` text/placeholder.
7. No developer-roadmap wording in Player page.
8. No fake XP/money/inventory/quest values.
9. `Все кампании` navigation available.
10. GM-only fields absent.
11. IDOR/cross-campaign denial.
12. Existing P4 ApprovalRequest GM functionality still works.
13. P5/P5.5/P5.6 regressions remain green.

---

# 26. Browser/manual verification

Verify with isolated data:

## Desktop

- Campaign list;
- Open Campaign;
- active Character Workspace;
- multiple-character switching;
- no requests links;
- no old knowledge placeholder;
- no console errors.

## 390×844 mobile

Same flow + no horizontal overflow.

Remove isolated browser data afterward.

---

# 27. Mandatory validation

After implementation:

```text
focused PW1 tests
related P4/P5/P5.5/P5.6 regression
full suite
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
git status
```

If PW1 genuinely requires no schema migration, do not create one just for phase bookkeeping.

---

# 28. Documentation updates

After successful implementation update:

- `AGENTS.md` — Player Campaign Index / diegetic-adjacent Player UX guardrails;
- `WORLD_HANDOFF_v2.md` — PW1 completion/current Player shell;
- Architecture Guardrails — Player vs GM workspace boundaries;
- `Fardecosmia_Master_Roadmap_v1_1.md` — mark PW1 complete, L1 next;
- implementation report `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`.

Do not mark future modules implemented simply because their visual slots exist.

---

# 29. Crash / resume protocol

Create `docs/PW1_PROGRESS.md` before implementation.

After each milestone record:

- completed work;
- changed files;
- tests passed;
- current failures/known issues;
- exact next step.

Suggested milestones:

```text
Phase 0 — audit current Player routes/templates/tests
Phase 1 — routing / Campaign open behavior
Phase 2 — Workspace layout
Phase 3 — remove requests/old knowledge surfaces
Phase 4 — multiple Character + permissions regressions
Phase 5 — browser/mobile
Phase 6 — full regression/docs/report
```

If session dies, resume from checkpoint and current git diff. Do not restart phase.

---

# 30. Explicit non-goals

PW1 MUST NOT implement:

- L1 Character location;
- live weather ambience;
- Notes models;
- Party models;
- CharacterKnowledge;
- Visibility/Discovery;
- Countries/Settlements/Roads/POI;
- XP transactions;
- final soul XP HUD/animations;
- Ledger/money;
- Inventory/Item models;
- Quests;
- Travel;
- CharacterSheet/normalized Roll20 sync;
- Apotheosis/Craft mechanics;
- C5 climate changes.

Stop after PW1 report.

---

# 31. Acceptance criteria summary

PW1 is accepted only if:

```text
PLAYER Campaign list:
✓ no «Мои запросы»

PLAYER Open Campaign:
✓ active Character Workspace directly
✓ no intermediate old Player dashboard

Character Workspace:
✓ approved module composition exists
✓ no «Что знает персонаж»
✓ no ApprovalRequest terminology
✓ no developer roadmap wording
✓ no fake gameplay data
✓ multiple Character switching preserved
✓ return to all Campaigns available
✓ GM-only/raw Roll20 data absent
✓ mobile 390×844 works

Backend:
✓ P4 ApprovalRequest still intact for GM/orchestration
✓ P5/P5.5/P5.6 regressions intact
✓ no out-of-scope gameplay phase started
```
