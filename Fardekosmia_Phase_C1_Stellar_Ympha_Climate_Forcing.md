# Фардекосмия — Phase C1
## Stellar & Ympha Climate Forcing

### Назначение
Этот этап подключает каноническую астрономию Фардекосмии к уже существующей оптимизированной `AtmosphericGrid`, не переписывая её с нуля.

Главная цель:

> Погода и температура должны реагировать не на абстрактный `season +X °C`, а на положение системы на орбите, расстояние до центральной звезды, широту, локальное время, наклон оси и видимость Ympha.

Phase C1 не должен реализовывать полноценную гидрологию, динамический океан, катаклизмы или новую систему штормов. Это отдельные будущие этапы.

---

# 0. Сначала проанализировать текущий код

Перед изменениями:

1. Прочитать текущую реализацию:
   - `world/services/calendar.py`
   - `world/services/astronomy.py`
   - `world/services/time.py`
   - `world/services/atmosphere/*`
   - текущую реализацию exact / fast-forward
   - текущую систему `TimeAdvanceReport`
   - модели кампании/атмосферы
   - актуальные тесты и benchmark'и.

2. Найти актуальные точки:
   - расчёта `CalendarMoment`;
   - `RegionalSky`;
   - текущего `radiative forcing`;
   - surface exchange;
   - atmospheric fast-forward reinitialization/spin-up;
   - сезонных modifier'ов;
   - Light/Dark/Mixed season;
   - legacy weather fallback.

3. Не предполагать, что структура кода совпадает со старым handoff: после Phase B.5/B.6 проект уже был оптимизирован.

4. Снять baseline benchmark:
   - 1 atmospheric step;
   - 1 phase / 24 h;
   - 1 Vitok / 168 h;
   - 1 Season fast-forward;
   - 1 Year fast-forward.

---

# 1. Что является каноном для C1

## Центральный объект
Использовать:

- mass: `1681 M_sun`
- radius: `4.0 R_sun`
- surface temperature: `12621 K`
- luminosity: `282 L_sun`
- density: `37.1 g/cm^3`

Важно:

- массу не использовать для вывода светимости;
- светимость не выводить из массы;
- для климатической энергии использовать заданные `282 L_sun`.

Физическая природа центрального объекта необычна, но C1 не должен её переопределять.

---

## Ympha
Использовать:

- mass: `78.4 M_jupiter`
- radius: `1 R_jupiter`
- average temperature: `2561 °C ≈ 2834 K`
- infrared emissivity as reported by Universe Sandbox: `19.2%`

Но:

`Infrared Emissivity = 19.2%` пока НЕ трактовать жёстко как болометрическую emissivity для закона Стефана–Больцмана.

Сохранить параметр как каноническое входное значение, но не строить на нём необратимую климатическую формулу в C1.

---

## Орбита Ympha вокруг звезды

Канон:

- semi-major axis: `12.2 AU`
- pericenter: `10.2 AU`
- apocenter: `14.2 AU`
- eccentricity: вычислять из геометрии или использовать около `0.164`
- орбита эллиптическая;
- один полный орбитальный цикл = `364 календарных дня`;
- `Universe Sandbox Orbital Period = 1.04 year` НЕ является каноном;
- перицентр приходится на середину глобального Лета.

Период solver должен быть строго:

```text
52 Vitok
= 364 days
= 524160 world minutes
```

Не выводить период заново из массы и `a`.

Использовать Keplerian форму движения по эллипсу, но нормировать mean motion на канонические 364 дня.

---

## Фардекосмия вокруг Ympha

- orbital period: `7.05 d`
- semi-major axis: `0.0300 AU`
- pericenter: `0.0288 AU`
- apocenter: `0.0313 AU`
- eccentricity: `0.0414`

Календарный Vitok остаётся:

```text
1 Vitok = 168 h = 7 calendar days
```

Не менять эту игровую единицу.

---

## Вращение Фардекосмии

- physical rotation period: `7.52 d`
- axial tilt: `8.79°`
- tilt direction: `109°`
- spin-axis latitude: `-73.2°`
- spin-axis longitude: `292°`
- exact tidal lock отсутствует.

