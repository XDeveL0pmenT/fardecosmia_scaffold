# Fardecosmia — World & Campaign Handoff for Coding Agents

> Назначение: этот файл передаёт coding-агенту контекст мира и правила обращения с каноном проекта **Фардекосмия**.
> Он дополняет `AGENTS.md`: `AGENTS.md` отвечает главным образом за технические правила проекта, этот файл — за модель мира, симуляцию, секретность, данные кампании и границы допустимых предположений.

---

## 1. Главный принцип: не выдумывать канон

Coding-агент **не является автором мира** и не должен самостоятельно придумывать факты лора, географии, истории, календаря, народов, религий, государств, магии, климата или текущих событий, если эти факты не были явно даны Game Master.

Нужно различать три типа информации:

1. **CONFIRMED CANON** — явно подтверждённые Game Master данные. Их можно хранить, отображать и использовать в симуляции.
2. **TECHNICAL MODEL / IMPLEMENTATION DECISION** — структура данных и алгоритмы приложения. Они могут существовать без утверждения конкретного лора.
3. **UNKNOWN / TO BE PROVIDED** — канонический факт пока неизвестен coding-агенту. Его нельзя заменять правдоподобной догадкой.

Если данных недостаточно для конкретного алгоритма:
- сделать поле/настройку конфигурируемой;
- использовать нейтральный placeholder только в development/demo данных;
- явно помечать его как non-canon/demo;
- не делать placeholder частью production fixtures или migrations как будто это канон.

---

# 2. Что такое Fardecosmia

**Фардекосмия** — мир и текущая tabletop RPG campaign, для которой создаётся собственный Django-сайт.

Сайт должен быть не просто wiki, а **campaign operating system / world simulation assistant**:
- игроки получают персональные страницы и доступ к тому, что знают их персонажи;
- Game Master получает мастерскую панель;
- приложение хранит объективное состояние мира;
- приложение умеет продвигать игровое время;
- погода и некоторые мировые процессы рассчитываются автоматически;
- события могут срабатывать по времени и условиям;
- Roll20 используется для боевой части персонажей;
- сайт должен постепенно становиться центральной долговременной памятью кампании.

Проект должен поддерживать долгую кампанию и накопление истории, а не только состояние одной игровой сессии.

---

# 3. Игровая система и Roll20

## CONFIRMED CANON / PROJECT FACT

Группа использует:

**D&D 5E (Classic)** в Roll20.

В текущей технической архитектуре это обозначается как:

`dnd5e_2014`

или:

`D&D 5E Classic / Legacy D&D 5E (2014)`

## Роли систем

**Roll20 — source of truth для боевого character-sheet state.**

Примеры данных, которые должны приходить из Roll20:
- current HP;
- max HP;
- temporary HP;
- AC;
- ability scores;
- saving throws/skills, когда будет реализовано;
- spell slots;
- hit dice;
- death saves;
- resources;
- inventory/equipment;
- attacks;
- spells;
- class/level и другие данные листа, когда их парсер будет реализован.

**Fardecosmia — source of truth для campaign/world state.**

Примеры данных сайта:
- биография персонажа в контексте кампании;
- знания;
- слухи;
- секреты;
- отношения;
- репутация;
- квесты;
- место нахождения;
- путешествия;
- мировые события;
- фракции;
- NPC;
- история;
- климат;
- погода;
- время мира;
- clocks;
- GM notes.

Не смешивать два слоя без необходимости.

---

# 4. Персонаж и пользователь — разные сущности

`accounts.User` — реальный пользователь сайта.

`characters.Character` — персонаж внутри кампании.

Один пользователь потенциально может:
- иметь несколько персонажей;
- участвовать в нескольких кампаниях;
- быть игроком в одной кампании;
- быть GM в другой.

Роль пользователя хранится на уровне `CampaignMembership`, а не глобально в User.

Персонаж может существовать:
- с владельцем;
- временно без владельца;
- с Roll20 binding;
- без Roll20 binding.

Никогда автоматически не связывать Roll20-персонажа и local Character только по имени.

---

# 5. Объективная реальность мира ≠ знания игроков

Это один из самых важных принципов архитектуры.

Система должна позволять хранить:

## Truth / Canonical World State

То, что объективно истинно в мире.

Примеры:
- NPC на самом деле состоит во фракции X;
- город заражён;
- король мёртв;
- тайный проход существует;
- реликвия находится в конкретном месте.

## Character Knowledge

То, что конкретный персонаж знает или считает истинным.

Знание может быть:
- true;
- false;
- incomplete;
- rumor;
- theory;
- outdated;
- uncertain.

## Player Visibility

То, что разрешено показать конкретному пользователю.

Следовательно, нельзя строить приложение так, чтобы все записи лора автоматически становились видимыми всем игрокам.

Минимальная концептуальная модель должна поддерживать:
- GM-only facts;
- public facts;
- facts known to selected characters;
- rumors;
- false beliefs;
- discovered facts;
- discovery time/source;
- potentially confidence/reliability.

