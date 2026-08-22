# ФАРДЕКОСМИЯ — PHASE C4.1
## Precipitation Regression Audit & Hydrological Sanity Fix

Phase C4 реализована, но обнаружена блокирующая регрессия:

> В реальной кампании/на карте ни в одном регионе и ни в один сезон визуально не наблюдаются осадки.

Не начинать Leaflet M1, C5, cyclone entities, catastrophes, WorldEvent или Travel Engine.

## 1. Не менять вслепую

Запрещено сразу снижать precipitation threshold, искусственно повышать humidity, добавлять random rain chance, возвращать Region precipitation modifier, добавлять biome rain bonuses или усиливать orographic cooling без диагностики.

Сначала instrumentation + root-cause analysis.

## 2. Проверить всю цепочку

Ocean SST
→ evaporation
→ q_v
→ advection
→ cooling / ascent
→ q_v > q_sat
→ condensation
→ q_c
→ autoconversion / fallout
→ precipitation_mass_flux
→ WeatherState sampling
→ Region UI

Найти первое звено, где значения становятся нулевыми или физически неверными.

## 3. Exact и fast-forward проверять отдельно

Провести:
- exact 1 Vitok;
- exact 1 season на reduced grid;
- exact 1 canonical year на reduced grid;
- season fast-forward;
- year fast-forward.

## 4. Собрать глобальную диагностику

Для контрольных прогонов вывести:

q_v:
- min/mean/p50/p90/p99/max

RH:
- min/mean/p50/p90/p99/max
- count RH >= 90%
- count RH >= 100%

q_sat:
- min/mean/max

q_c:
- min/mean/p90/p99/max
- count q_c > 0
- count q_c > precipitation threshold

condensation:
- total mass
- max per step
- active-cell count

cloud evaporation:
- total mass
- active-cell count

precipitation:
- total mass
- max mm/h
- mean over wet cells
- precipitating-cell count
- timesteps with any precipitation

evaporation:
- total mass
- max flux

vertical motion:
- w_orographic min/max
- w_convergence min/max
- w_total min/max
- meaningful-ascent cell count

temperature/pressure/wind:
- min/mean/max and useful percentiles.

## 5. Классифицировать failure

### A. q_v никогда не подходит к насыщению
Если RH низкая, q_c≈0 и condensation≈0, искать:
- слишком слабое evaporation;
- потерю q_v при advection;
- слишком высокую T/q_sat;
- неверное pressure interaction;
- слишком слабое vertical cooling;
- unit error в vertical-motion → temperature tendency.

### B. q_c появляется, precipitation = 0
Искать:
- autoconversion threshold выше всего реального q_c;
- unit mismatch;
- tau_precip integration bug;
- air-column conversion bug;
- q_c испаряется до fallout;
- неправильный operator order.

### C. Grid precipitation > 0, Region показывает 0
Искать:
- bilinear sampler;
- atmospheric_grid_v3 mapping;
- WeatherState semantics;
- mm/h conversion;
- UI template;
- wrong current snapshot;
- rain/snow condition derivation.

### D. Exact rains, FF does not
Искать boundary-grid q_c, condensation, precip accumulation, final spin-up и reinitialization.

### E. Rain exists globally, but not in existing Regions
Сравнить raw grid и arbitrary-coordinate sampler; вывести top wettest coordinates и проверить их без Region ORM.

## 6. Критический C4 audit — units vertical forcing

Проверить:
w_orographic = u * dh/dx + v * dh/dy
w_convergence ≈ -H_eff * divergence

Доказать единицы до temperature tendency:
- m/s;
- K/s или K per timestep.

Проверить отсутствие ошибок:
- ×1000;
- hours vs seconds;
- m vs km;
- degrees vs radians.

Новая C4 vertical pathway заменила/объединила старую C3 orography, поэтому это prime regression candidate.

## 7. Operator order

Документировать фактический порядок:
advection
→ ocean evaporation
→ pressure/wind
→ terrain/convergence vertical forcing
→ temperature change
→ saturation adjustment
→ q_c
→ precipitation fallout.

Проверить, что:
- condensation идёт после cooling;
- precipitation видит новый q_c;
- cloud evaporation не стирает весь q_c до fallout;
- pressure/wind update не перезаписывает T/q.

## 8. q_c threshold scale audit

Сравнить:
q_c p50/p90/p99/max

с:
precipitation_autoconversion_threshold.

