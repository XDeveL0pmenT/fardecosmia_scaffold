# ФАРДЕКОСМИЯ — PHASE C4
## Atmospheric Circulation & Terrain Dynamics
### Physical Coriolis, Pressure-Gradient Winds, Convergence, Orography & Route-Ready Sampling

> Перед началом прочитать:
> - `docs/FARDEKOSMIA_MASTER_ROADMAP.md` / актуальный Master Roadmap;
> - `docs/ARCHITECTURE_GUARDRAILS.md` / Future Architecture Guardrails;
> - актуальные документы C1–C3.5.
>
> Phase C4 реализует только атмосферную циркуляцию и взаимодействие с крупномасштабным рельефом.
> **Leaflet, Core Platform, Travel Engine, WorldEvent, катаклизмы и C5 НЕ начинать.**

---

# 0. Текущее состояние перед C4

Завершены:

- C1:
  - normalized 364-day stellar orbit;
  - non-equal seasons;
  - star-distance forcing;
  - local zenith/latitude forcing;
  - separate Ympha forcing.

- C2:
  - dynamic SST;
  - ocean thermal inertia;
  - air–sea sensible exchange;
  - evaporation;
  - prognostic `q_v`.

- C2.5:
  - accurate ocean/boundary fast-forward.

- C3:
  - prognostic `q_c`;
  - condensation;
  - cloud evaporation;
  - latent heating;
  - physical precipitation;
  - rain/snow;
  - orographic precipitation;
  - human-readable environment summary.

- C3.5:
  - fast-forward optimized;
  - Region climate autoconfiguration;
  - legacy region orbital response / volatility / precipitation bias isolated from AtmosphericGrid v5.

Current approximate performance baseline from C3.5:

```text
Season FF ≈ 0.482 s
Year FF   ≈ 1.911 s
```

Exact Vitok baseline should be re-measured immediately before implementation.

---

# 1. Главная цель C4

Сейчас ветер/давление уже существуют, но C4 должен превратить их в **пространственно организованную динамическую систему**, где:

```text
temperature / moisture / latent heating
        ↓
circulation pressure structure
        ↓
pressure-gradient acceleration
        ↓
wind
        ↓
Coriolis
        ↓
convergence / divergence / vorticity
        ↓
vertical-motion proxy
        ↓
clouds / precipitation
```

и одновременно:

```text
wind
+
terrain gradient
        ↓
orographic ascent / descent
        ↓
cooling / warming
        ↓
rain shadow
```

Не создавать hardcoded:
- `trade_wind_bonus`;
- `summer_wind_bonus`;
- `mountain_rain_penalty`;
- `storm_pressure_drop`;
- biome-specific wind directions.

---

# 2. Канонические физические параметры

Использовать:

```text
Planet circumference = 72 500 km
Rotation period       = 7.52 days
Gravity               ≈ 9.98 m/s²
```

Производный радиус:

```text
R = circumference / (2π)
```

примерно:

```text
R ≈ 11 539 km
```

Не hardcode Earth radius.

---

# 3. Направление вращения — всё ещё не канон

Физический период вращения известен:

```text
7.52 суток
```

Но словесная метка:

```text
prograde / retrograde
```

в каноне пока не закреплена.

Поэтому C4 должен изолировать знак вращения:

```python
rotation_direction_sign
```

или архитектурный эквивалент.

Default может соответствовать текущей coordinate convention проекта, но:

- явно назвать его technical working assumption;
- не размазывать знак по формулам;
- включить в fingerprint;
- смена знака должна требовать нового solver fingerprint/snapshot branch.

---

# 4. Angular velocity

Ввести единый helper/config:

```text
Ω = rotation_sign * 2π / rotation_period_seconds
```

Не использовать старый qualitative коэффициент вида:

```text
0.08 * sin(latitude)
```

как активный Coriolis.

---

# 5. Coriolis parameter