Game Master должен иметь возможность видеть и truth, и player-visible representation.

---

# 6. Время мира

## CONFIRMED IMPLEMENTATION DECISION

Внутреннее campaign time хранится как целое количество **игровых минут** от выбранной эпохи/начала кампании:

`Campaign.world_minutes`

Это техническое представление, а не утверждение о календаре мира.

## CONFIRMED CALENDAR CANON

- 1 Виток = 168 часов и является одним условным днём мира.
- Виток делится на 7 равных световых фаз по 24 часа. Название «день Витка» в исходных таблицах означает 1/7 Витка, а не отдельный 24-часовой день мира.
- 1 Круг Лика = 16 Витков = 112 световых фаз.
- Половина Круга Лика = 8 Витков = 56 световых фаз.
- 1 сезон = 13 Витков = 91 световая фаза.
- 1 год / Великий Круг = 52 Витка = 364 световые фазы.
- Сезоны следуют в порядке: Лето, Осень, Зима, Весна.
- Сезоны и Круг Лика не совпадают: каждый следующий год начинается на 4 Витка дальше в Круге Лика; через 4 года сочетание фаз повторяется.
- Витки 1–8 Круга Лика — Рассветание; Витки 9–16 — Угасание.
- За один Виток планета обходит Ympha примерно за 7,05 дня, а оборот планеты вокруг оси занимает примерно 7,52 дня. Поэтому световые день и ночь длинные.

Семь световых фаз Витка:

1. Рассвет.
2. День.
3. Яркий день.
4. Закат.
5. Ночь.
6. Глубокая ночь.
7. Предрассвет.

Виток бывает Красным или Чёрным в зависимости от того, видна ли Ympha ночью. Подтверждённые названия состояний дней:

- Красный: Яркий рассвет, Светлый день, Белый жар, Светлый закат, Светлая ночь, Красная ночь, Красный предрассвет.
- Чёрный: Холодный рассвет, Светлый день, Сухой день, Тёмный закат, Чёрная ночь, Глухая ночь, Тёмный предрассвет.

Фазы Рассветания: Начало Рассветания, Бледные ночи, Красный край, Половинная ночь, Светлые ночи, Красные ночи, Высокий Лик, Пик Рассветания.

Фазы Угасания: Начало Угасания, Тусклый Лик, Длинные тени, Половинная ночь, Тёмные ночи, Чёрные ночи, Глухие ночи, Пик Угасания.

## CONFIRMED REGIONAL LIGHT CYCLES

- Полная экваториальная окружность планеты равна 72 500 км.
- Световой цикл Звезды делает полный обход мировой карты за 1 Виток / 168 часов.
- Световой цикл Ympha делает полный обход мировой карты за 16 Витков.
- Местное время, световая фаза Витка, Рассветание/Угасание и ночная видимость Ympha зависят от долготы региона. Эти значения нельзя считать одинаковыми для всей планеты.
- Переданная GM растровая карта является полной эквидистантной проекцией окружности планеты с долготами от 180° з.д. до 180° в.д. и широтами от 90° с.ш. до 90° ю.ш.

## IMPORTANT UNKNOWN / CONFIGURABLE

Пока не зафиксированы названия/наличие месяцев, високосные правила, эпоха и текущий канонический год. Внутренний год кампании по умолчанию равен 0 и настраивается через `Campaign.calendar_epoch_year`.

Длительность Витка в 168 часов и семь равных 24-часовых фаз — подтверждённый канон. Деление часа на 60 внутренних игровых минут остаётся настраиваемым техническим представлением. Плавная численная видимость Ympha и порог перехода между Красным и Чёрным Витком — также technical model, а не самостоятельный канон.

Точные начальные меридианы и направления движения световых циклов пока не даны GM. Они должны оставаться настраиваемыми (`star_reference_longitude`, `star_motion_direction`, `ympha_peak_longitude_at_epoch`, `ympha_motion_direction`). Наклон оси и широтная форма границы света также неизвестны; текущая продольная визуализация является technical model, а не новым астрономическим каноном.

## Advance World

GM должен иметь быстрые действия вроде:
- +10 минут;
- +1 час;
- +6 часов;
- +1 фаза Витка;
- +1 Виток / день мира;
- позднее custom amount / переход к определённому моменту.

Продвижение мира — транзакционная service operation.

При продвижении времени потенциально происходят:
1. update campaign time;
2. weather update;
3. timed events;
4. conditional events;
5. clocks;
6. NPC schedules;
7. faction processes;
8. travel progression;
9. resource/economy processes;
10. world history entries.

Не обязательно реализовать всё сразу, но API/service boundaries должны позволять добавлять эти системы.

---

# 7. Планета, климат и опорные растровые карты

## CONFIRMED PROJECT FACT

У мира существуют **планетарные климатические параметры**, и GM предоставил **карту средней температуры планеты** со шкалой `−97.2…+74.6°C`, **карту высот** с дискретной шкалой `−29…6365 м` и чёрно-белую **маску суши** в той же мировой проекции.

