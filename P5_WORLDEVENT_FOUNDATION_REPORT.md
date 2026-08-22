# P5 WORLDEVENT FOUNDATION REPORT

1. **Pre-P5 full-suite baseline.** После P4.5.1: 338 tests, 346.220 s,
   `OK (skipped=4)`. Countdown resend был частью этой зелёной базы.
2. **Existing WorldEvent audit.** Найдена одна существующая модель
   `world.WorldEvent`; конкурирующей event architecture не было. Она смешивала
   mutable schedule и факт срабатывания.
3. **Existing model fields/semantics.** До P5: Campaign, optional Region, title,
   description, integer `trigger_at`, planned/triggered/cancelled status,
   legacy `visible_to_players`, `triggered_at`. Отдельного occurrence не было.
4. **Existing migrations/services/usages.** Таблица появилась в
   `world/0001_initial.py`; `advance_world()` выбирал planned `(old,new]` и делал
   `bulk_update`; dashboard и TimeAdvanceReport читали тот же mutable row;
   Django Admin разрешал прямое редактирование. Форм/отдельного event service и
   audit integration не было.
5. **Existing DB row audit.** В development DB до P5 было 0 WorldEvent rows, но
   миграция всё равно поддерживает непустые environments.
6. **Existing TimeAdvanceReport integration.** Старый compact JSON содержал
   definition `id`, title, trigger time и Region label. Шаблон не требовал
   отдельного occurrence.
7. **Chosen migration/evolution strategy.** Существующая таблица сохранена и
   эволюционирована как definition/schedule; добавлена одна новая immutable
   `WorldEventOccurrence`. Destructive replacement не применялся.
8. **Changed files.** Изменены `world/models.py`, `world/admin.py`,
   `world/forms.py`, `world/views.py`, `world/urls.py`, `world/services/time.py`,
   `world/services/time_reports.py`, `world/templatetags/audit_json.py`,
   `campaigns/views.py`, GM dashboard/quickbar/report/base templates,
   `static/css/app.css`, AGENTS/handoff/guardrails/roadmap. Добавлены
   `world/services/events.py`, migration 0020, пять event templates, P5 tests и
   rollback-only benchmark.
9. **Migrations.** Добавлена и применена
   `world.0020_worldevent_foundation`: additive fields/indexes, occurrence table,
   one-shot uniqueness и safe data migration.
10. **Old-data preservation proof.** Migration test откатывает schema к 0019,
    создаёт planned/triggered legacy rows, накатывает 0020 и доказывает сохранение
    обоих definitions и создание occurrence для triggered row.
11. **Definition/schedule model semantics.** `WorldEvent` хранит mutable
    campaign-scoped intention: event type, registered trigger/config/version,
    schedule, optional effect, active state, target/location and revision.
12. **Occurrence model semantics.** `WorldEventOccurrence` хранит objective fact:
    durable human snapshots, exact world minute, source/actor, trigger/effect
    versions/results, target/location and operation UUID.
13. **Campaign scope.** Definition и occurrence обязаны принадлежать Campaign;
    Region и campaign-bound generic target проверяются на тот же Campaign.
14. **Event type strategy.** Production-safe baseline type — namespaced
    `narrative.event`; неизвестные namespaced labels остаются расширяемыми без
    придумывания gameplay semantics.
15. **Trigger registry.** Trigger handlers зарегистрированы по `(type, version)` и
    имеют validator/presenter. Произвольное condition evaluation отсутствует.
16. **MANUAL trigger.** GM запускает manual definition только явным POST либо
    human-first “Записать событие сейчас”; сохраняется текущий world minute.
17. **WORLD_TIME trigger.** Due lookup использует Campaign, enabled, one-shot,
    WORLD_TIME и indexed `trigger_at`.
18. **Crossing `(old,new]` proof.** Tests покрывают before T1, `==T1`, inside,
    `==T2`, after T2 и zero advance. Срабатывают только inside и T2.
19. **Deterministic ordering.** Query order — `trigger_at`, затем stable database
    `id`; отдельный same-minute test подтверждает порядок.
20. **One-shot/idempotency strategy.** Definition row lock + exclusion existing
    occurrences + conditional unique constraint на non-null definition.
21. **Definition revision/versioning.** Definition начинает с revision 1 и
    увеличивает её при edit/disable; occurrence snapshot фиксирует использованную
    revision.
22. **Trigger versioning.** Stored `trigger_version` и immutable occurrence
    snapshot; неизвестная версия не исполняется молча.
23. **Effect registry.** Effects доступны только через explicit registered
    validator/presenter/apply handler; arbitrary model-field setter отсутствует.
24. **Effect versioning.** Definition и occurrence хранят effect type/version;
    неизвестный handler останавливает выполнение безопасно.
