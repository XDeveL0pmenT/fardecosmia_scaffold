# M1 LEAFLET PLANETARY ATLAS MIGRATION REPORT

## 1. Changed files

- Добавлены серверные модули `world/services/atlas.py` и `world/services/map_inspection.py`.
- Расширены `world/services/map_geometry.py` и `world/services/atmosphere/persistence.py`.
- Добавлена команда `world/management/commands/build_planet_tiles.py`.
- Изменены `world/views.py`, `world/urls.py`, `world/forms.py`.
- Полностью заменён картографический UI в `world/templates/world/world_map.html` и `world/templates/world/global_world_map.html`; добавлен общий partial `world/templates/world/_atlas_stage.html`.
- Добавлены ES-модули `static/js/atlas/fardecosmia_crs.js`, `fardecosmia_map.js`, `map_layers.js`, `map_point_inspector.js`, `region_contour_editor.js`.
- Изменены `static/css/app.css`, `templates/base.html` и `.gitignore`.
- Добавлены локальный Leaflet 1.9.4 с лицензией в `static/vendor/leaflet/1.9.4/`, тайловый manifest и новые M1 regression tests.
- Django models и migrations в M1 не менялись.

## 2. Frontend dependency strategy

Новый bundler и frontend framework не добавлялись. Карта остаётся server-rendered Django-страницей, а картографическая логика разделена на нативные ES-модули. Runtime не зависит от CDN или внешних картографических серверов.

## 3. Leaflet version/source strategy

Используется стабильный Leaflet 1.9.4 из официального release archive. JS, CSS, изображения controls, source maps и LICENSE хранятся локально в `static/vendor/leaflet/1.9.4/`.

## 4. Old map architecture summary

Прежняя карта была единым SVG/image canvas с большим inline-script, ручным масштабированием изображения и SVG-слоями. Она загружала цельные растры, смешивала navigation, drawing, climate tooltip и layer painting в шаблоне и плохо расширялась для глубокого zoom и будущих сущностей.

## 5. New map architecture

На странице создаётся ровно один `L.Map`. Сервер передаёт один JSON contract. Layer registry переключает raster/GridLayer слои без пересоздания карты; Region остаются отдельным vector layer; editing, point inspection и CRS вынесены в отдельные модули.

## 6. Fardecosmia CRS implementation

`createFardecosmiaCRS()` расширяет `L.CRS.EPSG4326`, использует `L.Projection.LonLat`, горизонтальный `wrapLng=[-180, 180]` и не задаёт latitude wrap.

## 7. Projection/transformation

Equirectangular extent равен 360°×180°. В zoom 0 мир занимает 512×256 px: −180°/90° соответствует (0, 0), +180°/−90° соответствует (512, 256). Каждый zoom удваивает обе размерности.

## 8. Planet radius/distance implementation

Окружность — 72 500 км. Радиус всегда выводится как `72500 / (2π) = 11538.733... км`. Leaflet scale control и backend helper используют spherical haversine с этим радиусом; Earth radius не используется.

## 9. Longitude wrap behavior

Карта допускает горизонтальные copies. UI и point inspector нормализуют longitude в `[-180, 180)`. Контуры около шва предварительно unwrap-ятся по короткой дуге и отображаются в ближайшей к viewport копии. В браузере подтверждён pan через шов без tile errors.

## 10. Latitude/pole behavior

Latitude ограничена диапазоном `[-90, 90]`, не wrap-ится и остаётся верхней/нижней границей. Backend отклоняет значения за полюсами; карта ограничивает вертикальный pan через `maxBounds`.

## 11. Base raster source dimensions

- Base: 7096×3548, точный 2:1.
- Mean temperature: 1774×1150; world extent явно задан crop `[0, 0, 1774, 887]`, потому что нижние 263 px — интерфейсная легенда, а не география.
- Elevation: 1798×875, близкий к 2:1 авторский raster, resample без crop береговой линии.
- Biome data: sparse 360×180 `GlobalWorldMapLayer.biome_cells`.

## 12. Tile pyramid algorithm

Команда проверяет source и допустимый 2:1 aspect, выбирает ближайший разумный native zoom, resample-ит world extent на точный equirectangular canvas и строит только уровни z0..native. Размер tile — 256×256. Raster downsample использует Lanczos; discrete biome — nearest neighbour с alpha.

## 13. Native zoom per layer

- Base: z4, canvas 8192×4096.
- Mean temperature: z2, canvas 2048×1024.
- Elevation: z2, canvas 2048×1024.
- Biomes: z0, canvas 512×256.

## 14. maxZoom

UI maxZoom равен 10. Выше native zoom Leaflet увеличивает существующие tiles через `maxNativeZoom`; фиктивная raster detail не генерируется, а vector geometry сохраняет точность.

## 15. Tile counts/disk size

Повторная детерминированная сборка:

