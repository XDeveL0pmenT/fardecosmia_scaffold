# ФАРДЕКОСМИЯ — R1
## Region Weather Semantics & Lifecycle

R1 — это не новая климатическая фаза. Не менять C1–C4.2 физику, коэффициенты, orbital forcing, precipitation physics или timestep.

Не начинать Leaflet M1, C5, Travel Engine, Character system, WorldEvent или catastrophes.

## 0. Терминология

В интерфейсе Region создаётся вручную:

GM ставит точки → точки соединяются → получается замкнутый контур региона.

В коде это хранится как `map_polygon` и геометрически является polygon.

В UI/документации использовать термин **контур региона**. `polygon` оставить техническим термином.

## 1. Текущая проблема

Сейчас:
- контур Region сводится к `polygon_center()`;
- обычная Weather card фактически описывает одну anchor-point координату;
- новый Region при активном AtmosphericGrid всё равно сначала получает `legacy_v2`;
- старые WeatherState не знают, в какой геометрической revision Region были рассчитаны;
- Region page может показывать старый state после изменения контура;
- WeatherState и текущий sky могут быть с разных временных границ;
- один point sample не может представлять огромную область.

## 2. Главный принцип

Разделить:

### Region-area weather
Что примерно происходит по всей территории внутри вручную нарисованного контура.

### Local point weather
Что происходит в конкретной точке lat/lon.

Правило:

`КОНТУР → состояние территории`

`ТОЧКА → состояние персонажа / конкретного места`

R1 реализует Region-area weather. Player marker пока не реализуется, но `sample_environment_at(lat, lon)` сохраняется как future foundation.

## 3. Не менять семантику Region.elevation

`Region.elevation` сейчас участвует в point sampling и surface pressure.

Не заменять её средней высотой огромного региона.

Area statistics хранить/вычислять отдельно.

В будущем Advanced Region Geography сможет иметь:
- mean elevation;
- min/max elevation;
- dominant biome;
- biome percentages;
- climatological area statistics.

## 4. Region weather/geometry revision

Добавить Region field, например:

`weather_geometry_revision`

Default существующих Region: `0`.

Revision увеличивается при изменении:
- `map_polygon`;
- `map_latitude`;
- `map_longitude`;
- manual elevation, влияющей на point sampling.

Не увеличивается при rename/description/unrelated metadata.

## 5. WeatherState provenance

Добавить nullable fields:
- `region_weather_revision`;
- `sample_latitude`;
- `sample_longitude`;
- `sample_elevation_m`;
- `solver_version`;
- optional compact atmosphere fingerprint/hash, если архитектурно дешёво.

Существующую историю не переписывать физически и не удалять.

## 6. Current WeatherState query

Текущая point-weather карточка должна выбирать:

region=current Region
AND region_weather_revision=current Region revision
AND world_minutes <= Campaign.world_minutes

После изменения контура старые rows остаются историей, но не считаются current weather новой геометрии.

## 7. Новый Region не должен начинаться с fake legacy weather

Если:
- AtmosphericConfig enabled;
- Region имеет valid coordinates;

не вызывать `generate_weather(weather-v2)` как initial source.

Preferred:
- если можно дешёво загрузить compatible physical AtmosphericGrid state для latest completed atmospheric boundary;
- sample anchor point;
- создать `atmospheric_grid_v3` WeatherState;
- не менять `Campaign.world_minutes`.

Если физическое состояние нельзя получить корректно:
- не генерировать fake weather;
- UI: `Физическое состояние атмосферы появится после ближайшего атмосферного обновления.`

Legacy `weather-v2` оставить только для настоящего fallback:
- AtmosphericGrid disabled/missing;
- Region без координат.

## 8. Same-timestamp source precedence

Сейчас UNIQUE(region, world_minutes) может позволить legacy row заблокировать physical grid row.

Если на той же минуте есть `legacy_v2` и приходит `atmospheric_grid_v3`, physical grid state должен иметь приоритет.

Реализовать безопасный replace/upsert только для такой source-precedence ситуации.

Не переписывать произвольно существующую physical history.

## 9. Stale weather

Показывать GM:
- atmospheric state timestamp;
- age in world minutes.

Если age <= AtmosphericConfig.step_minutes — normal.

Если age > step_minutes — warning:
`Атмосферное состояние устарело`.

## 10. Новый отдельный Region-area state

Не превращать point WeatherState в среднее региона.

Добавить отдельный concept/model, например:

