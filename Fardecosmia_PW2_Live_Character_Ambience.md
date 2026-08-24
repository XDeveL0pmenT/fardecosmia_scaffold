# Фардекосмия — PW2
# Live Character Ambience at Effective Location

Дата подготовки: 2026-08-24
Статус: implementation specification
Рекомендуемый Codex Reasoning: **Very High / Очень высокий**

---

# 0. Phase goal

PW2 оживляет Character Workspace реальным текущим окружением в физической точке персонажа.

Главная цепочка:

```text
active Character
↓
get_effective_character_location()
↓
точка Фардекосмии
↓
существующий authoritative point-environment sampler
+
существующий RegionalSky / sky-state pipeline
+
World Data / biome context where already supported
↓
Player-safe ambient state
↓
Character Workspace background / weather effects
```

PW2 — presentation/read phase.

Он НЕ:
- двигает Character;
- не меняет Weather;
- не запускает simulation advance;
- не создаёт Player Map;
- не создаёт Visibility/Discovery;
- не делает C5;
- не калибрует климат;
- не меняет Roll20/XP/Inventory/Economy.

---

# 1. Core product rule

Character Workspace — отражение восприятия Character в промежуточной реальности.

Ambience должен ощущаться как окружающая реальность:
- светло/темно;
- Ympha окрашивает свет;
- идёт дождь;
- идёт снег;
- небо облачное;
- окружение жаркое/холодное.

Player не должен видеть:
- grid cell indexes;
- solver internals;
- raw atmospheric JSON;
- pressure diagnostics;
- GM weather debug data;
- simulation revisions;
- latitude/longitude.

---

# 2. Mandatory Phase 0 audit

До изменений полностью перечитать:
- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Player_Experience_Architecture_v1.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`
- `L1_CHARACTER_LOCATION_INITIAL_PLACEMENT_REPORT.md`

Дополнительно проаудировать существующую Region ambience:
- Region page template;
- CSS/JS;
- Weather card;
- `RegionalSky`;
- day/night brightness;
- Ympha red-light handling;
- rain;
- snow;
- cloudiness;
- fog/haze, если реально существует;
- environment-summary services;
- arbitrary-point weather/environment sampler;
- C4.2 point semantics;
- existing Region visual ambience tests.

Главный принцип:

> Не писать второй отдельный weather/sky visual engine для Character Workspace, если существующую Region ambience можно переиспользовать или безопасно выделить в shared component/service.

---

# 3. Existing atmosphere contract — do not reinterpret

PW2 следует текущей C4.2/C4.1 архитектуре:
- continuous atmospheric fields at arbitrary point use existing point sampler;
- continuous fields follow existing bilinear semantics;
- surface pressure uses existing coherent point path;
- elevation follows existing point semantics;
- surface/biome remain discrete according to current World Data contract;
- current precipitation и accumulated precipitation не взаимозаменяемы;
- ambience uses **current** conditions, not accumulated rain;
- Region diagnostics/Weather card и Character ambience должны оставаться согласованными.

Не выбирать ближайший Region как замену фактической точке Character.

---

# 4. No simulation mutation on page read

Workspace GET только читает состояние.

Запрещено на GET:
```text
advance_world()
advance atmosphere
apply_external_tendencies()
spinup
fast-forward
write WeatherState
write Region state
write Character location
```

Если environment state недоступен — нейтральный ambience, а не скрытая симуляция.

---

# 5. Effective Character location is mandatory

Все location reads идут через:
```python
get_effective_character_location(character)
```

Не читать напрямую `character.location_state.latitude/longitude` в views/templates/JS.

---

# 6. Character without effective location

Если resolver возвращает `None`:
- sampler не вызывается;
- координаты не угадываются;
- Campaign/Region center не используется;
- `(0,0)` не используется;
- Workspace остаётся нейтральным.

---

# 7. Shared ambience service

Создать/выделить центральную Player-safe presentation boundary, например:
```python
build_character_ambience(character, campaign)
```

Ответственность:
```text
effective location
↓
read point environment
↓
read/derive sky state through existing RegionalSky path
↓
convert authoritative values to safe presentation tokens
↓
return immutable/read-only ambience context
```

Climate formulas не должны жить в templates/JS.

---

# 8. Prefer shared Region/Character presentation model

Если Region ambience сейчас ad-hoc:
1. проаудировать;
2. выделить common safe presentation logic;
3. сохранить Region behavior;
4. Character Workspace использует те же normalized ambient tokens.

Желаемая архитектура:
```text
authoritative atmosphere / sky
          ↓
shared ambient presentation adapter
          ↓
      ┌───────────┐
      │           │