Существующая каноническая логика `RegionalSky`, Красных/Чёрных Витков, Рассветания/Угасания и Круга Лика должна сохраниться.

Если текущее `RegionalSky` использует игровой 168-часовой цикл для визуального/календарного неба, не переписывать его автоматически на 7.52 d. Physical rotation period подготовить как отдельный параметр для будущей физики Coriolis.

---

# 2. Новый OrbitalClimateState

Создать один центральный источник истины для положения системы на годовой орбите.

Примерная структура:

```python
@dataclass(frozen=True)
class OrbitalClimateState:
    world_minutes: int

    year_fraction: float

    mean_anomaly_rad: float
    eccentric_anomaly_rad: float
    true_anomaly_rad: float

    star_distance_au: float

    stellar_flux_w_m2: float
    stellar_flux_earth_ratio: float
    annual_mean_flux_w_m2: float
    flux_anomaly_ratio: float

    global_season: str
    season_progress: float

    solar_declination_rad: float
```

Название/расположение можно адаптировать к архитектуре проекта.

Не сохранять это как DB row на каждый timestep, если оно полностью детерминировано из `world_minutes`.

---

# 3. Каноническая годовая орбита

## 3.1 Mean motion

Использовать:

```python
P = 364 days
n = 2*pi / P
```

`world_minutes` должен определять orbital phase полностью детерминированно.

---

## 3.2 Epoch

Начало календарного года должно совпадать с началом глобального Лета.

Чтобы перицентр был в середине Лета:

- `true_anomaly = 0°` в перицентре;
- начало Лета определить на `true_anomaly = -45°`;
- конец Лета на `+45°`.

Из этого вычислить соответствующий `mean anomaly at epoch`.

Не приближать true anomaly линейно по времени.

---

## 3.3 Kepler equation

На каждом нужном времени:

```text
M = M_epoch + n*t

solve:
M = E - e*sin(E)

then:
ν = 2 atan2(
    sqrt(1+e) * sin(E/2),
    sqrt(1-e) * cos(E/2)
)
```

Расстояние:

```text
r = a * (1 - e*cos(E))
```

или эквивалентная корректная формула.

Newton iteration должен быть:
- быстрым;
- детерминированным;
- ограниченным по итерациям;
- протестированным около periapsis/apopsis.

Для `e ≈ 0.164` проблем со сходимостью быть не должно.

---

# 4. Неравные глобальные сезоны

Старое правило `13 Vitok × 4` больше не использовать как физическую границу сезона.

Глобальные сезоны определять по true anomaly:

```text
Summer:
-45° <= ν < +45°

Autumn:
+45° <= ν < +135°

Winter:
+135° <= ν < +225°

Spring:
+225° <= ν < +315°
```

Таким образом:

- Summer центрирован на pericenter;
- Winter центрирован на apocenter;
- Autumn/Spring находятся между ними.

При `e = (14.2 - 10.2)/(14.2 + 10.2) ≈ 0.163934`
и `P = 364 d` ожидаемые длительности примерно:

```text
Summer ≈ 66.36 d  ≈ 9.48 Vitok
Autumn ≈ 88.65 d  ≈ 12.66 Vitok
Winter ≈ 120.33 d ≈ 17.19 Vitok
Spring ≈ 88.65 d  ≈ 12.66 Vitok
```

Это reference values для тестов, не hardcoded durations.

Длительности должны получаться из orbital geometry.

---

# 5. Миграция календарной сезонности

Нельзя допустить, чтобы одновременно существовали:

- старый `season = floor(turn / 13)`
- новый orbital season.

После C1 источник истины должен быть один.

Обновить все места, использующие season:

- `CalendarMoment`;
- UI;
- weather modifiers;
- TimeAdvanceReport;
- legacy fallback;
- event conditions, если они завязаны на season;
- Light/Dark/Mixed season;
- любые helper'ы `season_progress`.

Старые настройки `13 turns per season`, если они нужны для backward compatibility, можно оставить deprecated, но они не должны управлять текущим каноническим календарём.

---

# 6. Light / Dark / Mixed season при переменной длине

Старые пороги:

```text
Light: >= 8 red turns из 13
Dark:  <= 5 red turns из 13
```

нельзя применять напрямую к сезонам длиной 9–17 Vitok.

Сохранить смысл порогов как долю:

```text
LIGHT_THRESHOLD = 8/13 ≈ 0.6153846
DARK_THRESHOLD  = 5/13 ≈ 0.3846154
```

Для каждого longitude/region:

1. найти все Vitok, пересекающие текущий orbital season;
2. учитывать частичные Vitok на границах сезона через overlap duration;
3. вычислить долю времени сезона, приходящуюся на Red Vitok;
4. классифицировать:
   - `>= 8/13` → Light
   - `<= 5/13` → Dark
   - между → Mixed.

Не считать просто фиксированное количество 13 Vitok.

Круг Лика `16 Vitok` не менять.

---

# 7. Stellar flux

Использовать физический inverse-square flux:

```text
S(r) = S_earth * (L_star / L_sun) / r_AU^2
```

где:

```text
L_star/L_sun = 282
```

`S_earth` держать как физическую константу проекта, не как magic number внутри solver.

Reference checks:

```text
at 10.2 AU:
≈ 2.7105 S_earth
≈ 3689 W/m²

at 12.2 AU:
≈ 1.8947 S_earth
≈ 2579 W/m²

at 14.2 AU:
≈ 1.3985 S_earth
≈ 1903 W/m²
```

Pericenter/apocenter flux ratio:

```text
≈ 1.9381
```

Средний по времени поток за эллиптический год должен вычисляться отдельно, а не приниматься равным `S(a)`.

Reference annual mean:

```text
≈ 1.9206 S_earth
≈ 2614 W/m²
```

с использованием текущих канонических параметров.

---

# 8. Не double-count static mean-temperature map

Это критично.

`mean_temperature_at(lat, lon)` уже является климатической картой среднего состояния мира.

Нельзя сделать:

```text
static mean map
+
полный абсолютный stellar heating
```

так как часть среднего звёздного нагрева уже неявно содержится в карте.

Для C1 использовать orbital forcing как АНОМАЛИЮ относительно годового среднего потока:

```text
flux_anomaly_ratio =
    stellar_flux / annual_mean_stellar_flux
```

или:

```text
delta_flux =
    local_flux - reference_local_flux
```

Поверхностный target должен получать только отклонение от среднего климата.

Не менять базовую среднюю карту.

---

# 9. Local stellar geometry

Атмосферная ячейка должна учитывать:

- latitude;
- longitude;
- текущий orbital state;
- axial tilt;
- local rotation/day-night phase.

Для solar declination использовать стандартную геометрическую форму вида:

```text
sin(delta) = sin(obliquity) * sin(solar_longitude - axial_phase)
```

но mapping канонического `Tilt Direction = 109°` к `axial_phase` изолировать в одном конфиге/helper.

Не размазывать значение `109°` по коду.

Если точное значение Universe Sandbox `Tilt Direction` нельзя однозначно интерпретировать в координатной системе проекта:

- сохранить `109°` как canonical source value;
- добавить explicit `axial_phase_deg`;
- initial default связать с 109°;
- пометить mapping как working implementation;
- сделать его легко меняемым без миграции истории.

Не выдумывать быструю precession.

---

# 10. Local solar zenith

Использовать:

```text
cos(z) =
    sin(latitude) * sin(declination)
    +
    cos(latitude) * cos(declination) * cos(hour_angle)
```

```text
direct_insolation =
    stellar_flux * max(0, cos(z))
```

Ночью direct stellar flux = 0.

---

# 11. Совместимость с RegionalSky

`RegionalSky` остаётся каноничным источником:

- local time;
- phase;
- star/Ympha visual state;
- Red/Black Turn;
- Dawning/Fading;
- Ympha visibility;
- Darkness.

После C1 визуальное небо и atmospheric insolation не должны противоречить друг другу.

Не делать 16 200 вызовов Python `RegionalSky()` на каждом atmospheric timestep.

Для `AtmosphericGrid` реализовать векторизованный equivalent calculation:

- precomputed latitude array;
- precomputed longitude array;
- global rotation phase;
- vectorized hour angles;
- vectorized zenith;
- vectorized insolation.

Добавить regression tests:
- выбранная grid-cell и `RegionalSky` для той же координаты должны согласовываться по day/night;
- полдень не может иметь нулевую stellar insolation;
- глубокая ночь не может иметь direct stellar flux.

---

# 12. Axial tilt effect

Использовать `8.79°`.

Ожидаемое поведение:

- north и south hemisphere получают противоположную axial seasonal correction;
- equator меняется слабее;
- полярные/высокоширотные области сильнее чувствуют declination;
- глобальная distance forcing остаётся одинаковой для обеих hemispheres.

Важно:

эксцентриситет и axial tilt — разные факторы.

Нельзя делать:

```python
if season == SUMMER:
    all_cells += X
```

---

# 13. Связь с AtmosphericGrid

Добавить отдельный forcing layer / helper.

Пример:

```python
RadiativeForcingGrid:
    stellar_direct_w_m2
    stellar_anomaly
    ympha_forcing
    total_radiative_anomaly
```

Не обязательно сохранять этот grid в snapshot, если он полностью выводится из времени и static coordinates.

---

# 14. Как воздействовать на температуру в C1

C1 НЕ должен притворяться полноценной radiative-convective model.

Сейчас есть static mean temperature и surface exchange.

Использовать controlled response:

```text
surface_target =
    static_mean_temperature
    + stellar_temperature_anomaly
    + ympha_temperature_anomaly
```

Но `stellar_temperature_anomaly` должен зависеть от физического flux anomaly.

Коэффициент преобразования flux anomaly → °C оставить:
- явно именованным;
- configurable;
- документированным как technical calibration, НЕ canon.

Например допустима форма:

```text
stellar_temperature_anomaly =
    stellar_response_c
    * normalized_local_flux_anomaly
```

или другая стабильная monotonic form.

Не использовать raw `+20°C Summer`.

Не калибровать так, чтобы одна 6h итерация мгновенно прыгала на seasonal target — thermal inertia должен обеспечиваться existing surface exchange.

Добавить clamps/safeguards от экстремальных config values.

---

# 15. Daily / rotational thermal inertia

Фардекосмия вращается очень медленно по земным меркам.

Но C1 не должен вводить новый сложный ground heat model.

Сохранить текущую persistence/surface exchange механику.

Проверить только, что:
- длительная освещённая сторона постепенно нагревается;
- длительная ночь постепенно охлаждается;
- температура не прыгает мгновенно вслед за zenith angle.

Полноценная разница ocean/land thermal inertia будет C2.

---

# 16. Ympha forcing

Ympha должна давать:
- вторичное;
- небольшое;
- ненулевое тепловое влияние.

В C1 не выводить его абсолютную светимость из `Infrared Emissivity = 19.2%`.

Сделать geometry-dependent proxy:

```text
ympha_distance_factor =
    (reference_distance / current_planet_ympha_distance)^2

ympha_visibility_factor =
    existing RegionalSky visibility / night exposure

ympha_forcing =
    configured_ympha_response
    * visibility_factor
    * distance_factor
```

Учитывать орбиту Фардекосмии:

```text
0.0288 – 0.0313 AU
e = 0.0414
P = 7.05 d physical orbit
```

Если текущая система видимости Ympha использует Круг Лика и уже признана каноничной — не ломать её ради новой orbital calculation.

Новая физика должна усиливать/ослаблять уже существующий канонический visibility state, а не заменять его.

`configured_ympha_response` — технический параметр, пока не канон.

---

# 17. Star и Ympha — строго разные источники

Запретить смешение:

```text
central star orbital heating
```

и:

```text
Ympha night heating
```

В коде и diagnostics должны быть отдельные значения.

Центральная звезда:
- главный энергетический источник;
- меняется прежде всего через `r_star`.

Ympha:
- вторичный локальный источник;
- зависит от видимости ночью и расстояния Фардекосмия–Ympha.

---

# 18. Затмения

Канон разрешает редкие закрытия центральной звезды Ympha, но точная геометрия пока не определена.

В C1:

создать hook:

```python
stellar_occlusion_factor(...)
```