| Layer | Tiles | Bytes |
|---|---:|---:|
| Base | 682 | 4 225 032 |
| Mean temperature | 42 | 668 088 |
| Elevation | 42 | 458 892 |
| Biomes | 2 | 12 427 |
| Total | 768 | 5 364 439 |

## 16. Tile deployment/cache versioning

Каждый слой получает SHA-256-derived 16-character version directory. Общий manifest version — `3d0e54332e77b2e6`; повторная сборка дала тот же digest и байтовые размеры. URL содержит layer version. `static/atlas/tiles/` отмечен как build artifact в `.gitignore`; manifest сохраняется в проекте. Старые version directories команда автоматически не удаляет.

## 17. Current-light layer implementation

Физика света остаётся backend-only. `build_light_bands()` и `celestial_positions()` вычисляются по текущей campaign minute, JSON передаёт уже готовые opacity bands и longitudes. Frontend рисует Star, darkness и Ympha в отдельных Canvas GridLayers и vector markers.

## 18. Mean-temperature layer

Это tiled baseline climatology, явно подписанная как средняя, а не текущая температура. Hover берёт дешёвый sample из 360×180 static JSON; точная GM inspection выполняется сервером.

## 19. Elevation layer

Используется отдельный tiled author raster. Hover показывает authored grid value; read-only point inspector вызывает `WorldData.elevation_at()`, включая существующую bilinear semantics непрерывного physical elevation.

## 20. Biome layer

Global biomes собраны в прозрачный tiled layer. Campaign override остаётся отдельным динамическим GridLayer поверх global atlas. Редактор меняет только campaign sparse override и по-прежнему запрещает painting вне land mask.

## 21. Leaflet panes/z-order

Созданы panes: `baseRaster`, `staticClimate`, `campaignOverrides`, три dynamic-light panes, `regionFills`, `regionBorders`, `featureMarkers`, `labels`, `editHandles`, `gmDebug`. Они оставляют явные точки расширения для будущих overlays, но M1.5-сущности не добавлены.

## 22. Region normalized↔lat/lon conversion

Backend conversion централизован в `world/services/map_geometry.py`; frontend conversion — в `fardecosmia_crs.js`. Storage остаётся прежним `[[x, y], ...]` в диапазоне 0..1. Renderer работает с `[lat, lon]`; POST снова конвертирует contour в normalized storage.

## 23. Existing Region rendering

Все Region с `map_polygon` сериализуются как Leaflet vectors. В normal mode есть тонкая граница, прозрачная заливка, hover tooltip и popup/link. Карта не создаёт WeatherState и не меняет Region при GET.

## 24. Region drawing UX

Отдельный draw mode: click добавляет вершину, первая вершина визуально выделена, есть explicit finish, click первой вершины, undo, clear и Escape/cancel. Обычный pan/view не создаёт contour.

## 25. Region editing UX

Кнопка существующего Region переводит его contour в edit mode. Draggable `L.divIcon` handles имеют постоянные 14×14 screen pixels, видны только при edit и не растут с world zoom. После браузерной проверки исправлена область поиска sidebar-кнопок.

## 26. Seam-crossing Region behavior

Longitudes contour unwrap-ятся относительно предыдущей вершины, затем весь ring сдвигается на ближайшую display copy к center longitude. При сохранении каждая точка снова канонизируется. Regression test проверяет short-arc ring 179E↔179W.

## 27. R1 revision/history behavior after edit

M1 не обходит `Region.save()`. Реальное geometry edit увеличивает `weather_geometry_revision` один раз; старая WeatherState history остаётся. Viewing не увеличивает revision и не создаёт погоду. Это покрыто regression test.

## 28. Region climate preview compatibility

Сохранён flow `Leaflet contour → normalized JSON → region_climate_preview → server polygon_center → region_climate_at → advisory form values`. На create/place сервер повторно валидирует geometry, вычисляет center и применяет World Data независимо от preview.

## 29. Region area-weather integration

Region popup использует только уже persisted `RegionAreaWeatherState`: human-readable summary, snapshot minute, age, stale flag, sampling mode и link. Click не запускает area aggregation. Arbitrary point inspector не подменяет area weather point sample-ом.

## 30. Arbitrary-point inspector

GM включает отдельный inspect mode и кликает произвольную точку. Карточка показывает координаты, surface, elevation, biome, baseline temperature/humidity и, если есть совместимый snapshot, текущую C4 atmosphere.

## 31. Point weather/static World Data behavior

`inspect_map_point()` всегда возвращает static World Data. Atmosphere добавляется только через compatible fingerprint/version snapshot; иначе `weather_available=false`. Возвращаются T, RH из q_v/T/p, физически согласованные pressure, u/v и speed wind, clouds, current precipitation rate, rain/snow fractions и snapshot age.

## 32. Permission/security handling

Обе atlas pages и inspect endpoints требуют authentication и GM membership. Point endpoints принимают только GET. Region/layer mutations остаются POST+CSRF. Контуры ограничены 64 KiB и 512 вершинами, layer JSON — 4 MiB; диапазоны и finite values повторно валидируются сервером. Query params не участвуют в file paths.

