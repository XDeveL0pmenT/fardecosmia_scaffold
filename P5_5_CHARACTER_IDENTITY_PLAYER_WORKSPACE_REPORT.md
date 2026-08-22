# P5.5 CHARACTER IDENTITY & PLAYER WORKSPACE REPORT

Дата завершения: 2026-08-22.

## 1. Pre-phase full-suite baseline

До изменений P5.5 полный набор содержал 365 тестов. Результат: `OK (skipped=6)`, время выполнения 313.643 s. Это состояние использовалось как regression baseline.

## 2. Existing Character audit

До миграций был выполнен аудит приложения `characters`, связей с `campaigns`, Roll20, admin, templates, services, tests и локальных строк БД. В проекте уже существовала единственная модель `characters.Character`; конкурирующая модель не создавалась. Отдельных пользовательских Character views/forms/services/tests на baseline не было.

## 3. Existing models/fields

До P5.5 `Character` содержал `campaign`, nullable `owner`, `name`, `biography`, `public_notes`, `gm_notes`, `portrait`, `created_at`, `updated_at`. Механические поля листа D&D в него не добавлялись. P5.5 добавил только `is_active` и `archived_at` для недеструктивного жизненного цикла.

## 4. Existing ownership/controller semantics

`owner` уже ссылался на `CampaignMembership` с `SET_NULL`, поэтому он был сохранён как достаточное отношение «один текущий controller». Новая assignment-модель не вводилась. Контроль остаётся campaign-scoped и не меняет роль пользователя.

## 5. Existing Campaign relation

`Character.campaign` остаётся обязательным FK на `Campaign` с существующим lifecycle. Персонаж не стал глобальной сущностью; все выборки и mutations ограничиваются конкретной кампанией.

## 6. Existing Roll20 binding audit

Существующая `Roll20CharacterBinding.character` — optional OneToOne со стратегией `SET_NULL`. Binding, explicit Roll20 character ID, `raw_attributes` и `normalized_state` не менялись. Назначение игрока и Roll20 binding остаются независимыми отношениями; автоматического сопоставления по имени нет.

## 7. Existing DB row audit

Перед миграцией в development DB: 1 Character, assigned=1, unassigned=0, Roll20-bound=0, owner/campaign mismatch=0; распределение — одна кампания. После миграции та же строка сохранила PK, campaign и owner, получила безопасные defaults `is_active=True`, `archived_at=NULL`. Секреты и raw Roll20 payload в аудит не выводились.

## 8. Chosen evolution strategy

Существующая модель расширена без переименования таблицы и без destructive migration. `owner` используется как единственный controller, `CampaignMembership.active_character` хранит выбор пользователя в данной кампании, а архивирование заменяет normal hard delete.

## 9. Changed files

Созданы:

- `characters/forms.py`
- `characters/services.py`
- `characters/urls.py`
- `characters/views.py`
- `characters/templates/characters/gm_character_list.html`
- `characters/templates/characters/character_form.html`
- `characters/templates/characters/character_detail.html`
- `characters/templates/characters/player_character_list.html`
- `characters/tests/__init__.py`
- `characters/tests/test_character_identity_p55.py`
- `campaigns/migrations/0010_campaignmembership_active_character.py`
- `characters/migrations/0002_character_archived_at_character_is_active_and_more.py`
- `scripts/benchmark_character_p55.py`
- этот отчёт.

Обновлены `characters/models.py`, `characters/admin.py`, `campaigns/models.py`, `campaigns/admin.py`, `campaigns/services/memberships.py`, `campaigns/views.py`, campaign templates/navigation, `config/urls.py`, `static/css/app.css`, `templates/base.html`, `AGENTS.md`, оба WORLD_HANDOFF, architecture guardrails и Master Roadmap.

## 10. Migrations