Карты температуры и высоты являются входами для базовых параметров регионов. Приложение использует механически оцифрованные сетки их собственных палитр. Маска суши ограничивает редактор биомов, но сама визуально не отображается.

## IMPORTANT

Точная глобальная средняя, наклон оси, течения, ветры и другие параметры планеты по-прежнему **не присутствуют в текущем handoff-контексте**.

Coding-агент НЕ ДОЛЖЕН:
- придумывать среднюю температуру планеты;
- придумывать наклон оси;
- придумывать широту регионов;
- придумывать океанические течения;
- заменять неизвестные клетки биомов или закрытые исходной легендой клетки высот случайными данными как каноном.

Архитектура должна быть готова принять остальные данные позже.

Полезно предусмотреть сущность/настройки уровня мира, например концептуально:

`WorldClimateSettings`

в которой позже смогут появиться:
- global mean temperature;
- seasonal cycle;
- axial/astronomical parameters;
- climate-map revision;
- temperature-map source;
- global modifiers.

Не нужно создавать все эти поля заранее, если они пока не нужны MVP, но алгоритмы нельзя проектировать так, будто единственным климатическим источником является `Region.base_temperature`.

---

# 8. Региональная климатическая модель

## CONFIRMED PARAMETERS

Для региона уже определён набор параметров, который должен поддерживаться системой:

### `base_temperature`
Базовая/средняя температурная характеристика региона.

### `seasonal_amplitude`
Насколько сильно температура региона изменяется между сезонами.

### `humidity`
Характерная влажность региона.

### `elevation`
Высота региона над уровнем моря.

### `weather_volatility`
Насколько нестабильна и резко изменчива погода.

Эти параметры используются как климатические входы, а не как текущая погода.

## В будущем вероятно понадобятся дополнительные факторы

Они **не являются подтверждённым каноном**, но модель должна позволять расширение:
- latitude / climate-band position;
- distance to sea;
- ocean influence;
- prevailing wind;
- rain shadow;
- terrain/biome;
- magical climate modifiers;
- local anomaly;
- season offset;
- continentality;
- neighboring region influence.

Не добавлять их как обязательные поля без потребности, но избегать архитектуры, которую невозможно расширить.

---

# 9. Погода — динамическая система с памятью

Погода не должна быть независимым random choice на каждый час.

Нужна **weather continuity**.

Следующее состояние зависит от:
- регионального климата;
- сезона;
- времени суток;
- высоты;
- предыдущего weather state;
- влажности;
- volatility;
- random component;
- позднее — фронтов/соседних регионов и глобального климата.

Пример плохой модели:

10:00 +30°C clear  
11:00 -10°C snow  
12:00 +28°C thunderstorm

без климатической причины.

Погода должна ощущаться как процесс.

## WeatherState history

Нужно сохранять историю, а не только последнее значение.

Потенциальные показатели:
- world time;
- temperature;
- humidity;
- wind;
- precipitation;
- condition;
- cloudiness;
- visibility;
- pressure/front identifier позже.

Это позволит:
- показать игрокам текущую погоду;
- восстановить прошлую погоду;
- делать события, зависящие от погоды;
- анализировать путешествия;
- создавать последствия storms/flood/snow;
- воспроизводить campaign history.

## Determinism / reproducibility

Желательно, чтобы генерация могла быть воспроизводимой при одинаковом seed/world state, особенно для тестов.

Не привязывать canonical weather generation к Python global random без контролируемого seed/state.

---

# 10. Регионы

Регион — важная единица симуляции.

Он потенциально содержит:
- имя;
- campaign/world;
- географический parent;
- biome/terrain;
- climate settings;
- elevation;
- geography;
- settlements;
- roads;
- weather;
- events;
- factions;
- NPC presence;
- travel modifiers.

## IMPORTANT UNKNOWN

Конкретный список регионов Фардекосмии и их канонические параметры в текущем handoff не приведены.

Нельзя создавать production regions со случайными названиями.

Demo data допустимы только с явным маркированием `demo`.

---

# 11. География и карта

Сайт поддерживает подтверждённую GM растровую карту полной окружности планеты. Регионы могут хранить нормализованный полигон на этой карте, а его центр переводится в долготу и широту. Положение конкретного региона становится каноном кампании только после того, как GM нарисовал/сохранил его контур.

Концептуально должны существовать:
- regions;
- settlements;
- landmarks;
- points of interest;
- routes/roads;
- hidden locations;
- discovered locations;
- travel edges/connections.

Игрок не обязан видеть все объекты карты.

Например:
- GM видит тайный храм;
- Character A его обнаружил;
- Character B не знает о нём.

Поэтому visibility должна быть частью map/domain architecture.

## CONFIRMED MAP FORMAT / TECHNICAL STORAGE

