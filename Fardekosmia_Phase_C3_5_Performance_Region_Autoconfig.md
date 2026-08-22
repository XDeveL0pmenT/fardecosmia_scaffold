# ФАРДЕКОСМИЯ — PHASE C3.5
## Fast-Forward Performance + Region Climate Autoconfiguration

Phase C4 не начинать.

## A. Fast-forward performance

После C3:
- 1 timestep: ~0.127 s
- 1 Vitok exact: ~0.697 s
- Season FF: ~1.142 s
- Year FF: ~2.947 s

Точность:
- Season SST MAE ~0.146°C
- Year SST MAE ~0.143°C
- precipitation mass error: ~0.434% season / ~0.074% year

Цель: ускорить Year FF желательно ниже 2.0–2.2 s, не ослабляя физику C3 и не меняя C1 orbital physics.

Профилировать boundary-grid microphysics. Проверить:
- saturation vapor pressure / q_sat;
- saturation adjustment;
- cloud evaporation;
- precipitation conversion;
- repeated array allocations;
- repeated calculation of column mass, phase partition and thermodynamic diagnostics.

Использовать vectorized active masks:
- needs_condensation
- needs_cloud_evaporation
- needs_precipitation

Дорогую microphysics выполнять только на активных cells.

Переиспользовать thermodynamic arrays внутри одного boundary step вместо повторного вычисления.

Boundary fast-forward должен считать только физически нужные T/q_v/q_c/pressure/wind/SST/latent/precipitation mass. Не строить WeatherState, human summary, UI labels, region sampling и snapshots на каждом skipped step.

Adaptive 6h/12h timestep можно исследовать только если profiler подтверждает пользу и exact-vs-FF accuracy остаётся хорошей.

Не ускорять через изменение condensation efficiency, latent heat, evaporation, precipitation timescale или orbital forcing.

---

# B. Region Climate Autoconfiguration

## Проблема

Сейчас форма региона содержит:

- Название
- Биом
- Базовая температура
- Отклик на орбитальную аномалию, °C
- Средняя влажность
- Высота
- Изменчивость погоды
- Поправка осадков

Автоматически из карты подставляются только:
- Биом
- Базовая температура
- Высота

После C1–C3 это нужно привести в соответствие с новой физической системой.

## B1. Сначала audit всех полей

Найти все consumers фактических model fields:
- base temperature
- orbital anomaly response
- average humidity
- elevation
- weather volatility
- precipitation modifier

Для каждого вернуть:
- source;
- где используется;
- участвует ли в AtmosphericGrid solver v5;
- legacy only?;
- создаёт ли double-count;
- должен ли быть auto-derived;
- нужен ли manual override.

## B2. Главный архитектурный принцип

REGION не должен быть отдельным источником климатической физики.

Регион = location + identity + optional explicit GM overrides.

Основной климат:
World Data
+ latitude/longitude
+ elevation
+ orbit
+ AtmosphericGrid
+ SST
+ pressure/wind
+ q_v/q_c
+ terrain/orography.

## B3. Название

Оставить ручным. Никогда не перезаписывать при автозаполнении.

## B4. Биом

Источник:
`biome_at(lat, lon)` из World Data.

Сохранять существующее автоматическое поведение.

Если существует campaign biome override — явно показывать, что это override.

## B5. Базовая температура

Источник:
`mean_temperature_at(lat, lon)`.

Это климатическая средняя карты, а не текущая температура.

Желательно переименовать UI:
`Климатическая средняя температура`.

## B6. Высота

Источник:
`elevation_at(lat, lon)`.

Автозаполнение обязательно.

## B7. Средняя влажность

Больше не должна требовать ручного ввода.

Создать/переиспользовать ЕДИНЫЙ helper:
`climatological_humidity_at(lat, lon, ...)`

Он должен использовать ту же baseline/initial humidity logic, что AtmosphericGrid initialization.

Можно учитывать только те факторы, которые уже реально существуют в atmospheric initialization:
- latitude;
- surface/ocean;
- baseline temperature;
- elevation;
- global humidity config;
- другие существующие physical initialization factors.

Не hardcode по biome.

Важно:
`Средняя влажность` != `Текущая влажность`.

Текущая RH всегда идёт из q_v/T/p текущего AtmosphericGrid/WeatherState.

## B8. Отклик на орбитальную аномалию — критический audit

Это legacy поле появилось до C1.

C1 уже рассчитывает:
OrbitalClimateState
→ distance
→ stellar flux
→ solar zenith
→ radiative anomaly
→ atmospheric response.

Поэтому старое поле НЕ должно добавлять второй seasonal temperature bonus.

Предпочтительно:
- оставить только для legacy weather fallback;
- убрать из обычной формы;
- показывать read-only: `Рассчитывается автоматически атмосферной моделью`.

Если legacy fallback требует число — вывести legacy default автоматически, но не использовать его в AtmosphericGrid v5.

## B9. Изменчивость погоды — audit

Скорее всего это legacy random-weather parameter.

Новый solver получает variability через динамику pressure/wind/radiation/moisture/terrain.

Если поле не участвует в AtmosphericGrid:
- deprecated/legacy;
- скрыть из обычной формы;
- при необходимости оставить в Advanced Legacy Settings;
- не добавлять новый random multiplier в solver ради сохранения поля.