Добавлены две schema migrations: nullable `CampaignMembership.active_character`, затем Character archive fields и индекс `(campaign, is_active, name)`. Dependency chain учитывает взаимные связи приложений и применён к development DB. Data migration с удалением/перепривязкой строк отсутствует.

## 11. Existing-data preservation proof

Проведена проверка development DB до/после применения миграций. Дополнительно `CharacterMigrationTests` через `MigrationExecutor` создаёт исторический Character с owner/campaign и Roll20 binding, мигрирует schema и проверяет сохранность PK, campaign, owner и binding. Тест проходит.

## 12. Character campaign-scope semantics

Все service operations сначала блокируют/проверяют нужную Campaign и GM authority. Character извлекается одновременно по `pk` и `campaign`; foreign Character не может быть прочитан или изменён через P5.5 endpoints.

## 13. Character/User control model

Цепочка: `User → CampaignMembership → Character.owner`. Роли GM/PLAYER остаются исключительно в membership. Удаление controller не удаляет Character; knowledge/state в User не добавлялись.

## 14. Multiple Character support

Один PLAYER membership может контролировать несколько Characters одной Campaign. Уникального ограничения «один User — один Character» нет. Каждый Character по-прежнему имеет максимум одного controller.

## 15. Active Character implementation

Nullable FK `CampaignMembership.active_character` хранит один active Character в контексте membership/campaign. `clean()` и service validation требуют ту же Campaign, текущий control и активный неархивный Character. Центральный helper — `characters.services.get_active_character(user, campaign)`.

## 16. Active selection persistence

Выбор через selector выполняется POST+CSRF и сохраняется в DB, поэтому работает между refresh и устройствами. Cross-campaign, foreign, unowned и archived значения отклоняются. Это не скрытая session-only истина.

## 17. Single-character default behavior

Если persisted selection отсутствует и доступен ровно один контролируемый Character, helper возвращает его как UI fallback, не мутируя DB во время GET. При первом назначении единственного Character service может безопасно сохранить его как active. При нескольких без корректного выбора активный Character намеренно не угадывается.

## 18. GM Character creation

Campaign GM и superuser могут создать базовую identity через supported service/UI. Player, foreign GM и пользователь только с global canon permission не могут. Создание atomic и audited; ошибка AuditLog откатывает Character.

## 19. Character basic fields

Форма P5.5 редактирует только `name` и optional `biography`. Existing notes/portrait не удалены, но P5.5 не расширяет upload pipeline и не показывает raw/internal поля как лист персонажа. STR/DEX/HP/class/spells отсутствуют.

## 20. Assignment service

`assign_character()` принимает точные campaign/character/membership identities, блокирует campaign, Character и затронутые memberships, затем валидирует same-campaign active PLAYER membership. Изменение owner, repair active state и AuditLog выполняются в одной transaction.

## 21. Reassignment

Reassignment очищает stale active selection предыдущего controller, сохраняет Character и Roll20 binding и назначает нового PLAYER. Новому controller Character автоматически становится active только когда у него нет другого доступного Character; при нескольких выбор не навязывается.

## 22. Unassignment

Передача `membership_id=None` снимает control, не удаляя Character. Если Character был active у прежнего controller, selection очищается. Повторный no-op не создаёт лишний audit row.

## 23. Membership-removal behavior

Supported P4.5 removal service явно unassigns Characters и очищает active selection в той же transaction. Создаются читаемые `character.unassigned`/`character.active_changed` и membership audit rows с общим operation ID. Character остаётся в Campaign и может быть назначен снова.

## 24. User-deletion behavior

При удалении User его membership удаляется существующей DB-семантикой, а nullable `Character.owner` становится NULL. Character и связанный Roll20 binding сохраняются; это закреплено тестом.

## 25. Archive/restore behavior

GM может архивировать и восстановить Character. Archive задаёт `is_active=False`, `archived_at`, очищает все active selections, но сохраняет owner, identity, историю и Roll20 binding. Archived Character не получает новое назначение и не выбирается active. Normal hard-delete UI не добавлен.

