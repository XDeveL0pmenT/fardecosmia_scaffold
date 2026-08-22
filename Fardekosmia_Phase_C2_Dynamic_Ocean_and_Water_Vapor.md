# ФАРДЕКОСМИЯ — PHASE C2
## Dynamic Hot Ocean, Thermal Inertia & Physical Water Vapor
### C2A — Ocean Heat
### C2B — Evaporation & Moisture Foundation

---

# 0. Цель этапа

Phase C1 уже подключил к климату:

- эллиптическую орбиту Ympha;
- канонический год 364 дня;
- истинную аномалию;
- расстояние до центральной Звезды;
- физический stellar flux;
- широту;
- локальный солнечный зенит;
- наклон оси 8.79°;
- отдельный небольшой forcing от Ympha;
- fast-forward и TimeAdvanceReport.

Phase C2 должен сделать огромный горячий океан Фардекосмии **реальным медленным энергетическим и влажностным резервуаром**, а не статическим источником `temperature/humidity`.

Главная цепочка после C2:

```text
OrbitalClimateState
        ↓
RadiativeForcingGrid
        ↓
absorbed stellar anomaly
        ↓
Sea Surface Temperature
        ↓
air–sea sensible heat exchange
        ↓
evaporation + latent cooling
        ↓
physical water vapor
        ↓
AtmosphericGrid
        ↓
pressure / wind / advection
```

Phase C2 НЕ должен ещё делать полноценные облака, конденсацию, физические осадки, океанические течения или приливы.

---

# 1. Сначала проанализировать текущий код

Перед изменениями ничего не переписывать вслепую.

Прочитать актуальную реализацию после C1:

- `world/services/orbital_climate.py`
- `world/services/atmosphere/forcing.py`
- atmospheric solver
- atmospheric persistence/snapshots
- advection
- pressure/wind
- surface exchange
- initialization/reinitialization
- exact advance
- fast-forward
- TimeAdvanceReport
- static World Data API:
  - `surface_at`
  - `mean_temperature_at`
  - `elevation_at`
  - `biome_at`
- актуальный `AtmosphericConfig.parameters`
- текущий snapshot format/version
- тесты C1
- benchmark B.5/B.6/C1.

Найти фактическое текущее значение/поведение старой океанической температуры.

Если в коде всё ещё присутствует технический `64°C`, не считать его новым каноном автоматически. Определить, является ли он:

- fallback;
- baseline;
- hardcoded target;
- legacy parameter.

В отчёте явно написать, что было найдено.

---

# 2. Канон мира, обязательный для C2

Фардекосмия:

- имеет огромный центральный океан;
- океан в целом горячий;
- океан является важнейшим источником влаги, облаков и мощных штормов;
- климат планеты жарче земного;
- высокие плато заметно комфортнее горячих низин;
- полярные и высокогорные зоны сохраняют лёд;
- существующая карта средней температуры является климатическим baseline мира;
- C1 уже создаёт сезонную аномалию от Звезды и отдельный небольшой forcing Ympha.

Нельзя превращать океан в:

```python
if ocean:
    humidity = 100
    temperature = constant
```

После C2 SST должна быть состоянием, имеющим память.

---

# 3. Основное архитектурное решение

Добавить динамический ocean surface state.

Рекомендуемое представление:

```python
OceanSurfaceState / SST field

sea_surface_temperature_c
```

на той же 180×90 equirectangular сетке, что и AtmosphericGrid.

Можно хранить SST как full-grid NumPy array `float32` с ocean mask.

Для land cells:

- `NaN`, sentinel или mask;
- они не должны участвовать в ocean equations.

Не создавать Django row на каждую ocean cell.

---

# 4. Ocean mask

Источник истины:

```text
surface/world-data layer
```

а не biome.

Создать/переиспользовать vectorized:

```python
ocean_mask
```

который:

- кешируется;
- входит в static-world fingerprint;
- одинаково используется SST, evaporation и diagnostics.

Не считать `Coast`, `Azure Pillars` или другой biome автоматически океаном без проверки surface layer.

