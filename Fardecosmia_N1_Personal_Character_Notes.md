# Фардекосмия — N1
# Personal Character Notes / Held Thoughts Foundation

Дата подготовки: 2026-08-25  
Статус: implementation specification  
Рекомендуемый Codex Reasoning: **High / Высокий**

## 0. Цель

N1 превращает блок `Заметки` в первую полноценную интерактивную Character-facing систему.

Нарративная модель:

```text
Character
↓
устремляет восприятие в промежуточную реальность
↓
видит удержанные мысли / следы памяти
↓
может удержать новую мысль
```

Личная заметка — не запись игрока для GM и не административный объект. Это отражение мысли/памяти самого Character.

## 1. Язык интерфейса

Не использовать Player-facing формулировки:

```text
Заметки игрока
Ваш персонаж знает
Создать заметку
Title
Content
Save
Author
Created at
Updated at
Visibility
```

Использовать:

```text
Удержанные мысли
Удержать мысль
Памятка
Что вы хотите сохранить в памяти?
Удержать
Вернуться к мысли
Отпустить
```

Platform shell (`Кампании / Настройки / Выйти`) остаётся meta-layer.

## 2. Обязательный аудит

До изменений перечитать:

- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- Architecture Guardrails
- `Fardecosmia_Player_Experience_Architecture_v1.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`
- `L1_CHARACTER_LOCATION_INITIAL_PLACEMENT_REPORT.md`
- `PW2_LIVE_CHARACTER_AMBIENCE_REPORT.md`

Проаудировать Character/controller/active Character, reassignment/unassignment/archive, Workspace routes/templates, Notes placeholder, AuditLog visibility, admin, escaping, migration graph и development DB.

Не создавать Party Notes и generic visibility model.

## 3. Ownership / privacy

Personal Note принадлежит **Character**, не User:

```text
Character
└── Personal Notes
```

При reassignment мысли остаются у Character, старый controller теряет доступ, новый получает.

При unassignment/archive мысли сохраняются.

## 4. GM boundary

Campaign GM НЕ должен иметь обычного доступа к личным мыслям:

- не читать;
- не искать;
- не редактировать;
- не удалять;
- не видеть excerpts/title/content;
- не видеть это через Campaign Audit UI.

Предпочтительно вообще не регистрировать содержимое Personal Notes в обычном Django admin.

## 5. AuditLog privacy exception

Personal Notes — не объективная world mutation.

Create/edit/release Personal Note НЕ писать в Campaign AuditLog, потому что сам факт/время существования заметки уже раскрывает GM внутреннюю активность Character.

Нельзя помещать туда title/body/excerpt.

## 6. Модель

Предпочтительно:

```text
CharacterNote
-------------
character      FK -> Character
memo           optional short text
body           required plain text
created_at     technical only
updated_at     technical only
```

Не добавлять:

```text
visibility enum
GM-visible flag
party flag
author User
source
knowledge level
tags
attachments
Settlement/Quest/NPC/WorldEvent FK
```

Party Notes позже — отдельный Party-domain state.

## 7. Ограничения данных

Plain text only.

Рекомендуемо:

```text
memo <= 120 chars
body <= 16–32 KiB
```

Переносы строк сохранять. HTML не рендерить как safe.

## 8. Даты

`created_at/updated_at` можно хранить технически для ordering/diagnostics.

Но Character-facing UI НЕ показывает даты вообще.

Если Character хочет помнить дату, он пишет её сам внутри мысли.

## 9. Визуал списка

Не таблица и не обычные DB cards.

Мысли — приятные воздушные блоки:

- полупрозрачные;
- мягкая размытая граница;
- внутреннее свечение;
- лёгкий outer glow;
- variable height;
- memo крупнее, если есть;
- body preview;
- без metadata/footer/date.

Допустимое ощущение:

```text
        ·          ✦

     Северные болота

  Торговец всё-таки
  что-то скрывал...

          ·
```

## 10. Airy motion

Допустим очень лёгкий:

```text
1–3 px drift
slow glow breathing
```

Но без хаоса, overlap и random server-side positioning.

Hover/focus может слегка «собирать» мысль.

`prefers-reduced-motion: reduce` обязателен: drift/motion исчезают, static glow остаётся.

## 11. Workspace preview

Главная карточка `Заметки` показывает максимум 2–3 последние мысли.

Без дат/counts/IDs.

Пример:

```text
ЗАМЕТКИ

«Нужно ещё раз поговорить с Мирой...»
«Старый мост»
«Торговец чего-то боится...»

[Все мысли]   [Удержать мысль]
```

