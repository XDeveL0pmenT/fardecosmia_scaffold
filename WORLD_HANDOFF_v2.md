# Fardecosmia — World & Campaign Handoff for Coding Agents
## Version 2.0 — 2026-08-14

> Назначение: этот файл передаёт coding-агенту актуальный контекст мира **Фардекосмия**, границы канона, состояние симуляции и правила обращения с world/campaign data.
>
> Он дополняет `AGENTS.md`.
>
> `AGENTS.md` отвечает прежде всего за технические правила проекта: Django, auth, permissions, Roll20 integration, coding conventions и checks.
>
> Этот файл отвечает за:
> - канон мира;
> - астрономию;
> - календарь;
> - климат и атмосферную модель;
> - карту и географию;
> - Region semantics;
> - generated vs authored state;
> - future architecture constraints;
> - неизвестные данные, которые coding-agent не имеет права выдумывать.

---

# 1. Canon precedence

Если источники противоречат друг другу, приоритет:

1. Последняя явная инструкция Game Master.
2. Актуальные GM-confirmed canon/data files.
3. Этот `WORLD_HANDOFF.md`.
4. `AGENTS.md` для технических правил проекта.
5. Existing implementation assumptions.
6. Demo/test data.

Код никогда не имеет приоритет над новым подтверждённым каноном.

Если старый комментарий, migration, fixture, legacy model field или предыдущая версия этого файла противоречит последней инструкции GM, считать старую информацию superseded.

---

# 2. Главный принцип: не выдумывать канон

Coding-agent не является автором мира.

Различать:

## CONFIRMED CANON

Явно подтверждённые GM факты мира.

Можно:
- хранить;
- отображать;
- использовать в симуляции;
- ссылаться на них как на truth мира.

## TECHNICAL MODEL / IMPLEMENTATION DECISION

Алгоритм или структура приложения.

Примеры:
- grid resolution;
- numerical timestep;
- thresholds UI;
- fast-forward approximation;
- snapshot format;
- interpolation method.

Technical model НЕ становится каноном мира только потому, что существует в коде.

## UNKNOWN / TO BE PROVIDED

Факт не подтверждён GM.

Нельзя заменять его правдоподобной догадкой.

Если значение необходимо коду:
- configurable field;
- technical default;
- clearly marked non-canon assumption;
- no production lore invention.

---

# 3. Что такое Fardecosmia

**Фардекосмия** — persistent fantasy campaign world и Django-приложение для его ведения.

Сайт развивается как:

```text
world atlas
+
campaign operating system
+
world simulation assistant
+
character/campaign interface
+
long-term campaign memory
```

GM получает:
- world time;
- карту;
- регионы;
- климат;
- погоду;
- события;
- будущие travel/quest/economy/world controls.

Игроки в перспективе получают только ту часть мира, которая доступна их персонажам.

---

# 4. Основная архитектурная модель данных

Будущее направление проекта:

```text
GLOBAL CANON
      ↓
CAMPAIGN OVERRIDE
      ↓
CHARACTER KNOWLEDGE / CHARACTER STATE
```

Это направление архитектуры, а не требование немедленно переписать существующие models.

## Global Canon

Объективные шаблонные данные Фардекосмии:
- расы;
- биомы;
- магия;
- предметы;
- география;
- world lore;
- astronomical canon;
- shared atlas.

Редактируются:
- superuser;
- либо будущей отдельной ролью World/Canon Editor.

## Campaign Override

GM не должен менять глобальный канон для всех кампаний.

Campaign может:
- переопределить каноническую сущность;
- скрыть/изменить её в своей версии мира;
- создать campaign-only entity.

Предпочтительно хранить отличия/overlay, а не копировать весь canon object.

## Character Knowledge / State

Персонаж:
- знает не весь objective world truth;
- может знать rumor/false/outdated information;
- имеет собственное местоположение;
- квесты;
- inventory/economy;
- player-visible map state.

---

# 5. Пользователь, персонаж и роли

`accounts.User` — пользователь сайта.

`characters.Character` — персонаж кампании.

Один User может:
- иметь несколько characters;
- быть GM в одной кампании;
- player в другой.

Campaign role принадлежит `CampaignMembership`.

Не кодировать глобальную роль GM/player на User.

Будущие роли:
- Superuser;
- World / Canon Editor;
- Campaign GM;
- Player;
- возможно Assistant GM.

---

# 6. Roll20

Подтверждённая игровая система:

```text
D&D 5E Classic / Legacy D&D 5E (2014)
```

## Roll20 source of truth

Roll20 остаётся source of truth для combat-sheet mechanics:

- HP;
- AC;
- abilities;
- spell slots;
- hit dice;
- attacks;
- combat resources;
- inventory/equipment и другие sheet mechanics, когда parser их поддерживает.

## Fardecosmia source of truth

Сайт владеет:

- campaign/world state;
- location;
- travel;
- knowledge;
- quests;
- reputation;
- relationships;
- world events;
- climate/weather;
- GM notes;
- campaign history.

## Mirror

Roll20-specific raw state:

```text
Roll20CharacterBinding.raw_attributes
```

Normalized application-facing mirror:

```text
Roll20CharacterBinding.normalized_state
```

Protocol:

```text
Fardecosmia Roll20 Protocol v1
```

Поддерживать:
- snapshot;
- delta;
- idempotent `event_id`.

Никогда автоматически не bind персонажей по имени.

Future Django → Roll20 changes:
- queued commands;
- expected-old-value/conflict checks;
- no blind overwrite.

---

# 7. Objective truth ≠ player knowledge

Система должна различать:

## Objective world truth
То, что действительно существует/происходит.

## Character knowledge
То, что персонаж знает или считает истинным.

Знание может быть:
- true;
- false;
- incomplete;
- rumor;
- theory;
- outdated;
- uncertain.

## Player visibility
То, что сервер имеет право показать конкретному пользователю.

GM-only truth не должен:
- попадать в player HTML;
- сериализоваться player API;
- скрываться только CSS.

Future CharacterKnowledge/Fog of War архитектура должна учитывать это с самого backend permission layer.

---

# 8. Campaign world time

Основной источник времени:

```text
Campaign.world_minutes
```

Это integer game minutes от campaign epoch.

Продвижение времени:
- explicit;
- transactional;
- service operation;
- GET не должен менять мир.

---

# 9. Канонический календарь

## Великий Круг

```text
1 Великий Круг = 52 Витка = 364 световые фазы по 24 часа
```

В климатической/орбитальной модели:

```text
1 полный оборот Fardecosmia/Ympha system вокруг центральной Звезды
= ровно 364 calendar days
```

### Важно

Universe Sandbox значение около `1.04 year` — техническая неточность интерфейса/настройки sandbox и **НЕ канон**.

Не выводить orbital period из массы Звезды + semi-major axis через стандартный Kepler как новый source of truth.

Климатическая орбита использует Kepler-shaped geometry, нормализованную на:

```text
364 days exactly
```

---

# 10. Виток

```text
1 Виток = 168 часов
```

Это один условный day-scale мира.

Виток делится на 7 равных 24-часовых световых фаз:

1. Рассвет.
2. День.
3. Яркий день.
4. Закат.
5. Ночь.
6. Глубокая ночь.
7. Предрассвет.

Не называть каждую 24-часовую фазу отдельным мировым днём.

---

# 11. Круг Лика

```text
1 Круг Лика = 16 Витков = 112 световых фаз
```

Половина:

```text
8 Витков
```

Фазы:

## Рассветание — Витки 1–8

- Начало Рассветания
- Бледные ночи
- Красный край
- Половинная ночь
- Светлые ночи
- Красные ночи
- Высокий Лик
- Пик Рассветания

## Угасание — Витки 9–16

- Начало Угасания
- Тусклый Лик
- Длинные тени
- Половинная ночь
- Тёмные ночи
- Чёрные ночи
- Глухие ночи
- Пик Угасания

---

# 12. Красные и Чёрные Витки

Виток классифицируется по ночной видимости Ympha.

Confirmed visual/state names:

## Красный Виток

- Яркий рассвет
- Светлый день
- Белый жар
- Светлый закат
- Светлая ночь
- Красная ночь
- Красный предрассвет

## Чёрный Виток

- Холодный рассвет
- Светлый день
- Сухой день
- Тёмный закат
- Чёрная ночь
- Глухая ночь
- Тёмный предрассвет

RegionalSky и существующая Red/Black/Face логика — каноническая игровая система и не должна переписываться атмосферным solver.

---

# 13. Сезоны — актуальная каноническая орбитальная модель

Старое представление:

```text
каждый сезон = ровно 13 Витков
```

НЕ является текущим физическим source of truth для climate seasons.

После C1 сезоны определяются true-anomaly quadrants орбиты:

```text
Summer:
ν ∈ [-45°, +45°)

Autumn:
ν ∈ [+45°, +135°)

Winter:
ν ∈ [+135°, +225°)

Spring:
ν ∈ [+225°, +315°)
```

Год начинается при:

```text
ν = -45°
```

Перицентр:

```text
ν = 0°
≈ temporal middle of Summer
```

Апоцентр:

```text
ν = 180°
≈ temporal middle of Winter
```

Derived reference durations:

```text
Summer ≈ 66.363 days ≈ 9.480 Vitok
Autumn ≈ 88.654 days ≈ 12.665 Vitok
Winter ≈ 120.329 days ≈ 17.190 Vitok
Spring ≈ 88.654 days ≈ 12.665 Vitok
```

Эти значения вычисляются из орбиты и не должны быть hardcoded как отдельный календарный канон, если solver уже умеет их вывести.

---

# 14. Light / Dark / Mixed season classification

Локальный тип сезона зависит от доли Red-time внутри конкретного orbital season.

Текущие thresholds:

```text
Light:
red fraction >= 8/13 ≈ 0.6153846

Dark:
red fraction <= 5/13 ≈ 0.3846154

между ними:
Mixed
```

Partial Vitoks на границах сезона учитываются overlap-weighted.

Thresholds являются технической конфигурацией классификации, а не отдельной физической константой мира.

---

# 15. Central star / central luminous object

Confirmed current parameters:

```text
Mass:        1,681 M☉
Radius:      4 R☉
Temperature: 12,621 K
Luminosity:  282 L☉
Density:     37.1 g/cm³
```

Видимый источник:
- горячий бело-голубой;
- основной дневной свет;
- основной источник радиационного нагрева.

## Important physical caveat

Объект астрофизически exotic/non-standard.

Его:
- M;
- R;
- T;
- L

не обязаны удовлетворять обычной self-consistent stellar model.

Для климата использовать:

```text
explicit luminosity = 282 L☉
```

НЕ выводить luminosity из M/R/T.

НЕ выводить orbital period из M + semi-major axis.

---

# 16. Orbit around central star

Current confirmed geometry:

```text
semi-major axis = 12.2 AU
pericenter      = 10.2 AU
apocenter       = 14.2 AU
eccentricity    ≈ 0.163934
```

Broad accepted range:

```text
e ≈ 0.164–0.166
```

Pericenter расположен примерно в середине глобального Summer.

Climate time normalization:

```text
mean motion n = 2π / 364 days
```

---

# 17. Stellar flux references

Using explicit `282 L☉`:

```text
at 10.2 AU:
≈ 3689 W/m²
≈ 2.7105 S⊕

at 12.2 AU:
≈ 2579 W/m²
≈ 1.8947 S⊕

at 14.2 AU:
≈ 1903 W/m²
≈ 1.3985 S⊕
```

Pericenter/apocenter ratio:

```text
≈ 1.938
```

Annual ellipse mean:

```text
≈ 2614 W/m²
≈ 1.9206 S⊕
```

Static mean-temperature raster уже содержит baseline climatology.

Dynamic stellar forcing должен добавлять anomaly, а не второй раз применять полный mean climate.

---

# 18. Ympha

Ympha — massive host / massive brown-dwarf-like / almost-star object.

Current confirmed parameters:

```text
Mass:          78.4 M♃
Radius:        1 R♃
Density:       104 g/cm³
Temperature:   2561°C ≈ 2834 K
IR Emissivity: 19.2% (Universe Sandbox field)
```

Visual:
- red / red-orange.

Thermal effect:
- non-zero;
- secondary compared to central star.

### Important

Universe Sandbox `IR Emissivity 19.2%` не интерпретировать как прямой bolometric emission coefficient.

Current climate uses a small geometry/visibility-dependent Ympha thermal proxy.

---

# 19. Fardecosmia physical planet data

Fardecosmia — habitable super-Earth moon/planetary world orbiting Ympha.

Confirmed:

```text
Mass:           3.29 M⊕
Radius:         1.80 R⊕
Density:        ≈ 3.11 g/cm³
Surface gravity ≈ 9.98 m/s²
Circumference:  ≈ 72,500 km
Escape velocity ≈ 15.1 km/s
```

Canonical map circumference:

```text
72 500 km
```

Do not use Earth radius/circumference for geography/travel.

Derived world radius:

```text
R = circumference / (2π)
≈ 11,539 km
```

---

# 20. Orbit around Ympha

Confirmed:

```text
orbital period = 7.05 days
semi-major     = 0.0300 AU
pericenter     = 0.0288 AU
apocenter      = 0.0313 AU
eccentricity   = 0.0414
```

Calendar Vitok:

```text
7 days / 168 h
```

is rounded/game calendar structure.

Do not collapse physical `7.05d` orbit into the exact calendar Vitok when physical orbital code needs the former.

---

# 21. Rotation

Confirmed physical spin period:

```text
7.52 days
```

Confirmed axial tilt:

```text
8.79°
```

Tilt Direction:

```text
109°
```

The old `21.4°` tilt is superseded.

Current technical axial phase is tied to `109°`, but coordinate mapping between Universe Sandbox and map coordinates remains isolated/configurable.

Exact semantic label:

```text
prograde / retrograde
```

has NOT been canonized.

Current C4 therefore isolates:

```text
rotation_direction_sign
```

Do not turn current sign assumption into lore.

No fast precession is canonically present.