- Канонический визуальный источник сейчас является raster image.
- Координаты читаются как долгота/широта по нанесённой на изображение сетке.
- Контур региона хранится как нормализованные точки `[x, y]` в диапазоне 0–1, поэтому геометрия не зависит от разрешения веб-копии изображения.
- Световые слои и контуры рисуются отдельным SVG overlay и не изменяют исходную карту.
- Физические растровые слои температуры, высоты и суши общие для всех кампаний; состояние времени и контуры регионов остаются кампанийными.
- Общий слой биомов хранится независимо от кампаний. Редактировать его можно из GM-карты кампании, но изменение относится ко всему атласу Фардекосмии.
- Это не подтверждает наличие hex/square grid, маршрутов или GIS-топологии; такие слои остаются будущими расширениями.

---

# 12. Путешествия

Будущая система путешествий должна потенциально учитывать:
- origin;
- destination;
- route;
- departure time;
- travel mode;
- speed;
- terrain;
- weather;
- encumbrance/resources;
- interruptions;
- random/conditional events;
- arrival estimate;
- actual arrival time.

Travel должен быть процессом мира, а не просто вычислением расстояния.

Возможны состояния:
- planned;
- active;
- paused;
- delayed;
- completed;
- cancelled.

Погода и события могут менять travel progress.

---

# 13. События мира

Нужно поддерживать как минимум два класса событий.

## Timed event

Срабатывает при наступлении/пересечении определённого world time.

Например концептуально:
- армия достигает границы;
- корабль входит в порт;
- начинается церемония.

Это НЕ канонические события Фардекосмии — только примеры структуры.

## Conditional event

Срабатывает при выполнении условий.

Примеры типов условий:
- NPC status;
- NPC death;
- character location;
- possession of item;
- faction state;
- clock threshold;
- quest state;
- previous event;
- world time elapsed;
- weather condition;
- knowledge/discovery state.

## Rule representation

Не хранить произвольный Python-код условий в БД.

Использовать безопасное декларативное представление, например JSON/structured rules.

Концепт:

```json
{
  "all": [
    {"type": "npc_status", "npc_id": "...", "value": "dead"},
    {"type": "clock_at_least", "clock_id": "...", "value": 6}
  ]
}
```

Rule engine должен быть whitelist-based.

---

# 14. Clocks

В мире планируется поддержка progress clocks.

Примеры интерфейса:
- Rebellion 5/6;
- Ritual 3/6;
- War 2/8.

Названия выше — только UI examples, не канон.

Clock может относиться к:
- campaign;
- faction;
- NPC;
- quest;
- threat;
- region;
- secret process.

Clock может быть:
- player-visible;
- GM-only;
- partially revealed.

Достижение threshold может запускать event.

---

# 15. NPC

NPC должен быть полноценной сущностью мира, а не только текстовой страницей.

Потенциальное состояние:
- identity;
- current location;
- alive/dead/missing/etc.;
- faction membership;
- relationships;
- public description;
- GM-only truth;
- schedule;
- goals;
- resources;
- conditions;
- knowledge;
- history.

NPC state должен меняться во времени.

Нужно избегать хранения всего NPC state одним неструктурированным JSON, если данные активно используются в запросах/правилах.

JSON подходит для редко используемых flexible metadata, но ключевое domain state лучше моделировать явно.

---

# 16. Фракции

Будущая faction system может хранить:
- name;
- hierarchy;
- territory;
- resources;
- influence;
- relationships;
- goals;
- plans;
- clocks;
- current operations;
- secrets;
- known/public information.

Фракции должны иметь возможность действовать независимо от игроков при продвижении времени.

Не реализовывать сложную economy/AI simulation до появления требований, но не делать события исключительно player-triggered.

Мир должен иметь ощущение самостоятельного движения.

---

# 17. История мира / audit trail

Очень желательно иметь append-style campaign history.

Когда происходит важное изменение, система потенциально создаёт запись:
- world time;
- event type;
- actor;
- target;
- region;
- summary;
- source;
- visibility;
- structured payload.

История нужна для:
- GM recap;
- session recap;
- debugging simulation;
- understanding why current state exists;
- player journals;
- later automated summaries.

Не полагаться только на текущее состояние БД.

---

# 18. Сессии

Кампания состоит из игровых сессий.

В будущем полезно связывать:
- real-world session date;
- start/end world time;
- participating characters;
- notes;
- events;
- discoveries;
- loot;
- XP/milestones;
- recap.

Реальное время сессии и время мира — разные временные шкалы.

---

# 19. Knowledge / rumor / secret system

Это отдельный важный domain.

Возможные понятия:

## Fact
Объективное утверждение мира.

## Knowledge
Персонаж получил информацию.

## Rumor
Информация распространена, но не обязана быть истинной.

## Belief
Персонаж считает что-то истинным.

## Secret
GM-only или ограниченно раскрываемая информация.

Полезные поля/отношения:
- subject;
- statement/content;
- truth status;
- visibility;
- known_by characters;
- source;
- discovered_at world time;
- reliability/confidence;
- supersedes/outdated_by.

Нельзя автоматически раскрывать objective truth вместе с rumor.

---

# 20. Видимость и безопасность данных

