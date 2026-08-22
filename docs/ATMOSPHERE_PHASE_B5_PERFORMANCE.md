# Phase B.5 — Atmospheric performance report

Дата контрольного замера: 2026-08-10. Development machine, Windows, SQLite,
Python 3.13, NumPy 2.5.2. Кампания имела шесть размещённых регионов; стандартная
сетка — 180×90, timestep — 360 игровых минут. Каждый сценарий запускался в
отдельном процессе. Транзакция benchmark всегда откатывалась.

## Численная совместимость

Коэффициенты и порядок физических стадий не менялись. Scalar-результаты Phase B
были сохранены до векторизации для начального состояния, 1-го и 4-го шага.
Regression test сравнивает все девять `float32`-полей с допуском:

- absolute tolerance: `1e-4`;
- relative tolerance: `1e-6`.

Повтор одного и того же расчёта новым solver остаётся побитово детерминированным.

## До/после

| Сценарий | Шагов | До, wall | После, wall | До, CPU | После, CPU | Полных blobs до | Полных blobs после |
|---|---:|---:|---:|---:|---:|---:|---:|
| atmospheric step | 1 | 0.249 s | 0.091 s | 0.234 s | 0.094 s | 1 | 1 |
| фаза / 24 часа | 4 | 0.843 s | 0.116 s | 0.813 s | 0.094 s | 4 | 1 |
| Виток / 168 часов | 28 | 7.552 s | 0.323 s | 7.156 s | 0.297 s | 28 | 2 |

Два blobs в последней строке — нормальный случай для текущего времени кампании,
не выровненного по границе Витка: один постоянный checkpoint и один актуальный
`latest`. Для Витка от checkpoint до следующего checkpoint сохраняется один blob.

## Детальный trace после рефакторинга

| Стадия | 1 шаг | 4 шага | 28 шагов |
|---|---:|---:|---:|
| static-grid access | 0.0401 s | 0.0418 s | 0.0389 s |
| input fingerprint | 0.0141 s | 0.0155 s | 0.0132 s |
| deserialize once | 0.0027 s | 0.0023 s | 0.0026 s |
| advection | 0.0040 s | 0.0137 s | 0.0934 s |
| surface exchange | 0.0005 s | 0.0019 s | 0.0141 s |
| pressure | 0.0009 s | 0.0036 s | 0.0252 s |
| wind | 0.0018 s | 0.0057 s | 0.0413 s |
| orography | 0.0012 s | 0.0041 s | 0.0299 s |
| serialization/compression | 0.0132 s | 0.0136 s | 0.0267 s |
| regional sampling | 0.0004 s | 0.0010 s | 0.0053 s |
| regional bulk save | 0.0017 s | 0.0020 s | 0.0088 s |
| all DB queries | 0.0044 s | 0.0040 s | 0.0058 s |
| DB writes only | 0.0017 s | 0.0016 s | 0.0030 s |

Peak working set в отдельных процессах: 76.1 MiB (1 шаг), 75.7 MiB (4 шага),
79.7 MiB (28 шагов). За невыровненный Виток записывается 700,364 байта
compressed payload и 168 региональных `WeatherState`; сам benchmark всё это
откатывает.

## Baseline trace до рефакторинга

| Стадия | 1 шаг | 4 шага | 28 шагов |
|---|---:|---:|---:|
| static-grid access | 0.0405 s | 0.0401 s | 0.0407 s |
| advection | 0.0523 s | 0.2118 s | 1.8953 s |
| surface exchange | 0.0124 s | 0.0485 s | 0.4709 s |
| pressure | 0.0633 s | 0.2515 s | 2.4220 s |
| wind | 0.0289 s | 0.1178 s | 1.1327 s |
| orography | 0.0185 s | 0.0750 s | 0.7373 s |
| serialization/compression | 0.0134 s | 0.0543 s | 0.4570 s |
| deserialization | 0.0050 s | 0.0128 s | 0.0774 s |
| DB writes | 0.0012 s | 0.0028 s | 0.0900 s |
| regional sampling | 0.0048 s | 0.0141 s | 0.0969 s |

Payload до рефакторинга: 351,385 байт за один шаг, 1,405,572 байта за фазу
и 9,819,312 байт за Виток.

## Воспроизведение

```powershell
.venv\Scripts\python.exe scripts\benchmark_atmosphere.py CAMPAIGN_UUID --steps 1
.venv\Scripts\python.exe scripts\benchmark_atmosphere.py CAMPAIGN_UUID --steps 4
.venv\Scripts\python.exe scripts\benchmark_atmosphere.py CAMPAIGN_UUID --steps 28
```

Опциональный `--profile-output path.prof` сохраняет стандартный `cProfile`
trace. Скрипт требует уже применённых миграций и намеренно не входит в обычный
unit-test suite. Финальный trace Витка сохранён в
`docs/ATMOSPHERE_PHASE_B5_AFTER_28STEPS.prof`.