Для latitude `φ`:

```text
f = 2 Ω sin(φ)
```

В экваториальной зоне:

```text
f → 0
```

На противоположных полушариях знак меняется.

---

# 6. Интеграция Coriolis без искусственного разгона

Не использовать простой explicit Euler, если он создаёт energy growth.

Предпочтительно применять exact rotation step:

```text
u' = u cos(fΔt) + v sin(fΔt)
v' = v cos(fΔt) - u sin(fΔt)
```

с корректным знаком согласно принятой coordinate convention.

При действии только Coriolis:

```text
sqrt(u² + v²)
```

должно сохраняться с numerical tolerance.

---

# 7. Сферическая геометрия сетки

Все горизонтальные gradients/divergence/vorticity считать с реальными metric factors.

Для grid spacing:

```text
dx = R cos(φ) Δλ
dy = R Δφ
```

где углы в radians.

Longitude:
- periodic wrap.

Latitude:
- безопасное поведение у полюсов;
- no divide-by-zero;
- не использовать одинаковое физическое расстояние east-west на всех широтах.

---

# 8. Кэш геометрии

На grid resolution кешировать:

```text
latitude_rad
longitude_rad
sin_lat
cos_lat
coriolis_f
dx_m
dy_m
inverse_dx
inverse_dy
cell_area_m2
```

если нужно.

Не пересчитывать их каждый timestep.

---

# 9. Critical pressure problem: terrain must not create fake horizontal wind

Raw surface pressure над высокой горой естественно ниже, чем над низиной.

Нельзя использовать простой gradient:

```text
surface_pressure(high mountain)
vs
surface_pressure(lowland)
```

как horizontal pressure-gradient force на одном уровне.

Иначе рельеф будет создавать огромный ложный ветер только из-за высоты.

---

# 10. Separate displayed surface pressure from circulation pressure

C4 должен ввести явное разделение:

```text
circulation pressure / reduced pressure / sea-level-like pressure
```

и:

```text
local surface pressure
```

Горизонтальное ускорение ветра использует circulation/reduced pressure.

UI/WeatherState показывает local surface pressure.

Конкретное имя выбирается по архитектуре проекта.

---

# 11. Рекомендуемая pressure architecture

Предпочтительно:

```text
sea_level_pressure_pa
```

или:

```text
circulation_pressure_pa
```

как prognostic atmospheric field.

Локальное surface pressure выводить через hypsometric/barometric reduction с учётом:

- elevation;
- temperature;
- moisture/virtual temperature.

Если текущая архитектура предлагает эквивалентное более чистое решение — использовать его, но сохранить принцип разделения.

---

# 12. Atmosphere composition remains technical

Точный окончательный состав атмосферы Фардекосмии ещё не закреплён.

Поэтому, если нужен gas constant:

```text
R_d
```

использовать configurable technical default.

Не объявлять Earth dry-air value новым каноном мира.

Включить thermodynamic constant version/config в fingerprint.

---

# 13. Virtual temperature / density

Для pressure-gradient acceleration желательно использовать dynamic density:

```text
ρ = p / (R_d T_v)
```

с moisture-aware virtual temperature approximation.

Не использовать постоянное:

```text
rho_air = 1.2
```

для всего мира, если это можно безопасно заменить.

Если существующая 2D архитектура требует simpler approximation:
- isolating helper;
- document it.

---

# 14. Pressure-gradient acceleration

Для horizontal pressure field:

```text
a_x = -(1/ρ) ∂p/∂x
a_y = -(1/ρ) ∂p/∂y
```

Units:

```text
m/s²
```

Wind components:

```text
u = eastward
v = northward
```

или фактическая convention проекта — но convention должна быть явно документирована.

---

# 15. Direction test

Controlled pressure field:

```text
high pressure west
low pressure east
```

без Coriolis/drag должен ускорять воздух:

```text
from high toward low
```

