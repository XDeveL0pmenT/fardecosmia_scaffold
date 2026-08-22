# ФАРДЕКОСМИЯ — M1
## Leaflet Planetary Atlas Migration
### Equirectangular custom-planet CRS, tiled deep zoom, vector Region contours, layers & point inspection

> Перед началом прочитать:
> - актуальный Master Roadmap;
> - Architecture Guardrails;
> - C4/C4.1/C4.2 reports;
> - R1 Region Weather Semantics & Lifecycle report;
> - Region Weather Data Flow report.
>
> M1 — миграция существующей карты на Leaflet.
>
> НЕ начинать:
> - M1.5 precipitation/hazard/habitability analytical layers;
> - M2 countries/settlements/roads;
> - Character/Fog of War;
> - Travel Engine;
> - C5;
> - WorldEvent/catastrophes.
>
> Главная цель: заменить текущую SVG/image-navigation architecture на расширяемый Leaflet Atlas без изменения физики мира и без потери существующей функциональности Region.

---

# 0. Главный UX-результат

После M1 пользователь должен получить карту, которая ощущается как современный атлас:

```text
drag/pan
+
глубокий zoom
+
слои
+
векторные контуры Region
+
точные lat/lon
+
inspect arbitrary point
+
GM contour editing
```

Но это НЕ клон Google Maps.

Это planetary/fantasy atlas Фардекосмии.

---

# 1. Не использовать MapLibre

Основная библиотека:

```text
Leaflet
```

Не добавлять второй map framework.

Если проект не имеет frontend bundler:
- хранить Leaflet JS/CSS локально в static/vendor;
- сохранить license notice;
- не делать production functionality зависимой от CDN.

Если bundler уже существует:
- использовать текущий dependency workflow.

Не внедрять новый React/Vite/Webpack stack только ради M1.

---

# 2. Проекция Фардекосмии

Исходные World Data карты являются equirectangular:

```text
longitude: -180° .. +180°
latitude:   -90° .. +90°
```

M1 НЕ использует default Leaflet Web Mercator `EPSG:3857`.

Использовать custom/equivalent Leaflet CRS на базе:

```text
L.CRS.EPSG4326 / L.Projection.LonLat
```

с equirectangular 2:1 world geometry.

Важно:
- визуальный world extent = 360° × 180°;
- longitude wrap = ±180°;
- latitude не wrap;
- полюса остаются верхним/нижним краем карты.

---

# 3. Размер планеты

Каноническая окружность Фардекосмии:

```text
72 500 km
```

Радиус всегда выводить:

```text
R = circumference / (2π)
```

Не использовать Earth radius.

Не использовать Earth circumference.

Не полагаться на default `L.CRS.Earth.distance`.

---

# 4. Custom distance

Leaflet map distance для lat/lon должен использовать spherical haversine с радиусом Фардекосмии.

Sanity:

```text
1° дуги по экватору
≈ 72 500 / 360
≈ 201.39 km
```

```text
90° great-circle arc
≈ 18 125 km
```

```text
179°E ↔ 179°W
≈ 2° arc
```

а не почти полный круг планеты.

Этим же helper позже сможет пользоваться Travel Engine.

Backend geometry остаётся source of truth для gameplay-distance, frontend distance должен совпадать с ним в tolerance.

---

# 5. Pixel/tile geometry CRS

CRS должен сохранять 2:1 equirectangular world.

Conceptually at zoom 0:

```text
world width  = 512 px
world height = 256 px
```

Каждый следующий zoom:

```text
width  *= 2
height *= 2
```

Эквивалент Leaflet transformation должен давать:

```text
lon -180° → x = 0
lon +180° → x = worldWidth

lat +90°  → y = 0
lat -90°  → y = worldHeight
```

Предпочтительно расширить EPSG4326-compatible CRS и заменить planetary distance, а не писать огромный custom projection с нуля.

---

# 6. Deep zoom

M1 должен позволить сильно приближать карту независимо от native raster resolution.

Target:

```text
maxZoom >= 10
```

желательно configurable.

При equirectangular z0 width=512:

```text
z8  ≈ 0.55 km/pixel at equator
z9  ≈ 0.28 km/pixel
z10 ≈ 0.14 km/pixel
```

