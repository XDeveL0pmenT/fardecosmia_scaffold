# ФАРДЕКОСМИЯ — PHASE C3
## Condensation, Clouds, Physical Precipitation & Human-Readable Region Conditions

### Назначение
Phase C3 завершает основной атмосферный водный цикл, начатый в C2, и одновременно добавляет второй независимый слой: **понятное человеку описание текущих условий региона**.

C3 состоит из двух частей:

- **C3A — Condensation / Clouds / Precipitation**
- **C3B — Human-Readable Environmental Summary**

C3B является только интерпретатором уже рассчитанного состояния мира. Он **не должен менять физику, WeatherState или результаты solver**.

---

# 0. Что уже считается готовым

До C3 уже реализованы и не должны переписываться без необходимости:

- AtmosphericGrid 180×90;
- exact timestep 360 минут;
- optimized in-memory advancement;
- configurable exact/fast-forward threshold;
- TimeAdvanceReport;
- OrbitalClimateState;
- канонический год 364 дня;
- неравные орбитальные сезоны;
- stellar forcing;
- отдельный Ympha forcing;
- динамическая SST;
- air–sea sensible heat;
- evaporation;
- latent cooling океана;
- prognostic specific humidity `q_v`;
- diagnostic RH;
- moisture advection;
- C2.5 fast-forward boundary atmosphere 24×12;
- 6h boundary substeps;
- SST fast-forward accuracy:
  - Season MAE ≈ 1.665°C;
  - Year MAE ≈ 1.089°C;
  - max error < 8°C;
- final exact spin-up 28 steps.

Не ухудшать эти свойства без документированной причины.

---

# 1. Канон мира, относящийся к C3

Учитывать:

- Фардекосмия жарче Земли, но пригодна для сложной жизни;
- огромный горячий центральный океан является мощным источником влаги и штормов;
- низины в среднем жарче и влажнее;
- высокие плато комфортнее;
- полюса и высокогорья могут удерживать лёд;
- Красные Плато должны получать сухость прежде всего через rain shadow и перенос влаги, а не hardcoded biome penalty;
- Туманные Топи логично имеют очень влажные/туманные условия;
- Светлое Лето особенно опасно сочетанием жары, пара и Люмена;
- холод подавляет Жарную Порчу;
- Тёмные ночи особенно опасны из-за Ноктиса;
- Светлая ночь с Ympha безопаснее от Ноктиса, но теплее.

Последний актуальный орбитальный канон брать из Bible v1.3:
- 364 дня;
- `a≈12.2 AU`;
- periapsis 10.2 AU;
- apoapsis 14.2 AU;
- axial tilt 8.79°.

---

# 2. Сначала проанализировать фактический код

Перед изменениями:

1. Прочитать текущие:
   - `simulation.py`
   - `grid.py`
   - `advection.py`
   - `thermodynamics.py`
   - `ocean.py`
   - `orography.py`
   - `sampling.py`
   - `persistence.py`
   - `fingerprint.py`
   - `time.py`
   - `time_reports.py`
   - region/dashboard views/templates.

2. Найти:
   - где сейчас вычисляются cloud cover;
   - где создаётся precipitation proxy;
   - где выбираются `CLEAR/CLOUDY/RAIN/STORM/SNOW/FOG`;
   - как орография сейчас влияет на облака/осадки;
   - как WeatherState хранит precipitation;
   - текущую семантику precipitation unit/index;
   - текущий supersaturation safeguard;
   - текущий fast-forward boundary-grid state.

3. До изменения снять benchmark:
   - 1 timestep;
   - 1 Vitok exact;
   - Season FF;
   - Year FF;
   - 1–2 year reduced-grid exact stability.

---

# PART C3A — PHYSICAL CONDENSATION / CLOUDS / PRECIPITATION

# 3. Новый prognostic condensate field

Добавить в AtmosphericGrid:

```text
cloud_condensate_specific_humidity
```

Короткое обозначение:

```text
q_c
```

Единица:

```text
kg suspended condensate / kg moist air
```

В C3 это **единый total condensate reservoir**.

Не создавать пока отдельные prognostic:
- cloud liquid;
- cloud ice;
- graupel;
- hail;
- snow crystals.