Если legacy fallback всё ещё использует его — автозаполнять legacy helper'ом.

## B10. Поправка осадков — критический audit

После C3 осадки физически возникают:
evaporation → q_v → transport → cooling/uplift → q_c → precipitation.

Rain shadow также должен быть физическим.

Поэтому region precipitation modifier НЕ должен быть обычным input нового solver.

Предпочтительно:
- deprecated для AtmosphericGrid;
- hidden/read-only: `Осадки рассчитываются физически`;
- сохранить только для legacy fallback или явного GM override, если реально нужно.

Запрещено hardcode:
`if biome == RED_PLATEAU: precipitation_modifier -= X`.

Красные Плато должны быть сухими из-за geography/orography.

## B11. Manual overrides

Если GM всё-таки должен иметь возможность намеренно переопределять карту:

Добавить явное:
`[ ] Использовать ручные климатические поправки`

По умолчанию OFF.

Только после включения показывать Advanced/Legacy fields.

Обычное создание региона должно работать без ручного ввода климатических чисел.

## B12. Автозаполнение при выборе точки

После выбора lat/lon форма автоматически показывает:

- Биом
- Климатическую среднюю температуру
- Климатическую среднюю влажность
- Высоту
- Surface type: суша/океан (если полезно UI)

Без запуска полной атмосферной симуляции.

## B13. Один backend source of truth

Не дублировать формулы в JavaScript.

Frontend вызывает backend preview endpoint или существующий World Data endpoint.

Backend использует те же Python helpers, что и server-side Region creation.

При POST server-side снова вычислить auto-derived fields, если manual override не включён.

JS preview и реально сохранённые значения обязаны совпадать.

## B14. Кнопка обновления

Добавить:
`Обновить данные с карты`
или
`Пересчитать из World Data`.

Она обновляет только system-derived fields.

Не перезаписывает:
- название;
- explicit manual overrides;
- описание/прочий пользовательский текст.

## B15. Изменение координат существующего региона

Если lat/lon изменились:
- system-derived values автоматически пересчитать, если для них нет override;
- имя не менять;
- старую WeatherState history не переписывать;
- future sampling использует новую клетку;
- проверить необходимость invalidation только region-local cache.

## B16. Желаемый вид обычной формы

Название: [__________]

Положение: [карта]

Данные мира:
- Биом: Лес [авто]
- Средняя температура: 21.8°C [авто]
- Средняя влажность: 64% [авто]
- Высота: 225 м [авто]

[Дополнительные / ручные настройки]

Пользователь не должен видеть legacy orbital response / precipitation modifier / volatility как обязательные основные климатические параметры.

## B17. Тесты

Добавить минимум:

1. biome из World Data;
2. base temperature из карты;
3. elevation из карты;
4. climatological humidity auto-populates;
5. POST без ручных climate fields работает;
6. JS preview = saved backend values;
7. coordinate change recomputes derived values;
8. name не перезаписывается;
9. explicit override сохраняется;
10. AtmosphericGrid не double-count orbital response;
11. AtmosphericGrid не применяет legacy precipitation modifier;
12. weather volatility не создаёт второй random climate layer;
13. Red Plateau dryness не hardcoded через precipitation modifier;
14. preview GET не запускает full atmosphere simulation;
15. Region current weather всё ещё sample'ится из AtmosphericGrid.

---

# Acceptance Criteria

C3.5 готова, если:

1. Physics C3 не ослаблена.
2. Exact solver не упрощён ради benchmark.
3. Year FF ускорен либо profiler показывает, что дальнейшая оптимизация невыгодна.
4. FF SST accuracy остаётся хорошей.
5. precipitation mass error желательно <1%.
6. Region creation не требует ручного заполнения выводимых климатических параметров.
7. biome/temp/elevation идут из World Data.
8. mean humidity автоматически получается из единой atmospheric baseline logic.
9. orbital anomaly response не double-count C1.
10. precipitation modifier не вмешивается случайно в C3 physics.
11. weather volatility не создаёт legacy random layer в AtmosphericGrid.
12. legacy compatibility сохранена там, где реально нужна.
13. UI отличает auto-derived values от explicit overrides.
14. Все tests проходят.
15. Phase C4 не началась.

---

# PHASE C3.5 IMPLEMENTATION REPORT

A. FAST-FORWARD
1. Profiler before
2. Bottlenecks
3. Optimizations
4. Active-cell strategy
5. Thermodynamic reuse/cache
6. Adaptive timestep tests
7. Performance before/after
8. Accuracy before/after
9. Precipitation mass error
10. Determinism

B. REGION AUTOCONFIGURATION
11. Existing Region fields audit
12. Consumers field-by-field
13. Biome source
14. Base-temperature source
15. Elevation source
16. Mean-humidity source/helper
17. Orbital-response final role
18. Weather-volatility final role
19. Precipitation-modifier final role
20. Manual override architecture
21. Form/UI changes
22. Coordinate-change behavior
23. Preview endpoint / backend source of truth
24. Legacy compatibility
25. Double-count protections
26. Tests added

C. FINAL
27. Full test result
28. Migrations
29. Known approximations
30. Remaining questions for C4

Phase C4 НЕ начинать.