Это UI/geographic precision, а НЕ обещание такой детализации raster texture.

Если base map native resolution меньше:
- использовать `maxNativeZoom`;
- Leaflet может upscale raster выше native zoom;
- vector contours/markers остаются точными.

Не генерировать гигантские upscaled tile pyramids только ради maxZoom.

---

# 7. Tile pyramid

Перевести static raster layers на Leaflet tiles.

Минимум:

```text
Base/world map
Mean temperature
Elevation
Biomes
```

Создать deterministic tile-build command/script.

Preferred tile size:

```text
256 × 256
```

z0 equirectangular world:

```text
2 tiles × 1 tile
```

z1:

```text
4 × 2
```

и т.д.

---

# 8. Tile generation

Tile builder должен:

1. проверить источник;
2. проверить ожидаемую equirectangular 2:1 geometry;
3. определить reasonable native zoom из source resolution;
4. создавать только downsample/native pyramid;
5. не создавать уровни выше native resolution;
6. разрезать каждый raster на tiles;
7. сохранять transparency для overlay layers;
8. давать понятную ошибку при несовместимой карте.

Не менять World Data source rasters.

---

# 9. Source raster dimensions

Не hardcode предполагаемые размеры карт.

Codex должен определить фактические current source assets.

Если source width/height не являются perfect tile-pyramid dimensions:
- корректно resample на nearest appropriate equirectangular native canvas;
- документировать решение;
- не crop coastline silently.

Координатная привязка должна остаться точной.

---

# 10. Static tile versioning

Изменение World Data raster не должно требовать browser cache purge вручную.

Использовать:
- revision;
- digest;
- versioned tile directory;
- или cache-busting URL.

Не привязывать этот механизм к Campaign weather state.

---

# 11. Current light layer

`Свет сейчас` динамический и зависит от current world time / sky model.

M1 должен сохранить текущую визуальную семантику:
- Star light/shadow;
- Ympha visibility/light;
- black/deep night;
- current star/Ympha peak markers if currently displayed.

Не переносить C1/RegionalSky physics в frontend.

Frontend получает уже существующие server-derived parameters/data и только визуализирует их.

---

# 12. Light overlay implementation

Не обязательно tile current-light layer в M1.

Допустимые варианты:
- Leaflet ImageOverlay;
- SVG overlay inside Leaflet pane;
- Canvas/GridLayer.

Главное:
- правильно привязать к world bounds;
- zoom/pan синхронизирован;
- seam работает;
- physics remains backend-derived.

---

# 13. Leaflet panes

Заранее создать понятные panes/z-order:

```text
base raster
static climate raster
dynamic light/shadow
region fills
region borders
future feature markers
labels
edit handles
GM debug
```

Это важно для будущих:
- precipitation;
- hazards;
- countries;
- settlements;
- characters;
- Fog of War;
- WorldEvent.

M1 их не реализует.

---

# 14. Существующие map tabs

Сохранить функции:

```text
Свет сейчас
Средняя температура
Высота
Биомы
```

Можно оставить текущий tab UI.

Внутри tabs должны переключать Leaflet layers.

Не создавать четыре независимых map instances.

Один Leaflet map:
```text
layer switch
```

---

# 15. Base map behavior

При смене climate layer:

- pan/zoom сохраняются;
- выбранный Region сохраняется;
- fullscreen сохраняется;
- edit contour не должен неожиданно очищаться.

---

# 16. Zoom controls

Заменить старое image-scale увеличение на Leaflet zoom.

Минимум:

```text
+
-
Весь мир / reset view
fullscreen
```

Старое понятие `100% / 800%` можно убрать или оставить только как cosmetic display, если оно больше не вводит в заблуждение.

Предпочтительнее показывать:
- zoom level;
- real scale.

---

# 17. Scale control

Добавить scale в km, основанный на custom Fardecosmia distance.

Не показывать miles.

Scale должен быть корректен относительно широты настолько, насколько позволяет equirectangular display + spherical distance helper.

---

# 18. Cursor coordinates

В GM view показывать под курсором:

```text
lat
lon
```

Формат:
- decimal degrees;
- N/S, E/W или русская локализация.

Longitude всегда нормализовать:

```text
[-180°, +180°)
```