Regression test обязателен.

---

# 16. Prognostic circulation pressure

C4 не должен каждый timestep полностью пересоздавать pressure pattern из статической формулы.

Circulation pressure должно обладать памятью.

Рекомендуемый conceptual update:

```text
1. advect circulation-pressure anomaly
2. relax toward thermodynamic pressure target
3. apply bounded diffusion/smoothing
4. use result for pressure-gradient force
```

Это позволит pressure systems:
- перемещаться;
- сохраняться;
- реагировать на T/q/latent heating.

---

# 17. Thermodynamic pressure target

Не hardcode seasonal lows/highs.

Thermodynamic target должен выводиться из atmospheric state.

Он может учитывать:

```text
temperature anomaly
virtual temperature / moisture
baseline climatology
```

Направление должно быть физически осмысленным:

```text
persistently warm/expanded column
→ tendency toward lower circulation pressure

cold/dense column
→ tendency toward higher circulation pressure
```

Точные coefficients остаются technical/configurable.

---

# 18. Preserve baseline climate

Static World Data mean-temperature map уже содержит climatology.

C4 работает с anomalies/dynamic state.

Не добавлять второй climatological equator-pole forcing поверх уже существующей карты без доказанной необходимости.

---

# 19. Latent heating integration

C3 уже меняет actual air temperature при condensation.

C4 не создаёт новый:

```text
latent_pressure_bonus
```

Влияние идёт естественно:

```text
condensation
→ latent heating
→ T / virtual temperature
→ circulation pressure target
→ pressure gradient
→ wind
```

---

# 20. Initial circulation pressure

При первом v6/C4 state:

- инициализировать из текущего atmospheric pressure state / baseline;
- по возможности сохранить continuity с C3.5;
- добавить small deterministic perturbations только если они уже нужны для запуска weather dynamics.

Не генерировать новое случайное pressure noise каждый timestep.

---

# 21. Seeded weather perturbations

Если текущий solver каждый шаг повторно добавляет seeded spatial pressure noise:

- провести audit;
- не позволять fixed noise навечно прибивать weather systems к одним координатам.

Предпочтительно:
- initial perturbation;
- либо очень медленный background forcing, если он действительно нужен.

Документировать окончательное поведение.

---

# 22. Momentum becomes prognostic

`wind_u` и `wind_v` после C4 — настоящие prognostic momentum-like fields.

Они должны:

- advect;
- получать pressure-gradient tendency;
- получать Coriolis;
- получать drag;
- получать terrain effects;
- сохраняться в snapshots.

Не пересоздавать весь wind field с нуля из pressure gradient каждый step.

---

# 23. Wind advection

Переиспользовать vectorized semi-Lagrangian infrastructure.

Advect:

```text
u
v
```

без Python loop per cell.

Если текущая vector advection требует component handling на sphere:
- документировать approximation;
- no artificial longitude discontinuity.

---

# 24. Surface drag

Без drag pressure gradients могут бесконечно ускорять single-layer wind.

Ввести physically interpretable damping.

Допустим:

```text
du/dt = ... - u/τ_drag
dv/dt = ... - v/τ_drag
```

или stable quadratic bulk drag.

C4 не делает полноценную biome roughness — это C5.

Можно иметь только coarse:
- ocean drag;
- land drag.

Оба technical/configurable.

---

# 25. Stable drag integration

Для Rayleigh drag предпочтительно:

```text
u *= exp(-Δt/τ)
v *= exp(-Δt/τ)
```

чтобы timestep не создавал instability.

---

# 26. Wind caps are only emergency safeguards

Не использовать:

```text
wind = min(wind, 80 m/s)
```

как главный climate regulator.

Разумные скорости должны возникать из:

- pressure gradient;
- Coriolis;
- drag;
- advection;
- terrain.

Absolute cap может остаться только numerical safety.