Фазу жидкость/лёд определять diagnostic function по температуре.

---

# 4. Состояния атмосферной воды после C3

```text
q_v = water vapor
q_c = suspended cloud condensate

q_v
  ↕ condensation / cloud evaporation
q_c
  ↓ precipitation fallout
surface sink
```

После C3 precipitation обязан физически уменьшать atmospheric water.

---

# 5. Condensation нельзя делать простым clamp

Запрещено:

```python
if q_v > q_sat:
    q_v = q_sat
```

Нужно:

```text
vapor removed from q_v
=
condensate added to q_c
```

и выделить скрытую теплоту.

---

# 6. Saturation adjustment с latent heat

При supersaturation решить связанный процесс:

```text
q_v' = q_v - Δq
q_c' = q_c + Δq
T'   = T + L_v * Δq / c_p
```

с конечным условием примерно:

```text
q_v' ≈ q_sat(T', p)
```

Поскольку конденсация нагревает воздух и меняет `q_sat`, нельзя использовать `q_sat` только при исходной температуре.

Реализовать vectorized iterative saturation adjustment:

- fixed-point / Newton / другой устойчивый метод;
- ограниченное число итераций;
- deterministic;
- no Python loop per cell;
- tolerance configurable;
- diagnostics iteration count.

---

# 7. Moist enthalpy consistency

В controlled condensation test приблизительно сохранять:

```text
c_p * T + L_v * q_v
```

если нет внешних heat fluxes и precipitation fallout.

---

# 8. Cloud evaporation

Если:

```text
q_v < q_sat(T,p)
```

и:

```text
q_c > 0
```

часть облачного конденсата должна испариться:

```text
q_c -= Δq
q_v += Δq
T   -= L_v * Δq / c_p
```

до saturation либо исчерпания `q_c`.

---

# 9. Liquid / ice diagnostic fraction

Ввести smooth phase partition.

Технический configurable переход, например:

```text
T <= -2°C → ice_fraction ≈ 1
T >= +2°C → ice_fraction ≈ 0
между ними плавная интерполяция
```

Это default, НЕ канон.

---

# 10. Advection q_c

`q_c` должен переноситься atmospheric wind тем же vectorized semi-Lagrangian transport, что и другие scalars.

После C3 переносить:

```text
temperature
q_v
q_c
```

а не diagnostic RH/cloud cover.

---

# 11. Cloud column water

Поскольку атмосфера пока 2D bulk-column:

```text
m_air_column = p / g
```

```text
cloud_water_path_proxy = q_c * m_air_column
```

Единица:

```text
kg/m²
```

---

# 12. Cloud cover из condensate

Старый RH threshold больше не должен быть главным источником облачности.

Рекомендуемая форма:

```text
tau_cloud = cloud_optical_coefficient * cloud_water_path_proxy
cloud_cover = 1 - exp(-tau_cloud)
```

с `0..1`.

Без `q_c` воздух с RH=99% не должен автоматически становиться сплошной физической облачностью.

---

# 13. Fog

Поскольку атмосфера 2D, solver не знает реальную высоту cloud base.

`FOG` остаётся diagnostic/proxy и может зависеть от:

- RH близко к 100%;
- nonzero q_c;
- близости T к dew point;
- слабого/умеренного ветра;
- поверхности/низины.

Не утверждать, что весь `q_c` находится у земли.

---

# 14. Orographic uplift

Переработать существующую орографию так, чтобы она помогала **создавать физическую конденсацию**, а не напрямую генерировала дождь из RH.

Использовать существующий/рассчитанный proxy:

```text
uplift ~ wind · terrain_gradient
```

При положительном uplift:
- adiabatic/orographic cooling proxy;
- выше вероятность saturation;
- после saturation растёт `q_c`.

На lee side воздух уже потерял часть water mass через precipitation и становится суше.

Это должно создавать rain shadow.

Не делать:

```python
if biome == RED_PLATEAU:
    precipitation -= X
```

---

# 15. Precipitation reservoir

Осадки формируются **ИЗ `q_c`**.

Не использовать больше главным механизмом:

```text
RH + random chance → rain
```

---

# 16. Autoconversion / fallout

Допустима bulk-схема:

```text
excess_cloud = max(0, q_c - q_c_threshold)
```

```text
precip_mass_flux = excess_cloud * m_air_column / tau_precip
```

Единица:

```text
kg/(m²·s)
```

`q_c_threshold` и `tau_precip` — технические параметры.

---

# 17. Precipitation physically removes q_c

За timestep:

```text
precipitated_mass = precip_mass_flux * dt
Δq_c = precipitated_mass / m_air_column
q_c -= Δq_c
```

Нельзя выпасть больше condensate, чем существует.

---

# 18. Precipitation rate units

Внутренняя физическая unit:

```text
kg/(m²·s)
```

Для UI:

```text
1 kg/m² liquid water = 1 mm
```

поэтому вычислять:

```text
precipitation_rate_mm_h
precipitation_amount_mm_per_step
```

---

# 19. Не менять молча старую DB semantics

Если существующее:

```python
WeatherState.precipitation
```

раньше было индексом/условной величиной, нельзя просто начать писать туда `mm/h`.

Codex должен:

1. определить текущую семантику;
2. либо добавить новые физические fields;
3. либо выполнить явную migration/versioned semantic transition;
4. сохранить читаемость старой history.

---

# 20. Rain / snow partition

Использовать smooth diagnostic fraction.

Рабочий default:

```text
T >= +2°C → rain_fraction ≈ 1
T <= -2°C → snow_fraction ≈ 1
-2...+2°C → mixed
```

Не вводить freezing rain/hail/graupel в C3.

Snow хранить как water equivalent (SWE), не как depth.

---

# 21. Precipitation intensity labels

Рабочие UI thresholds для дождя:

```text
<0.5 mm/h      → морось / следы
0.5–2.5        → слабый дождь
2.5–7.5        → умеренный дождь
7.5–30         → сильный дождь / ливень
>30            → очень сильный ливень
```

Configurable, не канон.

Для снега — отдельные labels по SWE rate.

---

# 22. Latent heating from condensation

При condensation latent heat должен реально повышать `T_air`.

Это должно влиять далее через существующую цепочку:

```text
latent heating
→ temperature
→ pressure
→ pressure gradients
→ wind
```

Не добавлять отдельный `storm_temperature_bonus`.

---

# 23. Exact timestep order

Рекомендуемый conceptual order:

```text
1. orbital forcing
2. advection T/q_v/q_c
3. land/ocean exchange
4. evaporation
5. orographic/other cooling
6. saturation adjustment
   - condensation
   - cloud evaporation
   - latent heating/cooling
7. pressure update
8. wind update
9. q_c fallout → precipitation
10. cloud diagnostics
11. RH/dewpoint diagnostics
12. WeatherState sampling
13. numerical validation
```

Codex может адаптировать operator splitting, но обязан описать фактический порядок.

---

# 24. Weather conditions становятся diagnostics

После C3:

```text
CLEAR  → low cloud + no precip
CLOUDY → significant cloud + little/no precip
RAIN   → liquid precip > threshold
SNOW   → snow fraction dominates
FOG    → fog diagnostic
STORM  → severe combined diagnostic
```

`STORM` может учитывать:
- precipitation rate;
- cloud cover;
- wind;
- pressure pattern;
- condensation/latent-heating activity.

Но condition не создаёт физику сам.

---

# 25. Deterministic variability

Если небольшая stochastic variability нужна:

- deterministic seed;
- малая амплитуда;
- она может модулировать efficiency;
- но не может создать дождь без condensate.

---

# 26. Atmospheric water diagnostics

Добавить:

```text
total_vapor_mass_proxy
total_cloud_condensate_mass_proxy
total_precipitated_mass
total_evaporated_mass
condensation_mass
cloud_evaporation_mass
```

---

# 27. Water conservation

В controlled closed test без evaporation/precip/clamps:

```text
q_v + q_c ≈ const
```

При precipitation:

```text
atmospheric water loss ≈ surface precipitation sink
```

---

# 28. Surface precipitation sink

В C3 НЕ моделировать:
- soil moisture;
- runoff;
- rivers;
- puddles;
- snowpack.

Но учитывать:

```text
surface_precipitation_sink
```

для будущей hydrology.

