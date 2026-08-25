# N1 — Personal Character Notes / Held Thoughts Foundation — Progress

Last updated: 2026-08-25

## Phase boundary

N1 may add private plain-text thoughts owned by Character and a diegetic-
adjacent Player Workspace experience for the active Character's controller.
GM must not be able to read them, Campaign AuditLog must not receive them, and
controller reassignment must transfer access with the Character.

N1 must not start Party Notes, P6 Party, M2/V1, Player Map, Travel, Quests,
XP/Soul HUD, Tiamana mechanics, Inventory, Ledger, Economy, Roll20,
Apotheosis or C5. Existing PW2 ambience must remain intact.

## Starting state

- Checkpoint created immediately before implementation.
- PW2 worktree changes are intentional source state and must be preserved.

## Completed work

- Created this resumable checkpoint.
- Read the N1 specification and every mandatory architecture/handoff/report
  file in full.
- Completed Phase 0 privacy/model audit:
  - existing `Character.public_notes` / `gm_notes` are legacy identity fields
    and are not a private held-thought store;
  - controller authority is the nullable Campaign-scoped
    `Character.owner -> CampaignMembership`; active identity is resolved by
    the centralized `get_active_character()` service;
  - assignment, unassignment, archive and membership/User deletion preserve
    the durable Character row, so a Character-owned child naturally follows
    reassignment and survives loss of a controller;
  - normal PLAYER Workspace is rendered through both the role-aware Campaign
    route and its compatibility player-list route; both currently compose PW2
    ambience independently and need one shared Workspace context to avoid a
    divergent Notes preview;
  - the existing Notes card is a PW1 shell only and no Notes route/model exists;
  - GM Character screens and ordinary Django admin must not gain a relation,
    search field or content browser for personal thoughts;
  - N1 mutations are an explicit privacy exception and must not import/call
    `record_audit()`;
  - server-rendered templates use Django autoescaping and the new UI must not
    use `safe` for memo/body;
  - current Character migration leaf is `0003_character_location_state_l1`.
- Captured the development DB preservation baseline before migration:
  Users=5, Campaigns=1, Memberships=2, Characters=2 (1 active, 1 archived,
  1 assigned), CharacterLocationState=1, Roll20 bindings=0, AuditLog=52, and
  no CharacterNote table.
- Selected the additive design: opaque UUID `CharacterNote` rows owned only by
  Character, optional 120-character memo, required escaped plain-text body up
  to 32 KiB, technical timestamps used only for ordering, and no admin
  registration.
- Added `CharacterNote` and additive migration
  `characters.0004_character_note_n1`:
  - UUID primary key;
  - `character` FK with `related_name="personal_notes"`;
  - optional `memo` capped at 120 characters;
  - required `body` capped at 32 KiB plus a non-empty DB constraint;
  - technical timestamps and a Character/time index;
  - no User, author, visibility, GM, Party or world-object field;
  - no data operation and no admin registration.
- Verified the handwritten migration matches model state (`makemigrations
  --check --dry-run`: no changes) and `manage.py check` is clean.
- Added centralized private-thought authorization/mutation services in
  `characters.notes`:
  - GM, superuser-without-PLAYER-membership and non-members are denied;
  - the Character is always resolved through the existing active-Character
    service and every note lookup is scoped by both active Character and UUID;
  - writes lock the Campaign boundary shared by assignment/switch flows, then
    revalidate and lock the active controlled Character/note;
  - create/edit/release deliberately import no AuditLog API and emit no audit.
- Added plain-text `CharacterNoteForm` validation and Campaign-scoped opaque
  routes for list/hold/detail/return/release. Create never accepts a trusted
  Character ID; release mutates only on POST after a separate GET confirmation.
- Consolidated both compatible Player Workspace render paths through
  `build_character_workspace_context()`, preserving PW2 ambience while bounding
  the Notes preview to three rows from the active Character.
- Interim Django check remains clean after authorization/routes.
- Implemented the complete Held Thoughts presentation:
  - Workspace preview with at most three active-Character thoughts;
  - paginated 24-row airy index and human empty state;
  - focused escaped detail without dates/IDs/author/privacy metadata;
  - conversational two-question hold/return flow with the required Russian
    wording and a usable no-JS fallback;
  - separate confirmed `Отпустить` GET followed by destructive POST;
  - subtle CSS focus/glow, deterministic 1–3 px drift, mobile stacking and an
    explicit reduced-motion override;
  - small JS progressive enhancement for step/focus management only, without
    text rendering, trusted state or security decisions;
  - all Notes pages continue to render the shared PW2 ambient component.
- Added 24 focused N1 tests covering schema, privacy, create/edit/release,
  validation, GM/other-Player/foreign IDOR, forged Character input,
  reassignment, unassignment/archive/User deletion, switch semantics, XSS,
  no dates, no AuditLog leak, bounded preview, pagination, reduced motion,
  PW2 compatibility and migration preservation.
- Focused result: **24 tests — OK** in 64.745 s.
- Applied additive migration `characters.0004_character_note_n1` to the
  development DB. Post-migration preservation matches the baseline exactly:
  Users=5, Campaigns=1, Memberships=2, Characters=2 (1 active, 1 archived,
  1 assigned), locations=1, Roll20 bindings=0, AuditLog=52; the new note table
  exists with 0 rows.