Это не только frontend concern.

GM-only информация не должна:
- попадать в player template context;
- возвращаться player API;
- быть спрятана только CSS;
- находиться в HTML как hidden element;
- случайно сериализоваться вместе с public object.

Авторизация должна происходить server-side.

Каждая campaign-bound сущность должна проверять membership.

В будущем могут существовать:
- GM;
- player;
- observer/co-GM/guest — пока не канон, поэтому роли расширяемы.

---

# 21. Character page

Персональная страница игрока должна со временем объединять:

### Roll20 mirror
- HP;
- AC;
- abilities;
- spell/resources;
- inventory и т.д.

### Campaign state
- current location;
- conditions outside Roll20;
- reputation;
- relationships;
- quests;
- discoveries;
- character knowledge;
- journal/history;
- weather at location;
- travel state.

### GM layer
Дополнительные поля, которые игрок не видит:
- secrets;
- hidden conditions;
- private notes;
- hidden triggers;
- truth behind rumors.

---

# 22. Roll20 partial synchronization

Требование: **частичная синхронизация**, с перспективой browser extension.

Protocol:
`Fardecosmia Roll20 Protocol v1`

Поддерживать:
- `snapshot`;
- `delta`.

Каждое сообщение содержит idempotent:
`event_id`

Raw Roll20 state:
`Roll20CharacterBinding.raw_attributes`

Normalized state:
`Roll20CharacterBinding.normalized_state`

Binding:
по Roll20 character ID, не по имени.

## Future extension architecture

Концептуально:

Roll20 page  
→ content script / D&D5E2014 adapter  
→ extension service worker  
→ HTTPS  
→ Django `/api/v1/roll20/sync/`

Extension token не должен храниться в page context.

## Django → Roll20 later

Не делать blind overwrite.

Использовать queue/commands:
- desired change;
- expected old value;
- extension checks current Roll20 value;
- apply only if no conflict;
- acknowledge result.

---

# 23. D&D 5E Classic adapter

Adapter должен быть отдельным integration boundary.

Roll20-specific naming не должно распространяться по business code.

Например:

Roll20:
`hp`, `hp_temp`, `strength`, ...

Normalized:
```json
{
  "hp": {
    "current": 20,
    "max": 30,
    "temporary": 4
  },
  "abilities": {
    "strength": 14
  }
}
```

При первом реальном extension prototype нужен **diagnostic scanner**, который собирает реальные attribute names используемого листа.

Не считать заранее, что известен полный список repeating fields.

Особенно аккуратно работать с:
- repeating inventory;
- attacks;
- spells;
- class resources;
- computed/default values.

---

# 24. Что НЕ нужно моделировать в Character напрямую

Не создавать сотни Roll20-specific columns в `Character`.

Плохо:

`Character.roll20_strength`  
`Character.roll20_spellslot_1`  
`Character.roll20_attack_...`

Правильно:
- Roll20 integration stores raw/normalized mirror;
- Character stores Fardecosmia domain data.

Если определённая механическая характеристика позже понадобится для query/rules performance, её можно selectively denormalize с чёткой причиной.

---

# 25. Weather effects on gameplay

Погода должна в перспективе иметь gameplay consequences, но coding-агент не должен сам придумывать D&D house rules.

Возможные extension points:
- travel speed modifier;
- visibility;
- encounter probabilities;
- exhaustion risk;
- navigation;
- fire/survival conditions;
- environmental hazards.

Конкретные modifiers должны быть конфигурируемыми или вводиться GM.

---

# 26. Magic and supernatural climate

Мир fantasy, поскольку campaign использует D&D 5E, но конкретная метафизика/магическая система мира Фардекосмии в этом handoff не зафиксирована.

Следовательно:
- не считать Forgotten Realms каноном;
- не импортировать автоматически Forgotten Realms deities/history/geography;
- не считать стандартный D&D cosmology каноном мира;
- не придумывать planes/gods/moons;
- не считать RAW lore D&D лором Фардекосмии.

D&D 5E — механическая система игры, не автоматический источник world canon.

Если нужны supernatural modifiers, предусматривать extension points.

---

# 27. Не путать system rules и world lore

Пример:

`Strength = 16`
— mechanical character state.

`Империя Зари контролирует север`
— world lore.

`В этом мире год длится 360 дней`
— world/astronomical canon.

Только первый тип можно уверенно выводить из D&D sheet.

Остальные требуют данных Game Master.

---

# 28. Текущий статус известных климатических данных

Из доступного проектного контекста точно известно, что для регионов используются:

- Base temperature
- Seasonal amplitude
- Humidity
- Elevation
- Weather volatility

На уровне планеты теперь подтверждены:
- окружность карты `72 500 км` и циклы движения света;
- average-temperature map со шкалой `−97.2…+74.6°C`;
- elevation map со шкалой `−29…6365 м`;
- GM-provided land mask для границ рисования биомов.

