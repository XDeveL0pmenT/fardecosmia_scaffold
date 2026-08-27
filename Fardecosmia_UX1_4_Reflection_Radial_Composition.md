# Фардекосмия — UX1.4
# Reflection Radial Composition

Дата: 2026-08-26  
Статус: implementation specification  
Тип: frontend-only visual/layout pass

Рекомендуемый режим Codex:
- новый тред;
- Reasoning: **High / Высокий**;
- не использовать full-suite до визуального acceptance.

---

# 0. Цель

UX1.4 перестраивает Character Workspace из вертикальной композиции узлов в
**радиальное Отражение**, где сам Character находится в центре, а основные
сферы его существования расположены вокруг него.

Ключевая идея:

```text
                   Команда

          Карта                Быт

    Тиамана         CHARACTER        Квесты

       Мысли                    Apotheosis

                 Инвентарь
```

Character — не hero-card и не профиль пользователя. Он является **ядром Отражения**.

Сохраняются уже принятые UX1.3 системы:

- Dark Glass Shards;
- Focus Field;
- single-owner pointer focus;
- local refraction;
- hover/focus scale;
- controlled easing;
- reduced-motion;
- Memory Space;
- Notes whole-node navigation;
- PW2 live ambience на главном Workspace.

UX1.4 не переписывает эти системы, а перестраивает композицию вокруг них.

---

# 1. Scope guard

Frontend-only.

Не менять:

- Django models;
- migrations;
- permissions;
- Character ownership;
- Notes privacy;
- N1 create/edit/release semantics;
- AuditLog policy;
- L1 location;
- PW2 atmosphere/sampler;
- Campaign world time;
- Party;
- Travel;
- XP backend;
- Ledger/Money backend;
- Inventory backend;
- Quests backend;
- Apotheosis mechanics.

Не создавать fake gameplay state.

---

# 2. Перед началом

Прочитать только необходимое:

- `AGENTS.md`;
- `docs/UX1_3_PROGRESS.md`;
- `UX1_3_REFLECTION_VISUAL_POLISH_STABILIZATION_REPORT.md`;
- текущий `character_workspace.html`;
- текущий Reflection/Focus CSS;
- `reflection-focus.js`.

Не перечитывать весь исторический handoff и климатические документы: UX1.4 не меняет
domain logic.

Перед изменениями:

```text
git status
git diff
```

Зафиксировать текущий UX1.3 как baseline.

Создать:

```text
docs/UX1_4_PROGRESS.md
```

---

# 3. Main desktop composition

На desktop Character Workspace должен перестать читаться сверху вниз.

Создать отдельную сцену:

```text
reflection-radial-scene
```

В центре:

```text
character-core
```

Вокруг него стабильные anchors.

Рекомендуемая семантическая композиция:

```text
                       Party
                       top

          Map                         Lifestyle
        upper-left                  upper-right

  Tiamana                Character Core             Quests
  middle-left                                      middle-right

       Held Thoughts                         Apotheosis
       lower-left                            lower-right

                     Inventory
                    bottom-center
```

Это не случайный scatter.

Каждый node имеет постоянный conceptual anchor.

Асимметрия допустима внутри самого shard и в небольших отклонениях позиции, но общая
композиция должна быть сбалансированной.

---

# 4. Character Core

Удалить ощущение отдельного hero/header.

Character Core содержит:

- portrait;
- центральный visual aura/glitch asset;
- тихий Character name по Variant B;
- никаких больших profile-card borders.

## Variant B — имя

Имя Character **не показывается постоянно крупным текстом**.

На desktop:

```text
idle
→ portrait/core является главным identity signal
→ name hidden / almost invisible

hover/focus Character Core
→ Character name softly manifests near/below portrait
```

Имя не должно прыгать layout.

Использовать absolute/overlay presentation либо reserved tiny zone.

Keyboard focus обязан также проявлять имя.

На mobile имя можно показывать постоянно маленьким текстом, если hover отсутствует и
иначе identity станет непонятной.