## 33. Fullscreen/responsive behavior

Fullscreen API сохраняет map instance и вызывает `invalidateSize()` при fullscreen change и ResizeObserver. Проверены enter/exit. При ширине 800 px карта переходит в одноколоночную раскладку, остаётся pan/zoom-able, а sidebar уходит ниже.

## 34. Scale/cursor coordinates

Стандартный Leaflet metric-only scale использует переопределённый Fardecosmia distance. Cursor показывает decimal N/S/E/W и всегда нормализует longitude. Отдельно выводится zoom level z0..z10.

## 35. Performance

- Tile build: 19.814 s первый run; 21.303 s повторный deterministic run.
- Локальный browser wall time до `load`: 312 ms; через 700 ms видимы 8 viewport tiles.
- Первое переключение mean-temperature/elevation/biome: 329/321/328 ms соответственно, включая browser-control overhead и tile decode.
- Девять последовательных zoom interactions z1→z10 + 350 ms settle: 3.075 s; в viewport оставалось 8 loaded tiles.
- Pan, drawing и handles воспринимаются интерактивно; console warnings/errors и tile errors отсутствовали.
- Каждый zoom/layer загружает только viewport tiles; full source raster в браузер не передаётся.

## 36. Existing Region data verification

После M1 в development DB остаются те же 9 Region с IDs 15..23. Все имеют прежний `weather_geometry_revision=0`; браузерные view/draw-cancel/edit-cancel проверки ничего не сохранили. В DB сохранились 21 712 WeatherState и 5 303 RegionAreaWeatherState. Geometry/data migration не выполнялась.

## 37. Tests added

Добавлены проверки CRS corners, 512×256 geometry, lat/lon↔pixel roundtrip, longitude seam, no pole wrap, canonical distance, irregular/polar contours, server center, manifest/aspect/native zoom, literal Leaflet tile placeholders, JSON size limits, single map contract, existing Region non-mutation, edit revision/history, GM permissions, static inspector, land/ocean/high mountain/seam samples, compatible atmosphere и read-only behavior.

## 38. Full test result

`python manage.py test --verbosity 1`: **223 tests passed** за 44.485 s. `python manage.py check`: 0 issues. `makemigrations --check --dry-run`: no changes. Все пять ES-модулей прошли `node --check` встроенным workspace runtime.

## 39. Browser/manual visual verification

В authenticated local GM session проверены whole world, temperature, elevation, biome, current light, arbitrary point with live C4 data, z10, horizontal pan/wrap, fullscreen, draw mode (3 handles + finish), Escape cancel, existing Region edit (5 handles), desktop и 800 px responsive layout. После каждого исправления страница была перезагружена; console errors/warnings отсутствуют. Временный test GM и membership удалены.

## 40. Known approximations

- Deep zoom выше native resolution увеличивает raster pixels и не добавляет географическую detail.
- Elevation source слегка отклоняется от 2:1 и resample-ится на точный canvas без crop.
- Light overlay имеет 360 backend-derived longitudinal bands; это визуализация текущей модели, не новый solver.
- Hover static layers использует дешёвую cell lookup; inspector является источником подробного point sample.
- Graticule отдельно не добавлена: исходные authored rasters уже содержат координатную сетку, а пункт M1 был optional.
- Global biome tile нужно пересобирать после осознанного изменения global atlas; campaign override показывается сразу без rebuild.

## 41. Generated assets/build instructions

Запуск: `python manage.py build_planet_tiles`. Команда пишет `static/atlas/manifest.json` и versioned artifacts в `static/atlas/tiles/`. Для deployment tiles должны быть собраны до `collectstatic`/публикации static. Каталог tiles не предназначен для commit; manifest, builder, source assets и инструкция входят в проект.

## 42. Future M1.5 compatibility

Layer registry и panes готовы принять precipitation/hazard/habitability GridLayer/TileLayer без замены map/CRS. Ни один такой analytical layer в M1 не реализован.

## 43. Future Countries/Settlements compatibility

`featureMarkers`/`labels` panes, z10 и pixel-sized marker architecture позволяют позже добавить countries, cities, villages и roads как vector/data layers. Эти модели и UI не создавались.

## 44. Future Character/Fog compatibility

Permission flags и отдельные panes позволяют в будущем добавить filtered player layers и Fog of War. Текущий atlas остаётся GM-only и не раскрывает objective data игрокам.

## 45. Future Travel compatibility

Backend `planetary_distance_km()` уже использует canonical Fardecosmia circumference и short longitude arc, поэтому может быть повторно использован Travel Engine. Routes/pathfinding не реализованы.

## 46. Scope confirmation

C5, M1.5, M2, Countries, Settlements, Character/Fog of War, Travel Engine, WorldEvent overlays и catastrophes не начинались.