---

# 29. Supersaturation safeguard после C3

Старый C2 cap не должен быть нормальным механизмом.

После saturation adjustment RH в condensing cells должна быть около saturation.

Оставить только аварийный numerical cap и считать:

```text
supersaturation_emergency_clamp_hits
```

Long-run должен давать 0 или почти 0.

---

# 30. Fast-forward boundary atmosphere

C2.5 boundary-grid 24×12 обновить.

Добавить:

```text
q_c
```

и дешёвые версии:
- saturation adjustment;
- latent heating;
- cloud evaporation;
- precipitation fallout.

Не создавать detailed WeatherState внутри skipped interval.

---

# 31. Fast-forward precipitation semantics

Во время skipped периода разрешено интегрировать:

```text
integrated_macro_precipitation_mass
```

как **климатическую оценку**, потому что boundary model действительно её считает.

Но нельзя писать точное событие вроде:
> «на 127-й день шёл ливень»

если exact atmosphere этого дня не симулировалась.

---

# 32. FF accuracy после C3

На reduced grid сравнить exact vs FF:

- final SST;
- final T;
- final q_v;
- final q_c;
- RH;
- integrated precipitation mass.

Для SST постараться сохранить C2.5 targets:

```text
Season SST MAE <= 2°C
Year SST MAE <= 2°C
max local SST error <= ~8–10°C
```

---

# 33. Performance targets

C2.5 baseline:

```text
Vitok exact ≈ ~0.5 s
Season FF ≈ 0.85 s
Year FF ≈ 1.51 s
```

После C3 желательно:

```text
Vitok exact <= 1.0 s
Season FF <= 1.5 s
Year FF <= 2.0 s
```

Если выше — profile/vectorize, а не первым делом отключать condensation.

---

# 34. Snapshot/versioning

C3 добавляет `q_c`.

Bump:

```text
snapshot format
solver version
microphysics version
```

Fingerprint должен включать:
- q_c format;
- saturation adjustment version;
- latent heat constants/version;
- phase thresholds;
- cloud optical coefficient;
- precipitation conversion parameters;
- orographic condensation parameters;
- fast-forward microphysics version.

Старые snapshots не удалять, но не использовать молча.

---

# PART C3B — HUMAN-READABLE REGION CONDITIONS

# 35. Цель

На странице региона рядом с научными данными должна появиться отдельная карточка:

```text
УСЛОВИЯ ДЛЯ ПУТНИКА

Жарко и душно

Воздух тяжёлый и влажный. При длительной нагрузке быстро наступает
перегрев. Дует сильный северо-западный ветер, но он лишь частично
облегчает жару.

Опасности:
• Сильная жара
• Высокая влажность
• Сильный ветер
```

Экстремальный пример:

```text
СМЕРТЕЛЬНО ОПАСНАЯ ЖАРА

Воздух крайне горячий и насыщен влагой. Естественное охлаждение
испарением почти не работает; длительное пребывание без защиты
крайне опасно.
```

И холод:

```text
СМЕРТЕЛЬНЫЙ ХОЛОД

Открытая кожа быстро переохлаждается. Сильный ветер резко усиливает
ощущение холода. Без утепления длительное пребывание опасно.
```

---

# 36. Главное правило C3B

Human summary — **детерминированная интерпретация физических данных**.

Он НЕ должен:
- менять atmosphere;
- случайно выбирать фразы;
- придумывать неизвестные условия;
- заменять scientific values;
- использовать LLM/API при каждом GET.

Рекомендуемый pure service:

```python
build_environment_summary(...)
```

---

# 37. Scientific + Human UI вместе

Не убирать:
- °C;
- RH;
- pressure;
- wind;
- cloud cover;
- precipitation;
- q_v/q_c;
- diagnostics.

Добавить отдельный блок:

```text
Как здесь ощущается
```

или:

```text
Условия для путника
```

---

# 38. EnvironmentSummary

Рекомендуемая структура:

```python
EnvironmentSummary:
    headline
    short_description

    thermal_label
    humidity_label
    wind_label
    precipitation_label
    pressure_label
    visibility_label

    apparent_temperature_c
    wet_bulb_temperature_c
    wind_chill_c

    hazards
    overall_severity
    magical_warnings
```

