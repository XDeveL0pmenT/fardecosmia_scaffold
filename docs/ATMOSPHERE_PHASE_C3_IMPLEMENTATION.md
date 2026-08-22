# PHASE C3 IMPLEMENTATION REPORT

Контрольный замер: 2026-08-11, Windows, SQLite, Python 3.13, NumPy 2.5.2.
Полная сетка 180×90, exact timestep 360 игровых минут. Все full-grid benchmark
транзакции откатывались. Phase C4 не начиналась.

## 1. Changed files

Новые основные файлы: `world/services/atmosphere/microphysics.py`,
`world/services/environment_summary.py`, migration `0012`, два C3 test modules,
`scripts/benchmark_atmosphere_c3.py` и этот отчёт. Изменены defaults, models,
forms/admin, grid/advection/thermodynamics/orography/simulation/ocean/sampling,
persistence/fingerprint, weather presentation, region view/template/CSS,
time-report precipitation reader и performance probes.

## 2. New/changed models

`AtmosphericConfig.oxygen_fraction` — nullable 0..1. В `WeatherState` добавлены
nullable `precipitation_rate_mm_h`, `precipitation_amount_mm`, `rain_fraction`,
`snow_fraction`; source `atmospheric_grid_v2` обозначает физическую C3 запись.
Legacy source/поле осадков сохранены.

## 3. Migrations

`world.0012_phase_c3_cloud_microphysics` только добавляет поля и обновляет
choices/default versions. Старые snapshots и WeatherState не удаляются.
Миграция успешно применена к development SQLite.

## 4. Previous cloud/precip behavior

До C3 облачность в основном следовала порогу RH, а орография напрямую строила
условный precipitation proxy из RH/uplift. Осадки не были обязательным стоком
атмосферной воды, а `WeatherState.precipitation` был безразмерным индексом.

## 5. q_c field/storage/units

`cloud_condensate_specific_humidity` хранится в каждом `AtmosphericGrid` как
little-endian float32, единица — кг взвешенного total condensate на кг влажного
воздуха. Это единый liquid+ice reservoir. Grid v3 содержит 13 полей и занимает
842,400 bytes без compression на 180×90.

## 6. Condensation algorithm

В пересыщенных клетках масса `delta_q` вычитается из `q_v` и добавляется в
`q_c`. Конечный пар равен `q_sat(T',p)`, а `q_c'=q_c+q_v-q_sat`. Python-loop по
клеткам отсутствует.

## 7. Saturation-adjustment solver

Решается монотонное уравнение
`c_p*T' + L_v*q_sat(T',p) = c_p*T + L_v*q_v` ограниченным векторным Newton с
bracket/midpoint fallback. Default: tolerance `1e-8 kg/kg`, максимум 6
итераций. Аналитическая производная q_sat вычисляется вместе с q_sat, процесс
детерминирован.

## 8. Latent heat coupling

Конденсация даёт `+L_v*delta_q/c_p`, испарение `-L_v*delta_q/c_p` через одно
энтальпийное решение. Grid сохраняет diagnostic condensation mass flux и net
latent-heating W/m²; нагретая T затем участвует в pressure/wind.

## 9. Cloud evaporation

Если воздух ненасыщен и `q_c>0`, condensate испаряется до saturation либо до
исчерпания облака. Вода переходит в `q_v`, T падает, `q_v+q_c` сохраняется.

## 10. Liquid/ice diagnostic partition

Прогностические reservoirs не разделяются. Default ice fraction: 1 при
`T<=-2°C`, 0 при `T>=+2°C`, линейная интерполяция между; пороги configurable.

## 11. q_c advection

Semi-Lagrangian vectorized advection теперь переносит T, q_v и q_c. RH,
cloud-cover и фаза не адвектируются: они пересчитываются диагностически.

## 12. Cloud-water-path / cloud-cover formula

`m_air=p*100/g`, `CWP=q_c*m_air` кг/м²,
`tau=cloud_optical_coefficient*CWP`, `cover=clip(1-exp(-tau),0,1)`. Default
optical coefficient 0.22 м²/кг. RH=99% при q_c=0 не создаёт opaque deck.

## 13. Fog diagnostic

Fog — proxy из RH близкой к saturation, ненулевого q_c, слабого ветра и
lowland modifier. Он не утверждает реальную высоту cloud base и не меняет
водный цикл.

## 14. Orographic condensation changes

Wind-aligned upwind elevation difference даёт climb/descent. Default cooling:
`4.5°C/km * min(|wind|/10,1)`, descent warming `2.5°C/km`, абсолютный cap 8°C.
После этого обычная saturation adjustment создаёт q_c; direct RH-rain и biome
penalty удалены. Controlled ocean→mountain→lee test даёт rain shadow.

## 15. Precipitation conversion formula

