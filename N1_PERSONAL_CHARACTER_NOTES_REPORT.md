# N1 — Personal Character Notes / Held Thoughts Foundation — Final Report

Date: 2026-08-25
Status: **COMPLETE**

## 1. Outcome

N1 turns the PW1 Notes shell into a private Character-facing Held Thoughts
system. Thoughts belong to durable Character identity, follow that identity
between controllers and remain outside objective Campaign history. Campaign GM,
superuser diagnostic surfaces and other Players have no ordinary content or
existence browser.

Party Notes and every other future gameplay phase remain unimplemented.

## 2. Baseline and audit

Before schema work the development DB contained:

- 5 Users;
- 1 Campaign and 2 Memberships;
- 2 Characters: 1 active/assigned and 1 archived;
- 1 CharacterLocationState;
- 0 Roll20 bindings;
- 52 AuditLog rows;
- no CharacterNote table.

The code audit confirmed that `Character.public_notes` and `Character.gm_notes`
are legacy identity/GM fields with incompatible visibility semantics. They were
not repurposed. The existing ownership source remains
`Character.owner -> CampaignMembership`, and active selection remains the
central P5.5 `get_active_character()` boundary.

## 3. Model

`characters.CharacterNote` is additive and contains:

- opaque UUID primary key;
- `character` FK with `related_name="personal_notes"` and Character cascade;
- optional `memo`, max 120 characters;
- required `body`, max 32 KiB;
- technical `created_at` and `updated_at`;
- Character/time index;
- database non-empty-body constraint.

It has no User, author, visibility, GM-visible, Party, source, tags,
attachments, knowledge level or objective-world foreign key.

The explicit `MaxLengthValidator` on body is important: service-level
`full_clean()` does not rely on `TextField(max_length=...)` alone.

## 4. Ownership and privacy

Every read begins with:

```text
authenticated User
→ CampaignMembership in requested Campaign
→ role must be PLAYER
→ centralized active Character resolution
→ active Character must be controlled and active
→ note queryset filtered by that Character
```

GM membership is denied. A superuser does not receive an implicit Notes bypass.
Other Players and foreign Campaign users are denied. A valid UUID from another
Character returns no note.

Create accepts no Character ID. Forged `character` / `character_id` POST fields
are ignored because the backend resolves the current Character itself.

## 5. Mutation and locking

Create, edit and release are explicit domain services in `characters.notes`.
Each operation:

1. opens a transaction;
2. locks the Campaign row, sharing the serialization boundary used by supported
   assignment and active-selection flows;
3. re-resolves/revalidates the current PLAYER/Character relationship;
4. locks the Character and, for edit/release, the Character-scoped note;
5. validates escaped plain-text limits before persistence.

This prevents an old controller from retaining a supported write window across
a concurrent reassignment.

## 6. AuditLog privacy decision

Personal thoughts are not objective world/campaign mutations. Their create,
edit and release services deliberately do not import or call `record_audit()`.

Neither memo/body/excerpt nor note existence/activity enters Campaign AuditLog.
The focused lifecycle test proves the AuditLog count does not change across all
three mutations, and the GM audit page contains none of the supplied secrets.

Objective Character reassignment and active-selection changes continue to use
their pre-existing P3 audits. Those audits never include note content or note
existence.

## 7. Migration and preservation

Migration `characters.0004_character_note_n1` is one additive `CreateModel`
operation and contains no data migration.

The migration test carries existing CampaignMembership, active and archived
Characters, CharacterLocationState and Roll20 binding through 0003 → 0004. All
durable IDs/relationships remain unchanged and zero notes are auto-created.

After applying 0004 to the development DB, every pre-migration count was
unchanged and the new table contained zero rows.

## 8. Reassignment, unassignment, archive and User deletion

Because the FK is on Character rather than User/Membership:

- reassignment leaves rows/content/UUIDs unchanged, immediately removes old
  controller access and grants access to the new controller when that Character
  is active;