---

# 5. Character Core aura GIF

В static уже существует подготовленный пользователем белый animated aura/glitch asset.

Codex сначала должен найти **точный существующий static filename** и переиспользовать его.
Не создавать копию и не переименовывать asset без необходимости.

Layering:

```text
background
↓
white aura/glitch GIF
↓
portrait
↓
optional identity focus layer
```

Требования:

- прозрачность настраивается CSS;
- начать визуально примерно в диапазоне `opacity: 0.25–0.45`, подобрать в browser;
- aura не должна выжигать portrait;
- `pointer-events: none`;
- не перекрывает лицо/кликабельную область;
- размер может быть чуть больше portrait;
- никаких fake gameplay semantics.

При focus Character Core aura может стать немного ярче.

Не привязывать её к XP.

---

# 6. Character Core interaction

Character Core участвует в Focus Field.

При приближении pointer:

- portrait slightly scales;
- aura clarity/opacity немного возрастает;
- Character name проявляется;
- близлежащие connectors немного активируются;
- окружающие nodes слегка recede.

Не делать Character Core отдельной кнопкой, если route/action пока отсутствует.

Если текущий active Character switcher всё ещё технически необходим, сохранить native
fallback вне основной визуальной композиции максимально тихо.

Поскольку продуктово обычно ожидается один Character, switcher не должен занимать
центральное место.

Не создавать новую Character switching механику в UX1.4.

---

# 7. Radial connectors

От Character Core к каждому основному reflection node идут визуальные связи.

Пользователь уже подготовил animated narrow white connector GIF в static.

Сначала найти exact asset.

Connector architecture:

```text
Character center
→ connector visual layer
→ target node anchor
```

Каждый connector:

- находится под node content и под portrait;
- `pointer-events: none`;
- low idle opacity;
- не мешает PW2 rain/snow;
- не закрывает текст;
- не является gameplay route.

Рекомендуемое поведение:

```text
idle connector
opacity ~0.08–0.18

target node focused
corresponding connector opacity ↑
subtle glow ↑
```

Не делать все линии яркими одновременно.

---

# 8. Connector geometry

Не рисовать вручную SVG-граф дорогой архитектурой.

Разрешён простой visual connector element на каждый anchor.

Если asset вертикальный:

1. создать прямоугольный connector container;
2. вычислить/задать направление между Core и anchor;
3. повернуть container через CSS transform;
4. растянуть визуальный asset преимущественно по длине;
5. сохранить достаточную ширину, чтобы texture не превратился в один пиксель.

Если JS нужен только для геометрии:
- вычислять после layout;
- пересчитывать на resize;
- не запускать постоянный loop;
- не читать layout на каждом pointer frame.

Если CSS-only anchor geometry надёжнее — предпочесть CSS.

---

# 9. Connectors + Focus Field

Focus Field и connectors должны работать совместно.

Pointer не управляет самими линиями напрямую.

Линия активируется потому, что target node является текущим `activePointerNode`.

```text
focus Tiamana
→ Tiamana shard reacts
→ connector Character↔Tiamana clarifies
→ остальные connectors remain dim
```

Использовать уже существующий single-owner focus state.

Не создавать вторую hover-state machine.

---

# 10. Dark Glass Shards remain

Не переделывать визуальный material UX1.3.

Сохраняются:

- curated silhouettes;
- shape-aware highlights;
- local refraction;
- no roaming glare;
- single shape source;
- current hover/focus behavior.

UX1.4 меняет преимущественно:
- position;
- scale hierarchy;
- spatial composition.

Можно слегка адаптировать размеры shards под radial placement.

---

# 11. Node hierarchy

Не все блоки должны иметь одинаковый visual weight.

Предпочтительная иерархия:

```text
Character Core
→ главный центр

Party
→ широкий social anchor

Tiamana / Quests
→ крупные primary nodes

Map / Lifestyle
→ средние nodes

Held Thoughts / Apotheosis
→ средние internal/mystic nodes

Inventory
→ широкий, более материальный нижний node
```