даже если пользователь визуально pan'ит в wrapped copy мира.

---

# 19. World wrap

Карта должна горизонтально wrap'иться через ±180°.

Поведение:
- можно pan через край мира;
- запад/восток являются соседями;
- center/cursor longitude normalizes to canonical range;
- region contour near seam не растягивается через всю планету;
- current light overlay повторяется/стыкуется корректно.

Не wrap latitude.

---

# 20. World copies

Leaflet может визуально показывать horizontal copies мира.

Это допустимо для browsing.

Но:
- storage всегда canonical;
- один Region не должен создаваться дважды из-за wrapped copy;
- click в duplicated copy нормализуется к canonical lon;
- edit handles работают на выбранной display copy.

---

# 21. Region terminology

В UI:

```text
контур региона
```

В code:
```text
polygon/ring
```

Region по-прежнему создаётся вручную:
- GM ставит вершины;
- линии соединяются;
- замыкание образует контур.

---

# 22. Region storage — не ломать R1

Не делать destructive rewrite текущего `Region.map_polygon` только ради Leaflet.

Сейчас R1 и backend geometry уже работают.

M1 должен добавить/централизовать geometry conversion service:

```text
stored normalized contour
↔ canonical lat/lon ring
↔ Leaflet LatLng[]
```

Frontend не должен работать с raw image pixels.

Если позже потребуется schema migration на GeoJSON/lat-lon storage — отдельная phase.

---

# 23. Conversion formulas

Для current normalized equirectangular contour:

```text
lon = x * 360 - 180
lat = 90 - y * 180
```

Reverse:

```text
x = (lon + 180) / 360
y = (90 - lat) / 180
```

Не дублировать эти формулы хаотично по JS/templates.

Создать один JS helper/module и один backend geometry source.

---

# 24. Server remains authoritative

При Region create/edit:

Frontend:
- рисует contour;
- показывает preview.

Server:
- заново валидирует geometry;
- заново вычисляет center;
- заново применяет Region climate/world-data logic;
- сохраняет.

Не доверять browser-computed center как source of truth.

Это сохраняет current Region Data Flow.

---

# 25. Region drawing mode

Сделать отдельный GM mode:

```text
Просмотр
Редактирование контура
```

При drawing:
- click adds vertex;
- vertices connected immediately;
- clearly show first vertex;
- finish contour via click first vertex / explicit finish action;
- undo last vertex;
- clear contour;
- cancel.

Не создавать Region случайным drag при обычном browsing.

---

# 26. Region vertex handles

Edit handles:
- constant pixel size;
- не увеличиваются вместе с world zoom;
- точные center points;
- видны только edit mode;
- selected/hover states.

На глобальном масштабе они не должны быть огромными, как сейчас.

---

# 27. Existing Region editing

Сохранить current feature:

```text
перерисовать / изменить контур
```

При geometry save:
- существующая R1 `weather_geometry_revision` должна увеличиваться по текущим правилам;
- history сохраняется;
- current area weather ждёт новый physical state или создаётся согласно R1 lifecycle.

M1 не должен обходить Region revision logic.

---

# 28. Region outlines in normal mode

Region layer:
- thin border;
- subtle transparent fill;
- no edit handles;
- hover highlight;
- click selects Region.

Popup/side panel:
- name;
- latest RegionAreaWeatherState summary if available;
- age/stale info;
- link `Открыть регион`.

Не вычислять area aggregation on click — использовать R1 persisted state.

---

# 29. Region labels

Не показывать все названия постоянно на любом zoom.

Для M1 достаточно:
- optional label for selected/hover Region;
- или thresholded permanent labels.

Architecture должна позволить future zoom-dependent labels для countries/cities.

---

# 30. Region climate preview

Сохранить current preview flow:

```text
Leaflet contour
→ normalized contour
→ region_climate_preview
→ server polygon center
→ region_climate_at
→ form suggestions
```

Preview остаётся advisory.

POST server recalculates again.

---

# 31. Region creation panel

Сохранить:
- name;
- auto/manual climate mode;
- biome;
- climate mean temp;
- climatological humidity;
- elevation;
- create Region.

Не возвращать legacy orbital response/weather volatility/precipitation bias в normal UI.

---

# 32. Basic arbitrary-point inspection