Benchmark обязан показывать:
- median wind;
- p90;
- p95;
- p99;
- maximum;
- number of cap hits.

---

# 27. Convergence / divergence

Добавить spherical divergence diagnostic:

```text
∇·V
```

с корректной spherical metric.

Convention:

```text
divergence > 0 → расходящийся поток
divergence < 0 → convergence
```

Units:

```text
s⁻¹
```

---

# 28. Relative vorticity

Добавить diagnostic:

```text
ζ
```

(relative vertical vorticity)

с корректной spherical metric.

Это потребуется:
- для анализа circulation;
- будущих cyclones;
- severe-weather detection;
- GM diagnostics.

Не превращать `ζ` в новый hardcoded storm switch в C4.

---

# 29. Future-ready absolute vorticity

Можно diagnostic:

```text
η = f + ζ
```

если дёшево.

Не обязательно хранить в snapshot, если выводится из state.

---

# 30. Dynamic vertical-motion proxy

Поскольку atmosphere всё ещё 2D single-layer, полноценной vertical velocity нет.

C4 должен ввести общий диагностический proxy:

```text
vertical_motion_proxy
```

или физически понятный эквивалент.

Он объединяет:

```text
convergence ascent
+
orographic ascent/descent
```

без притворства, что это resolved 3D velocity.

---

# 31. Convergence ascent proxy

Например:

```text
w_conv ≈ -H_eff * divergence
```

где:

```text
H_eff
```

— configurable effective boundary-layer/mixing depth.

Positive `w_conv` = ascent.

Это approximation, не канон.

---

# 32. Elevation gradients

Из static elevation map precompute:

```text
∂h/∂x
∂h/∂y
```

в physical slope units.

Использовать spherical grid metrics.

Кешировать.

---

# 33. Orographic vertical velocity

Физически мотивированный proxy:

```text
w_orographic =
    u ∂h/∂x
    +
    v ∂h/∂y
```

Units:

```text
m/s
```

Interpretation:

```text
>0  upslope ascent
<0  lee-side descent
```

---

# 34. Terrain resolution honesty

Atmospheric grid 180×90 имеет огромные cells.

На Фардекосмии 2° соответствует сотням километров.

Поэтому C4 terrain dynamics — это:

> крупномасштабная орография материков/горных дуг,

а НЕ valley wind around individual mountain.

Не создавать UI/lore claims о локальных склонах, которых grid не разрешает.

---

# 35. Orographic cooling / lee warming

Заменить старый arbitrary orographic precipitation trigger на единый physically linked mechanism.

При ascent:

```text
adiabatic cooling proxy
```

При descent:

```text
adiabatic warming proxy
```

с configurable effective lapse rate / vertical coupling.

После изменения T обычная C3 saturation adjustment сама создаёт/испаряет `q_c`.

---

# 36. No double-count C3 orography

Найти старую C3 orographic cooling/condensation logic.

После C4 должен существовать один active source of orographic vertical forcing.

Не оставить одновременно:

```text
old rain-shadow bonus
+
new w_orographic
```

---

# 37. Terrain blocking / deflection

Рельеф должен ослаблять поток, пытающийся пересечь крупный крутой подъём.

Но не делать mountain cells непроходимыми стенами.

Допустимо использовать:

```text
upslope component damping
terrain ruggedness drag
```

с smooth bounded response.

---

# 38. Terrain drag cannot depend on biome yet

C4:
- elevation/slope/ruggedness;
- land/ocean coarse drag.

C5 позже:
- forests;
- grasslands;
- deserts;
- biome roughness;
- vegetation.

Не hardcode biome wind penalties сейчас.

---

# 39. Combined vertical forcing

C3 microphysics должна получать:

```text
w_total_proxy =
    w_convergence
    +
    w_orographic
```

или эквивалент.

Это влияет через:
- cooling/warming;
- saturation;
- condensation;
- cloud evaporation.

Не напрямую:
```text
w > threshold → rain
```