`excess=max(q_c-q_threshold,0)`,
`fallout_fraction=1-exp(-dt/tau_precip)`,
`delta_q=min(q_c,excess*fallout_fraction)`,
`P=delta_q*(p*100/g)/dt`. Defaults: threshold 0.00005 кг/кг, timescale 21,600 s.
Аварийный q_c-limit 0.2 кг/кг также удаляется как surface sink и считается.

## 16. Precipitation units

Solver хранит кг/(м²·с). UI использует `rate_mm_h=P*3600`; amount за шаг —
`P*dt`, потому что 1 кг/м² жидкого водного эквивалента = 1 мм. Snow amount —
SWE, не глубина снега.

## 17. WeatherState DB compatibility

Новые физические rows записывают unit-bearing nullable fields и source v2;
legacy `precipitation` у них остаётся 0. Старые rows с null physical fields
продолжают показывать исходный безразмерный индекс и не мигрируются задним
числом.

## 18. Rain/snow partition

Rain fraction = 1 - ice fraction с тем же плавным −2…+2°C переходом. Condition
SNOW выбирается при доминировании snow fraction; mixed UI показывает мокрый
снег/смешанные осадки.

## 19. Water-mass accounting

Diagnostics: vapor/cloud mass proxy, total precipitation, total evaporation,
condensation и cloud evaporation. В закрытом controlled test q_v+q_c
сохраняется; при fallout потеря `delta_q*m_air` равна `P*dt`.

## 20. Old precipitation proxy removal/deprecation

Exact AtmosphericGrid больше не использует RH/random/direct-orographic rain.
Совместимый wrapper orography только меняет T. Старая региональная weather-v2
остаётся fallback при выключенной атмосфере и для чтения истории.

## 21. Exact timestep order

Фактический порядок: clone → advection T/q_v/q_c → C1 forcing и land exchange
→ ocean sensible/evaporation/SST → orographic cooling → saturation/latent
coupling → pressure → wind → q_c fallout → cloud cover → emergency RH safety
→ finite validation → regional sampling в persistence.

## 22. Fast-forward q_c/microphysics

24×12 boundary state наследует и переносит T/q_v/q_c/p/wind. На каждом
6-часовом substep выполняются exchange, orography, saturation/latent coupling,
fallout и cloud diagnostics. Итоговая q_c граница возвращается на fine grid.
Skipped interval сохраняет только `integrated_macro_precipitation_mass_kg`;
instant precipitation очищается, detailed WeatherState не создаются. Затем
идёт прежний exact spin-up 28 шагов.

## 23. Fast-forward accuracy after C3

Reduced 24×12 exact reference, включая финальный exact Vitok:

| Interval | SST MAE / max | T MAE / max | q_v MAE / max | q_c MAE / max | RH MAE | precip mass rel. error |
|---|---:|---:|---:|---:|---:|---:|
| Season | 0.146 / 1.527°C | 0.191 / 3.540°C | 0.001033 / 0.008051 | 0.0000045 / 0.0001725 | 0.148% | 0.434% |
| Year | 0.143 / 1.791°C | 0.363 / 17.219°C | 0.001396 / 0.011941 | 0.0000175 / 0.002171 | 0.500% | 0.074% |

SST C2.5 accuracy не ухудшена; локальная annual air-T error остаётся известной
грубой особенностью boundary approximation.

## 24. Solver/snapshot versioning

Magic `FATM3`, format 3, solver 5, microphysics 1. Fingerprint включает static
map digests, solver-relevant AtmosphericConfig/parameters,
ocean/saturation/microphysics versions и orbital config. Presentation-only
`oxygen_fraction` намеренно не инвалидирует физический snapshot. Старые blobs
остаются в БД, но отвергаются как current и не relabel-ятся молча.

## 25. Human-readable summary architecture

Pure service `build_environment_summary()` получает один WeatherState,
RegionalSky, biome/elevation и optional oxygen config. Он возвращает frozen
`EnvironmentSummary`/`EnvironmentHazard` с codes, severity 0..4 и русским
presentation. Solver/DB не мутируются, runtime LLM/API отсутствует.

## 26. Heat / wet-bulb interpretation

Wet bulb решается 60-шаговой bisection moist-enthalpy equality с domain bounds.
Headline prioritizes lethal/extreme thermal hazard over ordinary weather.
Humid severity использует configurable qualitative Twb bands; dry heat —
отдельные T bands. Никакого времени до вреда здоровью не обещается.

## 27. Cold / wind-chill interpretation

Для T<=10°C и ветра >=4.8 км/ч используется стандартная диагностическая
wind-chill form; вне domain выводится только qualitative modifier. Extreme cold
подчёркивает влияние ветра без ложной медицинской точности.

## 28. Humidity/steam interpretation

Labels учитывают T, RH и vapor pressure. «Насыщенный горячим паром» требует
T>=40°C, RH>=85% и e>=7000 Pa; прохладные 100% RH описываются как сырые, не как
удушающая жара. Причина духоты явно отделена от дефицита кислорода.