`RegionAreaWeatherState`

Он описывает состояние всей территории контура на конкретной atmospheric boundary.

## 11. Region contour mask

Для Region + geometry revision + grid resolution построить reusable mask/weights:

Region contour × AtmosphericGrid cells → coverage weight per cell.

Учитывать:
- seam ±180°;
- latitude;
- polar regions;
- huge regions;
- tiny regions.

## 12. Area weighting

Не использовать простое среднее клеток.

Weight:
`cell_area_m2 × fraction_of_cell_covered_by_region`

Если exact spherical clipping недоступен, разрешён deterministic sub-cell sampling (например 4×4/8×8) с profiler.

Mask строится один раз на geometry revision и кешируется.

## 13. Tiny Region fallback

Если Region намного меньше atmospheric cell и area coverage ненадёжна:

`sampling_mode = POINT_FALLBACK`

Использовать anchor point.

UI:
`Регион меньше разрешения атмосферной сетки; показана точечная оценка.`

## 14. Temperature metrics

Area-weighted:
- mean;
- min/max;
- p10/p90.

Для обычного UI основной диапазон лучше p10–p90.

## 15. Humidity / pressure / cloud

Минимум:
- humidity mean/p10/p90;
- surface pressure mean;
- cloud cover mean;
- cloudy-area fraction;
- heavy-cloud fraction.

## 16. Precipitation metrics

Обязательно:
- precipitating area fraction;
- rain area fraction;
- snow area fraction;
- area mean precipitation rate;
- wet-area mean precipitation rate;
- max precipitation rate.

Не сводить осадки только к среднему.

Пример:
`Дождь идёт на 28% территории; там, где он идёт, средняя интенсивность 2.1 мм/ч; максимум 5.6 мм/ч.`

## 17. Rain/snow

Rain/snow split считать per cell из actual temperature тем же helper logic, что point WeatherState.

Один Region одновременно может иметь rain, snow и dry areas.

## 18. Wind

Нельзя усреднять градусы.

Считать weighted mean `u/v`, затем получать prevailing direction.

Также:
- mean speed;
- p90;
- max;
- strong-wind area fraction.

## 19. Fog / hazards

Если дешёво:
- fog area fraction;
- dangerous heat fraction;
- dangerous cold fraction;
- strong-wind fraction.

Не делать per-cell LLM summary.

Noctis/magical area aggregation можно отложить, если current sky model не даёт корректной spatial area treatment.

## 20. Human-readable regional summary

Добавить deterministic helper:

`build_region_area_weather_summary(...)`

Без LLM/API.

Пример:
`На большей части региона сухо и тепло. Местами идут дожди, примерно на четверти территории. Преобладает умеренный западный ветер.`

Coverage wording:
- <5% — единичные участки;
- 5–20% — местами;
- 20–50% — на части территории;
- 50–80% — на большей части;
- >80% — почти повсеместно.

Optional: directional sectors north/south/east/west, если реализуются надёжно.

## 21. Когда считать RegionAreaWeatherState

Не считать heavy area aggregation на каждом GET.

Preferred:
simulate_step
→ point WeatherState sampling
→ Region area aggregation
→ bulk_create RegionAreaWeatherState

Использовать cached masks и NumPy.

## 22. Fast-forward semantics

Skipped interval:
- не создавать вымышленные RegionAreaWeatherState.

Final exact spin-up:
- создавать area states на реальных exact boundaries.

Integrated precipitation в TimeAdvanceReport остаётся отдельной сущностью.

## 23. New Region area state

Если compatible physical grid доступен при создании:
- point WeatherState;
- RegionAreaWeatherState
для одной boundary.

Если нет:
- оба появляются на следующем atmospheric boundary;
- fake legacy area weather не создавать.

## 24. Region detail UI

Два разных блока:

### Погода в регионе
Area aggregate:
- общий текст;
- temperature range;
- precipitation coverage;
- cloudiness;
- prevailing wind;
- hazards.

### Погода в опорной точке
GM/debug:
- anchor lat/lon;
- point temperature/RH/pressure/wind/precip;
- C4 diagnostics.

Не выдавать anchor weather за погоду всего Region.

## 25. Future player-local weather

R1 не реализует Character.

Зафиксировать:
Character current lat/lon
→ `sample_environment_at()`
→ local player weather.

Персонаж не использует Region mean weather как свою текущую погоду.

## 26. Future Travel / Leaflet

Travel:
route points → point sampler.