Добавить GM `Inspect point` mode или click behavior.

At arbitrary lat/lon показать дешёвую info card:

Static World Data:
- latitude;
- longitude;
- surface;
- elevation;
- biome;
- mean temperature;
- climatological humidity if available.

Optional current atmosphere if compatible state exists:
- temperature;
- RH;
- pressure;
- wind;
- cloud;
- precipitation;
- atmospheric timestamp/age.

---

# 33. Point inspection must be read-only

Inspect GET:
- не продвигает Campaign time;
- не создаёт Region;
- не создаёт WeatherState;
- не запускает full atmosphere simulation;
- не мутирует DB.

Использовать existing:
```text
sample_environment_at(lat, lon)
```
только если compatible physical grid/snapshot доступен.

Если current physical state unavailable:
- вернуть static data;
- `weather_available=false`.

---

# 34. Permission boundary

M1 — GM Atlas.

Не делать новый arbitrary-point endpoint автоматически player-public.

GM/debug details могут содержать:
- pressure;
- q_v/q_c;
- climate diagnostics.

Future player endpoint будет фильтроваться CharacterKnowledge/Fog of War.

---

# 35. Region-area vs point weather

M1 обязана сохранять R1 semantics.

Click Region:
```text
RegionAreaWeatherState
```

Inspect arbitrary point:
```text
point sampler
```

Не подставлять Region mean weather в point inspection.

Не подставлять point weather как summary всего Region.

---

# 36. Map rendering must not drive physics

Никакие:
- zoom;
- pan;
- active layer;
- hidden layer;
- browser viewport

не должны менять solver state.

Map = visualization/controller only.

---

# 37. Climate raster semantics

Static layers:
- mean temperature = baseline climatology;
- elevation = World Data;
- biome = World Data/global atlas + appropriate visual source.

Не подписывать mean-temperature layer как `температура сейчас`.

Dynamic current weather layers будут отдельными future M1.5+ features.

---

# 38. Precipitation/Hazard/Habitability — NOT M1

В M1 только заложить panes/layer registry/API.

TODO after M1:

```text
M1.5 Climate Analytical Layers
- annual precipitation
- seasonal precipitation
- rain/snow climatology
- current precipitation
- hazard map
- habitability map
- settlement suitability
```

Не реализовывать их скрыто в M1.

---

# 39. Future city/settlement zoom readiness

M1 maxZoom и vector precision должны позволять future markers на масштабе:
- country;
- city;
- village;
- road;
- player.

Но сами entities не создаются.

---

# 40. Marker sizing architecture

Future map markers должны быть pixel/SVG-based, а не огромным geographic radius.

M1 Region edit handles уже должны следовать этому принципу.

Prepare CSS utility/class architecture:
- major marker;
- minor marker;
- edit handle;
- selected marker.

Не добавлять settlements.

---

# 41. Atmospheric resolution honesty

Leaflet может zoom намного глубже AtmosphericGrid.

Это нормально.

Не делать вид, что deep zoom увеличивает physical climate resolution.

Point sampler может интерполировать existing grid.

UI/debug может позже показывать atmospheric cell boundary/size, но это optional M1.

---

# 42. Base raster resolution honesty

Deep zoom existing raster может pixelate.

Это допустимо.

Не генерировать fictitious detail via AI/upscaling in M1.

Future:
- higher-resolution global map;
- regional maps;
- local city maps.

---

# 43. Fullscreen

Сохранить fullscreen behavior.

Use browser Fullscreen API / existing approach.

Leaflet must call:
```text
invalidateSize()
```
after entering/exiting fullscreen or container resize.

No stretched/blank tiles.

---

# 44. Responsive layout

Existing right-side Region form remains usable.

At reasonable desktop width:
- map dominates;
- form/inspector side panel visible.

On smaller widths:
- side panel can move below/overlay.

Do not redesign entire website during M1.

---

# 45. Loading/error UI

Map should handle:
- missing tile;
- unavailable climate layer;
- tile build not run;
- point-weather unavailable.

Clear GM-facing error:
```text
Слой карты недоступен
```

No silent blank map.

---

# 46. Graticule

Optional but recommended:

Leaflet vector graticule:
- latitude/longitude grid;
- labels depending on zoom.