Осадки всё равно происходят из `q_c`.

---

# 40. Rain shadow acceptance

Controlled test:

```text
warm/moist ocean
→ wind
→ mountain belt
→ inland lee side
```

Expected after enough steps:

- windward ascent > lee;
- windward q_c/precip higher;
- air loses water crossing mountains;
- lee RH/q_v lower;
- lee precipitation lower;
- possible lee warming.

Без biome precipitation modifier.

---

# 41. Large-scale circulation must emerge, not be painted

Не задавать вручную:

```text
equator easterlies
midlatitude westerlies
polar easterlies
```

как полосы.

Поскольку Фардекосмия вращается гораздо медленнее Земли, circulation structure может заметно отличаться.

Пусть модель выводит flow из:
- thermal gradients;
- pressure;
- rotation;
- drag;
- terrain.

---

# 42. Weak-rotation expectations

C4 documentation/debug benchmark должен отметить:

- 7.52-day rotation gives much weaker Coriolis than Earth;
- broad planetary-scale circulation is therefore expected;
- tight Earth-like small-scale geostrophic structures should not be forced artificially.

Это physical expectation, не hardcoded target map.

---

# 43. Equatorial behavior

Near equator:

```text
f ≈ 0
```

Pressure-gradient flow не должен получать artificial strong Coriolis deflection.

Test:
- same gradient at equator vs midlatitude;
- midlatitude deflection stronger.

---

# 44. Hemisphere sign test

При одинаковой initial wind и |latitude|:

```text
north
south
```

Coriolis deflection должна иметь противоположный знак.

Тест не должен зависеть от словесного prograde/retrograde label — только от configured `rotation_sign`.

---

# 45. Geostrophic-like balance diagnostic

Не требовать идеальной Earth-like geostrophy.

Но controlled midlatitude test может подтвердить, что при постоянном gradient + Coriolis + drag wind со временем начинает получать cross/isobaric balance вместо бесконечного acceleration.

---

# 46. Pressure systems should move

Создать controlled low/high pressure anomaly.

С wind advection enabled:
- anomaly должна переноситься;
- не быть навсегда зафиксированной на seed coordinates;
- diffusion/relaxation не должны уничтожать её мгновенно.

---

# 47. Coupling with ocean

C2 SST остаётся медленным source of thermal contrast.

C4 не меняет ocean heat equation без необходимости.

Но atmospheric circulation должна позволять:

```text
hot central ocean
→ warm/moist pressure pattern
→ winds
→ moisture transport onto continents
```

Это один из ключевых acceptance scenarios Фардекосмии.

---

# 48. Polar cold-air outbreaks

Без hardcoded random event.

Если pressure/temperature structure создаёт flow из холодной high-latitude области в более тёплые широты:

- cold air должен advect;
- human summary должен отражать реально получившееся похолодание;
- future severe-weather system сможет использовать это later.

---

# 49. No cyclone engine yet

C4 может создавать:
- lows;
- rotating flow;
- convergence;
- vorticity.

Но НЕ добавлять:
- tropical cyclone entity;
- hurricane category;
- eyewall;
- storm track DB model.

Это C6/WorldEvent future work.

---

# 50. Existing STORM label

C3 diagnostic `STORM` можно дополнительно использовать:
- wind;
- precipitation;
- pressure;
- convergence;
- vorticity

как derived evidence.

Но STORM label:
- не создаёт pressure;
- не создаёт wind;
- не создаёт precipitation.

---

# 51. Environment summary

Human-readable conditions остаются derived-only.

После C4 проверить, что:
- wind labels;
- storm wording;
- pressure wording;
- lethal heat/cold

по-прежнему основаны на scientific sampled state.

Не менять solver из-за текста UI.

---

# 52. Coordinate-based sampling — future Travel/Leaflet requirement

C4 обязан проверить/создать service-level sampling, не зависящий от Region ORM.