Сохранять читабельность текста.

---

# 12. Party placement

Party/Команда располагается сверху над Character Core.

В UX1.4 это только существующий placeholder node.

Не создавать Party logic.

В будущем этот anchor сможет вместить portraits/names членов Party.

Не добавлять fake portraits сейчас.

---

# 13. Map / Lifestyle

Расположение:

```text
Map       upper-left
Lifestyle upper-right
```

Семантический баланс:

```text
Map
→ где Character находится

Lifestyle
→ как Character живёт
```

Map продолжает показывать только текущий player-safe state.

Не создавать Player Map в UX1.4.

---

# 14. Tiamana / Quests

Расположение ближе всего к центральной горизонтали:

```text
Tiamana   left of Character
Quests    right of Character
```

Семантика:

```text
Tiamana
→ внутреннее развитие

Quests
→ внешнее направление
```

Не создавать реальные mechanics.

---

# 15. Held Thoughts / Apotheosis

Расположение:

```text
Held Thoughts   lower-left
Apotheosis      lower-right
```

Notes shard остаётся целиком кликабельным и ведёт в Memory Space.

`Удержать мысль` остаётся отдельным действием.

Не ломать N1 interaction.

Apotheosis остаётся placeholder.

---

# 16. Inventory

Inventory располагается под Character Core в bottom-center.

Он должен ощущаться наиболее материальным reflection node.

Не превращать его в footer.

Не растягивать почти на всю ширину viewport.

Подобрать умеренную ширину, чтобы он оставался самостоятельным shard.

No inventory backend work.

---

# 17. PW2 ambience

Главный Workspace продолжает использовать настоящее окружение Character из PW2.

Radial scene должна существовать поверх:

- day/night;
- Ympha;
- clouds;
- rain;
- snow;
- fog;
- heat/cold.

Новые GIF layers не должны уничтожать читаемость PW2.

Z-index hierarchy должна быть явно организована.

Пример:

```text
PW2 ambient background
↓
radial connector layer
↓
Character aura
↓
reflection nodes + Character portrait
↓
HUD
↓
platform shell
```

Фактический порядок адаптировать под текущий DOM.

---

# 18. HUD — Soul / XP visual anchor

Нижний левый угол получает отдельный fixed Soul visual.

В static уже находится подготовленный пользователем animated chromatic circular burst
и существующий soul/sigil visual asset.

Сначала найти реальные asset filenames.

Желаемая layering:

```text
chromatic animated burst
↓
soul sigil
↓
future XP state
```

В UX1.4 это **только visual integration anchor**.

Запрещено отображать fake:

```text
XP 42%
Level 4
2380 XP
```

Если backend XP ещё не существует — никаких чисел/progress.

Soul HUD:
- `position: fixed`;
- нижний левый;
- достаточно заметный;
- не перекрывает Workspace shard;
- clickable только если уже существует реальное действие (скорее всего нет);
- `pointer-events:none` для purely decorative animated layers.

---

# 19. Soul GIF opacity

Chromatic burst не должен визуально захватывать страницу.

Настроить:
- opacity;
- brightness/filter;
- size.

Проверить на:
- bright PW2 day/rain;
- dark/night Workspace.

Цель: Soul anchor заметный, но не становится самым ярким объектом интерфейса постоянно.

В будущем XP animation сможет кратко усиливать его, но UX1.4 это не реализует.

---

# 20. Money HUD

Верхний правый угол резервируется под Money HUD.

Форма может следовать текущему Dark Glass HUD language.

Важно:

**не показывать mock `000` как будто это реальный баланс.**

Пока E1 Ledger не существует, safe state:

```text
◇   —
```

или только icon/neutral unrevealed state согласно уже существующей shell semantics.

Не создавать money model.

Money HUD fixed и остаётся на Character-facing pages where intended.

---