---

# 22. Local stellar geometry

Current physical implementation uses:

```text
sin(delta)
= sin(obliquity)
* sin(solar_longitude - axial_phase)
```

and:

```text
cos(z)
= sin(lat) sin(delta)
+ cos(lat) cos(delta) cos(hour_angle)
```

Local direct stellar forcing:

```text
direct_flux
= stellar_flux(distance)
* max(0, cos(z))
```

RegionalSky remains source of visual/day-night/Face-cycle semantics.

Atmospheric solver may use vectorized physical geometry but must not casually replace RegionalSky.

---

# 23. Eclipses

Rare Ympha occultations/eclipses of the star may physically be possible.

Exact eclipse geometry is not canonically defined enough for deterministic event simulation.

Current model:

```text
stellar_occlusion_factor = 1
```

unless explicitly configured.

Do not add random eclipse-per-Vitok logic.

---

# 24. Atmosphere — canon vs technical model

Confirmed broad canon:

- breathable atmosphere;
- N₂-dominated;
- O₂ roughly Earth-ish in gameplay terms;
- strong water-vapor variability;
- hotter than Earth overall but compatible with complex life.

Exact full atmospheric composition is NOT yet canonized.

Do not hardcode:

```text
O₂ = 20.9%
```

as world canon.

Do not claim hypoxia solely from local pressure unless oxygen fraction/composition is configured.

Technical thermodynamic constants may use Earth-like defaults if needed, but mark them technical and include them in solver fingerprint/config.

---

# 25. Lumen

Lumen is canonically associated with:

- light;
- heat;
- life;
- growth;
- memory;
- creation.

Excess Lumen can contribute to overheating and dangerous conditions.

Do not reduce Lumen to a simple numeric "magic radiation" unless GM explicitly defines such a model.

---

# 26. Noctis

Noctis is associated with:

- darkness;
- absence of light;
- depths;
- black nebula;
- memory distortion;
- dangerous creatures / threats.

Dark Night / absence of both star and Ympha increases Noctis danger.

Light Night:
- Ympha visible;
- less Noctis;
- somewhat warmer.

Dark Night:
- neither main star nor Ympha;
- maximum Noctis danger.

Noctis warnings in environment summary are qualitative world-aware interpretation unless a future explicit mechanical system is added.

---

# 27. Heat Corruption / Fiery Plague

Heat Corruption / Fiery Plague is associated with overheated/excessive Lumen.

Conditions favor it especially in:

- high heat;
- high humidity;
- hot lowlands;
- steam;
- Light Summer;
- Lumen-rich geology.

Cold suppresses it.

Current environment summary may say:

```text
conditions favorable
conditions highly favorable
```

Do NOT invent exact infection probability from climate unless GM defines rules.

---

# 28. Global geography — confirmed high-level traits

Confirmed broad world geography:

- very large hot central ocean;
- large continents;
- high plateaus;
- hot lowlands;
- polar ice;
- island arcs;
- active tectonics;
- spreading/hydrothermal/trench activity in central ocean;
- polar ice combines high plateaus/ice sheets + albedo effects.

Broad climatic geography:

- western lands tend to be wetter/greener;
- eastern areas include hot/dry red plateaus;
- left/western major landmass is huge and is NOT a small island;
- working label `Green Plateau` exists for one major left-continent area;
- Red Plateaus should be dry because of geography/rain shadow, not because code hardcodes a biome precipitation penalty.

Do not invent continent/state names beyond explicit GM data.

---

# 29. Authoritative World Data rasters

Current authoritative planet-level raster inputs:

## Average temperature map

- full equirectangular world;
- source palette scale approximately:
  `-97.2°C … +74.6°C`;
- numeric digitisation currently exists on a `360×180` grid.

This is baseline climatology.

It is NOT "temperature now".

## Elevation map

- full equirectangular source;
- palette values approximately:
  `-29 m … 6365 m`;
- numeric digitisation exists;
- source-hidden/legend-obscured or invalid cells can remain `UNKNOWN`.

Do not invent elevation for UNKNOWN cells.

## Land mask

- authoritative editor mask;
- same projection;
- determines land/ocean classification and biome painting permission.

## Biome atlas

Shared objective-world biome layer.

Campaign can have overrides where currently supported.

---

# 30. Map projection and geography coordinates

Current world map:

```text
equirectangular / plate carrée
longitude: -180° … +180°
latitude:   +90° … -90°
```

Normalized existing Region contour storage:

```text
x = 0..1
y = 0..1
```

Conversion:

```text
lon = x * 360 - 180
lat = 90 - y * 180
```

Storage is resolution-independent.

Longitude seam at:

```text
±180°
```

must be treated as continuous planetary wrap.

Latitude does NOT wrap.

---

# 31. Region creation semantics

In UI, Region is created by manually drawing a **контур региона**:

```text
GM places vertices
→ vertices connect
→ closed contour
```

Technical storage remains polygon/ring geometry.

Server computes authoritative contour center.

Browser preview is advisory only.

On POST server recalculates:
- center;
- World Data values;
- allowed auto-derived fields.

---

# 32. Region auto-derived climate metadata

Current normal Region creation can derive:

- biome;
- base / climatological mean temperature;
- climatological humidity;
- elevation;
- surface type.

These values come from World Data / shared helpers.

Explicit manual climate override mode exists.

Important:

```text
Region climate metadata
≠ current physical atmosphere
```

---

# 33. Legacy Region climate fields

Fields such as:

- `seasonal_amplitude`;
- `weather_volatility`;
- `precipitation_bias`;

belong to legacy/fallback weather architecture.

After C3.5 they are isolated from `AtmosphericGrid`.

Do NOT reintroduce them into current AtmosphericGrid physics.

Especially forbidden:

```text
Region precipitation_bias
→ physical C3/C4 precipitation
```

and:

```text
Region seasonal_amplitude
→ second C1 seasonal heating
```

---

# 34. Current atmospheric model overview

Current physical atmosphere is a 2D prognostic global grid.

It is not legacy `weather-v2`.

Current implemented phases:

## C1 — Stellar & Ympha Climate Forcing
- orbital state;
- stellar distance/flux;
- unequal seasons;
- local zenith;
- axial forcing;
- separate Ympha thermal proxy.

## C2 — Dynamic Ocean & Water Vapor
- dynamic SST;
- ocean thermal inertia;
- sensible heat exchange;
- evaporation;
- prognostic specific humidity `q_v`.

## C2.5 — Ocean Fast-Forward Accuracy
- reduced boundary atmosphere;
- accurate slow ocean state during long skips.

## C3 — Condensation, Clouds & Physical Precipitation
- prognostic cloud condensate `q_c`;
- saturation adjustment;
- cloud evaporation;
- latent heat;
- physical rain/snow;
- precipitation removes atmospheric water;
- cloud cover from condensate;
- rain shadow;
- environment summary.

## C3.5 — Performance & Region Climate Autoconfiguration
- fast-forward optimization;
- unified climatological Region auto-fill;
- legacy Region modifiers isolated.