Region UI    Character Workspace
```

---

# 9. Safe presentation tokens

Допустимы normalized tokens:
```text
has_environment
light_level
is_dark
ympha_light_strength
ympha_tint_strength
cloud_fraction
precipitation_kind
precipitation_intensity
rain_intensity
snow_intensity
fog_or_haze_strength   # только если authoritative support существует
temperature_band
biome_visual_key       # только stable biome ID
```

Это presentation state, не новая canonical climate state.

---

# 10. Day/night and sky

Reuse `RegionalSky`/existing sky pipeline.

Поведение:
```text
day → brighter ambience
night → darker ambience
Ympha relevant/visible → redder illumination
```

Не использовать browser local time.
Не создавать второй astronomical calculation.

---

# 11. Ympha

Красное освещение должно совпадать с Region implementation.
Не делать random red overlay.
Интенсивность только из existing sky state.

---

# 12. Clouds

Cloud ambience берётся из authoritative current cloud/environment state.

Визуально:
- subtle contrast/brightness reduction;
- optional soft cloud overlay if Region already uses it;
- intensity proportional to normalized cloud state.

No fake random clouds.

---

# 13. Rain

Rain появляется только при authoritative current rain.

Требования:
- current precipitation semantics;
- no accumulated precipitation misuse;
- no random rain;
- no world mutation;
- текст/кнопки остаются читаемыми.

Reuse Region rain visuals where practical.

---

# 14. Snow

Snow появляется только согласно existing authoritative environment classification.

Не вводить новый произвольный temperature threshold в PW2, если проект уже классифицирует precipitation/conditions.

---

# 15. Fog / haze

Реализовать только если Phase 0 подтверждает существующий authoritative condition/token.

Не синтезировать туман через `humidity > arbitrary threshold`.

---

# 16. Heat / cold ambience

Только presentation:
```text
hot → subtle warm shimmer / warmer ambience
cold → subtle cooler/crisper ambience
```

Использовать existing human-conditions/environment summary if available.

Не создавать gameplay penalties.
Не добавлять biome heat hacks.

Критично:
> PW2 визуализирует текущий solver output как есть. Не исправлять C5-дефицит land diurnal response UI-хаком.

Никакого:
```python
if biome == "desert":
    temp += 8