- unassignment preserves rows and removes ordinary Player access;
- archive preserves rows and clears active access;
- deleting the controller User cascades the Membership, sets Character.owner to
  null through the existing relation and preserves the CharacterNote rows.

All four paths have focused regression coverage.

## 9. Routing

Campaign-scoped Character-facing routes are:

```text
/campaign/<campaign>/thoughts/
/campaign/<campaign>/thoughts/hold/
/campaign/<campaign>/thoughts/<opaque-uuid>/
/campaign/<campaign>/thoughts/<opaque-uuid>/return/
/campaign/<campaign>/thoughts/<opaque-uuid>/release/
```

No route contains or accepts a Character ID. Detail/edit/release scope UUID to
the current active Character. Release confirmation is GET; deletion is POST
with CSRF.

## 10. Workspace integration and performance

The role-aware Campaign route and compatibility Player Character-list route now
use one `build_character_workspace_context()` composition path. That preserves
PW1 active selection and PW2 ambience without duplicating Notes queries.

Workspace preview fetches at most three current-Character rows. The full index
uses Django pagination with 24 thoughts per page. There is no User/Campaign
cache, search, tag or unlimited render. Existing Workspace query-bound tests
remain green in the full suite.

## 11. Conversational create/edit flow

`Удержать мысль` opens a focused surface over the Character ambience.

Question one is exactly:

```text
Желаете дать памятку этой мысли?
```

The Player may enter the optional memo or choose `Оставить без памятки`.

Question two is exactly:

```text
Что вы хотите сохранить в памяти?
```

The completion action is `Удержать`. Edit uses the same focused language under
`Вернуться к мысли` and starts from existing values.

The server always renders both semantic questions and ordinary CSRF POST
fields, so no-JS remains usable. A small progressive-enhancement script reveals
one step at a time, clears memo only for the explicit skip action and moves
keyboard focus to the body. It does not render text, delay keystrokes or make
security decisions.

## 12. Airy visual design and text effect

Thoughts are translucent, softly glowing, variably sized blocks with deterministic
1–3 px drift. There is no random server positioning, overlap or table/card
metadata footer. Hover/focus gently gathers the block.

Typing remains native input. The appearance effect is CSS focus glow/fade,
avoiding a custom typewriter renderer and preserving Russian IME behavior.

The explicit `prefers-reduced-motion: reduce` rule removes thought/spark
animation and transforms while keeping static light and glow.

## 13. Detail, edit and release

Focused detail renders only optional memo and full body. It exposes no author,
Campaign label, privacy badge, ID or timestamp. Available actions are:

- `Вернуться к мысли`;
- `Отпустить`;
- return to the other thoughts.

Release opens the required confirmation:

```text
Отпустить эту мысль?

Она больше не останется среди удержанных мыслей.

[Оставить] [Отпустить]
```

A GET never deletes. The confirmed POST hard-deletes only the current
Character-scoped row.

## 14. Dates

Technical timestamps exist only for ordering/diagnostics. No Player template
renders them. Tests set a conspicuous year and prove it is absent alongside
`Создано` / `Обновлено` labels.

## 15. Plain text and XSS

Memo/body are plain text only. Django autoescaping remains enabled and multiline
display uses `linebreaksbr` without `safe`. `<script>` and `<img onerror>`
payloads are rendered escaped and never become executable markup. The
progressive script never assigns `innerHTML`.

## 16. Admin

`CharacterNote` is intentionally not registered in ordinary Django admin.
There is no GM search/list/detail or mutation bypass for note content.

## 17. PW2 compatibility

Workspace and all Notes pages render the existing shared
`world/_ambient_layers.html` component using `build_character_ambience()` for
the same active Character. N1 stores no ambience/weather state, adds no sampler
endpoint and does not alter C4/PW2 physics. Active switching changes both
ambience and Notes source through their established boundaries.

## 18. Focused and related tests

Focused N1:

```text
24 tests
OK
64.745 s
```

Coverage includes model shape, validation, create with/without memo,
controller-only reads, GM/superuser denial, same/foreign Player IDOR, forged
Character input, reassignment, unassignment, archive, User deletion, active
switch, edit/release scoping, XSS, no dates, no AuditLog leak, bounded preview,
pagination, reduced motion, PW2 integration and migration preservation.