## C4 — Atmospheric Circulation & Terrain Dynamics
- physical Coriolis from 7.52-day spin;
- planetary spherical grid metrics;
- circulation pressure;
- prognostic wind;
- pressure-gradient acceleration;
- drag;
- convergence/divergence;
- vorticity;
- terrain/orographic coupling;
- coordinate sampling.

## C4.1 / C4.2
- precipitation regression fixed;
- current precipitation persistence verified;
- unified bilinear point sampling;
- terrain-consistent surface-pressure derivation.

## R1 — Region Weather Semantics & Lifecycle
- Region area weather;
- Region point weather separation;
- geometry/weather revision;
- WeatherState provenance;
- no fake initial legacy weather when physical grid is active;
- stale-state handling.

## M1 — Leaflet Planetary Atlas
- custom equirectangular planetary CRS;
- tiled raster atlas;
- normalized Region contour compatibility;
- arbitrary-point inspection;
- canonical 72 500 km distance geometry.

## P1/P2 — Canon, Campaign Overrides & Roles Foundation
- `WorldEntry` with explicit GLOBAL/CAMPAIGN scope;
- sparse whitelist-validated `CampaignEntityOverride`;
- immutable effective resolver;
- centralized global/campaign access policy;
- `world.manage_global_canon` permission;
- CampaignMembership remains campaign authority.

---

# 35. Atmospheric solver state

Current snapshot family:

```text
magic:  FATM4
format: 4
solver: 7
```

Current modern regional source:

```text
atmospheric_grid_v3
```

Do not silently load incompatible snapshots.

Solver/config/static-map changes must be fingerprint/version aware.

R1 did not change climate physics/solver version.

---

# 36. Atmospheric timestep

Current exact atmospheric step:

```text
360 game minutes = 6 hours
```

This is a technical numerical timestep, not a world-law that weather only changes every six hours.

Campaign time can sit between atmospheric boundaries.

UI may therefore show:
- exact current sky/time;
- latest atmospheric state from the last completed boundary.

R1 exposes age/staleness semantics.

---

# 37. Dynamic ocean

Ocean SST is prognostic.

Do not restore old behavior:

```text
ocean RH = 100%
constant ocean temperature
```

Current ocean uses physical/technical energy exchange including:
- stellar anomaly forcing;
- sensible heat;
- evaporation latent cooling;
- horizontal mixing;
- deep relaxation.

Static mean-temperature raster is baseline, not a permanently fixed SST.

---

# 38. Water vapor

Atmospheric moisture:

```text
q_v
```

is prognostic specific humidity.

Relative humidity is diagnostic from:

```text
q_v
T
p
```

using Clausius–Clapeyron / saturation helpers.

Do not directly advect RH as the main moisture state.

---

# 39. Clouds

Cloud condensate:

```text
q_c
```

is prognostic.

Cloud cover derives from condensate mass / cloud water path, not simply RH.

Clouds can:
- form via condensation;
- evaporate;
- precipitate.

---

# 40. Precipitation

Precipitation is physical.

Chain:

```text
evaporation
→ q_v
→ transport
→ cooling/ascent
→ saturation
→ condensation
→ q_c
→ fallout
→ precipitation
```

Precipitation:
- removes water from atmosphere;
- has current rate in `mm/h`;
- has amount per timestep in `mm water equivalent`;
- supports rain/snow phase fractions.

Invariant:

```text
q_c = 0
→ precipitation = 0
```

Do not add random rain to modern AtmosphericGrid.

---

# 41. Orography

Modern rain shadow must emerge through:

```text
wind
+
terrain gradient
→ orographic ascent/descent
→ cooling/warming
→ saturation/evaporation
→ q_c
→ precipitation
```

Do NOT add:

```text
if biome == RED_PLATEAU:
    precipitation -= X
```

Red Plateaus are a geography/rain-shadow outcome.

---

# 42. Atmospheric circulation

Current circulation uses:

- spherical grid metrics;
- physical planet radius;
- prognostic circulation pressure;
- local surface pressure derived from circulation pressure + local elevation + T/q;
- prognostic u/v wind;
- physical Coriolis;
- drag;
- convergence/divergence;
- vorticity;
- terrain vertical-motion proxy.

Do not use raw elevation-biased surface-pressure gradients as horizontal pressure-gradient force.

---

# 43. Point surface pressure

For arbitrary coordinate:

1. interpolate circulation pressure;
2. interpolate temperature;
3. interpolate humidity;
4. obtain local continuous elevation;
5. derive local surface pressure for that elevation.

Do NOT bilinearly interpolate already elevation-dependent surface pressures across mountain/lowland cells.

This was fixed after C4.2.

---

# 44. Point sampling

Current future-facing concept:

```python
sample_environment_at(
    latitude,
    longitude,
    ...
)
```

It can sample environment without requiring a Region ORM row.

Continuous fields:
- T;
- q_v;
- circulation pressure;
- wind u/v;
- cloud;
- precipitation;
- derived surface pressure.

Discrete fields:
- biome;
- surface type.

Elevation is continuous/bilinear where source data is valid.

Sampling:
- must not advance time;
- must not mutate DB;
- should be usable by future Leaflet/Travel/Character systems.

---

# 45. Region weather after R1

Critical semantic distinction:

## Region Area Weather

Answers:

```text
Что происходит по всей территории внутри контура?
```

Stored/derived via `RegionAreaWeatherState`.

Metrics include:
- mean/range temperature;
- RH;
- pressure;
- cloud coverage;
- precipitation coverage;
- rain/snow coverage;
- wind u/v aggregation;
- fog/heat/cold/strong-wind fractions.

Area weighting uses:
- spherical cell area;
- contour coverage fraction.

Current boundary-cell coverage approximation:
- deterministic 4×4 sub-cell sampling.

Tiny contours can use explicit `POINT_FALLBACK`.

## Point Weather

Answers:

```text
Что происходит в конкретной точке?
```

Used for:
- Region anchor diagnostics;
- future Character location;
- future Travel route point;
- future Leaflet arbitrary-point inspection.

Never use Region area mean as a character's local weather.

---

# 46. Region weather lifecycle

Modern located Region with active AtmosphericGrid should not start with fake random `legacy_v2` weather.

If compatible physical state is available:
- sample it.

If unavailable:
- UI waits for nearest atmospheric update.

Legacy `weather-v2` remains fallback only when:
- AtmosphericGrid disabled/unavailable;
- Region lacks usable location;
- explicit legacy path is required.

---

# 47. Region geometry/weather revisions

Region has weather/geometry revision semantics.

When relevant geometry changes:
- contour;
- anchor coordinates;
- effective elevation;

revision increments.

Old historical WeatherState:
- remains in DB;
- does not become current state for new geometry.

WeatherState stores provenance including:
- Region revision;
- sampled coordinates/elevation;
- solver version;
- atmosphere fingerprint where implemented.

Do not delete history merely because Region moved.

---

# 48. Current Region area vs point rule

Canonical architecture principle:

```text
КОНТУР
→ состояние территории

ТОЧКА
→ состояние конкретного места / персонажа
```

This principle must survive future map/character/travel changes.

---