```

---

# 17. Biome ambience

Biome может давать только subtle cosmetic flavor, если stable biome ID уже доступен.

Не раскрывать Settlement/POI/Country.
Не переопределять weather/sky.

Priority:
```text
sky/light
weather
clouds
temperature
optional biome flavor
```

Biome theming не обязателен для PW2.

---

# 18. No hidden-world leakage

PW2 может показывать только физически воспринимаемое окружение.

Не раскрывать:
- hidden Settlement;
- unknown POI;
- Country;
- secret Region metadata;
- GM notes;
- неперцептивные hazards;
- objective event information.

---

# 19. Workspace visual architecture

PW1 layout сохраняется.

Рекомендуемые слои:
```text
base Workspace
↓
sky/light tint
↓
cloud/fog
↓
precipitation particles
↓
subtle thermal/biome layer
↓
content cards
```

Weather layers:
```css
pointer-events: none;
```

---

# 20. PW1 module structure remains

Не перерабатывать:
- Тиамана;
- Active Quests;
- Map;
- Быт / Обязательства;
- Party;
- Notes;
- Apotheosis;
- carried Inventory;
- XP anchor;
- Money anchor.

---

# 21. Accessibility / motion

Обязателен:
```text
prefers-reduced-motion: reduce
```

При reduced motion:
- particle movement отключается;
- shimmer/cloud movement отключается;
- static lighting/tint сохраняется;
- no flashing/strobing.

---

# 22. Performance

- no simulation on view;
- one bounded environment/sky read path;
- avoid repeated point sampling;
- no N+1;
- no per-frame server calls;
- no giant video/raster backgrounds;
- bounded particles;
- GPU-friendly transform/opacity;
- no WebSockets in PW2.

---

# 23. “Live” semantics

Live = соответствует authoritative Campaign/world state на момент render/refresh.

Не строить realtime push architecture, если Region page её уже не имеет.

---

# 24. Graceful failures

Если atmosphere/sky data недоступен:
- Workspace рендерится;
- neutral ambience;
- никакой technical Player error;
- не мутировать мир ради восстановления.

---

# 25. Security

Player не получает arbitrary coordinate weather query.

Нельзя вводить:
```text
/player/weather?lat=...&lon=...
```

Sampling coordinates приходят только с server-side active Character effective location.

---

# 26. Do not create Player weather API oracle

Если JS нужны данные:
- предпочтительно server-rendered safe ambience tokens;
- либо Character-scoped endpoint, игнорирующий произвольные координаты.

---

# 27. AuditLog

PW2 read-only.

Не писать AuditLog за:
- Workspace GET;
- sampling;
- rain render;
- sky state;
- refresh.

---

# 28. Database/schema

Ожидаемо **no migration**.

Не persist:
```text
Character.current_weather
Character.current_temperature
Character.is_raining
```

---

# 29. Focused tests — data flow

Покрыть минимум:
1. no location → neutral, sampler not called;
2. location → exact resolver coordinates passed;
3. no arbitrary Player coordinate input;
4. Character A cannot sample Character B;
5. foreign Campaign denied;
6. bounded/one sample per request;
7. no world-time/atmosphere mutation on GET;
8. Region/Character shared adapter compatible for same point/state;
9. current precip, not accumulated;
10. Player HTML excludes diagnostics;
11. raw coordinates absent;
12. GM atlas data absent;
13. unavailable environment safe fallback;
14. no schema migration;
15. no Earth CRS/distance helper.

---

# 30. Focused tests — visual tokens

Test representative states:
```text
bright day
dark night
Ympha red light
clear sky
heavy cloud
rain
snow
hot
cold
```

Fog only if supported.

Validate semantic classes/tokens, not pixels.

---

# 31. Browser/manual verification

Desktop 1280 and mobile 390×844.

Verify:
- unplaced → neutral;
- positioned → ambience from Character point;
- day brighter;
- night darker;
- Ympha red tint;
- rain visible/readable;
- snow visible;
- clouds visible but subtle;
- reduced motion works;
- no raw coords;
- no arbitrary weather endpoint;
- no GM atlas leakage;
- no console errors;
- no horizontal overflow;
- active Character switch updates ambience.

Delete only isolated test data afterward.

---

# 32. Active Character switching

Switch A → B at different coordinates must derive B ambience after redirect/render.

Не кешировать ambience глобально только по User/Campaign.

---

# 33. Query/performance acceptance

Record before/after query count and render time.

Не заменять point semantics nearest-Region approximation ради скорости.

---

# 34. Regression requirements

Known baseline after L1:
```text
443 tests
OK
skipped=9
```

Run:
1. focused PW2;
2. PW1 Workspace;
3. L1 location/resolver;
4. Region ambience/weather presentation;
5. C4.2 point sampling tests if boundary touched;
6. related combined regression;
7. full suite.

Final:
```text
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
git status
```

---

# 35. Documentation updates

Update:
- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- Architecture Guardrails
- Master Roadmap

Permanent rules:
```text
Character ambience derives from effective Character location.
Player cannot query arbitrary atmosphere points.
Workspace GET never advances simulation.
Character and Region ambience share authoritative sky/weather presentation semantics.
Derived ambience is not persisted on Character.
C5 land-surface limitations are not patched in UI.
Reduced-motion fallback is mandatory.
```

Mark `[x] PW2`.

---

# 36. Checkpoint protocol

Immediately create:
```text
docs/PW2_PROGRESS.md
```

Milestones:
```text
Phase 0 Region/atmosphere audit
↓ checkpoint
Shared presentation/data-flow design
↓ checkpoint
Workspace integration
↓ checkpoint
Focused tests
↓ checkpoint
Related climate/Workspace regressions
↓ checkpoint
Browser verification
↓ checkpoint
Full suite + docs + report
```

---

# 37. Final report

Create:
```text
PW2_LIVE_CHARACTER_AMBIENCE_REPORT.md
```

Include:
1. baseline;
2. Region ambience audit;
3. shared/reused design;
4. effective-location integration;
5. atmosphere point path;
6. RegionalSky path;
7. day/night;
8. Ympha;
9. clouds;
10. rain;
11. snow;
12. fog/haze decision;
13. heat/cold;
14. biome decision;
15. security/no oracle;
16. no world mutation;
17. accessibility;
18. performance/query counts;
19. Character switch behavior;
20. graceful fallback;
21. focused tests;
22. related regressions;
23. full suite;
24. browser desktop/mobile;
25. schema status;
26. docs;
27. known limitations including C5;
28. scope confirmation.

---

# 38. Explicit out-of-scope

DO NOT START:
```text
M4 Player Map
V1 Visibility & Discovery
M2 Geography
Travel
Party
Notes backend
Quests
XP mechanics
Soul HUD
Тиамана mechanics
Ledger
Inventory
Economy
Roll20 normalized sync
Apotheosis/Craft
C5/C6/C7
```

---

# 39. Acceptance criteria

PW2 complete only if:
- Character Workspace ambience uses `get_effective_character_location()`;
- exact Character point used;
- authoritative point sampler reused;
- RegionalSky reused;
- Region/Character visual semantics not forked;
- day/night visible;
- Ympha real red tint;
- clouds authoritative;
- rain current authoritative;
- snow authoritative;
- fog only if authoritative;
- heat/cold presentation does not alter climate mechanics;
- C5 not patched in UI;
- Player cannot query arbitrary coordinates;
- raw coordinates hidden;
- GM atlas/debug hidden;
- Workspace GET no mutation;
- no ambience persistence;
- safe fallback;
- active Character switch updates ambience;
- reduced motion supported;
- desktop/mobile clean;
- focused/related/full suite pass;
- checks pass;
- docs/report updated;
- next phase not started.

---

# 40. Stop condition

After PW2 final report and validation, STOP.

Do not begin Player Map, Travel, Party, M2/V1, Notes, XP/HUD, Economy or C5 automatically.