---

# 5. Baseline SST

Карта `mean_temperature_at(lat, lon)` уже является климатическим baseline.

Для ocean cell:

```text
baseline_sst = mean_temperature_map value
```

если текущий World Data API действительно содержит корректную температуру океана.

Если для ocean pixels карта средней температуры не содержит валидных значений:

1. использовать существующий ocean-temperature fallback/config;
2. НЕ придумывать новое каноническое число;
3. оставить API:

```python
ocean_baseline_temperature_at(lat, lon)
```

чтобы позже можно было подключить отдельную SST climatology map без переписывания solver.

---

# 6. Не разрушать климатическую карту

Как и в C1, baseline уже содержит средний климат.

Поэтому океан должен динамически хранить:

```text
SST = baseline_SST + dynamic_anomaly
```

и не получать повторно полный абсолютный stellar heating поверх baseline.

Критическое правило:

> C2 интегрирует главным образом ОТКЛОНЕНИЕ энергетического баланса от climatological baseline.

Иначе SST будет систематически разогреваться каждый год.

---

# 7. C2A — Ocean energy model

Использовать bulk mixed-layer модель океанической поверхности.

На ocean cell:

```text
C_ocean * dT_sst/dt =
    Q_star_anomaly
    - Q_sensible
    - Q_latent
    + Q_horizontal
    + Q_deep_relaxation
```

где все `Q` в `W/m²`.

---

# 8. Effective ocean heat capacity

Не моделировать глубину океана по вертикальным слоям.

Ввести технический configurable parameter:

```text
ocean_mixed_layer_depth_m
```

и:

```text
C_ocean =
    rho_water
    * cp_water
    * mixed_layer_depth
```

Использовать физические константы:

```text
rho_water ≈ 1000 kg/m³
cp_water  ≈ 4180 J/(kg·K)
```

Default mixed-layer depth должен быть технической калибровкой, не каноном мира.

Все числа вынести в config/constants.

---

# 9. Stellar heating океана

Переиспользовать forcing C1.

Нельзя вводить новый:

```text
summer_ocean_bonus
```

Использовать именно radiative anomaly.

Пример:

```text
Q_star_anomaly =
    ocean_absorptivity
    * local_stellar_flux_anomaly_w_m2
```

или эквивалентный уже существующий C1 anomaly field.

Важно:

- использовать local latitude/longitude/day-night geometry;
- использовать orbital distance;
- использовать 364-day orbit;
- не double-count baseline;
- не создавать отдельную синусоиду сезона.

`ocean_absorptivity` — технический параметр.

В C2 не добавлять полноценный cloud radiative feedback, если его ещё нет физически.

---

# 10. Deep/climatological relaxation

Чтобы unresolved longwave radiation, deep-ocean mixing и static climatology не были потеряны, использовать мягкую релаксацию SST к baseline:

```text
Q_deep_relaxation =
    C_ocean
    * (baseline_sst - current_sst)
    / tau_deep
```

где:

```text
tau_deep
```

— configurable technical timescale.

Это не должно уничтожать сезонный лаг.

Слишком короткий `tau_deep` запрещён как default.

---

# 11. Air–sea sensible heat exchange

Использовать bulk form:

```text
Q_sensible =
    rho_air
    * cp_air
    * C_H
    * U_eff
    * (SST - T_air)
```

где:

```text
U_eff = sqrt(wind_u² + wind_v²)
```

с небольшим configurable minimum wind:

```text
U_eff = max(U, min_exchange_wind)
```

чтобы полностью штилевой океан не становился идеальным изолятором.

`C_H` — technical bulk transfer coefficient.

Знак должен быть физически корректным:

- если SST > air → океан теряет sensible heat, воздух получает;
- если SST < air → обратный обмен.

---

# 12. 2D atmosphere как bulk column

В C2 не вводить многослойную атмосферу.

Для энергобаланса считать atmospheric cell эффективным вертикальным столбом.

Масса воздуха над 1 м²:

```text
m_air_column = pressure_pa / gravity
```

Использовать каноническую гравитацию Фардекосмии:

```text
g ≈ 9.98 m/s²
```

Тогда sensible heat изменяет температуру атмосферной ячейки:

```text
delta_T_air =
    Q_sensible * dt
    / (cp_air * m_air_column)
```

Это лучше arbitrary `air_response += X`.

Добавить numerical caps на один timestep.

---

# 13. C2B — физический water vapor

Главное изменение C2B:

> Relative Humidity больше не является запасом воды в атмосфере.

Добавить prognostic field:

```text
water_vapor_specific_humidity
```

Рекомендуемая единица:

```text
kg water / kg moist air
```

то есть dimensionless `kg/kg`.

В diagnostics также показывать:

```text
g/kg
```

для читаемости.

---

# 14. Relative Humidity становится diagnostic

После C2:

```text
q_v = prognostic state
RH  = derived state
```

`WeatherState.humidity` можно сохранить как процент RH для совместимости UI/history.

Но AtmosphericGrid должен переносить именно `q_v`, а не RH.

---

# 15. Saturation vapor pressure

Использовать единый helper:

```python
saturation_vapor_pressure_pa(T)
```

Не размазывать формулу по solver.

Для C2 допустима физическая Clausius–Clapeyron approximation:

```text
e_s(T) =
    e0 * exp[
        (L_v / R_v)
        * (1/T0 - 1/T)
    ]
```

где:

```text
T  = Kelvin
T0 = 273.15 K
e0 ≈ 611.2 Pa
R_v ≈ 461.5 J/(kg·K)
L_v ≈ 2.5e6 J/kg
```

Если проект уже использует проверенную equivalent formula — можно сохранить её.

Версию saturation formula включить в solver fingerprint.

---

# 16. Saturation specific humidity

При pressure `p`:

```text
epsilon = 0.622

q_sat =
    epsilon * e_s
    /
    (p - (1 - epsilon) * e_s)
```

Использовать одинаковые units для `p` и `e_s`.

Добавить safeguard:

```text
e_s < p
```

Если температура настолько высокая, что saturation vapor pressure приближается к total pressure:

- не допускать NaN/negative denominator;
- clamp;
- записать diagnostic warning;
- не молча возвращать бессмысленное значение.

---

# 17. Deriving vapor pressure and RH from q

Из specific humidity:

```text
e =
    q * p
    /
    (epsilon + (1 - epsilon) * q)
```

```text
RH =
    100 * e / e_s(T)
```

RH для UI может быть clipped, например 0–200%, но сам `q` не должен уничтожаться только ради красивого процента.

C3 позже будет физически убирать supersaturation в condensate/cloud water.

---

# 18. Migration from old RH state

Для старых compatible/reinitialized atmospheric states:

```text
q_initial =
    RH_old/100
    * q_sat(T_old, p_old)
```

Это conversion bridge, а не новая физическая история.

Нельзя интерпретировать старые `RH/100` как `kg/kg`.

---

# 19. Initial water vapor

При полном initialization/reinitialization:

1. взять текущий climatic RH baseline/initial humidity logic;
2. вычислить `q_sat(T, p)`;
3. получить:
   ```text
   q_v = RH_fraction * q_sat
   ```
4. потом solver переносит `q_v`.

Не хардкодить одинаковый `q_v` по всей планете.

---

# 20. Moisture advection

Существующий atmospheric advection должен переносить:

```text
q_v
```

как scalar.

После C2 не адвектировать RH как физический запас воды.

RH вычислять ПОСЛЕ:

- temperature update;
- pressure update;
- q_v advection;
- evaporation.

Порядок задокументировать.

---

# 21. Ocean evaporation

Использовать bulk aerodynamic evaporation:

```text
E =
    rho_air
    * C_E
    * U_eff
    * max(0, q_sat_surface - q_air)
```

где:

```text
q_sat_surface =
    q_sat(SST, surface_pressure)
```

Единица `E`:

```text
kg / (m²·s)
```

Умножать на:

```text
open_water_fraction
```

который пока:

- 1 для обычной ocean cell;
- 0 для land;
- hook на будущее sea ice.

Не делать evaporation над сушей в C2.

---

# 22. Calm-wind evaporation

Использовать:

```text
U_eff = max(wind_speed, evaporation_min_wind)
```

но minimum wind должен быть небольшим configurable technical parameter.

Не позволять:

```text
U=0 → evaporation=0 навсегда
```

и не делать штиль равным сильному ветру.

---

# 23. Moisture addition to atmosphere

Испарившаяся вода за timestep:

```text
water_mass_added =
    E * dt
```

Изменение specific humidity bulk-column:

```text
delta_q =
    water_mass_added
    / m_air_column
```

где:

```text
m_air_column = p/g
```

Использовать small-step/cap safeguard.

---

# 24. Latent cooling океана

Испарение должно реально охлаждать SST:

```text
Q_latent =
    L_v * E
```

и входить со знаком потери энергии океаном.

Пока НЕ добавлять это тепло напрямую к sensible temperature воздуха.

Latent energy высвободится при condensation в C3.

---

# 25. Water mass accounting

C2 ещё не делает физические осадки, поэтому полный глобальный water cycle пока не замкнут.

Тем не менее добавить diagnostics:

```text
total_atmospheric_vapor_mass_proxy
total_evaporated_water
```

и тесты, что evaporation:

- увеличивает q_v;
- уменьшает ocean energy;
- не создаётся над land.

Явно задокументировать:

> mass conservation precipitation/condensation будет завершена в C3.

---

# 26. Supersaturation до C3

Поскольку C3 ещё нет, advection/cooling может дать RH > 100%.

Не удалять такую влагу молча.

Разрешить controlled temporary supersaturation.

Добавить safeguard:

```text
max_supersaturation_ratio
```

например technical upper safety bound.

Если он превышен:

- clamp только как numerical safety;
- считать/логировать removed_excess_vapor diagnostic;
- тестировать, что нормальная симуляция почти никогда не упирается в cap.

Cap не является физикой.

C3 заменит это конденсацией.

---

# 27. Existing precipitation system

Не переписывать precipitation/cloud engine полностью в C2.

Но его humidity input должен после C2 получать:

```text
derived RH
```

из `q_v`, `T`, `p`.

Не использовать старый humidity storage как independent prognostic field.

Важно:

текущие осадки пока НЕ обязаны удалять соответствующее количество `q_v`.
Это известное временное несоответствие до C3.

Не пытаться в C2 наполовину реализовать precipitation mass conservation.

---

# 28. Horizontal SST transport

Не делать ocean currents.

Разрешён только дешёвый diffusive/smoothing term:

```text
sst_anomaly = SST - baseline_SST
```

Сглаживать именно anomaly, а не абсолютную baseline map.

Пример:

```text
Q_horizontal ∝ Laplacian(sst_anomaly)
```

или эквивалентный stable neighbor mixing.

Требования:

- ocean-to-ocean only;
- не размазывать тепло через материки;
- longitude wraps;
- poles handled safely;
- coefficient obeys numerical stability;
- vectorized NumPy.

Это unresolved mixing, НЕ течение.

---

# 29. Почему diffuse anomaly, а не absolute SST

Если сглаживать абсолютную SST:

- горячая климатическая область начнёт искусственно стирать холодную;
- static mean-temperature map потеряет смысл.

Поэтому horizontal mixing должен переносить только отклонение от climatological baseline.

---

# 30. Thermal lag

C2 считается успешным только если океан имеет память.

Ожидаемое поведение:

```text
stellar flux peak (pericenter)
        ↓
SST peak occurs later
```

Точный lag НЕ считать каноном.

Он должен быть результатом:

- mixed-layer heat capacity;
- exchange coefficients;
- deep relaxation;
- evaporation.

Настраивать parameters, а не hardcode:
```text
SST_peak = pericenter + N days
```

---

# 31. Ocean vs land inertia