## 26. Roll20 binding preservation

Create/assign/reassign/unassign/archive/restore не создают и не изменяют binding. Тест archive/restore и migration preservation подтверждают его сохранность. Raw attributes не попадают в страницы и AuditLog serializer.

## 27. P2 access integration

Views используют существующие campaign membership/GM access boundaries и superuser override, а не роль на User. Player endpoints требуют PLAYER membership и control конкретного Character; GM endpoints работают только внутри управляемой Campaign.

## 28. Final permission matrix

- Campaign GM: list/create/read/edit/assign/unassign/archive/restore Characters своей Campaign.
- Player: list/read только контролируемых активных Characters и POST switch между ними.
- Foreign GM/Player: нет доступа к чужой Campaign/Character.
- Canon Editor-only: не получает campaign Character authority.
- Superuser: diagnostic/service override; normal admin mutation закрыта.

## 29. Player campaign dashboard

Dashboard показывает human-first блок «Ваш персонаж/Ваши персонажи», active identity, кнопку открытия и понятный selector при нескольких. Существующий блок «Мои запросы» сохранён. Для совместимости P4.5 страница явно говорит, что пользователь является участником Campaign.

## 30. Player Character list

Список содержит только активных Characters, которыми управляет current membership в current Campaign. Другие игроки и unassigned rows исключены. Active selection визуально отмечен; переключение доступно только там, где оно имеет смысл.

## 31. Player Character detail

Страница отвечает, какой это Character и в какой Campaign он используется. Future sections «Игровой лист», «Знания», «Инвентарь», «Квесты» обозначены как будущие без fake data. Player не видит GM notes, FK/DB IDs или raw Roll20 payload.

## 32. Character switcher

Switcher отправляет Character PK только как opaque POST target; backend заново проверяет campaign, owner и archive state. GET не меняет `active_character`, повторный выбор не спамит audit.

## 33. GM Character list

Campaign-scoped страница разделяет active и archive состояние, показывает readable owner либо «Игрок не назначен», lightweight Roll20 linked badge и основные actions. Empty state ведёт к созданию Character.

## 34. GM Character detail

Показывает identity, Campaign, readable controller, active/archive status и только факт Roll20 link. Доступны edit, assignment и archive/restore. Raw Roll20 JSON отсутствует.

## 35. GM assignment UI

Форма предлагает только PLAYER memberships той же Campaign. GM membership не предлагается как новое назначение; существующие legacy GM-owned Characters не разрушаются. Reassign и unassign имеют понятные подписи.

## 36. Empty states

Player без Character видит, что GM ещё не назначил персонажа и что он появится позже. GM без Character видит приглашение создать первый. Не создаются fake/placeholder DB rows.

## 37. Human-first readability

Нормальный UI использует Character и user display labels вместо внутренних identifiers. Actions описаны глаголами, archive предупреждает о сохранении истории, будущие функции обозначены без технических таблиц.

## 38. Mobile behavior

Проверено при viewport 390×844: cards stack, кнопки доступны для touch, длинный контент переносится, horizontal overflow отсутствует (`innerWidth=390`, document/body scroll width=375). Добавлены responsive character styles.

## 39. P3 AuditLog integration

Реализованы actions `character.created`, `character.updated`, `character.assigned`, `character.unassigned`, `character.active_changed`, `character.archived`, `character.restored`. Meaningful mutation и audit commit атомарно. GET/page views/no-op не аудируются.

## 40. Human audit summaries

Summaries называют Character и readable player label: например, назначение, переназначение и active switch описываются словами, а не как изменение `owner_id`. Explicit serializer включает базовую identity/campaign/controller/archive state, но исключает secrets и Roll20 raw state.

## 41. IDOR tests

Проверены denial для Player A→Character B, switch на чужой/foreign Character, foreign GM mutation, forged foreign membership, self-assignment Player и canon-editor-only authority. Нормальный UI также скрывает чужих Characters.