## 12. Создание — НЕ обычная форма

Ключевое правило: normal create flow не должен выглядеть как `Название / Текст / Сохранить`.

Нажатие:

```text
Удержать мысль
```

переводит интерфейс в focused conversational state: остальной Workspace мягко приглушается/размывается, но accessibility/focus остаются правильными.

## 13. Шаг 1 — памятка

Первый вопрос:

```text
Желаете дать памятку этой мысли?
```

Можно:
- ввести короткую памятку;
- выбрать `Оставить без памятки`.

Не показывать label `Название`.

## 14. Шаг 2 — сама мысль

Затем:

```text
Что вы хотите сохранить в памяти?
```

Появляется свободное многострочное пространство.

Не показывать `Текст заметки:` и обычный form-card UI.

## 15. Эффект появления текста

Во время ввода допустим короткий мягкий glow/fade.

Но:
- без задержки keystrokes;
- без медленной typewriter-анимации;
- не ломать русский ввод/IME;
- reduced motion отключает эффект;
- JS не является source of truth.

Лучше CSS enhancement, а не собственный JS text renderer.

## 16. Завершение

Главное действие:

```text
Удержать
```

После успешного POST допустима короткая анимация: текст собирается/светится и становится новой воздушной мыслью.

Не делать длинную заставку.

## 17. Progressive enhancement

Backend остаётся обычным безопасным Django POST flow:

- CSRF;
- semantic/ARIA labels;
- keyboard navigation;
- правильный focus management;
- validation errors;
- no-JS fallback остаётся usable и стилизован как вопросы, не admin CRUD.

## 18. Открытие мысли

При выборе мысль становится центром внимания:

```text
selected thought expands/focuses
other thoughts fade/blur
full body visible
```

Можно отдельной server-rendered detail page; не нужен SPA router.

## 19. Detail

Показывать только memo (если есть) и full body.

Не показывать dates, IDs, author, Campaign, privacy badge.

Действия:

```text
Вернуться к мысли
Отпустить
```

## 20. Editing

`Вернуться к мысли` = изменить уже удержанную мысль.

Edit UX остаётся focused/conversational, с уже заполненными значениями.

Только current active controller; POST+CSRF.

## 21. Release/delete

Character-facing action:

```text
Отпустить
```

Обязательно подтверждение:

```text
Отпустить эту мысль?

Она больше не останется среди удержанных мыслей.

[Оставить]   [Отпустить]
```

Удаление только POST. GET не мутирует.

## 22. Active Character semantics

Все Notes routes работают только через текущий active Character.

Если switch A → B, notes index/preview сразу отражают B.

Не кешировать по одному User/Campaign.

Create POST не должен принимать trusted `character_id`; owner определяется backend через authenticated user → CampaignMembership → active Character.

## 23. IDOR / reassignment

Note detail/edit/release fetch одновременно scoped to:

```text
Campaign
active controlled Character
note id
```

Обязательный тест:

```text
Player A контролирует Character
→ видит мысли

Character reassigned Player B
→ A теряет доступ
→ B получает доступ
→ note rows/content не меняются
```

## 24. Archive/unassignment/User deletion

Notes survive:

- Character archive;
- owner removal;
- User deletion, если Character сохраняется.

Ordinary Player не читает их пока Character ему не доступен.

## 25. XSS

Plain text escaped.

Тестировать `<script>`, `<img onerror>` и подобное.

Никакого `|safe`.

## 26. Routes

Предпочтительно Campaign-scoped Character-facing routes, например:

```text
/campaigns/<campaign>/thoughts/
/campaigns/<campaign>/thoughts/hold/
/campaigns/<campaign>/thoughts/<opaque-id>/
/campaigns/<campaign>/thoughts/<opaque-id>/return/
/campaigns/<campaign>/thoughts/<opaque-id>/release/
```

Player не передаёт Character ID.

## 27. Query/performance

Workspace preview максимум 2–3 rows.

Full Notes page — pagination (примерно 20–30) вместо unlimited render.

No search/tags/folders in N1.

## 28. Browser verification

Desktop 1280 + mobile 390×844.

Проверить:

1. empty Notes block;
2. `Удержать мысль`;
3. вопрос про памятку;
4. create with memo;
5. create without memo;
6. body looks like free text, not form;
7. subtle text appearance;
8. thought becomes airy block;
9. open focused thought;
10. edit;
11. release confirmation;
12. no dates;
13. no GM/meta labels;
14. GM direct URL denied;
15. another Player denied;
16. reassignment transfers access;
17. Character switch changes notes;
18. keyboard/focus;
19. reduced motion;
20. no console errors/overflow;
21. PW2 ambience remains compatible behind Notes UI.