If current raster already has baked coordinate grid, do not necessarily duplicate it.

Do not make M1 blocker.

---

# 47. Tile requests/performance

Do not load full high-resolution world raster into browser.

Leaflet requests viewport tiles only.

Inactive climate raster layers should not download their entire pyramid.

Performance baseline/report:
- initial page load;
- number/size of tile requests at default view;
- pan;
- z0→z8/10 zoom;
- layer switch.

---

# 48. Tile storage size

Report:
- source raster dimensions;
- native zoom;
- generated tile count;
- disk size per layer;
- total disk size.

Avoid unexpectedly committing multi-gigabyte generated directories without documenting.

If generated tiles should be build artifacts:
- add appropriate build instruction;
- decide repository/static deployment policy explicitly.

---

# 49. No hidden external map dependency

No OpenStreetMap/Google tiles.

Fardecosmia base map is project-owned custom raster.

Leaflet is only rendering engine.

---

# 50. JS architecture

Do not leave another monolithic 1000-line inline script in template if current code can reasonably be split.

Suggested modules/services:

```text
fardecosmia_crs.js
fardecosmia_map.js
region_contour_editor.js
map_layers.js
map_point_inspector.js
```

Names can differ.

Keep Django template responsible for:
- URLs;
- permission flags;
- initial JSON/config.

Keep mapping logic in static JS.

---

# 51. Server map config

Expose one serialized map config:

```text
planet circumference
world bounds
initial center
initial zoom
max zoom
native zoom per layer
tile URLs
current Campaign world_minutes
permission flags
existing Region geometry
active layer
```

Do not scatter dozens of data-* attributes if avoidable.

---

# 52. Security

All Region mutations remain POST + CSRF.

Point inspection is read-only.

Do not allow arbitrary file/tile path input from query params.

Validate contour:
- minimum vertices;
- valid coordinate ranges;
- finite numbers;
- bounded JSON size.

---

# 53. Accessibility/basic usability

Buttons have labels/tooltips.

Selected mode clearly visible:
- view;
- draw;
- edit;
- inspect.

Escape cancels current drawing/edit action where safe.

Keyboard focus should not be completely trapped by map.

---

# 54. Tests — CRS

Required:

1. lon/lat corners project correctly.
2. roundtrip `LatLng → pixel → LatLng`.
3. ±180 seam normalizes correctly.
4. no latitude wrap.
5. world aspect ratio 2:1.
6. 1° equatorial distance ≈ 201.39 km.
7. 90° arc ≈ 18 125 km.
8. 179E↔179W uses short 2° path.

---

# 55. Tests — contour conversion

1. old normalized contour → lat/lon → normalized roundtrip.
2. irregular Region.
3. seam-crossing Region.
4. polar Region.
5. server `polygon_center()` remains authoritative.
6. migrated Leaflet-created Region gets same center as old system within tolerance.
7. R1 area mask consumes saved contour correctly.

---

# 56. Tests — existing regions

Load all existing current Regions.

Assert:
- contour renders;
- center remains same;
- no geometry revision increment merely from viewing;
- no WeatherState mutation;
- no loss of history.

---

# 57. Tests — edit Region

After actual contour edit:
- save works;
- revision increments once;
- old history remains;
- current R1 semantics preserved;
- region climate auto fields recalc according to existing rules.

---

# 58. Tests — point inspection

1. arbitrary land point.
2. ocean point.
3. high mountain point.
4. seam point.
5. no Region at point.
6. static World Data returned.
7. atmosphere returned only when available.
8. GET doesn't mutate DB.
9. GET doesn't advance time.

---

# 59. Tests — layers

At minimum template/JS integration proves:
- one map instance;
- each current layer registered;
- switch preserves view;
- Region vectors stay on top;
- current light overlay aligns to bounds.

---

# 60. Browser/manual checks

If authenticated GM browser is available, verify screenshots at:

```text
whole world
mid zoom
deep zoom
seam crossing
fullscreen
Region draw mode
Region edit mode
temperature layer
elevation layer
biome layer
current-light layer
```

Do not change user password or production-like credentials.

If authenticated UI unavailable:
- use Django tests/static fixtures and report limitation.

---

# 61. Performance acceptance

M1 should feel interactive on current machine.