25. **Generic narrative event.** `effect_type=null` создаёт историю без
    автоматической мутации других доменов.
26. **Effect atomicity.** Effect, immutable occurrence, domain audits и
    `world_event.occurred` находятся в одной transaction boundary.
27. **Failed-effect rollback proof.** Test мутирует Campaign и пишет domain audit,
    затем бросает ошибку; Campaign, occurrence, audits, report и time advance
    полностью откатываются.
28. **operation_id propagation.** На одно срабатывание создаётся UUID, который
    передаётся effect handler и обеим audit rows.
29. **Occurrence immutability.** Instance save/delete и QuerySet update/delete
    отклоняются; Admin read-only; normal UI не имеет edit/delete occurrence.
30. **Definition update/disable/delete behavior.** Изменения идут через audited
    services. Disable убирает future execution. Delete удаляет только planning
    row; occurrence остаётся с `definition=NULL` и snapshots.
31. **Target/location strategy.** Optional generic target — только контекст,
    никогда не implicit permission to mutate. Optional Region/lat/lon имеют
    durable labels/coordinates.
32. **Deleted-target history behavior.** Regression test удаляет Region/generic
    target и подтверждает, что occurrence читается по snapshot labels/coordinates.
33. **Source/actor snapshots.** Manual = USER + real actor + label; WORLD_TIME =
    SYSTEM + `actor=NULL`, без fake system user.
34. **World-time vs real-time semantics.** `occurred_world_minutes` — campaign
    truth; `occurred_at` — secondary real timestamp фиксации.
35. **advance_world integration.** Due events выполняются один раз на high-level
    interval после weather calculation и до report/audit commit, внутри прежней
    Campaign row-lock transaction.
36. **Exact-mode event behavior.** Exact advance вызывает тот же interval service
    и report получает реальные occurrence rows.
37. **Fast-forward event behavior.** Skipped weather interval всё равно пересекает
    все safe WORLD_TIME events; подробная WeatherState history не выдумывается.
38. **Exact-vs-FF equivalence proof.** Два Campaign с одинаковыми narrative
    schedules и разными thresholds дают одинаковые title/type/time/order sets.
39. **Simulation-coupled-effect limitation.** Effects, которым нужно изменить
    атмосферу внутри skipped interval, не зарегистрированы: для них понадобится
    future split-at-event-boundary simulation.
40. **TimeAdvanceReport integration.** Report сохраняет occurrence ID, title,
    exact minute, event/type label и location label без полного payload.
41. **Historical report compatibility.** Legacy `id/trigger_at/region_name` keys
    сохранены; test рендерит старый JSON без `occurrence_id`.
42. **P3 AuditLog integration.** Definition create/update/disable/remove и
    occurrence используют centralized `record_audit()`.
43. **Human audit summaries.** Примеры: “Запланировано событие …” и “Событие …
    произошло.”; raw payload и секреты не копируются.
44. **P4 boundary confirmation.** Event scheduling не использует
    ApprovalRequest; P4 intent workflow не изменён.
45. **CharacterKnowledge visibility boundary.** Objective event UI строго GM-only;
    legacy `visible_to_players` не считается publication boundary.
46. **GM events list.** Добавлена страница с tabs Upcoming/Occurred/Disabled/All и
    empty states.
47. **Upcoming events UI.** Карточка сразу показывает active state, what/when,
    remaining game time, location и consequence.
48. **Occurrence history UI.** История показывает immutable facts, formatted
    world time, location и human cause.
49. **Definition detail.** What, trigger/time, place, consequences, actions,
    occurrence history и collapsed technical details.
50. **Occurrence detail.** What happened, formatted world time, place, cause,
    consequence, source и AuditLog operation group.
51. **Manual event UI.** Есть “Записать событие сейчас” и explicit “Запустить
    сейчас” для manual definitions; raw JSON не запрашивается.
52. **Human trigger/cause presentation.** Internal MANUAL/WORLD_TIME заменены
    понятными текстами в primary UI.
53. **Collapsed technical details.** IDs, UUID, versions и JSON находятся только
    в закрытом `<details>`.
54. **Mobile/responsive behavior.** Browser viewport 390×844: body/document
    scroll width 375 px, горизонтального overflow нет; technical blocks закрыты.
55. **Permission matrix.** Own GM и superuser разрешены; player, foreign GM и
    Canon Editor-only получают denial.
56. **Player denial.** Прямая event URL возвращает 403; player campaign page не
    содержит Events link.
57. **Canon Editor boundary.** `world.manage_global_canon` не даёт Campaign event
    authority.
58. **IDOR tests.** Campaign A GM получает 404 для Campaign B definition и
    occurrence IDs даже через URL Campaign A.