- Ran the 104-test N1/P5.5/PW1/L1/PW2 related matrix. One superseded PW1 copy
  assertion required the Workspace module to retain its stable `Заметки`
  kicker while N1 uses `Удержанные мысли` as the Character-facing heading;
  all other 103 tests passed and the two expected backend skips remained.
- Restored that compatible module kicker and reran the affected PW1 module:
  **14 tests — OK**. No routing, ownership, location or ambience behavior
  changed. The final full suite will re-cover the complete related matrix.
- Completed isolated real-browser verification:
  - desktop 1280×720 and mobile override 390×844;
  - empty Workspace/list, two-question create with memo, skip-memo create,
    focused detail, prefilled edit, release confirmation, active Character
    switch, GM direct denial, other-Player denial before reassignment, access
    transfer to the new controller and 404 for the old controller afterward;
  - the memo→body transition moved keyboard focus to the textarea;
  - the PW2 ambient component remained present behind Workspace/Notes;
  - loaded CSSOM contained the explicit held-thought reduced-motion rule;
  - no Player-facing dates/prohibited technical wording, console warnings/errors
    or horizontal overflow; at 390 px, document `scrollWidth == clientWidth`;
  - visual inspection confirmed readable airy blocks and focused question UI.
- The destructive release POST was not clicked in the live browser because the
  browser safety boundary requires separate action-time confirmation for a
  deletion. The confirmation screen was verified and the exact POST lifecycle
  is covered by the green focused test.
- Reset the mobile viewport, closed the agent-created browser tab and stopped
  the temporary Django server.
- Deleted the isolated browser Campaign, all its Characters/Notes/Memberships
  and the three exact `n1-browser-*` Users. Five assignment/active-selection
  AuditLog rows remain detached by design because project AuditLog is
  append-only; an attempted raw removal was correctly rejected. Those rows
  contain no Note memo/body or note-existence action. Remaining browser
  Campaigns/users/notes are all zero.
- Full project regression completed: **482 tests — OK, skipped=9** in
  735.407 s. This is the prior 458-test PW2 baseline plus exactly 24 focused
  N1 tests and re-covers the complete related matrix after the copy fix.
- Updated `AGENTS.md`, `WORLD_HANDOFF_v2.md`, Architecture Guardrails, Player
  Experience Architecture and Master Roadmap with implemented N1 Personal
  Notes invariants only. Personal N1 is marked complete; Party Notes/P6 and all
  later phases remain planned.
- Created `N1_PERSONAL_CHARACTER_NOTES_REPORT.md` with the complete baseline,
  architecture, privacy, migration, UX, test/browser and scope record.
- Final validation passed:
  - `manage.py check`: no issues;
  - `makemigrations --check --dry-run`: no changes detected;
  - `git diff --check`: clean (LF→CRLF notices only);
  - all N1 untracked implementation/report/checkpoint files have no trailing
    whitespace and end with a newline;
  - final git status contains only intended N1 changes and the user-supplied N1
    specification.

## Changed files

- `docs/N1_PROGRESS.md` — resumable N1 checkpoint.
- `characters/models.py` — additive private Character-owned note model.
- `characters/migrations/0004_character_note_n1.py` — additive N1 schema.
- `characters/notes.py` — private active-controller query/write boundary.
- `characters/workspace.py` — shared PW1/PW2/N1 Workspace composition.
- `characters/forms.py` — held-thought plain-text validation.
- `characters/views.py` — Player-only Notes endpoints and shared Workspace use.
- `characters/urls.py` — Campaign-scoped opaque thought routes.
- `campaigns/views.py` — shared Workspace context use.
- `characters/templates/characters/personal_notes_base.html` — shared private
  thought surface over PW2 ambience.
- `characters/templates/characters/_held_thought.html` — escaped airy thought.
- `characters/templates/characters/personal_note_list.html` — paginated index.
- `characters/templates/characters/personal_note_detail.html` — focused detail.
- `characters/templates/characters/personal_note_form.html` — two-question flow.
- `characters/templates/characters/personal_note_release.html` — confirmation.
- `characters/templates/characters/character_workspace.html` — real N1 preview.
- `static/js/held-thoughts.js` — progressive step/focus enhancement.
- `static/css/app.css` — airy/reduced-motion/mobile N1 presentation.
- `templates/base.html` — N1 stylesheet cache version.
- `characters/tests/test_personal_notes_n1.py` — 24 focused tests.
- `AGENTS.md`, `WORLD_HANDOFF_v2.md`, Architecture Guardrails, Player
  Experience Architecture and Master Roadmap — completed N1 invariants.
- `N1_PERSONAL_CHARACTER_NOTES_REPORT.md` — final implementation report.

## Tests

- Development DB baseline captured read-only; no test suite run yet.
- Model/migration drift check: no changes detected.
- Interim `manage.py check`: no issues.
- Authorization/routes interim `manage.py check`: no issues.
- Focused N1: 24 tests OK.
- Migration preservation test: passed; zero notes auto-created.
- Related matrix before copy fix: 103/104 passed, skipped=2; sole failure was
  the stable PW1 `Заметки` copy assertion.
- Targeted PW1 rerun after fix: 14 tests OK.
- Browser desktop/mobile: passed with the release POST caveat documented above.
- Full suite: 482 tests OK, skipped=9.

## Known issues

- Five detached objective assignment/active-selection audit rows from the
  isolated browser Campaign remain because AuditLog is append-only. No personal
  note content or personal-note action entered them.

## Exact next step

N1 is complete. Stop and wait for a separate explicit user instruction. Do not
start Party Notes, P6 or any other phase automatically.