---

# 39. Hazard object

```python
EnvironmentHazard:
    code
    severity  # 0..4
    title
    description
```

Severity:

```text
0 — нет
1 — заметно
2 — тяжело
3 — опасно
4 — экстремально / смертельно опасно
```

Это UI classification, не медицинский диагноз.

---

# 40. Heat evaluation — учитывать влажность

Для жары смотреть не только на dry-bulb T.

Использовать:
- air temperature;
- RH / vapor pressure;
- preferably wet-bulb temperature.

Добавить:

```python
wet_bulb_temperature_c(T, RH, pressure)
```

Предпочтительно физически/итерационно либо валидированной approximation с domain checks.

---

# 41. Heat-stress qualitative categories

Configurable technical defaults:

```text
Twb < 18°C  → нормально отдаётся тепло испарением
18–24        → влажно / душно
24–28        → тяжёлая духота
28–31        → опасный тепловой стресс
31–33        → экстремальный тепловой стресс
>33          → потенциально смертельно опасные условия
               при длительном пребывании без защиты
```

Не писать:
> «человек умрёт через N минут».

---

# 42. Dry extreme heat

Отдельно оценивать dry-bulb temperature.

Рабочие defaults:

```text
< -40       → экстремальный мороз
-40..-25    → очень сильный мороз
-25..-10    → сильный холод
-10..5      → холодно
5..15       → прохладно
15..27      → умеренно/тепло
27..35      → жарко
35..45      → сильная жара
45..55      → экстремальная жара
>55         → смертельно опасная жара
```

Итоговая thermal severity должна учитывать и dry heat, и humid heat.

---

# 43. Фраза «дышать почти невозможно»

Не использовать её только из-за высокого RH.

Высокая влажность сама по себе не означает нехватку кислорода.

Допустимые формулировки:

```text
Воздух тяжёлый и душный.
Дышать неприятно из-за жары и влажности.
Горячий влажный воздух делает физическую нагрузку крайне тяжёлой.
Воздух насыщен паром; без защиты длительное пребывание опасно.
```

Фразу:

```text
«дышать почти невозможно»
```

использовать только при severity 4 и действительно экстремальном сочетании T + vapor pressure / wet-bulb.

Tooltip/description должен давать понять, что причина — жара/влажность, а не автоматически дефицит кислорода.

---

# 44. Steam / vapor description

Использовать T + vapor pressure + saturation.

Labels:

```text
сухой воздух
умеренно влажный
влажный
душный
очень влажный
насыщенный горячим паром
```

Для `hot steam-like` требовать одновременно:
- высокую T;
- высокое vapor pressure;
- RH near saturation.

25°C / 90% RH не называть «обжигающим паром».

---

# 45. Cold evaluation

Для холода учитывать wind.

Если T <= 10°C и wind в domain формулы — вычислять wind-chill equivalent.

Если вне domain — не показывать ложную точность, а использовать qualitative modifier.

---

# 46. Cold phrases

```text
Прохладно
Холодно
Сильный мороз
Ледяной ветер
Экстремальный мороз
Смертельно опасный холод
```

При severity 4:

```text
Без утепления длительное пребывание крайне опасно.
Сильный ветер резко ускоряет потерю тепла.
```

Без медицинских обещаний времени до frostbite.

---

# 47. Wind interpretation

Technical defaults:

```text
<0.5 m/s  → штиль
0.5–5     → слабый ветер
5–10      → умеренный
10–17     → сильный
17–25     → очень сильный / штормовой
25–33     → буря
>33       → ураганный
```

Direction переводить:

```text
С, СВ, В, ЮВ, Ю, ЮЗ, З, СЗ
```

---

# 48. Pressure interpretation

Scientific pressure оставить.

Human labels:

```text
очень низкое
пониженное
обычное
повышенное
очень высокое
```

Но не утверждать «не хватает кислорода» только из total pressure.

---

# 49. Optional oxygen partial pressure

Точный состав атмосферы ещё не закреплён.

Сделать:

```text
oxygen_fraction = optional / nullable config
```

Если не задан:
- не выводить hypoxia risk.

Если позже задан:

```text
pO2 = pressure * oxygen_fraction
```