# 48A. Global canon and campaign-effective truth after P1/P2

Generic encyclopedic/lore foundation:

```text
WorldEntry GLOBAL
      ↓
CampaignEntityOverride sparse patch / suppression
      ↓
immutable effective projection for Campaign
```

`WorldEntry CAMPAIGN` is a campaign-only record and does not appear in other
campaigns. A campaign-only record may not collide with an existing GLOBAL
`(kind, slug)`; use an override instead.

Generic overrides are allowed only for models registered in the override-policy
registry and only for explicitly allowed fields. Identity, scope, campaign,
provenance and revision are not generic patch fields.

Future Country, Settlement, Race, Item, NPC, Road and Quest remain structured
domain models. They must not be forced into `WorldEntry` JSON.

Player visibility is still a later CharacterKnowledge layer and must not be
inferred from objective effective truth.

---

# 48B. Current access-policy boundary

Global canon writes:

```text
superuser
OR world.manage_global_canon
```

Campaign writes and campaign overrides:

```text
GM membership in that Campaign
OR superuser
```

A Campaign GM is not automatically a Canon Editor. A Canon Editor without
campaign membership cannot edit campaign state or advance its time.

The global objective atlas can currently be viewed by superuser, Canon Editor,
or a user who is GM in at least one campaign. Players are denied until a
player-safe knowledge/visibility layer exists.

---

# 49. WeatherState history

WeatherState is historical generated data.

Exact advancement:
- can create states at real atmospheric boundaries.

Fast-forward:
- does NOT fabricate detailed regional weather for skipped interval;
- final exact spin-up produces real detailed states.

TimeAdvanceReport can report integrated precipitation over skipped/macro interval without pretending it was a sequence of exact regional events.

Do not reconstruct fake historical storms from macro totals.

---

# 50. Human-readable environment summary

Scientific state and prose interpretation are separate layers.

Pipeline:

```text
physical state
→ deterministic interpreter
→ human-readable conditions
```

No LLM/API is required on normal Region GET.

Current summary may include:
- temperature;
- wet-bulb;
- apparent heat;
- wind chill;
- humidity;
- wind;
- visibility;
- pressure;
- precipitation;
- Noctis;
- Ympha;
- qualitative Heat Corruption conditions.

Human label must never become an input to solver.

---

# 51. Wet-bulb / heat interpretation

High RH alone does NOT mean:
- hypoxia;
- impossible breathing.

"Difficult to breathe" style wording should only be used for genuinely severe heat/humidity load and framed as heat/humidity stress, not assumed oxygen deficiency.

Dry lethal heat is handled separately.

Cold uses wind chill only where its formula is applicable.

These thresholds are technical UI/config, not immutable world canon.

---

# 52. Current weather vs climatology

Never confuse:

```text
World Data mean temperature
```

with:

```text
current atmospheric temperature
```

Likewise:

```text
climatological humidity
```

is not current RH.

Region creation preview uses climatological/static data.

Current weather comes from AtmosphericGrid / WeatherState.

---

# 53. Static climate map double-count rule

Mean-temperature raster is baseline climate.

Dynamic forcing adds anomaly.

Do not apply:
- baseline raster;
- plus another full latitude/season climatology;
- plus legacy seasonal amplitude;

unless intentionally and explicitly justified.

---

# 54. Current known temperature behavior

Current atmosphere can produce warm low-latitude desert/forest climates with modest daily air-temperature amplitudes.

This is not automatically a bug.

However, detailed land-surface thermal inertia/albedo/vegetation feedback is planned for future C5.

Do not "fix" desert air temperature by adding a biome temperature bonus.

Future C5 should use physical surface properties.

---

# 55. Biomes

Canonical biome IDs/colors:

1. `meadow` — Луга — `#95A843`
2. `forest` — Лес — `#446D3C`
3. `jungle` — Джунгли — `#115D39`
4. `sahara` — Сахара — `#E8C370`
5. `swamp` — Болото — `#859A7B`
6. `desert` — Пустыня — `#D0AA75`
7. `tundra` — Тундра — `#92B5C4`
8. `mountains` — Горы — `#82817C`
9. `boiling_crystal_lagoons` — Кипящие хрустальные лагуны — `#25BFBC`
10. `geyser_wasteland` — Гейзерная пустошь — `#E3A06A`
11. `lumenvein_thickets` — Светожильные чащобы — `#0E6958`
12. `mycelial_groves` — Мицелиевые Рощи — `#786A8D`
13. `azure_pillars` — Лазурные Столпы — `#26BCBA`
14. `misty_marshes` — Туманные Топи — `#7598A4`
15. `red_plateaus` — Красные Плато — `#BE5D39`
16. `hellscape` — Адская местность — `#000000`

Legacy coast color:

```text
#47A4B8
```

is non-canonical.

---

# 56. Important biome semantics

## Red Plateaus

Dry elevated rain-shadow terrain behind mountains.

Dryness must emerge from:
- terrain;
- circulation;
- moisture transport.

Not a biome penalty.

## Azure Pillars

Warm shallow-sea biome/formation.

## Misty Marshes

Hot wetland / mist-heavy environment.

Biomes may later provide physical surface properties, but they are not allowed to replace climate physics with arbitrary bonuses.

---

# 57. Canon atlas vs campaign map

Long-term architecture:

## Canon/shared atlas
Objective shared world.

## Campaign map
Campaign-specific:
- Region contours;
- campaign overrides;
- future events/characters/Fog of War.

GM editing of global canon must eventually be separated from campaign editing by permissions.

Current implementation may still have partial shared/campaign behavior; do not infer that current DB layout is final design.

---

# 58. Map — current storage

Region contour:

```text
Region.map_polygon
```

stores normalized 0–1 points.

This is current compatible storage and R1 depends on it.

Do not destructively migrate it casually.

Server remains authoritative for:
- geometry validation;
- center;
- Region climate auto-fill.

---

# 59. Map — current M1 foundation

Implemented map foundation:

```text
M1 — Leaflet Planetary Atlas Migration
```

Target:
- Leaflet;
- no MapLibre;
- custom Fardecosmia planetary/equirectangular CRS;
- tiled raster layers;
- deep zoom;
- vector Region contours;
- arbitrary-point inspection.

Do not use Earth Web Mercator as planetary truth.

Do not use Google/OSM tiles as world base map.

---

# 60. Leaflet planetary requirements

Canonical geometry:

```text
circumference = 72 500 km
projection = equirectangular
longitude wraps ±180°
latitude does not wrap
```

Distance must use Fardecosmia radius, not `L.CRS.Earth`.

Deep visual zoom does NOT imply equal climate-grid resolution.

A city/player marker may be placed precisely even if atmospheric cell is hundreds of kilometers wide.

---

# 61. Future analytical map layers

Planned after foundational Leaflet work:

- annual precipitation map;
- seasonal precipitation maps;
- current precipitation;
- hazard map;
- habitability map;
- settlement suitability;
- later WorldEvent/catastrophe overlays.

These layers are derived visualization/analysis.

They must not become hidden new sources of climate physics.

---

# 62. Future precipitation map