Другие конкретные значения планетарных данных сейчас отсутствуют в этом handoff. Биомы известны только там, где их явно нарисовал GM. Высота известна из растровой карты, кроме участков, которые в исходнике закрыты её собственной легендой; там значение остаётся `UNKNOWN`.

Coding-агент должен считать их pending canonical input.

## CURRENT TECHNICAL WEATHER MODEL (NOT CANON)

Новые погодные состояния создаются только при пересечении настраиваемого интервала региона (`weather_update_interval_minutes`), а не при каждом вызове продвижения времени. Расчёт сохраняет историю и использует предыдущее состояние для инерции.

Численные параметры `light_cycle_temperature_amplitude`, `ympha_temperature_influence`, `season_light_temperature_influence`, `elevation_temperature_per_1000m`, `weather_persistence` и `precipitation_bias` являются редактируемыми коэффициентами симуляции. Их значения по умолчанию не являются правилами мира. Температура учитывает среднее значение из предоставленной карты, местные сезон и фазу 168-часового Витка, локальную видимость Ympha, высоту и региональные климатические поля.

---

# 29. Recommended canonical-data strategy

World lore желательно хранить не внутри migrations.

Migrations — схема данных, а не энциклопедия мира.

Для канонических данных лучше предусмотреть:
- admin interface;
- import/export;
- fixtures только если они действительно являются стабильным seed;
- versioned data files при необходимости.

Хороший будущий layout:

```text
world/
  canon/
    README.md
    climate/
    geography/
    calendar/
    factions/
```

Но создавать это дерево необязательно, пока нет реальных данных.

Если такие файлы появятся:
- они должны быть version-controlled;
- иметь schema/version;
- отличать canon от demo/test fixtures.

---

# 30. Suggested data provenance

Для важных канонических записей позже полезно иметь:
- source;
- created_by;
- updated_by;
- canonical status;
- notes;
- revision timestamp.

Это помогает отличать:
- imported legacy lore;
- GM-confirmed canon;
- auto-generated weather;
- player rumor;
- simulation result.

Не обязательно добавлять эти поля во все MVP models сразу; это направление архитектуры.

---

# 31. Generated data vs authored data

Система будет содержать два принципиально разных типа данных.

## Authored
Создано/утверждено GM:
- lore;
- NPC;
- regions;
- faction goals;
- event definitions.

## Generated
Получено симуляцией:
- current weather;
- triggered event occurrence;
- travel progress;
- potentially faction ticks.

Generated result не должен автоматически становиться immutable canon definition.

Например:
- climate settings — authored;
- конкретный дождь на 152-й день — generated historical fact.

---

# 32. Randomness policy

Randomness должна быть:
- testable;
- controllable;
- optionally seeded;
- recorded where important.

Если random roll породил важное world event:
желательно сохранить результат/seed/context, чтобы потом понимать происхождение состояния.

Не строить critical campaign state так, чтобы повторный запрос страницы мог случайно пересчитать его иначе.

GET request не должен случайно изменять мир.

Simulation changes происходят только через explicit service/action/task.

---

# 33. Automation boundaries

Автоматизация нужна, чтобы облегчать жизнь Game Master, а не лишать GM контроля.

Поэтому важные auto-generated events должны потенциально поддерживать режимы:
- automatic;
- proposed/pending GM approval;
- disabled/manual.

Конкретное решение для каждого subsystem определяется позднее.

Не делать необратимые массовые изменения мира без audit/history.

---

# 34. Performance assumptions

На старте это одна/несколько tabletop campaigns, а не MMO.

Приоритеты:
1. correctness;
2. maintainability;
3. auditability;
4. permissions;
5. developer velocity;
6. performance optimization.

Не создавать преждевременную сложную distributed architecture.

Django + PostgreSQL достаточно для core.

---

# 35. Domain service boundaries

Business logic должна уходить в services.

Предпочтительные направления:

```text
world/services/time.py
world/services/weather.py
world/services/events.py
world/services/travel.py

characters/services/knowledge.py

integrations/roll20/services/sync.py
```

Views должны:
- authenticate;
- authorize;
- validate input;
- call service;
- render/return result.

---

# 36. Testing priorities

Особенно важно тестировать:

## Permissions
Игрок не получает GM-only данные.

## Time advancement
Одно действие увеличивает время ровно один раз.

## Idempotency
Roll20 event повторно не применяется.

## Weather continuity
Weather generation не создаёт невозможные скачки без причины.

## Event crossing
При прыжке времени с T1 на T2 не пропускаются события между ними.

## Transaction safety
Concurrent GM actions не удваивают/теряют world advancement.

## Knowledge
Player A не получает knowledge Player B.

## Binding
Roll20 characters не связываются по имени автоматически.

---

# 37. UI priorities

GM dashboard должен быстро отвечать:
- который сейчас world time;
- где персонажи;
- какая погода;
- какие события скоро;
- какие события только что произошли;
- какие clocks опасно близки к завершению;
- какие NPC/factions требуют внимания;
- есть ли sync problems с Roll20.