Нужен architectural equivalent:

```python
sample_environment_at(
    grid_or_state,
    latitude,
    longitude,
)
```

и удобный campaign-level wrapper, если он уже естественно вписывается.

Region sampling должен использовать тот же core helper.

---

# 53. Sampling must not require Region row

Обязательный test:

```text
lat/lon point with no Region in DB
→ atmosphere can still be sampled
```

Это потребуется будущим:
- Leaflet cursor inspection;
- Travel route sampling;
- hazards along route.

---

# 54. Sampling performance

Sampling одной точки:
- no ORM scan over Regions;
- no full-grid recomputation;
- no simulation advance.

Только:
- locate/interpolate cell;
- derive diagnostics.

---

# 55. Interpolation

Если текущий Region sampling всё ещё nearest-cell:

C4 может улучшить до bilinear interpolation для continuous fields:

- temperature;
- pressure;
- u/v;
- q_v/q_c;
- cloud;
- precipitation.

Discrete:
- biome/surface
используют World Data, не атмосферную bilinear interpolation.

Если изменение слишком рискованно — оставить nearest в C4, но sampler API должен позволять улучшить это позже.

В отчёте указать решение.

---

# 56. Leaflet compatibility

C4 НЕ реализует Leaflet.

Но grid outputs должны оставаться отделены от renderer.

Не добавлять climate logic в JavaScript current map.

Future climate layers должны быть возможны как:

```text
grid
→ raster/tile/API overlay
```

---

# 57. Fast-forward boundary atmosphere

C3.5 boundary solver должен получить те же ключевые circulation processes:

- prognostic wind;
- physical Coriolis;
- pressure-gradient force;
- drag;
- circulation pressure;
- coarse terrain coupling;
- divergence/convergence;
- q_v/q_c microphysics.

Не обязательно вычислять все diagnostics every boundary step, если они не влияют на state.

---

# 58. Boundary terrain

24×12 terrain очень грубый.

Использовать appropriately downsampled:
- elevation;
- slope/ruggedness.

Не брать full-resolution terrain gradients внутри каждой boundary step, если это разрушает performance.

---

# 59. Fast-forward accuracy after C4

На reduced test grid сравнить exact vs FF для:

```text
Season
Year
```

Минимум:

- SST MAE;
- T MAE;
- pressure MAE;
- wind vector MAE;
- q_v MAE;
- q_c MAE;
- precipitation integrated mass error.

Не требовать bit-identical.

---

# 60. Performance targets

До C4:

```text
Season FF ≈ 0.482 s
Year FF   ≈ 1.911 s
```

После C4 желательные цели:

```text
1 Vitok exact <= 1.0 s
Season FF     <= 1.5 s
Year FF       <= 2.5 s
```

Hard warning:

```text
Year FF > 3.0 s
```

требует profiler и объяснения.

Не упрощать physics автоматически, если цель немного превышена.

---

# 61. Snapshot changes

C4 вероятно добавит/переопределит pressure state.

Если меняется persisted grid state:

- bump snapshot format if payload layout changes;
- bump solver version;
- bump circulation model version;
- fingerprint includes rotation period/sign and circulation parameters.

Старые snapshots:
- не удалять;
- не принимать как current без compatibility.

---

# 62. Suggested versions

Если текущие:

```text
format 3
solver 5
FATM3
```

и payload меняется:

предпочтительно перейти на следующее versioned state, например:

```text
format 4
solver 6
FATM4
```

но Codex должен использовать фактически следующий корректный version scheme проекта.

---

# 63. GM diagnostics

Добавить/обновить:

```text
circulation/reduced pressure
surface pressure
pressure anomaly
pressure-gradient acceleration
Coriolis f
Coriolis acceleration / tendency
wind u/v/speed/direction
divergence
convergence
relative vorticity
absolute vorticity if implemented
w_orographic proxy
w_convergence proxy
total vertical-motion proxy
terrain slope/ruggedness
drag tendency
```