## 29. Pressure/oxygen safeguards

Pressure label сравнивается с configurable technical reference 1000 hPa.
`oxygen_fraction` по умолчанию null; тогда pO2 и hypoxia warning отсутствуют.
20.9% не hardcoded как канон. Если доля задана, service может вывести pO2, но
точная модель breathing risk ещё не вводилась.

## 30. Noctis/Ympha wording

Service использует уже рассчитанный RegionalSky. Dark night создаёт warning об
отсутствии света и повышенной опасности Ноктиса; light night — о красном свете
Ympha, более слабом Ноктисе и более тёплой ночи. Небо повторно не симулируется.

## 31. Heat Corruption qualitative hook

Возвращаются codes `low/favorable/highly_favorable` по фактическим T/RH,
lowland и light-summer context. Текст говорит только «условия благоприятны»;
процентов и вероятности заражения нет. Biome сам по себе риск не создаёт.

## 32. UI changes

На Region page перед погодой появилась responsive карточка «Условия для
путника»: headline, связное описание, до четырёх hazard badges, apparent/Twb/
wind-chill, visibility/pressure/precipitation и отдельные world warnings.
Научные значения сохранены; GM diagnostics дополнены q_c, CWP, condensation,
latent heat, physical precipitation, rain/snow fraction и fog proxy.

## 33. Performance before/after

Full grid, шесть регионов:

| Scenario | Before C3 wall | After C3 wall | Peak RAM after | Snapshot bytes after | DB write queries after |
|---|---:|---:|---:|---:|---:|
| 1 timestep | 0.126 s | 0.127 s | 74.3 MiB | 405,127 | 4 |
| 1 Vitok exact | 0.532 s | 0.697 s | 83.8 MiB | 1,017,465 | 6 |
| Season FF | 0.760 s | 1.142 s | 86.5 MiB | 1,296,611 | 6 |
| Year FF | 1.527 s | 2.947 s | 86.9 MiB | 1,316,763 | 6 |

До C3 peak RAM был примерно 75.9/83.0/84.3/84.2 MiB, payload bytes
513,401/1,032,522/1,022,934/1,019,550. Exact target <=1 s и Season FF target
<=1.5 s выполнены. Year выше desirable 2 s: profile показывает около 2.05 s
в 1428 обязательных 6h boundary substeps (saturation 1.18 s под cProfile,
forcing 0.61 s, pressure 0.50 s); микрофизика не отключалась ради benchmark.

## 34. Long-run stability

Два канонических года / 2912 sequential steps на 24×12 повторены дважды;
compressed payload побитово одинаков. NaN/Inf нет. Наблюдавшиеся bounds:
air −104.51…201.54°C, pressure 505.53…1014.40 hPa, SST −25.25…80.28°C,
max q_v 0.41467, max q_c 0.005882 кг/кг. 9.0% land cells в финале остались
сухими по benchmark criterion; cloudy fraction 36.1%.

## 35. Numerical clamp statistics

За 838,656 cell-steps: supersaturation emergency 93 hits (0.0111%), cloud-q_c
emergency 0, precipitation-without-condensate 0. Saturation vapor-pressure
domain cap сработал 76,412 раз в экстремально горячих/низкодавленных states;
это ограничение формулы e_s<0.98p, не удаление воды. Maximum adjustment
iterations used: 6. Эта высокая domain-cap частота и экстремальные air-T —
явные ограничения bulk 2D prototype.

## 36. Tests added

Добавлены controlled condensation/enthalpy/water, cloud evaporation,
extreme-domain saturation, q_c advection/roundtrip, fallout mass+units,
rain/snow smoothness, condensate cloud cover, RH-only clear/fog diagnostics,
physical rain shadow, FF q_c/macro precipitation, legacy DB presentation,
current/extreme human heat/cold/pressure/Dark-Light Night cases и Region UI.

## 37. Full test result

`manage.py test`: 146 tests, OK за 22.063 s. `manage.py check`: no issues.
`makemigrations --check --dry-run`: no changes detected. Отдельный двухлетний
C3 benchmark и все full-grid performance runs также завершены.

## 38. Known approximations

Атмосфера остаётся 2D bulk-column; q_c не разделён на liquid/ice и не знает
cloud base; fog — proxy; fallout — one-moment exponential autoconversion;
orographic lapse — configurable proxy; semi-Lagrangian advection не строго
массо-консервативна; surface sink не имеет soil/runoff/snowpack; boundary FF
24×12 сглаживает побережья и локальную air T; oxygen composition неизвестен.

## 39. Remaining questions for C4

Без реализации: вертикальная структура, отдельные hydrometeor reservoirs,
storm electricity/cyclones, soil/runoff/rivers/snowpack, sea ice/ocean currents,
канонический состав атмосферы и geology layer для Жарной Порчи. Эти вопросы
только зафиксированы; Phase C4 не начиналась.