# 21. HUD and Platform shell

Money HUD не должен конфликтовать с верхним Platform shell.

Проверить spacing для:

```text
Кампании
Настройки
аккаунт
Выйти
Money HUD
```

Если верхний правый угол занят shell, HUD может располагаться сразу под shell или в
безопасной fixed зоне.

Не перекрывать navigation.

---

# 22. Desktop viewport

Radial composition проектируется для нормального desktop/laptop viewport.

Нельзя требовать 4K display.

Проверить минимум:
- 1280×720;
- около 1440×900 / эквивалент.

Scene может иметь sensible min/max dimensions.

Если viewport недостаточно высокий:
- radial distances уменьшаются;
- shards slightly scale down;
- не появляется overlap.

Не заставлять пользователя горизонтально scroll.

---

# 23. Mobile behavior

На mobile НЕ пытаться сохранять radial graph в уменьшенном виде.

При `390×844` использовать понятную вертикальную Character composition.

Но сохранить новую визуальную identity:

```text
Character Core
↓
Tiamana
↓
Quests
↓
Map
↓
Lifestyle
↓
Party
↓
Notes
↓
Apotheosis
↓
Inventory
```

Connectors на mobile:
- убрать либо радикально упростить;
- не рисовать хаотичные диагональные линии;
- Soul/Money HUD адаптировать, чтобы не закрывали content.

No pointer Focus Field on coarse pointer, как уже принято.

---

# 24. Reduced motion

При `prefers-reduced-motion: reduce`:

- Focus pointer motion disabled как сейчас;
- connector GIF animation нельзя надёжно остановить CSS, поэтому предусмотреть static
  fallback / hidden animated layer where practical;
- Character aura animated GIF заменить/снизить до static-safe representation where
  current project conventions allow;
- Soul animated burst не должен быть mandatory для comprehension.

Минимум:
- animations являются декоративными;
- функциональность и layout не зависят от них.

Не переписывать GIF-файлы.

---

# 25. Asset handling

Все три пользовательских visual assets уже находятся в static.

Codex обязан:

1. найти exact current filenames;
2. не дублировать файлы;
3. не base64-embed assets;
4. использовать `{% static %}` / существующий Django static pattern;
5. не менять original GIF files;
6. настраивать размер/opacity/filter только presentation CSS.

Если несколько похожих GIF assets существуют — определить нужный по dimensions/content
и зафиксировать выбор в checkpoint.

---

# 26. Page entrance

Radial scene может иметь короткий entrance:

```text
Character Core appears
↓
connectors faintly resolve
↓
nodes softly settle around Core
```

Но:
- коротко;
- не каждый hover;
- не задерживать доступ;
- не более ~300–500ms ощущения;
- no long cinematic.

Если текущие Character page transitions уже дают достаточно эффекта — не дублировать.

---

# 27. Focus behavior in radial scene

Существующий Focus Field становится сильнее семантически.

Node focus:

```text
target shard clarity ↑
scale ↑
local refraction ↑
corresponding connector ↑
Character Core shifts subtly relative to target
siblings recede slightly
```

Не двигать весь radial layout настолько сильно, чтобы anchors теряли композицию.

Focus motion = depth, не repositioning layout.

---

# 28. Character Core focus

При наведении на portrait:

- portrait scale slightly ↑;
- white aura ↑;
- Character name manifests (Variant B);
- all connectors may softly clarify together;
- nodes remain mostly idle.

Это показывает, что внимание вернулось к самому Отражению.

---

# 29. Accessibility

- reflection nodes остаются semantic links/sections;
- keyboard focus не зависит от mouse;
- Character name должен быть доступен screen reader постоянно, даже если визуально
  проявляется только на hover;
- decorative GIFs `aria-hidden`;
- decorative layers не получают Tab focus;
- HUD placeholders не должны выдавать fake semantic data;
- whole-node Notes link сохраняется.

---

# 30. Performance

Нельзя добавлять новый постоянный RAF engine.