Не перегружать обычный player UI.

---

# 64. Optional circulation overlays

Если текущая GM-карта легко поддерживает debug overlay без frontend refactor, можно добавить:

- pressure;
- wind;
- convergence;
- vorticity.

Но это **не acceptance blocker**.

Не делать Leaflet migration внутри C4.

---

# 65. Tests — spherical metrics

Добавить:

1. east-west cell distance decreases with `cos(latitude)`;
2. longitude wraps;
3. gradients finite near poles;
4. divergence/vorticity finite;
5. world radius derives from 72 500 km circumference.

---

# 66. Tests — Coriolis

1. equator `f≈0`;
2. |f| increases toward poles;
3. hemisphere sign flips;
4. changing `rotation_sign` flips deflection;
5. pure Coriolis preserves wind speed;
6. 7.52-day period is actual source of Ω.

---

# 67. Tests — pressure gradient

1. uniform reduced pressure → no pressure acceleration;
2. high→low acceleration direction correct;
3. local elevation difference alone does NOT generate fake circulation pressure gradient;
4. surface pressure still decreases with elevation.

---

# 68. Tests — prognostic wind

1. wind persists between steps;
2. wind advects;
3. pressure gradient accelerates it;
4. drag damps it;
5. without pressure/Coriolis/drag it follows pure advection;
6. deterministic resume from snapshot.

---

# 69. Tests — convergence/vorticity

Controlled vector fields:

- uniform translation → divergence≈0, vorticity≈0;
- converging field → divergence<0;
- diverging field → divergence>0;
- rotational field → expected vorticity sign.

---

# 70. Tests — terrain

1. flat terrain → w_orographic≈0;
2. upslope flow → positive ascent;
3. downslope flow → negative;
4. cross-mountain component damped reasonably;
5. no heat/moisture created from terrain alone;
6. longitude seam terrain gradient safe.

---

# 71. Tests — rain shadow

Controlled multi-step experiment:

```text
ocean source
→ moist flow
→ mountain ridge
→ lee side
```

Assert statistically:

- windward precipitation > lee;
- windward condensation > lee;
- downwind vapor reduced;
- no biome precipitation modifier required.

---

# 72. Tests — latent circulation feedback

Controlled moist condensation zone:

- condensation warms air;
- thermodynamic pressure target responds;
- resulting pressure gradient changes wind;
- no explicit storm bonus used.

Do not require explosive cyclone formation.

---

# 73. Tests — arbitrary coordinate sampling

1. sample point with Region row;
2. sample same coordinates without Region row;
3. atmospheric values match core sampler;
4. sampling does not mutate DB;
5. sampling does not advance world time;
6. sampling is deterministic.

---

# 74. Long-run benchmark

At least:

```text
2 canonical years
```

on reduced grid.

Check:

- no NaN/Inf;
- pressure bounded;
- wind bounded by dynamics, not constant cap;
- q_v/q_c bounded;
- SST bounded;
- no permanent runaway vortex;
- no permanent checkerboard pressure noise;
- emergency wind caps rare/zero;
- emergency pressure clamps rare/zero;
- deterministic payload.

---

# 75. Statistics to report

For long-run:

```text
temperature min/max/mean
surface pressure min/max/mean
circulation pressure min/max/mean
wind median/p90/p95/p99/max
divergence min/max
vorticity min/max
q_v max
q_c max
annual precipitation
wind-cap hits
pressure-cap hits
supersaturation emergency hits
```

---

# 76. Visual sanity checks

Codex cannot always access authenticated GM UI.

Therefore add deterministic scripts/exports if useful to inspect:

- global wind arrows/downsampled vectors;
- pressure map;
- convergence map;
- vorticity map.

Could save debug PNGs locally in project `docs/debug/` or temp benchmark outputs if project convention allows.