## 42. Character creation tests

Проверены own-campaign GM create, Player/foreign GM/canon editor denial, superuser override, обязательный campaign context, минимальные fields, audit row и rollback при audit failure.

## 43. Assignment tests

Проверены assign/reassign/unassign, same-campaign PLAYER validation, foreign/GM target rejection, archived target rejection, Player/foreign GM/editor denial, no-op audit suppression и rollback owner/active при audit failure.

## 44. Active Character tests

Проверены single fallback без GET mutation, persisted selection при multiple Characters, valid switch, foreign/unowned/archived rejection, а также stale-selection cleanup при reassignment, unassignment, archive и membership removal.

## 45. Archive tests

Проверены GM archive/restore, Player denial, сохранение Character row и Roll20 binding, запрет active selection/нового assignment archived Character и readable audit actions.

## 46. Deletion-relation tests

Проверены User deletion и supported membership removal: Character остаётся, owner становится NULL, active selection очищается, Roll20 binding сохраняется. CharacterKnowledge FK пока отсутствует по scope.

## 47. UI/permission tests

Проверены GM management visibility, Player denial, dashboard own active Character, empty/multiple states, controlled-only list/detail, отсутствие technical payload, POST-only switch, bounded query counts и diagnostic-only admin.

## 48. PostgreSQL concurrency tests/skips

Добавлен `TransactionTestCase` для competing GM assignment с real row locks. Он запускается на PostgreSQL и ожидаемо skipped на SQLite, где `select_for_update` не доказывает production locking semantics. Service использует `transaction.atomic()` и `select_for_update()` независимо от backend.

## 49. Browser/manual verification

На isolated local Campaign выполнены GM empty list → create Aérion → assign Player → create/assign Torvald → archive/restore; Player dashboard/list/detail → active switch → refresh persistence. После исправления campaign quickbar context console errors отсутствуют. Temporary Campaign/users затем точно удалены; production/user campaign data не затрагивались.

## 50. 5-second readability acceptance

Player сразу видит active Character, кнопку открытия и selector либо причину отсутствия. GM сразу видит Characters, assignment labels и create/assign/archive actions. Manual desktop/mobile flow подтвердил критерий.

## 51. Query counts

Rollback-only benchmark на development machine:

- Player dashboard: 9 queries, 35.983 ms.
- Player Character list: 9 queries, 11.844 ms.
- GM list с 20 Characters: 8 queries, 14.626 ms.
- GM Character detail: 12 queries, 15.121 ms.

Controller/user и Roll20 status загружаются через bounded `select_related`/prefetch paths; N+1 от количества rows не выявлен.

## 52. Performance

Assignment median: 5.736 ms. Active switch median: 4.255 ms. Benchmark выполняется внутри rollback и не оставляет тестовые данные. Атмосферный solver не запускался и не менялся.

## 53. Tests added

Добавлен focused module из 30 P5.5 tests, включая migration preservation и один PostgreSQL-only concurrency test. Последний focused result: 30 tests, 91.936 s, `OK (skipped=1)`.

## 54. Full test result

После всех исправлений: 395 tests, 502.437 s, `OK (skipped=7)`. Test database создана и уничтожена штатно.

## 55. manage.py check

`python manage.py check`: `System check identified no issues (0 silenced)`.

## 56. makemigrations --check --dry-run

Результат: `No changes detected`. Обязательные P5.5 migrations уже присутствуют и соответствуют моделям.

## 57. git diff --check

Exit code 0; whitespace errors отсутствуют. Git вывел только неошибочные Windows line-ending warnings LF→CRLF.

## 58. P5 regression

WorldEvent definitions/occurrences, exact/fast-forward integration, report и player denial остаются зелёными в полном suite. P5 target logic не менялась.

## 59. P4.5 regression