Суша продолжает использовать существующий C1/surface response.

Океан должен реагировать заметно медленнее суши.

Regression test:

при одинаковой radiative anomaly и controlled initial conditions:

```text
abs(delta_T_ocean)
<
abs(delta_T_land)
```

за короткий интервал.

---

# 32. Ympha и океан

Ympha forcing уже существует.

В C2 его небольшой temperature/energy effect можно включать в ocean anomaly через existing forcing layer, но:

- отдельно от central-star energy;
- без нового random effect;
- без удвоения уже применённого forcing;
- magnitude остаётся technical calibration.

Если текущий C1 Ympha forcing выражен только в °C proxy, не притворяться, что это W/m².

Либо:
- оставить его как small thermal target contribution;
- либо добавить отдельный configurable energy proxy с явной маркировкой approximation.

---

# 33. Sea ice hook

Полноценную динамику морского льда НЕ реализовывать.

Но архитектурно предусмотреть:

```text
open_water_fraction
```

чтобы позже:

- ice cover уменьшал evaporation;
- увеличивал albedo;
- изолировал ocean-atmosphere exchange.

Default в C2:

```text
1.0 ocean
0.0 land
```

если отдельной ice mask пока нет.

---

# 34. Snapshot format

C2 добавляет минимум:

```text
sea_surface_temperature_c
water_vapor_specific_humidity
```

или эквивалентные arrays.

Рекомендуется `float32`.

Не хранить отдельный full-grid RH, если он дешёво вычисляется.

Если compatibility/UI требует cached RH — доказать необходимость.

---

# 35. Solver version

Bump atmospheric solver version:

```text
v3 → v4
```

или актуальная следующая версия проекта.

Fingerprint должен включать:

- ocean model version;
- saturation formula version;
- ocean mask/static world version;
- mixed layer depth;
- heat capacities/constants version;
- deep relaxation;
- transfer coefficients;
- evaporation coefficients;
- vapor field format;
- supersaturation safeguard;
- C1 orbital forcing fingerprint.

Старый v3 snapshot не использовать молча.

---

# 36. Migration / old snapshots

Старые snapshots не удалять.

При необходимости:

- reinitialize SST from baseline;
- derive q_v from old RH;
- сохранить исторические snapshots как legacy;
- новые future states считать solver v4.

Не задним числом переписывать WeatherState history.

---

# 37. Exact simulation order

Явно задокументировать timestep order.

Рекомендуемый conceptual order:

```text
1. OrbitalClimateState
2. RadiativeForcingGrid
3. Load current SST + atmosphere
4. Advect atmospheric temperature / q_v / momentum
5. Pressure/wind update according to current solver architecture
6. Compute saturation diagnostics
7. Ocean stellar anomaly input
8. Sensible air–sea exchange
9. Evaporation
10. Latent cooling of SST
11. Horizontal SST anomaly mixing
12. Deep/baseline SST relaxation
13. Update air temperature
14. Update q_v
15. Recompute RH diagnostic
16. Existing cloud/precip proxy
17. clamps / validation
18. sample WeatherState
```

Codex может адаптировать порядок, если текущий solver требует operator splitting.

Но в отчёте он обязан описать фактический порядок и почему он стабилен.

---

# 38. Fast-forward — принципиально важно

Длинный fast-forward НЕ должен возвращаться к 1456 полным atmospheric steps/year.

Но SST — slow state и его нельзя просто телепортировать без памяти.

Добавить отдельный:

```python
advance_ocean_fast_forward(...)
```

который продвигает только медленные ocean/moisture macro-state без полной погоды.

---

# 39. Ocean fast-forward strategy

Предпочтительный вариант:

- atmosphere detailed steps пропускаются как сейчас;
- SST продвигается дешёвыми coarse vectorized steps;
- forcing берётся в середине coarse interval;
- рекомендуемый configurable coarse step:
  ```text
  1 day – 1 Vitok
  ```
- final atmospheric spin-up использует уже корректный SST target date.

Для 1 года:

```text
не 1456 full atmosphere steps
а, например, 52 дешёвых SST macro-steps
+ final normal spin-up
```

Не хардкодить 52, если выбран другой coarse timestep.

---

# 40. Fast-forward moisture

Не симулировать точную историю q_v по всей планете месяцами без атмосферы.

При fast-forward:

1. SST продвинуть как slow macro-state.
2. Atmospheric q_v reinitialize к физически разумному target-date climatological state:
   - из baseline RH logic;
   - target T/P;
   - target SST/ocean evaporation influence.
3. final spin-up обычным solver постепенно формирует реальное moisture field.

Не создавать точные historical humidity/evaporation events внутри skipped interval.

---

# 41. Fast-forward accuracy test

На reduced test grid сравнить:

```text
A: exact 6h simulation
B: fast-forward + ocean macro stepping + spin-up
```

для:

- 1 season;
- 1 canonical year.

Сравнить:

- mean SST;
- SST spatial MAE;
- max SST anomaly;
- final atmospheric temperature;
- final q_v/RH.

Не требовать bit-identical.

Цель для SST:

```text
mean absolute difference желательно <= 1–2°C
```

Если реальная стабильная tolerance другая — измерить, обосновать и зафиксировать тестом.

Производительность имеет приоритет над мнимой точностью недосимулированной погоды.

---

# 42. Fast-forward many years

Не делать runtime линейным безгранично по количеству лет.

Если UI позволяет несколько лет:

- использовать bounded macro-step;
- при очень больших skips разрешено cycle acceleration / convergence approximation;
- но итоговая SST должна зависеть от target orbital phase и исходного slow-state.

Не делать:

```text
100 years → 5200 full atmospheric steps
```

---

# 43. TimeAdvanceReport

Exact-mode report может собирать:

- начало/конец mean SST;
- warmest ocean anomaly;
- strongest evaporation episode;
- заметное изменение humidity.

Но не перегружать UI.

Fast-forward report может показывать deterministic macro climate summary:

```text
Океан:
средняя SST выросла/снизилась на X°C
к концу периода океан оставался теплее/холоднее климатической нормы
```

Только если эти данные реально были рассчитаны slow-state model.

Не придумывать точные штормы.

---

# 44. Region / GM diagnostics

Добавить GM diagnostics.

Для ocean cell:

```text
Baseline SST
Current SST
SST anomaly
Q_star_anomaly W/m²
Q_sensible W/m²
Q_latent W/m²
Evaporation kg/m²/day
```

Для atmosphere:

```text
Specific humidity q_v (g/kg)
Saturation q_sat (g/kg)
Derived RH %
Vapor pressure
Saturation vapor pressure
```

Для land cell:

```text
SST: not applicable
Evaporation from ocean: 0 locally
```

Не показывать technical data обычному игроку без необходимости.

---

# 45. Optional map overlays

Если существующая карта уже поддерживает atmospheric overlays, добавить GM-only layers:

```text
Sea Surface Temperature
SST anomaly
Specific humidity
Relative humidity
Evaporation
```

Только если это можно сделать без большого UI refactor.

Не блокировать C2 acceptance отсутствием overlay.

---

# 46. Performance

Нельзя потерять достигнутую оптимизацию.

На 180×90:

C1 baseline из отчёта:

```text
1 timestep ≈ 0.112 s
1 Vitok    ≈ 0.442 s
Season FF  ≈ 0.447 s
Year FF    ≈ 0.442 s
```

После C2 target:

```text
1 Vitok ideal: <= 0.8 s
1 Vitok hard target: <= 1.0 s

Season fast-forward: желательно <= 1.0 s
Year fast-forward:   желательно <= 1.0 s
```

Если performance выше hard target:

- профилировать;
- не уменьшать physics quality первым решением;
- проверять Python loops, repeated serialization, ORM, mask creation, saturation exp calls.

---

# 47. NumPy/vectorization requirements

На timestep:

- no Python loop per cell;
- ocean mask cached;
- baseline SST cached;
- latitude geometry reused;
- q_sat vectorized;
- sensible/latent flux vectorized;
- SST diffusion vectorized;
- q_v advection integrated into existing vectorized transport.

