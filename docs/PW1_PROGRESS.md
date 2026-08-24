# PW1 — Character Workspace Shell — Progress

Last updated: 2026-08-24

## Phase boundary

PW1 changes Player UX, routing and the Character Workspace shell only. It must
not implement L1/location, live weather ambience, Notes backend, Party, M2/V1,
normalized Character/Roll20 sync, XP/final soul HUD, Ledger/money, Inventory,
Quests, Travel, Apotheosis/Craft mechanics or C5.

## Completed work

- Read `Fardecosmia_PW1_Character_Workspace_Shell.md` in full.
- Re-read `AGENTS.md` in full.
- Re-read `WORLD_HANDOFF_v2.md` in full.
- Re-read `Codex Handoff — Future Architecture Guardrails.md` in full.
- Re-read `Fardecosmia_Player_Experience_Architecture_v1.md` in full.
- Re-read `Fardecosmia_Master_Roadmap_v1_1.md` in full.
- Re-read `P5_5_CHARACTER_IDENTITY_PLAYER_WORKSPACE_REPORT.md` in full.
- Re-read `P5_6_CAMPAIGN_CREATION_GM_ELIGIBILITY_ALIGNMENT_REPORT.md` in full.
- Captured the pre-PW1 worktree: completed P5.6 changes remain intentionally
  uncommitted; the PW1 specification is a newly supplied untracked document.
- Completed Phase 0 audit:
  - PLAYER Campaign card currently opens an intermediate Campaign landing;
  - that landing links to the old Character detail and a generic “Мои запросы”;
  - both PLAYER and GM Campaign cards expose “Мои запросы”;
  - the GM quickbar also exposes the requester inbox alongside the real GM queue;
  - old Player Character detail contains developer-roadmap wording and the
    “Что знает персонаж” placeholder;
  - `get_active_character()`, `controlled_characters()` and the existing
    POST-only `set_active_character()` flow already provide the required P5.5
    resolution/security semantics;
  - no Character location or safe live ambience source exists in PW1 scope;
  - no account Settings route currently exists despite the approved minimal
    Platform Shell contract.
- Chosen no-schema implementation:
  - `campaign_detail` renders the new Character Workspace directly for PLAYER;
  - GM keeps the objective Campaign landing/dashboard route;
  - the compatibility Player Character detail redirects to the Workspace;
  - the existing player-list route can render the same selection/workspace shell;
  - successful POST switch returns to the Workspace;
  - add a small real account-settings landing rather than a fake settings link;
  - remove requester-inbox discovery from Campaign cards/Player surfaces while
    preserving ApprovalRequest backend and GM queue.
- Completed Phase 1 routing:
  - PLAYER `campaign_detail` now directly renders active Character Workspace;
  - GM `campaign_detail` remains the objective Campaign landing;
  - no Character and unresolved multiple-Character states are human-first;
  - Player compatibility Character detail redirects to the Workspace;
  - player-list compatibility route renders the same Workspace shell;
  - successful POST switch redirects to the Workspace.
- Completed Phase 2 layout:
  - identity/portrait/biography hero;
  - Тиамана, active Quests, Map, Быт/Обязательства, Party, Notes,
    Apotheosis and carried-Inventory integration surfaces;
  - non-numeric XP and money layout anchors without fake balances/progress;
  - responsive in-flow layout; no live ambience or atmosphere access;
  - real account Settings landing plus Platform Shell Campaigns/Settings/Logout.
- Completed Phase 3 navigation cleanup:
  - removed “Мои запросы” from both Campaign card variants;
  - removed the requester inbox from the GM quickbar while preserving the real
    “Запросы” GM queue;
  - old Player knowledge/developer placeholders are no longer reachable through
    normal Player routing;
  - ApprovalRequest models, handlers, routes and GM pages remain unchanged.

## Changed files

- `campaigns/views.py` and Campaign list/detail templates — role-aware direct
  Workspace routing and navigation cleanup.
- `characters/views.py` and new `character_workspace.html` — Workspace states,
  compatibility redirect and switch destination.
- `accounts/views.py`, `accounts/urls.py` and new account settings template —
  real Platform Shell settings destination.
- `templates/base.html` and `_campaign_quickbar.html` — Platform links and
  requester-inbox cleanup.
- `static/css/app.css` — PW1 desktop/mobile shell styling.
- `characters/tests/test_character_workspace_pw1.py` — focused PW1 routing,
  security, disclosure, compatibility, query and UI-contract tests.
- P5.5/P4.5 test modules — only superseded landing/detail expectations updated.
- `docs/PW1_PROGRESS.md` — resumable checkpoint.

## Tests

- P5.6 completion baseline: 408 tests in 528.095 s, `OK (skipped=8)`.
- Focused PW1: 14 tests in 16.814 s, `OK`.
- Combined PW1 + P5.5 after expectation alignment: 44 tests in 83.997 s,
  `OK (skipped=1)`.
- Related P4/P4.5/P5/P5.5/P5.6/PW1 regression: 135 tests in
  244.121 s, `OK (skipped=8)`.
- `manage.py check`: no issues at this milestone.
- Full project suite: 422 tests in 552.817 s, `OK (skipped=8)`.
- Final `manage.py check`: no issues.
- `makemigrations --check --dry-run`: `No changes detected`.
- `git diff --check`: exit code 0; only Windows LF→CRLF conversion notices,
  no whitespace errors.

## Browser verification

- Desktop verification completed at 1280 px:
  - a PLAYER Campaign card has no “Мои запросы” link;
  - “Открыть кампанию” opens Character Workspace directly, with no old Player
    Campaign dashboard in between;
  - Platform navigation, identity hero, active-Character switch and approved
    module slots render correctly;
  - no fake XP, money, Inventory, Quests, Location or Weather values appear;
  - no `CharacterKnowledge`, “Что знает персонаж”, `ApprovalRequest` or
    developer/roadmap wording appears in the Player Workspace.
- Mobile verification completed at 390×844:
  - Workspace cards and switcher stack in-flow;
  - document width remains inside the viewport and no horizontal overflow was
    found;
  - all approved module headings remain readable.
- Active Character switching was exercised with two controlled Characters:
  the selected Character remained active and the POST returned to the same
  Campaign Workspace URL.
- The no-assigned-Character state renders a human-first empty state without
  fake modules or requester-inbox navigation.
- The old Player Character detail URL was opened directly and correctly
  redirected to the Campaign Workspace while preserving the active Character.
- The GM Campaign flow remains separate; its objective landing and the real
  GM ApprovalRequest queue both remain accessible.
- Browser console error inspection was empty for the checked Player, empty and
  GM states.
- No PW1 browser defect required a code change.
- The temporary server is stopped. The isolated `PW1 Browser Campaign`, its
  three memberships/two Characters and the three exact
  `pw1-browser-20260824-*` accounts were deleted; no other development data was
  targeted.

## Current failures / known issues

- Initial P5.5 run had exactly two expected obsolete UI assertions: old
  dashboard wording and HTTP 200 for old Player detail. Both were updated to
  the intended Workspace/redirect contract; no service failure was found.

## Exact next step

PW1 is complete. The four architecture/roadmap documents and
`PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md` record the implemented contract and
all final checks are green. Capture the final `git status`/diff summary and stop;
do not start L1 or any other subsequent phase automatically.