No strict GPU benchmark required, but report:

- default map initial render;
- z0→z8/10 interaction;
- layer switch;
- Region draw/edit responsiveness;
- tile generation time.

No full-world image decode for every zoom interaction.

---

# 62. Migration/data policy

Prefer:
```text
no destructive DB geometry migration in M1
```

Existing `map_polygon` stays compatible.

If a DB migration becomes necessary:
- explain why;
- preserve original contour;
- reversible migration;
- verify all existing Regions before/after.

---

# 63. Architecture result after M1

Desired:

```text
WORLD DATA RASTERS
        ↓
tile pyramid
        ↓
Leaflet custom Fardecosmia CRS
        ↓
layer registry
        ├── base
        ├── current light
        ├── mean temperature
        ├── elevation
        └── biomes

REGION CONTOURS
        ↓
lat/lon conversion service
        ↓
Leaflet vector layer/editor
        ↓
existing Django Region lifecycle + R1

ARBITRARY MAP POINT
        ↓
lat/lon
        ↓
World Data + optional point atmosphere
```

---

# 64. Future architecture that M1 must not block

After M1 we need to be able to add without replacing the map:

```text
M1.5 precipitation map
M1.5 hazard map
M1.5 habitability map

M2 countries
M2 cities/villages
M2 roads

Character markers
Fog of War
Travel routes
WorldEvent overlays
catastrophes
regional/local maps
```

---

# 65. Acceptance Criteria

M1 complete when:

1. Main campaign world map uses Leaflet.
2. No MapLibre.
3. No default Web Mercator.
4. Custom/equivalent equirectangular Fardecosmia CRS works.
5. Planet distance uses 72 500 km circumference.
6. ±180 wrap is correct.
7. Deep zoom >= 10 works.
8. Static base map is tiled.
9. Mean temp/elevation/biome current layers work as Leaflet layers.
10. Current-light visualization works inside Leaflet.
11. One map instance handles layer switching.
12. Existing Region contours render correctly.
13. Region contour drawing is Leaflet-based.
14. Existing Region contour editing works.
15. Vertices/handles stay small in screen pixels.
16. Existing Region storage/data survive.
17. Server remains authoritative for contour center/preview/save.
18. R1 Region-area weather semantics are preserved.
19. Region click can expose latest area summary/link.
20. Arbitrary GM point inspection works.
21. Point inspection does not mutate/advance simulation.
22. Fullscreen works.
23. Current tests continue passing.
24. New CRS/geometry/Leaflet tests pass.
25. Performance/report is acceptable.
26. M1.5/C5/Character/Travel/Countries/Cities not started.

---

# 66. M1 IMPLEMENTATION REPORT

After implementation stop and return:

```text
M1 LEAFLET PLANETARY ATLAS MIGRATION REPORT

1. Changed files
2. Frontend dependency strategy
3. Leaflet version/source strategy
4. Old map architecture summary
5. New map architecture
6. Fardecosmia CRS implementation
7. Projection/transformation
8. Planet radius/distance implementation
9. Longitude wrap behavior
10. Latitude/pole behavior
11. Base raster source dimensions
12. Tile pyramid algorithm
13. Native zoom per layer
14. maxZoom
15. Tile counts/disk size
16. Tile deployment/cache versioning
17. Current-light layer implementation
18. Mean-temperature layer
19. Elevation layer
20. Biome layer
21. Leaflet panes/z-order
22. Region normalized↔lat/lon conversion
23. Existing Region rendering
24. Region drawing UX
25. Region editing UX
26. Seam-crossing Region behavior
27. R1 revision/history behavior after edit
28. Region climate preview compatibility
29. Region area-weather integration
30. Arbitrary-point inspector
31. Point weather/static World Data behavior
32. Permission/security handling
33. Fullscreen/responsive behavior
34. Scale/cursor coordinates
35. Performance
36. Existing Region data verification
37. Tests added
38. Full test result
39. Browser/manual visual verification
40. Known approximations
41. Generated assets/build instructions
42. Future M1.5 compatibility
43. Future Countries/Settlements compatibility
44. Future Character/Fog compatibility
45. Future Travel compatibility
46. Confirmation C5/M1.5/M2/Character/Travel were not started
```

Stop after report.