Delete only isolated browser data afterward.

## 29. Focused tests

Минимум:

1. create with memo;
2. create without memo;
3. body required;
4. size limits;
5. controller list/detail;
6. GM denied;
7. foreign/same-Campaign other Player denied;
8. forged note denied;
9. create cannot choose arbitrary Character;
10. reassignment transfers access;
11. unassignment preserves rows/removes access;
12. archive preserves rows;
13. User deletion preserves note with surviving Character;
14. Character switch changes source;
15. edit controller-only;
16. release POST-only;
17. release scoped;
18. XSS escaped;
19. dates absent;
20. Campaign AuditLog does not leak note existence/content;
21. preview bounded;
22. pagination;
23. reduced motion;
24. PW2 ambience compatibility.

## 30. Migration safety

До migration снять baseline Character/owner/archive/location/Roll20 counts.

Migration additive only.

После:
- existing Characters unchanged;
- locations unchanged;
- Roll20 unchanged;
- zero notes auto-created.

## 31. Admin

Предпочтительно CharacterNote не регистрировать в ordinary Django admin.

Если project policy требует — только superuser diagnostic metadata, без нормального content browser и mutation bypass.

## 32. Regression

Known baseline после PW2:

```text
458 tests
OK
skipped=9
```

Run:
1. focused N1;
2. P5.5 ownership/reassignment;
3. PW1 Workspace;
4. L1;
5. PW2;
6. P5.6 if membership services touched;
7. related regression;
8. full suite.

Final:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
git status
```

## 33. Docs

Обновить:

- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- Architecture Guardrails
- Player Experience Architecture
- Master Roadmap

Permanent rules:

```text
Personal Notes belong to Character, never User.
Personal Notes are private from Campaign GM.
Personal Note content/existence is not Campaign AuditLog material.
Reassignment transfers access with Character.
Party Notes will be separate Party domain.
Player-facing Notes use held-thought UX, not generic CRUD.
Player-facing dates are not displayed.
Notes are plain text and escaped.
```

Mark `[x] N1`.

## 34. Checkpoint protocol

Immediately create:

```text
docs/N1_PROGRESS.md
```

Milestones:

```text
Phase 0 privacy/model audit
↓ checkpoint
Model + migration
↓ checkpoint
Authorization/query services
↓ checkpoint
Held-thought UX
↓ checkpoint
Focused tests
↓ checkpoint
Related regression
↓ checkpoint
Browser desktop/mobile
↓ checkpoint
Full suite + docs + report
```

## 35. Final report

Create:

```text
N1_PERSONAL_CHARACTER_NOTES_REPORT.md
```

Include baseline, model, privacy, AuditLog decision, migration/preservation, reassignment, routing, conversational create flow, airy visual design, text effect, detail/edit/release, no-date decision, XSS, admin, pagination/performance, reduced motion, PW2 compatibility, tests/browser/full suite, known limitations and scope confirmation.

## 36. Explicit out-of-scope

DO NOT START:

```text
Party Notes
P6 Party
M2/V1
M4 Player Map
Travel
Quests
XP
Soul HUD
Тиамана mechanics
Inventory
Ledger
Economy
Roll20 normalized sync
Apotheosis/Craft
C5/C6/C7
CharacterKnowledge
AI summaries
attachments/images
rich text
tags/folders/search
```

## 37. Acceptance criteria

N1 complete only if:

- Personal Note belongs to Character;
- no User ownership field;
- GM/other Players cannot read;
- reassignment transfers access;
- unassignment/archive preserve rows;
- Character switch changes visible thoughts;
- create cannot choose arbitrary Character;
- Campaign AuditLog does not leak notes;
- no Player-facing dates;
- create is conversational, not generic form;
- step 1 = optional `Памятка`;
- step 2 = `Что вы хотите сохранить в памяти?`;
- completion = `Удержать`;
- airy blocks are used;
- focused detail exists;
- `Отпустить` is confirmed destructive action;
- plain-text/XSS safety;
- reduced motion works;
- PW2 ambience remains compatible;
- desktop/mobile clean;
- focused/related/full suite green;
- docs/report updated;
- next phase not started.

## 38. Stop condition

After N1 report and validation, STOP.

Do not begin Party, Party Notes, M2/V1, Player Map, Travel, XP/HUD, Economy or any other future phase automatically.