Использовать `float32` там, где это безопасно.

---

# 48. Numerical safeguards

Добавить explicit safeguards:

```text
SST finite
q_v finite and >= 0
pressure > 0
e_s denominator safe
wind finite
evaporation finite and >= 0
```

Per-step caps должны быть техническими safety bounds, а не основным климатическим механизмом.

Логировать/count, сколько cells упёрлись в cap во время benchmark.

Нормальная симуляция не должна постоянно жить на clamps.

---

# 49. Energy diagnostics

Для controlled tests добавить возможность проверить:

```text
Ocean energy lost through sensible heat
≈
Air sensible energy gained
```

с numerical tolerance.

Для evaporation:

```text
Ocean latent energy loss =
L_v * evaporated water mass
```

Не добавлять latent heat к air temperature до condensation.

---

# 50. Tests — baseline SST

Добавить:

1. Без anomaly/exchange SST остаётся около baseline.
2. Ocean initialization совпадает с baseline map/fallback.
3. Land cells не имеют активной SST.
4. Solver restart из snapshot сохраняет SST.

---

# 51. Tests — thermal inertia

Controlled forcing:

- land реагирует быстрее;
- ocean медленнее;
- после снятия forcing ocean дольше сохраняет anomaly.

Annual integration:

```text
SST maximum occurs after/around stellar maximum,
not before it under normal positive inertia parameters.
```

Не hardcode exact lag days.

---

# 52. Tests — sensible exchange

Проверить:

```text
SST > Tair → ocean cools, air warms
SST < Tair → ocean warms, air cools
```

Exchange → 0 при равных температурах.

Сильнее wind → stronger exchange при прочих равных.

---

# 53. Tests — evaporation

Проверить:

- warmer SST → stronger evaporation;
- drier air → stronger evaporation;
- stronger wind → stronger evaporation;
- saturated air over same-temperature water → near-zero evaporation;
- land → zero ocean evaporation;
- evaporation cools SST;
- evaporation increases q_v.

---

# 54. Tests — RH / q_v

Проверить:

- fixed q_v + cooling → RH grows;
- fixed q_v + warming → RH falls;
- fixed T/P + more q_v → RH grows;
- pressure change affects q_sat consistently;
- RH → q → RH roundtrip within tolerance.

---

# 55. Tests — moisture advection

Создать controlled moisture blob.

Проверить:

- q_v переносится ветром;
- total q_v approximately conserved when evaporation/precip/clamps disabled;
- RH не переносится как independent scalar;
- после переноса RH recomputed from local T/P.

---

# 56. Tests — hot ocean influences land indirectly

Controlled map:

```text
warm ocean → evaporation → moist air
wind blows toward land
```

После нескольких steps downwind land cell должна получить больше q_v/RH, чем upwind/control.

Не добавлять `distance_to_ocean humidity bonus`.

Это должен быть transport effect.

---

# 57. Tests — seasonal lag / Fardekosmia orbit

На canonical year:

- pericenter ≈ middle Summer;
- stellar flux peak there;
- SST responds smoothly;
- ocean does not jump 10+° instantly in one 6h step;
- Autumn can remain oceanically warm after short hot Summer;
- Winter cooling is gradual.

---

# 58. Tests — polar stability

Существующие полярные cold/elevation zones не должны автоматически превращаться в горячий океан.

Проверить:

- ocean mask vs polar land/ice;
- high-latitude low-insolation SST remains bounded;
- no absurd evaporation from frozen/invalid cells.

Sea-ice physics отдельно позже.

---

# 59. Tests — long run

Reduced grid:

```text
>= 2 canonical years
```

Проверить:

- no NaN/Inf;
- no unbounded SST drift;
- no unbounded q_v;
- no perpetual clamp saturation;
- repeatable seasonal pattern;
- deterministic result.

---

# 60. Snapshot / determinism tests

Одинаковые:

- initial snapshot;
- target world_minutes;
- config;
- world maps;
- seed;
- solver version

дают одинаковый результат.

Проверить exact advancement:

```text
one big request
vs
same interval split into smaller requests
```

на одинаковых atmospheric boundaries.

---

# 61. C2 не должен ломать C1

Все C1 tests остаются валидными:

- orbital period = 364 d;
- season durations;
- pericenter/apocenter;
- stellar flux;
- axial tilt;
- RegionalSky;
- Circle of Face;
- Red/Black Turns;
- Light/Dark/Mixed seasons;
- TimeAdvanceReport astronomical milestones.

---

# 62. Что НЕ делать в C2

Не реализовывать:

- physical condensation;
- cloud water mass;
- ice cloud microphysics;
- precipitation water removal;
- latent heat release from condensation;
- thunderstorms/cyclones overhaul;
- ocean currents;
- thermohaline circulation;
- tides;
- storm surge;
- sea-level model;
- dynamic sea ice;
- river runoff;
- soil moisture;
- biome evapotranspiration;
- volcanoes/tsunami;
- multi-layer atmosphere.

Это следующие этапы.

---

# 63. Будущий C3 interface

C2 должен оставить C3 готовые поля:

```text
air_temperature
pressure
q_v
q_sat
RH diagnostic
SST
evaporation_flux
wind
```

Чтобы C3 мог добавить:

```text
supersaturation
→ condensation
→ cloud water
→ precipitation
→ vapor removal
→ latent heat release
```

без переписывания C2.

---

# 64. Acceptance Criteria

C2 готов, если:

1. SST — динамическое state, а не constant.
2. SST имеет тепловую память.
3. Static mean-temperature map остаётся baseline.
4. Ocean heating использует C1 radiative anomaly.
5. Ocean не double-count абсолютную звёздную энергию.
6. Суша и океан имеют разную effective inertia.
7. Air–sea sensible exchange двусторонний.
8. Evaporation зависит от SST, q_air и wind.
9. Evaporation охлаждает океан.
10. Atmospheric moisture хранится как physical specific humidity `q_v`.
11. RH вычисляется из `q_v`, T и pressure.
12. Advection переносит q_v, а не RH.
13. Existing WeatherState.humidity продолжает получать RH%.
14. Старые snapshots не переиспользуются молча.
15. Fast-forward сохраняет ocean slow-state.
16. Season/year fast-forward остаётся быстрым.
17. SST имеет сезонный lag.
18. Warm ocean способен увлажнять downwind land через transport.
19. No NaN/Inf/runaway.
20. Все существующие C1 tests проходят.
21. Все новые C2 tests проходят.
22. Performance измерена до/после.
23. C3 можно начать без смены основной moisture architecture.

---

# 65. PHASE C2 IMPLEMENTATION REPORT

После реализации остановиться и НЕ начинать C3.

Вернуть:

```text
PHASE C2 IMPLEMENTATION REPORT

1. Changed files
2. New/changed models
3. Migrations
4. Previous ocean behavior found in code
5. Ocean mask implementation
6. Baseline SST source
7. SST snapshot/storage format
8. Ocean energy equation
9. Mixed-layer heat capacity
10. Stellar anomaly coupling
11. Deep relaxation
12. Sensible heat exchange
13. Water-vapor field and units
14. Saturation vapor pressure formula
15. RH derivation
16. Legacy RH → q_v migration
17. Evaporation formula
18. Latent cooling
19. q_v advection
20. Existing precipitation compatibility
21. Supersaturation temporary handling
22. SST horizontal mixing
23. Exact timestep order
24. Fast-forward ocean strategy
25. Fast-forward moisture strategy
26. TimeAdvanceReport changes
27. Diagnostics/UI changes
28. Solver version/fingerprint
29. Snapshot invalidation
30. Performance before/after
31. Fast-forward accuracy comparison
32. Seasonal SST lag observed
33. Tests added
34. Full test result
35. Numerical clamps hit during long-run test
36. Known approximations
37. Remaining questions for C3
```