и можно добавить отдельный breathing-pressure hazard.

Не hardcode 20.9% как окончательный канон.

---

# 50. Precipitation human description

Использовать physical rate:

```text
без осадков
следы
морось
слабый дождь
умеренный дождь
сильный дождь
ливень
очень сильный ливень
```

Для снега:

```text
слабый снег
снег
сильный снегопад
```

Mixed:

```text
мокрый снег / смешанные осадки
```

---

# 51. Cloud human description

Из physical cloud cover:

```text
ясно
почти ясно
переменная облачность
облачно
пасмурно / сплошная облачность
```

---

# 52. Visibility

Если project уже имеет visibility field — использовать.

Если нет:
- можно добавить diagnostic qualitative visibility estimate из precip + fog potential;
- не выдавать ложную точность в километрах.

Labels:

```text
отличная
хорошая
дымка
плохая
очень плохая
почти ничего не видно
```

---

# 53. Combined sentence generation

Нужен priority-based composer, а не набор несвязанных строк.

Пример:

```text
T=42°C
RH=88%
wind=3m/s
heavy rain
```

→

```text
Очень жарко и душно. Воздух почти насыщен влагой, а слабый ветер
почти не облегчает тепловую нагрузку. Идёт сильный тёплый дождь.
```

---

# 54. Headline priority

Headline определяется наиболее важной опасностью:

```text
1. lethal/extreme thermal danger
2. hurricane/violent storm
3. extreme precipitation/blizzard
4. severe fog/visibility
5. dangerous heat/cold
6. ordinary weather sensation
```

Не выводить «небольшая облачность» как headline при +58°C.

---

# 55. Multiple hazards

Показывать максимум 2–4 главных badge:

```text
Критическая жара
Удушающая духота
Штормовой ветер
Сильный ливень
```

---

# 56. Current-region sanity regression

Для примерно:

```text
T = 23.6°C
RH = 52%
wind = 12.3 m/s
pressure = 970.7 hPa
cloud = 0%
```

summary НЕ должен писать:
- «смертельная жара»;
- «дышать невозможно»;
- «смертельно разреженный воздух».

Ожидаемо примерно:

```text
Тепло и ясно. Воздух умеренно влажный.
Дует сильный северо-западный ветер.
```

---

# 57. Extreme humid heat test

Например:

```text
T = 48°C
RH = 90%
weak wind
```

должен дать severity 4 с wording уровня:

```text
Смертельно опасная жара.
Воздух крайне горячий и насыщен влагой; естественное охлаждение
испарением почти не работает. Длительное пребывание без защиты
крайне опасно.
```

---

# 58. Extreme dry heat test

```text
T = 60°C
RH = 10%
```

→

```text
Смертельно опасная сухая жара.
```

Но НЕ `воздух насыщен паром`.

---

# 59. High RH cool test

```text
T = 8°C
RH = 100%
```

→ `холодно и сыро`, а не `удушающая духота`.

---

# 60. Extreme cold + wind test

```text
T = -35°C
wind = 20m/s
```

должен подчеркнуть:
- экстремальный мороз;
- усиление холода ветром;
- опасность без защиты.

---

# 61. Pressure test

```text
970 hPa
```

при неизвестном oxygen_fraction не создаёт hypoxia warning.

---

# 62. Magical / world-specific warnings

Human card должна учитывать существующий канонический `RegionalSky`.

Отдельная секция:

```text
Особенности Фардекосмии
```

### Dark Night

```text
Тёмная ночь: нет света Звезды и Ympha.
Опасность Ноктиса повышена.
```

### Light Night

```text
Ympha освещает ночь красным светом.
Ноктис слабее, но ночь теплее обычного.
```

Не пересчитывать sky state повторно.

---

# 63. Heat Corruption / Жарная Порча

Канон говорит, что риск выше в:
- жарких;
- влажных;
- паровых низинах;
- Светлом Лете;
- соответствующих Lumen-geology zones.

Точной probability model нет.

Разрешён qualitative hook:

```text
heat_corruption_conditions:
low
favorable
highly_favorable
```