Leaflet:
- click Region → RegionAreaWeatherState;
- click arbitrary point → point sampler/API;
- player token → point weather.

## 27. Existing climate metadata

R1 не удаляет:
- base_temperature;
- humidity;
- elevation;
- biome.

Legacy:
- seasonal_amplitude;
- weather_volatility;
- precipitation_bias
остаются изолированными от AtmosphericGrid.

## 28. Region creation preview

R1 может оставить current center-based World Data preview.

Не превращать existing `Region.elevation` в mean region elevation.

Future task после Leaflet/climate analytics:
- mean annual temperature;
- mean/min/max elevation;
- dominant biome + percentages;
- annual/seasonal precipitation;
- hazard index;
- habitability;
- settlement suitability.

## 29. Required tests

### Lifecycle
1. Grid enabled + located Region → no initial legacy_v2.
2. Compatible physical state → physical initial point weather.
3. No physical state → no fake weather; pending message.
4. Grid disabled → legacy fallback works.

### Revision
5. rename does not increment.
6. move contour increments.
7. anchor change increments.
8. manual elevation change increments.
9. old WeatherState remains in DB.
10. old revision is not current.
11. new state uses new revision.

### Source precedence
12. legacy_v2 at same minute cannot block incoming atmospheric_grid_v3.

### Geometry
13. rectangle.
14. irregular contour.
15. huge contour.
16. tiny contour.
17. seam-crossing contour.
18. polar contour.
19. deterministic spherical weights.

### Area aggregate
20. weighted temperature correct.
21. precip-area fraction correct.
22. rain/snow coexistence correct.
23. vector wind aggregation correct.
24. human summary matches metrics.

### Critical point-vs-area distinction
25. anchor dry, 60% Region raining:
    point weather dry;
    Region weather says rain on majority.

26. anchor raining, most Region dry:
    point weather rainy;
    Region weather says mostly dry.

### Fast-forward
27. skipped interval creates no fake area history.
28. final spin-up creates area states.
29. area timestamp aligns with exact boundary.
30. TimeAdvance integrated precip remains separate.

## 30. Performance

Report added cost of Region-area aggregation.

Use:
- cached masks;
- NumPy;
- no ORM per cell;
- bulk create.

Benchmark:
- 1 exact Vitok;
- Season FF;
- Year FF;
- if practical 1/10/100 synthetic Regions.

Do not tune climate physics for R1 performance.

## 31. Acceptance Criteria

R1 ready when:
1. Located Region with active grid no longer starts with fake legacy weather.
2. Real legacy fallback remains.
3. Region revision exists.
4. Historical weather survives contour movement.
5. Old revisions are not used as current.
6. New rows carry provenance.
7. Legacy same-timestamp row cannot block physical state.
8. GM sees weather age/stale state.
9. Area weather is separate from point weather.
10. Area weather uses manually drawn contour.
11. Spherical area weighting is used.
12. Precipitation coverage is reported.
13. Rain/snow can coexist in one Region.
14. Wind uses vector aggregation.
15. Deterministic human regional summary exists.
16. Tiny regions have explicit point fallback.
17. Fast-forward invents no skipped area weather.
18. Point sampler remains ready for Character/Travel/Leaflet.
19. C1–C4.2 physics unchanged.
20. Tests pass.
21. Leaflet/C5/Character/Travel not started.

## 32. R1 IMPLEMENTATION REPORT

Return:
1. Changed files
2. Models/migrations
3. Region revision design
4. WeatherState provenance
5. Initial Region weather before/after
6. Legacy fallback
7. Same-timestamp source precedence
8. Current WeatherState query
9. Stale-state handling
10. Region contour data flow
11. Area-mask algorithm
12. Seam/polar handling
13. Area weighting
14. Tiny-region fallback
15. Temperature metrics
16. Humidity/pressure/cloud metrics
17. Precipitation coverage
18. Rain/snow split
19. Wind aggregation
20. Hazard/fog coverage
21. Human-readable regional summary
22. Point-vs-area example
23. New Region creation example
24. Geometry-edit/history example
25. Exact advancement integration
26. Fast-forward integration
27. Region detail UI
28. Character point-weather compatibility
29. Leaflet compatibility
30. Travel compatibility
31. Performance before/after
32. Tests added
33. Full test result
34. Known approximations
35. Confirmation climate physics unchanged
36. Confirmation Leaflet/C5/Character/Travel not started

Stop after report.