Отдельно выполнен `campaigns.tests.test_onboarding_p45`: 27 tests, 48.672 s, `OK (skipped=3)`. Signup/email/invitation/membership/last-GM flows не сломаны. Full suite также зелёный.

## 60. P4 regression

ApprovalRequest foundation покрывается существующим полным regression suite; P5.5 не меняет approval handlers/schema/UI. Все соответствующие тесты прошли.

## 61. M1 regression

Существующие map/world-data проверки прошли в полном suite. Models, samplers и map assets M1 не менялись.

## 62. R1 regression

Существующие Region/weather data-flow проверки прошли. `Region`, `WeatherState`, environment summary и sampling paths не менялись.

## 63. Atmosphere scope confirmation

AtmosphericGrid, snapshots, solver, coefficients, Region weather и C1–C4.2 код не менялись. Никакой climate calibration/benchmark не выполнялся.

## 64. CharacterKnowledge scope confirmation

CharacterKnowledge, rumor/known states, knowledge registry и event publication не реализованы. P5.5 предоставляет только durable Character identity и validated controller/active foundation.

## 65. CharacterSheet/Roll20 sync scope confirmation

CharacterSheet, stats, combat fields, sync protocol и Django→Roll20 commands не добавлены. Existing Roll20 adapter/storage semantics сохранены.

## 66. WORLD_HANDOFF update

`WORLD_HANDOFF.md` и `WORLD_HANDOFF_v2.md` зафиксировали завершение P5.5 и разделение Character/User, campaign-scoped control, explicit active selection, knowledge ownership и Roll20 boundaries.

## 67. AGENTS update

Добавлены постоянные правила: сначала audit existing Character; control только campaign-scoped; gameplay knowledge/state не хранится на User; identity не равна sheet/raw state; Player UI показывает только controlled Characters.

## 68. Guardrails update

Architecture handoff фиксирует: `Character != User`, identity != CharacterSheet, assignment != Campaign role, knowledge следует за Character при reassignment, Roll20 binding отделён от player control.

## 69. Master Roadmap update

P5 и P5.5 отмечены выполненными; K1 CharacterKnowledge и M2 остаются невыполненными. P5.5 расположен перед knowledge-dependent следующими этапами.

## 70. E3/E4 economy roadmap status

Future E3 Recurring Economy & Lifestyle и E4 Employment & Side Jobs сохранены в roadmap как unchecked future stages. В P5.5 они не реализовывались.

## 71. Known limitations

- P5.5 хранит одного controller через existing owner FK; party/multi-controller support отсутствует.
- Новые normal assignments разрешены только PLAYER memberships; legacy GM ownership сохраняется, но не предлагается UI.
- Single Character может быть UI fallback без persisted write на GET.
- Player self-creation/edit отсутствуют до Builder/Approval phase.
- Portrait upload pipeline не расширялся.
- PostgreSQL concurrency proof ожидаемо не исполняется на local SQLite.

## 72. Future K1 CharacterKnowledge path

Будущий K1 должен ссылаться на durable `Character`, читать active Character через central helper и отделять objective truth/player knowledge/GM-only data. Archive/reassignment не должны переносить знания на User или другой Character. K1 не начат.

## 73. Future normalized Character/Roll20 path

Будущий normalized state остаётся за versioned Roll20 integration boundary: raw attributes в binding, stable normalized values в `normalized_state`, explicit binding by Roll20 character ID, idempotent snapshot/delta events. Base Character остаётся identity/campaign anchor.

## 74. Future Character Builder path

Future Builder может создавать identity/player proposal через Approval workflow, но не должен обходить CampaignMembership authority или дублировать combat-sheet fields. В P5.5 Player creation намеренно отсутствует.

## 75. Confirmation no out-of-scope phase was started

K1/CharacterKnowledge, M2, CharacterSheet/Roll20 sync, Character Builder, Inventory, Ledger, Purchases, recurring economy, Travel, Quests и C5 не начинались. P5.5 завершён и работа остановлена на его границе.