Default:

```text
1.0
```

Не генерировать случайные затмения.

Не делать eclipse every Vitok.

Будущая система сможет вернуть:

```text
0.0 – 1.0
```

и умножить direct stellar flux.

---

# 19. Atmospheric pressure / wind response

C1 напрямую не переписывает wind model.

Но новая spatial heating anomaly должна естественно менять:
- temperature;
- затем pressure;
- затем pressure gradients;
- затем wind.

Не добавлять отдельный:

```text
summer_wind_bonus
```

или случайный сезонный ветер.

---

# 20. Fast-forward

Новая орбитальная физика обязана работать и с оптимизированным fast-forward.

Для длинного skip:

- macro skipped period не симулировать по 6h;
- target orbital state вычислить напрямую из target `world_minutes`;
- atmospheric reinitialization должен учитывать orbital forcing целевой даты;
- final spin-up должен использовать корректное движение орбиты на каждом 6h шаге;
- TimeAdvanceReport должен знать, какие global seasons были пересечены.

Не возвращать линейную стоимость по длине года.

---

# 21. TimeAdvanceReport

Exact report:

может дополнительно показывать:
- season transition;
- прохождение periapsis, если оно реально попало в exact interval;
- заметный рост/падение stellar forcing.

Fast-forward report:

может показывать фактические deterministic astronomical milestones:

```text
• Завершилось Лето
• Система прошла перицентр
• Началась Осень
```

Это не выдуманная погода, поэтому такие события допустимы даже внутри fast-forward interval.

Не создавать ложные точные weather events для skipped периода.

---

# 22. Diagnostics / GM debug

Добавить debug diagnostics, доступные GM/dev, без перегруза обычного UI:

```text
Orbital year progress
True anomaly
Star distance AU
Current stellar flux W/m²
Flux in Earth units
Current global season
Season progress
Solar declination
Local solar zenith for selected region
Local direct stellar flux
Ympha forcing factor
```

Это очень важно для настройки C1.

---

# 23. Performance

Нельзя потерять оптимизацию B.5/B.6.

Требования:

- все global orbital quantities считать один раз на timestep;
- latitude/longitude arrays precompute/cache;
- local zenith и insolation vectorize NumPy;
- не создавать Python object на каждую atmospheric cell;
- не делать ORM queries per cell;
- forcing grid не сохранять каждый timestep, если его можно восстановить.

После C1 повторить benchmark.

Цель:
- 1 Vitok желательно по-прежнему < 1 s на текущей development machine;
- hard regression target: не более ~1.5 s без документированной причины;
- Season/Year fast-forward не должны снова стать линейно дорогими.

---

# 24. Determinism

При одинаковых:

- world_minutes;
- canonical orbital config;
- static world maps;
- atmospheric state;
- seed;
- solver version;

результат должен быть воспроизводим.

OrbitalClimateState не должен использовать system clock.

---

# 25. Snapshot version / invalidation

C1 меняет forcing и сезонную модель.

Существующие atmospheric snapshots, созданные старым solver, нельзя молча считать физически совместимыми с новым.

Использовать существующую solver/config fingerprint систему:

- bump solver/forcing version;
- invalidation/rebranch old future checkpoints according to current project policy;
- не уничтожать историю без необходимости.

Fast-forward reinitialization должен использовать новую version.

---

# 26. Tests — orbital mechanics

Добавить tests:

### Period
```text
state(t) ≈ state(t + 364 days)
```

### Pericenter
в середине Summer:
```text
r ≈ 10.2 AU
ν ≈ 0°
stellar flux maximum
```

### Apocenter
в середине Winter:
```text
r ≈ 14.2 AU
ν ≈ 180°
stellar flux minimum
```

### Flux
Reference:
```text
peri ≈ 2.7105 S_earth
apo  ≈ 1.3985 S_earth
ratio ≈ 1.9381
```

### Nonlinear orbital motion
За одинаковый time interval около periapsis должно проходиться больше true anomaly, чем около apocenter.

Не использовать линейный true anomaly.

---

# 27. Tests — seasons

Проверить:

```text
Summer ≈ 66.36 d
Autumn ≈ 88.65 d
Winter ≈ 120.33 d
Spring ≈ 88.65 d
```

с разумным tolerance.

Сумма:

```text
364 d
```

Pericenter должен быть в temporal midpoint Summer.

Apocenter — в temporal midpoint Winter.

---

# 28. Tests — latitude / light

Минимум:

- equator noon > equator dawn;
- night direct flux = 0;
- northern and southern same latitude respond oppositely to axial declination;
- at zero axial tilt test config N/S symmetry is restored;
- longitude shifts local noon, но не меняет global star distance.

---

# 29. Tests — Ympha

Проверить:

- Ympha forcing zero/near-zero when not visible according to canonical sky;
- forcing >0 on Light Night with nonzero response;
- closer Fardekosmia–Ympha distance → stronger proxy;
- changing Ympha response does not change central-star flux.

---

# 30. Tests — integration

Проверить:

1. AtmosphericGrid receives nonzero astronomical forcing.
2. Summer/pericenter and Winter/apocenter produce different surface targets.
3. Same static cell at different orbital phases evolves differently.
4. Pressure/wind remain stable/finitе.
5. Exact one-Vitok simulation remains deterministic.
6. Fast-forward target orbital phase exactly matches direct calculation.
7. Existing TimeAdvanceReport still works.
8. Existing Red/Black Turn and Circle of Face tests remain valid.
9. Light/Dark/Mixed season works with variable season lengths.
10. No old fixed-13-turn season calculation remains as active source of truth.

---

# 31. Long-run stability test

Добавить отдельный slow/integration test или benchmark:

```text
simulate at least 1 canonical year
```

Можно использовать optimized test grid.

Проверить:

- no NaN/Inf;
- temperature bounded;
- pressure bounded;
- wind bounded;
- orbital state exactly wraps;
- no secular drift caused solely by orbital phase;
- seasonal pattern repeats approximately when starting atmospheric state is controlled.

---

# 32. Не делать в Phase C1

Не реализовывать сейчас:

- полноценную absolute humidity;
- Clausius–Clapeyron;
- latent heat;
- dynamic SST;
- ocean currents;
- multi-layer atmosphere;
- new storm/cyclone engine;
- tides;
- volcanoes/tsunami;
- random eclipses;
- biome evapotranspiration;
- full ground heat equation;
- Coriolis rewrite.

Это следующие фазы.

---

# 33. Acceptance criteria

Phase C1 считается готовым, если:

1. Год строго 364 дня.
2. `1.04 year` нигде не используется как канон.
3. Орбита эллиптическая и проходит peri/apo 10.2/14.2 AU.
4. True anomaly движется неравномерно.
5. Summer физически короче Winter.
6. Pericenter — середина Summer.
7. Stellar flux рассчитывается в W/m².
8. Static mean-temperature map остаётся baseline, а orbital heating применяется как anomaly.
9. Latitude и axial tilt влияют на local stellar forcing.
10. North/South seasonal tilt effects противоположны.
11. Existing RegionalSky, Circle of Face и Red/Black Turns не сломаны.
12. Ympha даёт отдельное небольшое geometry-dependent heating.
13. Star и Ympha forcing не смешаны.
14. Fast-forward остаётся быстрым.
15. TimeAdvanceReport корректно отражает astronomical milestones.
16. Все tests проходят.
17. Производительность измерена до/после.
18. Код готов к C2 без необходимости переписывать C1.

---

# 34. Итоговый отчёт Codex

После реализации ничего больше не добавлять.

Вернуть отчёт:

```text
PHASE C1 IMPLEMENTATION REPORT

1. Changed files
2. New/changed models
3. Migrations
4. OrbitalClimateState implementation
5. Epoch definition
6. Season boundaries and actual durations
7. Stellar flux formulas
8. Local zenith/latitude implementation
9. Axial tilt phase handling
10. Atmospheric coupling
11. Ympha coupling
12. Fast-forward integration
13. TimeAdvanceReport integration
14. Snapshot invalidation/versioning
15. Performance before/after
16. Tests added
17. Full test result
18. Known approximations
19. Remaining questions for C2
```

Не начинать C2.