Но:
- без процентов;
- без infection probability;
- biome alone не определяет риск;
- если geology layer отсутствует, писать только:
  `условия благоприятны для Жарной Порчи`,
  а не `вы заразитесь`.

---

# 64. Biome context

Biome может добавлять контекст, но не подменять physical state.

Примеры:
- Туманные Топи + фактическая высокая влажность → «топи наполнены тяжёлой сыростью»;
- Красные Плато + dry/windy → «сухой ветер несёт пыль»;
- Горы + cold/wind → «на высоте холод усиливается ветром».

Если физика не подтверждает состояние, biome не должен заставлять summary лгать.

---

# 65. Region elevation

Elevation можно использовать для context:

```text
высокогорье
низина
плато
```

Но thermal/pressure labels брать из фактического WeatherState.

---

# 66. Human summary и TimeAdvanceReport

Exact report может использовать тот же interpreter:

```text
Во 2-м Витке регион X пережил период опасной духоты.
```

только если exact states реально были рассчитаны.

Fast-forward:
- не создавать точные human weather episodes;
- можно показывать climate aggregate/hazard tendency, если boundary solver её реально вычислил.

---

# 67. UI layout

Предлагаемый порядок Region page:

```text
[Название региона]

[Как здесь ощущается]
Жарко и душно
Короткое описание
Hazard badges

[Текущая погода]
23.6°C
Ясно
...

[Научные данные]
RH / q / pressure / flux / diagnostics

[Астрономия / сезон]
...
```

Адаптировать к текущему дизайну.

---

# 68. Player vs GM visibility

Human-readable summary полезна всем.

GM diagnostics дополнительно:
- q_v;
- q_sat;
- q_c;
- vapor pressure;
- wet-bulb;
- cloud water path;
- condensation rate;
- latent heating;
- precipitation mass flux.

---

# 69. No runtime LLM

Текст строится локально:
- deterministic rules;
- templates;
- thresholds;
- localization-ready strings.

Не делать внешний AI call при GET.

---

# 70. Localization

Не захардкодить физическую логику на русские строки.

Использовать codes:

```text
THERMAL_EXTREME_HEAT
HUMIDITY_OPPRESSIVE
WIND_STRONG
PRECIP_HEAVY_RAIN
NOCTIS_DARK_NIGHT
```

и отдельно labels/templates.

---

# 71. C3B performance

Environment summary строить только для открываемого региона / sampled WeatherState.

Не запускать grid-wide human interpretation на каждый GET.

---

# 72. Tests C3A — condensation

Добавить:

1. supersaturated q_v condenses;
2. q_v decreases;
3. q_c increases matching mass;
4. air warms;
5. final RH near saturation;
6. no NaN/Inf;
7. enthalpy approximately conserved.

---

# 73. Tests C3A — cloud evaporation

1. dry air + q_c evaporates cloud;
2. q_c decreases;
3. q_v increases;
4. T decreases;
5. water mass conserved.

---

# 74. Tests C3A — precipitation

1. q_c above threshold generates precipitation;
2. precipitation removes q_c;
3. cannot remove more than exists;
4. rate converts correctly to mm/h;
5. rain/snow partition smooth.

---

# 75. Tests C3A — rain shadow

Controlled terrain:

```text
ocean → moist wind → mountain → lee land
```

Expected:
- windward q_c/precip larger;
- downwind q_v lower;
- lee precipitation lower after enough steps.

No biome penalty.

---

# 76. Tests C3A — cloud cover

1. q_c=0 → cloud cover near 0;
2. increasing cloud-water path raises cover monotonically;
3. cover bounded 0..100%;
4. RH alone without q_c does not produce full opaque cloud deck.

---

# 77. Tests C3A — long run

Reduced grid, >=2 canonical years:

- deterministic;
- no NaN/Inf;
- no runaway q_v/q_c;
- emergency supersaturation clamps ~0;
- bounded T/P/SST;
- precipitation occurs only where condensate exists;
- dry regions can remain dry;
- hot ocean produces meaningful moist/cloudy downwind zones.

---

# 78. Tests C3B — human interpretation

Minimum cases:

```text
23.6°C / 52% / 12.3m/s / clear
→ warm/clear + strong wind
```

```text
48°C / 90%
→ extreme/lethal humid heat
```