Do not make these production assets.

---

# 77. Architecture boundaries

C4 must NOT create:

- Countries;
- Settlements;
- Roads;
- Character;
- Travel;
- WorldEvent;
- AuditLog;
- ApprovalRequest;
- Leaflet map.

But C4 services must remain compatible with them.

---

# 78. Future WorldEvent hook

Do not implement event engine.

But if circulation forcing service is refactored, leave a clean future point where external forcing can later contribute:

```text
temperature tendency
pressure tendency
wind tendency
moisture tendency
```

without rewriting the solver core.

No actual database-backed WorldEvent logic now.

---

# 79. Future catastrophe readiness

C4 diagnostics should make it possible later to detect:

- strong low pressure;
- convergence;
- vorticity;
- extreme wind;
- intense precipitation.

Do not yet convert those into catastrophe records.

---

# 80. Acceptance Criteria

C4 готова, если:

1. old qualitative Coriolis is no longer active source of truth.
2. Ω derives from 7.52-day rotation.
3. rotation sign is isolated/configurable.
4. spherical grid metrics are used.
5. wind pressure force uses reduced/circulation pressure, not raw elevation-biased surface pressure.
6. local surface pressure remains physically lower at elevation.
7. circulation pressure is prognostic/persistent.
8. u/v are prognostic and advected.
9. physical Coriolis acts on wind.
10. drag prevents uncontrolled acceleration.
11. convergence/divergence are physically derived diagnostics.
12. vorticity is derived.
13. orographic vertical forcing uses terrain gradient and wind.
14. convergence contributes to ascent proxy.
15. C3 q_v/q_c microphysics uses the new vertical-motion pathway without double-counting old orography.
16. rain shadow emerges without biome precipitation bias.
17. central hot ocean can drive organized moist transport.
18. no hardcoded Earth wind belts are painted.
19. no full cyclone/catastrophe system is started.
20. arbitrary lat/lon atmosphere sampling works without Region ORM.
21. future Leaflet can consume climate state without frontend physics rewrite.
22. C1–C3.5 regression tests pass.
23. exact and FF remain deterministic.
24. long-run stable.
25. performance benchmark documented.
26. snapshot/version compatibility handled.
27. Phase C5, Leaflet M1, Core Platform and catastrophes NOT started.

---

# 81. PHASE C4 IMPLEMENTATION REPORT

После реализации остановиться и вернуть:

```text
PHASE C4 IMPLEMENTATION REPORT

1. Changed files
2. New/changed models
3. Migrations
4. Previous wind/pressure architecture
5. Grid coordinate/vector convention
6. Planet-radius/world-geometry implementation
7. Rotation period/sign implementation
8. Coriolis formula/integration
9. Spherical metric implementation
10. Surface-pressure vs circulation-pressure separation
11. Circulation pressure state/storage
12. Pressure initialization/migration
13. Thermodynamic pressure target
14. Air-density/virtual-temperature handling
15. Pressure-gradient acceleration
16. Wind advection
17. Surface drag
18. Terrain slope/ruggedness
19. Orographic vertical-motion formula
20. Convergence/divergence
21. Vorticity
22. Convergence vertical-motion proxy
23. Combined vertical forcing
24. C3 microphysics/orography integration
25. Rain-shadow result
26. Hot-ocean circulation result
27. Polar-air transport result
28. Arbitrary coordinate sampling API
29. Region sampling compatibility
30. Fast-forward circulation integration
31. Fast-forward accuracy
32. Snapshot/solver/fingerprint versions
33. GM diagnostics
34. Performance before/after
35. Wind statistics
36. Pressure statistics
37. Numerical clamp statistics
38. Long-run stability
39. Tests added
40. Full test result
41. Known approximations
42. Future Leaflet/Travel/WorldEvent compatibility
43. Explicit confirmation that C5/M1/Core/Catastrophes were not started
```