Precipitation climatology should derive from AtmosphericGrid/history/statistical runs.

Useful metrics:

- annual total;
- seasonal totals;
- rain/snow partition;
- wet-time frequency;
- peak/typical intensity.

Region creation may later show these as area analytics.

Do not restore `precipitation_bias` as the source.

---

# 63. Future hazard map

Potential layers:

## Climate
- dangerous heat;
- humid heat;
- cold;
- strong wind;
- storms;
- heavy snow;
- flood risk.

## Geological
- volcanism;
- earthquakes;
- tsunami;
- unstable terrain.

## Magical
- Noctis danger;
- Heat Corruption favorability;
- Lumen anomalies.

## Gameplay
- wars;
- hostile areas;
- monsters;
- blocked routes;
- active WorldEvent.

Combined hazard score may be a technical/game index, not fundamental canon.

---

# 64. Future habitability

Habitability is an analytical layer, not a declaration that a biome is "good" or "bad".

Potential inputs:

- temperature;
- wet-bulb;
- cold/wind chill;
- pressure;
- water availability;
- precipitation;
- terrain;
- hazards;
- Noctis;
- Heat Corruption;
- future race-specific adaptations.

Future UI may support:
- general humanoid;
- selected race;
- selected character.

Do not implement race-specific habitability before race mechanics are defined.

---

# 65. Future settlement suitability

Separate from raw habitability.

May include:
- habitability;
- water;
- terrain;
- coast/river access;
- agriculture;
- roads;
- resources;
- hazards.

Any `0..100` score is a technical/GM planning index, not a physical constant of the world.

---

# 66. Future Player map weather

When Character markers exist:

```text
Character lat/lon
→ sample_environment_at(...)
→ local player weather
```

Do NOT use Region average weather as the character's immediate weather.

Region-area weather is strategic overview.

Point weather is local experience.

---

# 67. Future Fog of War

Planned map visibility states:

```text
unknown
explored
currently visible
```

Immediate vision radius may default around 1 km but must be GM-configurable and character-specific.

Do not expose full objective map state to player APIs merely because Leaflet can render it.

---

# 68. Future Travel Engine

Travel will depend on:

- origin;
- destination;
- route;
- lat/lon;
- Fardecosmia distances;
- terrain;
- elevation;
- biome;
- roads;
- weather;
- hazards;
- transport;
- party speed;
- buffs/debuffs;
- provisions;
- world time.

Travel must use point/route sampling, not Region mean weather.

Travel checks should emerge from route conditions and configured game rules, not arbitrary random d100 only.

---

# 69. P5 WorldEvent foundation and future extensions

P5 is implemented. `WorldEvent` is the mutable campaign definition/schedule and
`WorldEventOccurrence` is the immutable objective Campaign-history fact.
Initial registered/versioned trigger types are `MANUAL` and `WORLD_TIME`.
WORLD_TIME uses deterministic one-shot crossing `(old, new]`; exact and
fast-forward call the same high-level due-event service. Occurrences snapshot
their human description, exact scheduled/occurred world minute, source/actor,
Region/location/target labels, definition revision and effect result.

Registered effect handlers are the only automatic mutation boundary. Effect,
occurrence and related P3 audits share one transaction and `operation_id`; a
failure rolls back the time advance rather than committing past an unapplied
safe event. `TimeAdvanceReport` stores compact occurrence references, not full
payloads. Objective event pages remain GM-only until CharacterKnowledge provides
explicit player publication.

WorldEvent is not AuditLog, ApprovalRequest, TimeAdvanceReport, an application
pub/sub bus or an event-sourcing store. Simulation-coupled effects are not wired:
they require a future split-at-event-boundary simulation design.

Future extensions may connect:

```text
simulation
→ world event
→ map
→ settlement
→ travel
→ quest/economy/character consequences
```

Do not add scattered permanent flags such as:
- `is_global_storm_active`;
- `is_war_everywhere`;
- etc.

if a generic event layer is the future architecture.

---

# 70. AuditLog / ApprovalRequest foundations

P3 AuditLog foundation is implemented. `AuditLog` is an append-only history of
meaningful authored/control actions. It is distinct from WorldEvent,
WeatherState, AtmosphericSnapshot and ordinary application logs.

Current audited boundaries include:
- global and campaign WorldEntry create/update/delete;
- campaign override create/update/remove/suppress/restore;
- Region create/update/delete;
- global and campaign biome-layer edits with compact digests/counts;
- one high-level row per explicit campaign time advance;
- explicit GM atmosphere/time-simulation configuration changes.

Rules for future audited domains:
- call `world.services.audit.record_audit()` from an explicit domain service;
- mutation and audit share one transaction;
- use a whitelisted serializer, never `request.POST` or credentials;
- one user operation must not expand into solver/generated-data audit spam;
- global history and each campaign history keep separate access boundaries;
- normal application/admin update, deletion and pruning of audit rows are forbidden.

Future AuditLog consumers:
- CharacterSheet changes;
- economy;
- inventory;
- quests;
- campaign edits;
- world edits.

P4 ApprovalRequest foundation is implemented as a campaign-scoped workflow for
registered, versioned intents. It provides PENDING / APPROVED / REJECTED /
CANCELLED / EXPIRED lifecycle states, requester/resolver and world-time
snapshots, optional target snapshots, dedupe/expiry support, GM and requester
views, and P3 lifecycle audits sharing one operation_id.

Approval invariants:
- request payloads are bounded, secret-safe data for a whitelisted handler, not
  arbitrary commands or model field setters;
- each handler validates at request time, presents human intent and
  consequences, and revalidates current state immediately before apply;
- APPROVED means the registered domain mutation succeeded;
- apply, resolution, structured result and audit records commit atomically;
- concurrent decisions lock the request and cannot apply it twice;
- terminal requests are immutable through normal application paths;
- normal UI is human-first and keeps UUID/raw payload details collapsed;
- ApprovalRequest is not WorldEvent and does not replace event scheduling.

The foundation intentionally registers no invented gameplay handlers. Future
registered domains may support:
- purchases;
- travel;
- party consent;
- rewards.

Do not build many incompatible one-off approval systems.

P4.5 account onboarding and Campaign lifecycle foundation is implemented.
Normal users no longer depend on Django Admin for registration, verified-email
onboarding, Campaign creation or invitation acceptance.

P4.5 invariants:
- verified email is a transactional-contact state, never a GM/player role;
- Campaign authority remains exclusively in `CampaignMembership`;
- a verified creator receives the first GM membership atomically with Campaign
  creation and its P3 audit row;
- verification codes are six-digit, expiring, attempt-limited and slow-hashed;
- invitation tokens are high-entropy, email-bound, single-use, expiring and
  persisted only as a slow hash plus lookup prefix;
- invitation acceptance creates PLAYER membership and is not ApprovalRequest;
- at least one GM must remain after any role change/removal;
- account/security activity is not world AuditLog activity;
- authentication, verification, reset and invitation secrets never enter audit
  payloads or summaries;
- transactional email goes through the centralized Django email boundary with
  environment-only provider configuration.