Использовать существующий Focus Field.

Connector geometry:
- calculate on initial layout/resize only if JS required;
- no geometry calculation per pointer frame.

GIF assets:
- ограничить rendered dimensions;
- не создавать десятки копий одного high-resolution GIF без необходимости;
- 7–8 connector instances допустимы только если browser performance остаётся нормальной.

Если animated connector GIF оказывается слишком тяжёлым:
- использовать fewer shared visual lines;
- либо CSS/static fallback;
- не ухудшать responsiveness ради точного повторения mockup.

---

# 31. Что НЕ делать

Не превращать layout в:
- RPG skill tree;
- constellation map с fake mechanics;
- spider chart;
- radial menu;
- navigation wheel.

Это не меню вокруг аватара.

Это **пространственная композиция Отражения**, где nodes всё ещё являются содержательными
блоками.

Не использовать connecting lines как interactive edges.

---

# 32. Implementation strategy / quota guard

Из-за текущих Codex rate limits UX1.4 выполнять короткими milestones.

## Turn 1 — Radial Composition

Сделать только:

- Character Core;
- remove remaining hero layout;
- desktop radial anchors;
- balanced shard sizing;
- responsive fallback/mobile;
- preserve Focus Field.

После:
- `manage.py check`;
- very focused presentation tests;
- 2–3 browser screenshots;
- update `docs/UX1_4_PROGRESS.md`;
- STOP.

НЕ делать GIF/HUD в Turn 1.

Пользователь проводит visual acceptance.

## Turn 2 — GIF & HUD Integration

После explicit continue:

- Character aura GIF;
- connectors;
- Soul visual anchor;
- Money HUD placement;
- opacity/filter/z-index;
- Focus connector response.

После:
- targeted browser check;
- mobile;
- checkpoint;
- STOP.

## Turn 3 — Final polish

Только после visual feedback:

- spacing;
- opacity;
- connector strength;
- Core/name focus;
- small transition polish;
- focused regression.

Full Django suite — только после final visual acceptance.

---

# 33. Turn 1 acceptance criteria

Первый milestone принят, если:

- desktop Workspace читается как radial Reflection scene;
- Character находится в центре;
- hero-card больше нет;
- Variant B name behavior подготовлено/работает;
- nodes имеют стабильные balanced anchors;
- Dark Glass UX1.3 сохранён;
- Focus Field не сломан;
- Notes whole-node navigation не сломана;
- PW2 ambience работает;
- no node overlap на 1280×720;
- mobile 390×844 остаётся usable;
- никаких новых GIF/HUD changes пока нет;
- no backend/migration changes.

---

# 34. Turn 2 acceptance criteria

GIF/HUD milestone принят, если:

- white aura sits behind Character portrait;
- opacity не выжигает portrait;
- connectors visually connect Core and nodes;
- idle connectors remain subtle;
- focused node connector becomes clearer;
- no connector crosses readable text;
- Soul HUD correctly uses existing assets without fake XP;
- Money HUD does not show fake balance;
- PW2 remains readable;
- GIF layers are decorative/accessibility-safe;
- desktop/mobile clean;
- no new backend state.

---

# 35. Final verification

После visual acceptance:

```text
focused presentation/N1/PW2 tests
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

Full suite один раз в самом конце.

Не гонять full suite после каждого CSS adjustment.

---

# 36. Documentation

UX1.4 пока остаётся visual experiment.

Обновлять:
- `docs/UX1_4_PROGRESS.md`.

Не переписывать глобальный Character UI Design System до того, как пользователь визуально
примет radial composition.

После final acceptance создать:

```text
UX1_4_REFLECTION_RADIAL_COMPOSITION_REPORT.md
```

Но только после всех visual turns.

---

# 37. Stop

После каждого Turn строго STOP.

Не начинать следующий milestone без явного сообщения пользователя.

Не начинать P6, XP1, Ledger, Inventory, Travel или другие gameplay-фазы.