The first 104-test N1/P5.5/PW1/L1/PW2 run found only one copy compatibility
issue: PW1 expected the stable module word `Заметки`. The module now keeps that
kicker while using `Удержанные мысли` as its N1 heading. All other 103 tests
passed; the affected PW1 module then passed 14/14. The final full suite re-ran
the complete matrix successfully.

## 19. Browser verification

Real in-app browser verification completed at desktop 1280×720 and mobile
390×844:

- empty Notes Workspace/list;
- two-question hold with memo;
- skip-memo hold;
- body focus transfer;
- airy list and focused detail;
- prefilled edit and updated result;
- release confirmation;
- Character switch changes visible thoughts;
- GM direct route returns 403;
- other Player is denied before reassignment;
- reassignment exposes unchanged thoughts to the new controller;
- old controller receives 404 for the old note;
- shared PW2 ambience remains present;
- reduced-motion CSS contract is loaded;
- no dates/prohibited technical wording;
- no console warnings/errors;
- no horizontal overflow (`scrollWidth == clientWidth`) at 390 px.

The browser did not submit the destructive release button because browser
safety requires separate action-time confirmation for deletion. Its real
confirmation UI was verified; the exact CSRF POST deletion and GET-no-mutation
semantics are covered by the green focused test.

The viewport was reset, temporary tab closed and server stopped. The isolated
Campaign, Characters, Notes, Memberships and three `n1-browser-*` Users were
deleted. Five objective assignment/active-selection audit rows remain detached
because AuditLog is append-only. They contain Character/controller history only
and no Note content or Note activity.

## 20. Full regression and final checks

Full suite:

```text
482 tests
OK
skipped=9
735.407 s
```

The total is the prior PW2 baseline of 458 plus exactly 24 N1 tests.

Final validation:

- `python manage.py check`: no issues;
- `python manage.py makemigrations --check --dry-run`: no changes detected;
- `git diff --check`: clean; only the repository's existing Windows LF→CRLF
  notices were printed;
- untracked N1 files were separately checked for trailing whitespace and final
  newline integrity: clean;
- final status contains only the intended N1 changes plus the user-supplied N1
  specification.

## 21. Changed files

- `characters/models.py`
- `characters/migrations/0004_character_note_n1.py`
- `characters/notes.py`
- `characters/workspace.py`
- `characters/forms.py`
- `characters/views.py`
- `characters/urls.py`
- `campaigns/views.py`
- `characters/templates/characters/character_workspace.html`
- `characters/templates/characters/personal_notes_base.html`
- `characters/templates/characters/_held_thought.html`
- `characters/templates/characters/personal_note_list.html`
- `characters/templates/characters/personal_note_detail.html`
- `characters/templates/characters/personal_note_form.html`
- `characters/templates/characters/personal_note_release.html`
- `static/js/held-thoughts.js`
- `static/css/app.css`
- `templates/base.html`
- `characters/tests/test_personal_notes_n1.py`
- `docs/N1_PROGRESS.md`
- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Player_Experience_Architecture_v1.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`
- this report.

## 22. Known limitations

- There is deliberately no rich text, attachment, tag, folder, search or AI
  summary system.
- There is no Player-facing date/history/version UI; release is final deletion.
- There is no ordinary GM recovery/content browser by privacy design.
- Party Notes are not a flag on CharacterNote and remain a separate future
  Party-domain model.
- The Browser safety boundary prevented a live destructive click; server
  deletion behavior remains fully regression-tested.

## 23. Scope confirmation and stop

N1 did not start Party Notes, P6 Party, M2/V1, Player Map, Travel, Quests,
XP/Soul HUD, Tiamana mechanics, Inventory, Ledger, Economy, Roll20 normalized
sync, Apotheosis, C5/C6/C7, CharacterKnowledge, rich text, attachments, tags or
search.

N1 Personal Character Notes is complete. Work stops here pending a separate
explicit instruction.