Existing accounts were not falsely marked verified. Legacy users retain access
to existing memberships; normal transactional onboarding actions require a
verified contact email. Superuser/staff compatibility does not grant ordinary
Campaign authority outside the established access services.

---

# 71. Generated vs authored data

## Authored / GM-approved

Examples:
- lore;
- canon;
- Region contour;
- countries;
- NPC definitions;
- event definitions;
- campaign overrides.

## Generated

Examples:
- weather;
- triggered event occurrence;
- dynamic travel progress;
- simulation diagnostics.

Generated historical result is a world-history fact, but it is not automatically a new immutable canon definition.

Example:

```text
climate model settings = authored/technical
rain at world minute X = generated historical event/state
```

---

# 72. Randomness policy

Simulation randomness must be:
- deterministic where possible;
- seeded;
- testable;
- recorded where important.

GET must not reroll world state.

A page refresh must not create a different storm.

---

# 73. Fast-forward philosophy

Long skips are allowed to use reduced/macro physical approximation.

But:

```text
fast-forward
≠ invent exact skipped weather history
```

Skipped interval:
- no fake WeatherState sequence;
- no fake exact player-facing storm timeline.

Final exact spin-up restores detailed current state.

Reports may contain aggregate/macro quantities.

---

# 74. Performance philosophy

Project scale is tabletop campaigns, not MMO.

Priority:

1. correctness;
2. maintainability;
3. auditability;
4. permissions;
5. developer velocity;
6. optimization.

Use vectorized NumPy for climate.

Avoid:
- ORM per grid cell;
- Python loop per grid cell;
- premature distributed architecture.

---

# 75. Current performance notes

Exact/FF timings change with phase and machine load.

Do not treat one benchmark as canon.

Current architecture has proven:
- sub-second to low-second Vitok advancement depending on feature set;
- multi-second Year fast-forward;
- stable deterministic multi-year reduced-grid runs.

Every physics phase should report before/after benchmark and accuracy.

---

# 76. Canonical season/light naming and astronomy are not frontend decorations

Do not rewrite:
- Red/Black Turns;
- Face Cycle;
- Light/Dark/Mixed seasons;
- local sky;
- Ympha visibility;
- orbital seasons

merely to simplify frontend.

Frontend must consume domain/service output.

---

# 77. Known technical approximations

Current known approximations include:

- 2D atmospheric column, not full 3D GCM;
- reduced-grid fast-forward;
- effective vertical-motion proxy instead of resolved vertical atmosphere;
- technical atmosphere composition constants;
- R1 Region contour boundary coverage via deterministic 4×4 sampling;
- current land-surface model is less developed than ocean SST;
- no full cyclone entity engine yet;
- no full catastrophe engine yet;
- no explicit ocean-current circulation system yet.

These are implementation limitations, not missing lore.

---

# 78. Planned C5 direction

C5 is NOT started.

Likely future scope:

```text
Land Surface / Biome Feedbacks
```

Potential:
- albedo;
- land thermal inertia;
- sensible heat response;
- nighttime cooling;
- roughness;
- evapotranspiration;
- vegetation/soil moisture effects.

Important:

```text
biome
→ physical surface properties
→ physics
→ temperature/moisture
```

NOT:

```text
if desert:
    temperature += arbitrary bonus
```

Current observation that dry desert daily air-temperature amplitude can be modest is a future C5 surface-physics question, not a reason to rewrite biome map automatically.

---

# 79. Cyclones / severe weather

C4 diagnostics can provide:
- lows;
- convergence;
- vorticity;
- wind;
- precipitation.

But full:
- cyclone entity;
- hurricane category;
- eyewall;
- storm-track DB;
- catastrophe record

is not implemented.

Do not infer Earth hurricane categories as world canon.

---

# 80. Tides

Tides are a separate future subsystem.

Do not silently fold tides into current atmospheric/ocean model.

---

# 81. Political/geographic canon still missing

Do not invent without GM input:

- country names;
- borders;
- capitals;
- rulers;
- wars;
- alliances;
- settlements;
- roads;
- canonical routes.

Map architecture must be able to support them later.

---

# 82. Races/cultures canon still incomplete in this handoff

Do not invent:
- full race list;
- biology;
- culture;
- languages;
- settlement distribution;
- racial environmental tolerances.

When provided, these should integrate with:
- encyclopedia;
- settlements;
- CharacterKnowledge;
- future habitability.

---

# 83. Magic lore not fully encoded here

Confirmed high-level:
- Lumen;
- Noctis;
- Heat Corruption / Fiery Plague.

Do not assume:
- Forgotten Realms;
- D&D cosmology;
- standard D&D gods;
- planes;
- afterlife;
- spell lore

as Fardecosmia canon.

D&D 5E is a mechanics system, not automatic world lore.

---

# 84. Canon pages / future encyclopedia

Planned site sections include:
- races;
- biomes;
- classes;
- spells;
- magic items;
- equipment;
- bestiary;
- traits;
- weapons;
- magic/Lumen/Noctis;
- solar system;
- chronology.

Canonical content should be editable by privileged canon editor/superuser.

Campaign GM should create campaign overrides, not mutate global canon.

---

# 85. Chronology

Future world chronology should support:
- eras;
- historical events;
- start/end;
- linked countries/races/places/people;
- detailed event pages.

Architecture should allow historical map state later.

Do not encode lore directly in migrations if avoidable.

---

# 86. Events and clocks

Future events can be:

## Timed
Triggered when world time crosses threshold.

## Conditional
Triggered from structured conditions.

Do not store arbitrary executable Python in DB.

Use whitelist-based declarative rules.

Clocks may belong to:
- campaign;
- faction;
- NPC;
- quest;
- threat;
- Region;
- secret process.

---

# 87. GM generators

Planned generators:
- NPC;
- names;
- rumors;
- weather;
- encounters;
- treasure;
- complications;
- settlement events;
- quest drafts.

Generators should create editable drafts/proposals.

They should not silently publish canon/campaign events.

---

# 88. Region vs settlement

Region is a manually drawn geographic simulation area.

Future settlements are different entities:
- village;
- city;
- capital;
- fortress;
- port;
- camp.

Do not overload Region model to represent all future cities.

Settlements should link to:
- Region;
- country;
- races/population;
- economy;
- events;
- map position;
- local map.

---

# 89. Region area-weather performance note

R1 area aggregation is efficient for current small Region counts.

At very high Region counts, mass area aggregation may need optimization through precomputed sparse masks/vectorized multi-region processing.

Do not prematurely redesign while Region count is small.

---

# 90. World history / audit trail

Generated and authored important state changes should eventually be traceable.

Useful fields:
- world time;
- event type;
- actor;
- target;
- Region/location;
- summary;
- source;
- visibility;
- structured payload.

Do not rely only on current DB state for understanding why world state exists.

---

# 91. Data provenance

For important authored canon data, future useful metadata:
- source;
- created_by;
- updated_by;
- canonical status;
- notes;
- revision.

For generated climate:
- solver/source;
- revision/fingerprint;
- sampled location/time.

Do not force provenance onto every MVP model if not needed, but preserve extension path.