```text
60°C / 10%
→ lethal dry heat, NOT steam
```

```text
8°C / 100%
→ cold/damp, NOT humid heat
```

```text
-35°C / 20m/s
→ extreme cold + wind hazard
```

```text
970hPa, oxygen unknown
→ no hypoxia claim
```

```text
Dark Night
→ Noctis warning
```

```text
Light Night
→ Ympha / lower Noctis / warmer-night wording
```

---

# 79. Snapshot/version tests

- old format rejected as current;
- old data not deleted;
- new q_c survives roundtrip;
- deterministic resume;
- FF boundary q_c advances correctly.

---

# 80. Benchmark after C3

Вернуть:

```text
Before C3 / After C3

1 timestep
1 Vitok exact
Season FF
Year FF

peak RAM
snapshot bytes
DB writes
```

Также:

```text
Season/Year FF:
SST MAE
T MAE
q_v MAE
q_c MAE
max errors
```

---

# 81. Что НЕ делать в C3

Не реализовывать сейчас:

- 3D vertical atmosphere;
- separate liquid/ice prognostic reservoirs;
- hail/graupel;
- full thunderstorm/electrical model;
- tropical cyclone engine;
- ocean currents;
- tides;
- dynamic sea ice;
- snowpack;
- soil moisture;
- runoff/rivers;
- biome evapotranspiration;
- volcanoes/tsunami;
- disease probability model.

---

# 82. Acceptance criteria

C3 готов, если:

1. `q_c` существует как prognostic condensate.
2. Supersaturation физически конденсируется.
3. Condensation сохраняет water mass.
4. Latent heat возвращается в air temperature.
5. Clouds могут испаряться в сухом воздухе.
6. q_c адвектируется.
7. Cloud cover происходит в первую очередь из condensate.
8. Precipitation происходит из q_c.
9. Precipitation удаляет atmospheric water.
10. Осадки имеют физические units.
11. Rain/snow partition smooth.
12. Orography участвует через uplift/condensation.
13. Rain shadow получается физически.
14. Старый RH-random precipitation больше не source of truth.
15. Existing WeatherState conditions становятся diagnostics.
16. Fast-forward boundary solver включает q_c/latent/precip.
17. C2.5 FF accuracy не деградирует катастрофически.
18. Exact performance остаётся приемлемой.
19. Human-readable Region Summary реализована.
20. Human summary согласована с scientific values.
21. Summary умеет описывать жару, холод, духоту, ветер, дождь/снег, облака.
22. Summary не врёт про нехватку кислорода без composition config.
23. Dark/Light Night дают world-specific warning.
24. Heat Corruption wording остаётся qualitative, без fake probability.
25. Все старые тесты проходят.
26. Все C3 tests проходят.
27. Solver deterministic.
28. Phase C4 не начиналась.

---

# 83. PHASE C3 IMPLEMENTATION REPORT

После реализации остановиться.

Вернуть:

```text
PHASE C3 IMPLEMENTATION REPORT

1. Changed files
2. New/changed models
3. Migrations
4. Previous cloud/precip behavior
5. q_c field/storage/units
6. Condensation algorithm
7. Saturation-adjustment solver
8. Latent heat coupling
9. Cloud evaporation
10. Liquid/ice diagnostic partition
11. q_c advection
12. Cloud-water-path / cloud-cover formula
13. Fog diagnostic
14. Orographic condensation changes
15. Precipitation conversion formula
16. Precipitation units
17. WeatherState DB compatibility
18. Rain/snow partition
19. Water-mass accounting
20. Old precipitation proxy removal/deprecation
21. Exact timestep order
22. Fast-forward q_c/microphysics
23. Fast-forward accuracy after C3
24. Solver/snapshot versioning
25. Human-readable summary architecture
26. Heat / wet-bulb interpretation
27. Cold / wind-chill interpretation
28. Humidity/steam interpretation
29. Pressure/oxygen safeguards
30. Noctis/Ympha wording
31. Heat Corruption qualitative hook
32. UI changes
33. Performance before/after
34. Long-run stability
35. Numerical clamp statistics
36. Tests added
37. Full test result
38. Known approximations
39. Remaining questions for C4
```

Не начинать C4.