59. **Secret/payload limits.** Trigger/effect/result objects ограничены 64 KiB,
    проходят deterministic JSON round-trip и P3 secret-key rejection; non-JSON,
    token-like and oversized payload tests присутствуют.
60. **Event crossing tests.** Boundary matrix, zero, deterministic ordering,
    disabled and one-shot replay covered.
61. **Manual trigger tests.** Current minute, GET no mutation, POST one occurrence,
    repeated POST, UI creation and actor/source covered.
62. **Effect tests.** Validation, apply once, grouped audits, failure rollback,
    unknown handler and missing target covered test-only handler.
63. **Immutability tests.** Instance/QuerySet/Admin immutability plus definition
    rename/delete and deleted target history covered.
64. **TimeAdvanceReport tests.** Exact/FF actual occurrences, compact payload,
    old JSON rendering and one advance audit invariant covered.
65. **Existing-data migration tests.** Planned and triggered 0019 rows are tested
    through real MigrationExecutor forward migration.
66. **PostgreSQL concurrency tests/skips.** Два TransactionTestCase проверяют
    concurrent advance и manual trigger. На SQLite они explicit skipped; final
    PostgreSQL CI должен исполнить их.
67. **Browser/manual verification.** Passed: empty, schedule, before boundary,
    crossing, report link, history/detail, disable, record now, player denial,
    mobile and console inspection.
68. **5-second readability acceptance.** Upcoming и occurrence DOM snapshots
    показывают what/when/where/cause/consequence without opening technical data.
69. **Query counts.** Rollback benchmark: zero due 1 query; ten-upcoming lookup 1;
    crossing ten events 48; list 5; detail 5.
70. **Performance.** Development machine: zero due median 0.980 ms, ten upcoming
    lookup 1.258 ms, crossing ten events 19.149 ms, list 5.180 ms, detail 4.196 ms.
71. **Tests added.** `world/tests/test_world_events_p5.py`: 27 tests total,
    including two PostgreSQL-only race tests.
72. **Full test result.** 365 tests in 442.374 s: `OK (skipped=6)`.
73. **manage.py check.** 0 issues.
74. **makemigrations --check --dry-run.** `No changes detected`.
75. **git diff --check.** Exit 0; no whitespace errors (only Windows LF/CRLF
    informational warnings).
76. **P3 regression.** Full suite green; append-only audit semantics preserved.
77. **P4 regression.** Full suite green; approval services/models untouched.
78. **P4.5 regression.** Full suite green; onboarding/email/Campaign lifecycle
    unchanged.
79. **P4.5.1 resend-countdown regression.** Existing countdown JS/backend tests
    remain in the 365-test green suite; onboarding asset remains loaded.
80. **M1 regression.** Full suite green; Leaflet CRS/tiles/map services untouched.
81. **R1 regression.** Full suite green; area/point weather lifecycle untouched.
82. **Atmosphere/C4.2 regression.** Full suite green; solver/snapshot/precipitation
    and point-pressure code untouched.
83. **External atmospheric tendencies unused.** No production event effect is
    connected to atmospheric forcing; only high-level safe narrative scheduling
    is active.
84. **WORLD_HANDOFF update.** Added P5 definition/occurrence, crossing,
    atomicity/report/visibility and future simulation-boundary rules.
85. **AGENTS update.** Added permanent WorldEvent audit, immutability, registry,
    atomicity, crossing and CharacterKnowledge rules.
86. **Guardrails update.** WorldEvent section now records implemented P5 boundary
    and prohibits pub/sub/event-sourcing/arbitrary mutation misuse.
87. **Master Roadmap update.** P5 foundation checked complete; recurrence,
    publication, cross-Campaign/global and simulation-coupled extensions remain
    explicitly open.
88. **Known limitations.** One-shot only; Campaign scope only; no recurrence/end
    interval, polygon overlay, player publication or simulation-coupled effects;
    old status/visible fields remain compatibility data.
89. **Future Travel path.** Travel domain may create departure/arrival occurrences
    through registered services; not implemented in P5.
90. **Future Quest path.** Quest transitions may later create/react to occurrences;
    not implemented in P5.
91. **Future CharacterKnowledge path.** Objective occurrence → explicit
    publication/propagation → CharacterKnowledge → player-safe history.
92. **Future recurrence path.** Requires separate semantics/constraints rather
    than weakening current one-shot uniqueness.
93. **Future simulation-coupled event path.** Advance must split at event world
    minute, apply forcing/effect, then resume physics; current P5 intentionally
    does not simulate this.
94. **Scope confirmation.** CharacterKnowledge, M2, Travel, Inventory/Ledger,
    Quest implementation and C5 were not started.

P5 stops here.