Если threshold на порядки выше создаваемого q_c, это calibration/unit bug. Не снижать его до показа сравнения.

## 9. Сравнить C3.5 и C4

Если git history позволяет, запустить одинаковый deterministic scenario на последнем C3.5 commit и текущем C4:
- same seed;
- same grid;
- same initial fields;
- same world_minutes;
- same forcing.

Сравнить после N steps:
T, q_v, RH, q_c, condensation, precipitation.

Найти первое существенное расхождение.

## 10. Required Fardecosmia sanity scenario

Создать integration scenario:

hot/moist ocean
→ persistent wind toward land
→ mountain belt
→ lee interior.

Через достаточное число exact steps должно быть:
- evaporation > 0;
- q_v transport > 0;
- saturation somewhere;
- condensation > 0;
- q_c > 0;
- precipitation > 0;
- windward precipitation > lee.

Использовать реальный C4 pipeline.

## 11. Global hydrological regression test

На reduced real World Data grid за representative annual exact run:

total annual evaporation > 0
total annual condensation > 0
total annual precipitation > 0
number of wet cells > 0

Не требовать дождя в каждом Region или каждом сезоне. Тест нужен только против глобально сухой регрессии.

## 12. Wettest-cell diagnostic

Добавить dev/benchmark utility, выводящий top N wettest coordinates:
- lat/lon;
- integrated precipitation mm;
- peak mm/h;
- mean RH;
- mean q_v;
- mean q_c;
- nearby/current SST where meaningful.

Затем проверить arbitrary-coordinate sampler на этих координатах без Region ORM.

## 13. Current vs integrated precipitation

Явно разделить:
- Region current weather = precipitation_rate_mm_h NOW;
- TimeAdvanceReport = integrated precipitation over interval.

Не делать вывод "весь сезон без дождя" только из текущего сухого snapshot.

## 14. WeatherState persistence audit

Проверить семантику полей:
- current rate;
- amount per step;
- old precipitation index;
- rain fraction;
- snow fraction.

Документировать source of truth UI.

## 15. Region UI end-to-end audit

Для координаты, где raw grid прямо сейчас показывает rain:
1. raw AtmosphericGrid;
2. arbitrary-coordinate sampler;
3. Region sample;
4. WeatherState;
5. environment_summary;
6. rendered Region view.

Все стадии должны согласоваться:
physical precip > threshold
→ Region показывает rain/snow
→ human summary упоминает осадки.

## 16. No fake rain

Regression:
q_c = 0
→ precipitation = 0

Оставить обязательным.

## 17. Performance

C4 Year FF ≈ 3.011 s.
C4.1 не является performance phase. Не оптимизировать отдельно, если fix не создаёт патологическую регрессию.

## 18. Acceptance criteria

C4.1 готова, если:
1. Root cause идентифицирован.
2. Exact pipeline даёт precipitation в подходящих условиях.
3. Annual reduced-world run имеет evaporation > 0, condensation > 0, precipitation > 0.
4. q_c обязателен для precipitation.
5. Physical rain shadow сохраняется.
6. Region/WeatherState/UI показывают дождь/снег, когда sampled cell действительно мокрая.
7. Current и integrated precipitation не перепутаны.
8. Arbitrary lat/lon sampler правильно видит wet cells.
9. C1–C4 regressions проходят.
10. Legacy Region precipitation bias/random rain не возвращён.
11. Biome rain bonus/penalty не добавлен.
12. Determinism сохранён.
13. C5/Leaflet/Core не начинались.

## 19. PHASE C4.1 PRECIPITATION REGRESSION REPORT

Вернуть:
1. Root cause
2. Physics/sampling/persistence/UI classification
3. Exact hydrological stats before
4. Exact hydrological stats after
5. q_v/RH distributions
6. q_c distribution vs threshold
7. Condensation stats
8. Evaporation stats
9. Precipitation stats
10. Vertical-motion unit audit
11. Operator-order audit
12. C3.5 vs C4 comparison
13. Rain-shadow scenario
14. Wettest coordinates diagnostic
15. Raw grid vs coordinate sampler vs Region
16. WeatherState/UI fixes
17. Fast-forward behavior
18. Performance before/after
19. Tests added
20. Full test result
21. Known approximations
22. Confirmation no legacy/random/biome rain hack was added
23. Confirmation C5/Leaflet/Core were not started

Stop after report.