Player dashboard:
- персонаж;
- campaign time/date;
- location;
- weather;
- known information;
- quests/goals;
- journal;
- Roll20 mirrored combat data.

Не перегружать MVP всеми подсистемами сразу.

---

# 38. MVP world functionality

Первый реальный usable milestone:

1. Custom User.
2. Campaign.
3. CampaignMembership.
4. Character.
5. Region.
6. Campaign world time.
7. Regional climate parameters.
8. WeatherState + weather generation.
9. Timed WorldEvent.
10. Advance-time GM action.
11. GM dashboard.
12. Player-safe character/campaign page.
13. Roll20Connection.
14. Roll20CharacterBinding.
15. Roll20 snapshot/delta endpoint.
16. Explicit Roll20 ↔ Character binding.
17. Basic audit/history for important world changes.

Knowledge/factions/travel/clocks can follow.

---

# 39. Critical unknown canon checklist

Coding-агент должен знать, что следующие сведения пока отсутствуют в этом handoff и требуют будущего GM input:

## Planet / astronomy
- planet name if different from world/project name;
- radius/gravity;
- axial tilt;
- detailed orbital parameters beyond the confirmed cycle durations;
- moons;
- astronomy affecting seasons.

## Calendar
- era;
- current date;
- months;
- weeks;
- festivals;
- leap rules.

## Global climate
- exact global mean temperature;
- climate bands;
- ocean currents;
- prevailing winds;
- exact quantitative strengths of the already confirmed seasonal effects beyond GM-configured technical defaults.

## Geography
- continents;
- oceans;
- canonical biome and elevation values for cells that GM has not painted on the world map;
- canonical placement of regions not yet drawn by GM;
- settlements;
- distances;
- routes.

## Politics
- states;
- factions;
- rulers;
- wars;
- alliances.

## Peoples/cultures
- nations;
- races/species interpretation;
- languages;
- customs.

## Religion/metaphysics
- gods;
- planes;
- afterlife;
- magic cosmology.

## History
- eras;
- major events;
- current geopolitical situation.

## Campaign state
- current player characters;
- current locations;
- active quests;
- current NPCs;
- active events/clocks.

Absence в этом файле **не означает, что этих вещей нет в мире**. Это означает только, что coding-agent не получил их канонические значения.

---

# 40. Instructions when new world data arrives

Когда GM предоставляет новые канонические данные:

1. Не переписывать старую модель автоматически.
2. Определить, это:
   - lore text;
   - structured domain state;
   - simulation parameter;
   - secret/player knowledge;
   - immutable history.
3. Выбрать правильное место хранения.
4. Указать visibility.
5. Не терять источник/контекст.
6. При необходимости обновить этот handoff.
7. Добавить tests, если данные влияют на simulation/business rules.

---

# 41. Canon precedence

Если источники противоречат друг другу, приоритет:

1. Последняя явная инструкция Game Master.
2. Актуальные project canon files / structured data, подтверждённые GM.
3. Этот `WORLD_HANDOFF.md`.
4. Existing implementation assumptions.
5. Demo/test data.

Код никогда не имеет приоритет над новым подтверждённым каноном.

---

# 42. Hard prohibitions for coding agents

**DO NOT:**
- invent lore to fill missing database fields;
- assume Forgotten Realms;
- assume Earth geography;
- assume Gregorian calendar;
- assume 365-day year;
- assume 360-day year;
- assume the prototype weather constants are canon;
- expose GM notes to players;
- use frontend-only hiding for secrets;
- bind characters by name;
- let a GET request mutate world state;
- store extension secrets in plaintext when avoidable;
- store arbitrary executable Python from DB event rules;
- make Roll20 the owner of Fardecosmia campaign lore;
- make Fardecosmia silently overwrite Roll20 combat state;
- turn demo fixtures into world canon.

---

# 43. Summary for the agent

The application models a persistent fantasy campaign world.

The most important architectural truths are:

- D&D 5E Classic is the game mechanics sheet in Roll20.
- Roll20 owns combat-sheet state.
- Fardecosmia owns world/campaign state.
- Player knowledge is not equal to objective truth.
- GM-only data must remain server-side protected.
- Campaign time is an internal simulation timeline.
- One Turn is the 168-hour day of the world. It contains seven 24-hour light phases; a year contains 52 Turns. Do not present a 24-hour phase as a separate world day.
- Regional longitude shifts local Turn time and the local light/Face phases. Star light circles the map in one Turn; Ympha light circles it in 16 Turns.
- Regional climate uses base temperature, seasonal amplitude, humidity, elevation and weather volatility.
- A GM-supplied planet-level average-temperature raster exists and feeds regional base temperature through a technical sampled grid. Unpainted biome/elevation cells remain unknown.
- Weather is continuous, stateful and historical.
- World advancement can drive weather, events, clocks, NPCs, factions and travel.
- Important changes should be auditable.
- Random simulation must not mutate world state merely because a page was viewed.
- Missing lore must remain unknown, not be invented.

When uncertain whether something is canon, treat it as **UNKNOWN** and build a configurable extension point rather than inventing an answer.