---

# 92. Current next-development direction

At the time of this handoff update:

Completed:
- C1;
- C2;
- C2.5;
- C3;
- C3.5;
- C4;
- C4.1;
- C4.2;
- R1;
- M1;
- P1/P2.
- P3 AuditLog foundation.
- P4 ApprovalRequest foundation.
- P4.5 Account Onboarding, Email & Campaign Lifecycle.

Completed additionally:
- P5 WorldEvent foundation.

Any next phase requires a separate explicit GM instruction.
CharacterKnowledge, M2, Inventory/Purchases, Travel and C5 have not been started
by P5.

C5 is intentionally not started yet.

Coding-agent must not auto-start the next phase after completing a requested one.

---

# 93. M1 guardrails summary

M1 should:
- use Leaflet;
- preserve equirectangular world;
- use custom Fardecosmia distance;
- preserve normalized Region geometry compatibility;
- add deep zoom;
- tile static rasters;
- keep vector Region contours;
- preserve R1 area vs point weather;
- remain Django/server-rendered friendly.

M1 should NOT yet add:
- countries;
- cities;
- roads;
- Character markers;
- Fog of War;
- Travel;
- precipitation analytical map;
- hazard map;
- habitability;
- C5 physics.

---

# 94. Critical tests to preserve

Particularly important invariants:

## Permissions
Player cannot receive GM-only world truth.

## Time
One advance changes world time exactly once.

## GET safety
GET does not mutate simulation.

## Weather determinism
Same compatible initial state + seed/config reproduces result.

## Moisture
`q_c = 0 → precipitation = 0`.

## Sampling
Arbitrary point sampling does not require Region.

## Region semantics
Area weather and point weather remain distinct.

## Geometry
±180° seam remains correct.

## World size
Distance uses 72 500 km circumference.

## Roll20
No auto-bind by name.

---

# 95. Hard prohibitions

DO NOT:

- invent world lore;
- assume Forgotten Realms;
- assume Earth geography;
- assume Earth planet radius;
- assume Gregorian calendar;
- assume 365-day year;
- restore `1.04 year` as canonical orbital period;
- restore fixed 13-Vitok physical seasons;
- restore axial tilt 21.4°;
- hardcode O₂ 20.9% as final world canon;
- make biome directly dictate modern precipitation;
- make desert directly receive arbitrary heat bonus;
- use Region legacy volatility/precipitation bias in AtmosphericGrid;
- expose GM-only data through player frontend/API;
- bind Roll20 characters by name;
- let GET mutate world state;
- let random page refresh reroll weather;
- store arbitrary executable Python event rules;
- silently rewrite historical WeatherState after solver changes;
- fabricate exact skipped weather during fast-forward;
- use Earth Web Mercator as physical planet truth;
- use Earth radius for map/travel distance;
- make Region average weather equal player-local weather.
- let a Campaign GM mutate global canon without the canon permission;
- let a campaign override mutate its global base row;
- accept arbitrary generic override fields/models;
- expose objective effective canon to players before CharacterKnowledge.

---

# 96. Critical unknowns still requiring GM input

## Astronomy
- canonical prograde/retrograde wording;
- exact eclipse geometry/rules;
- any additional system bodies not explicitly confirmed.

## Atmosphere
- exact gas composition;
- exact oxygen fraction;
- detailed atmospheric mass/pressure canon if GM later sets it.

## Geography
- all final continent/ocean names;
- all countries;
- settlements;
- roads;
- political borders;
- detailed river network;
- future local maps.

## Oceanography
- canonical currents, if they become authored rather than simulated.

## Races/cultures
- full structured canon.

## Politics/history
- states;
- rulers;
- wars;
- eras;
- chronology content.

## Religion/metaphysics
- gods;
- planes;
- afterlife;
- detailed magic cosmology beyond confirmed Lumen/Noctis/Heat Corruption facts.

## Campaign
- future player characters;
- active quests;
- current NPC/faction states, unless stored in project DB/data.

Absence here means UNKNOWN, not nonexistent.

---

# 97. When new GM world data arrives

1. Classify:
   - canon lore;
   - structured domain state;
   - simulation parameter;
   - player knowledge;
   - secret;
   - immutable/generated history.
2. Choose correct storage layer.
3. Define visibility.
4. Preserve source/provenance if important.
5. Do not overwrite unrelated history.
6. Update this handoff if the information affects future coding decisions.
7. Add tests if it changes simulation/business logic.

---

# 98. Summary for coding-agent

The essential truths:

- Fardecosmia is a persistent campaign world, not a generic D&D wiki.
- D&D 5E Classic provides mechanics; it does not define world lore.
- Roll20 owns combat-sheet truth.
- Fardecosmia owns world/campaign truth.
- Player knowledge is not objective truth.
- Campaign time is `Campaign.world_minutes`.
- 1 Vitok = 168h.
- 1 Great Circle = 52 Vitoks = 364 days exactly.
- Physical orbital seasons are unequal after C1.
- Central-star orbit is normalized to exactly 364 days; `1.04 year` is not canon.
- Planet circumference is 72 500 km.
- Rotation period is 7.52 days.
- Axial tilt is 8.79°.
- Ympha orbital period is 7.05 days.
- World Data rasters provide baseline temperature, elevation and land/biome geography.
- Modern weather is AtmosphericGrid physics, not legacy random weather-v2.
- SST, q_v, q_c, circulation, physical precipitation and terrain effects are implemented.
- Region area weather and local point weather are different concepts.
- Global canon and campaign-only truth have explicit `WorldEntry` scopes.
- Campaign overrides are sparse, whitelist-validated and resolved without mutating base.
- Global canon authority and Campaign GM authority are separate permissions.
- Meaningful authored/control actions use append-only `AuditLog`; generated
  climate rows and solver steps do not create audit spam.
- Campaign approvals are registered human-readable intents; they are validated
  and revalidated, and approval/domain mutation/audit commit atomically.
- `APPROVED` means the domain action completed successfully; resolved approval
  requests are immutable and are never arbitrary command payloads.
- Normal account onboarding uses verified transactional email; Campaign
  creation/invitations still derive authority only from CampaignMembership.
- Verification, reset and invitation secrets are never plaintext persistence or
  world-audit data.
- P5 separates mutable WorldEvent definitions from immutable objective
  WorldEventOccurrence history; WORLD_TIME crosses `(old,new]` equally in exact
  and fast-forward, and registered effects/audits commit atomically.
- Objective event history is GM-only until a future CharacterKnowledge
  publication layer explicitly makes a fact player-known.
- Region legacy climate fields are not allowed to re-enter modern physics.
- Fast-forward does not invent detailed skipped weather history.
- Lumen, Noctis and Heat Corruption are world-specific concepts and must be treated according to canon.
- Missing lore remains UNKNOWN.
- The next major map direction is Leaflet on a custom Fardecosmia planetary/equirectangular CRS.
- Do not start unrequested future phases automatically.

When uncertain whether a fact is canon:

```text
treat it as UNKNOWN
+
make the implementation configurable
+
ask/await GM input
```

rather than inventing a world fact.