---

# 44. Confirmed global map and local season implementation

## New GM-provided source data

- The supplied `Temperature.png` is the authoritative average-temperature raster for the full equirectangular world map.
- Its own displayed scale runs from `−97.2°C` to `+74.6°C`.
- The application contains a mechanically sampled `360 × 180` numeric grid derived from that raster and its own palette. This grid is a technical digitisation of the supplied source, not invented climate canon.
- The supplied `ElevationMap.png` is the authoritative elevation raster currently available to the application. Its displayed discrete scale runs from `−29 м` to `6365 м`; the application mechanically samples those legend values into a `360 × 180` grid.
- Ocean cells and cells hidden by the elevation source's own on-image legend remain `UNKNOWN` (`null` in the sampled elevation data). The application must not convert the ocean colour into a height or wrap/extrapolate terrain into the hidden strip.
- The supplied `LandMap.png` is the authoritative editor mask in the same projection. It remains visually invisible and permits biome painting only in cells classified as land.
- The supplied `DarkDay.jpg`, `DarkNight.jpg`, `LightDay.jpg` and `LightNight.jpg` define visual targets for brightness/colour only. Their depicted terrain, suns and cities are not world geography canon.
- The supplied rain and snow GIFs are presentation assets only. They do not define simulation probabilities.

## Map data layers

- The top navigation contains a campaign-independent physical atlas for GMs. It has surface, average-temperature, elevation and biome modes. It deliberately has no campaign time or campaign regions.
- A campaign map has current light, average-temperature, elevation and biome modes plus that campaign's region contours.
- Average temperature comes from the GM raster.
- Elevation comes from the GM raster, with optional shared GM-authored corrections. Biomes are a shared sparse objective-world layer in `world.GlobalWorldMapLayer`, not one copy per campaign.
- `world.WorldMapLayer` is retained only as recoverable legacy storage for pre-migration campaign drawings; current atlas reads and writes use the shared layer.
- An unpainted biome cell means `UNKNOWN`; code must not fill it from Earth assumptions.
- Map layer editing and region pages are GM-only because they expose objective world state.
- The common atlas is also server-side GM-protected. A user may open it when they are GM in at least one campaign; hiding buttons in the frontend alone is not the permission boundary.
- Viewing a map or region remains read-only; saves happen only through explicit POST actions.
- When a new region contour is drawn, the browser may suggest base temperature and elevation from the rasters and biome from the shared painted layer. GM can adjust the resulting fields before saving.

## Local season labels

- `Светлое Лето`, `Тёмная Зима`, and similar labels are local to longitude, just like local Ympha visibility.
- Classification examines all 13 Витков of the local season and counts those that pass the campaign's configured Red Turn visibility threshold.
- `Campaign.light_season_min_red_turns` and `Campaign.dark_season_max_red_turns` are GM-configurable technical thresholds. Values between them produce a Mixed season.
- The strength with which this local Light/Dark season affects a region's temperature is configured by `Region.season_light_temperature_influence`; its default is technical, not immutable canon.

## Weather configuration boundary

- Weather generation now uses local season, longitude-dependent light/Ympha, supplied map temperature, region elevation, humidity/dryness, precipitation bias, persistence and volatility.
- `Campaign.season_weather_modifiers` stores editable seasonal humidity/precipitation coefficients. Its defaults implement the confirmed qualitative descriptions (Autumn storms/fog, Winter cold/snow opportunity, Spring floods) but remain technical values that GM may replace.
- Snow still requires freezing local temperature and sufficient precipitation conditions; Winter raises its opportunity rather than forcing snow in every region.
- Weather transitions still happen only at the region's configured simulation boundaries, not on every small time advance.

---

# 45. P4.5 account and Campaign lifecycle foundation

P4.5 is completed. A normal user can register without Django Admin, verify a
required transactional email with a hashed six-digit challenge, recover a
password, create a Campaign and join one through a secure invitation.

Project boundaries:

- verified email is the transactional contact foundation, not a Campaign role;
- Campaign authority remains in `CampaignMembership`;
- a verified Campaign creator atomically receives the initial GM membership;
- invitations are email-bound, single-use, expiring tokens stored only as a
  slow hash plus lookup prefix;
- accepting an invitation creates a PLAYER membership and is not an
  `ApprovalRequest`;
- a Campaign can never lose its final GM through normal role-management paths;
- campaign creation, invitation lifecycle and membership changes are P3 domain
  audit actions;
- registration, verification, login, password reset and other security activity
  are not world `AuditLog` events;
- no authentication code, reset token or invitation token may enter AuditLog.

Existing pre-P4.5 users are not falsely marked verified. Legacy accounts remain
usable for their existing memberships, while transactional actions such as
normal Campaign creation require a verified contact email. Staff/superuser
compatibility is preserved for administration; it does not replace
CampaignMembership authority.

Current next named roadmap phase is P5 WorldEvent, but it must not be started
without a separate explicit GM instruction.
