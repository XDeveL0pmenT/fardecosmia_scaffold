# PW1 — Character Workspace Shell — Final Report

Date: 2026-08-24

## 1. Outcome

PW1 is complete. The normal PLAYER entry into a Campaign is now the active
Character Workspace. The GM continues to use a separate objective Campaign
flow. The work is a routing, presentation and integration-shell phase only: it
does not add new gameplay state or change database schema.

## 2. Player Campaign routing

`campaigns.views.campaign_detail()` is now role-aware:

- a PLAYER membership renders `characters/character_workspace.html` directly;
- a GM-capable membership keeps the existing objective Campaign landing;
- access remains membership-scoped;
- no intermediate legacy Player Campaign dashboard is part of the normal flow.

Campaign cards still use the stable Campaign detail URL. The role-aware view,
not a separate public URL convention, selects the correct experience.

## 3. Active Character resolution

PW1 reuses the P5.5 Character-control foundation rather than adding another
selection system:

- controlled active Characters are obtained through the existing
  Campaign-scoped query/service boundary;
- the persisted active selection is resolved through `get_active_character()`;
- a single controlled Character can be used as a read-only fallback without a
  GET request mutating the selection;
- no controlled Character produces a human-first unassigned state;
- multiple controlled Characters with no valid active selection produce an
  explicit choice state instead of an arbitrary guess;
- archived, foreign-Campaign and uncontrolled Characters cannot be selected.

The switch form is POST-only with CSRF protection. A successful switch uses the
existing P5.5 `set_active_character()` semantics and returns to the same Campaign
Workspace URL.

## 4. Multiple Character behavior and compatibility routes

The Workspace provides a Character switcher whenever the PLAYER controls more
than one active Character. The selected Character remains persisted through the
P5.5 selection model.

The old Player Character detail route remains available for compatibility, but
after ownership validation it redirects to the Campaign Workspace. It no longer
maintains a second, divergent Player screen. GM Character-detail behavior remains
available for the GM flow. The compatibility player-character-list route renders
the same Workspace/selection shell.

## 5. GM flow preservation

GM Campaign detail still renders the objective Campaign landing and its GM
controls. PW1 does not reinterpret the GM dashboard as Character perception and
does not move Campaign authority away from `CampaignMembership`.

The existing ApprovalRequest backend, registered handlers, requester
compatibility routes and GM decision queue remain present. Browser verification
confirmed that the GM queue still opens and renders “Запросы на одобрение”.

## 6. Player-facing ApprovalRequest navigation

The generic “Мои запросы” destination was removed from normal Player discovery:

- no link remains on PLAYER Campaign cards;
- no link remains on the normal Player Campaign destination;
- no requester-inbox link remains in the shared Campaign quick navigation;
- Player Workspace copy uses world/Character language and does not expose the
  `ApprovalRequest` term.

This is a UX/navigation change only. It does not delete ApprovalRequest models,
routes, orchestration, stored data or the GM queue.

## 7. Character Workspace shell

The new server-rendered Workspace contains:

- active Character portrait, name and biography identity hero;
- Character switcher/choice state;
- Тиамана slot;
- active Quests slot;
- Map slot;
- Быт / Обязательства slot;
- Party slot;
- Notes slot;
- Apotheosis slot;
- quick carried-Inventory slot;
- stable nonnumeric XP and money HUD integration anchors.

These are deliberately shell boundaries. PW1 does not claim that the underlying
domain systems exist.

## 8. Disclosure and product-language boundaries

The normal Player Workspace does not contain:

- `CharacterKnowledge` or “Что знает персонаж” wording;
- `ApprovalRequest` terminology;
- developer instructions, roadmap phrases or implementation placeholders;
- raw Roll20 attributes;
- GM-only objective state.

The Player presentation is Character-facing/diegetic-adjacent while remaining a
clear application interface.

## 9. No fabricated gameplay state

PW1 does not fabricate or expose placeholder values for:

- XP;
- money/balance;
- Inventory contents;
- Quests;
- Character Location;
- live Weather or ambience;
- Notes data;
- Party state;
- Apotheosis mechanics.

XP and money exist only as layout anchors. The module cards explain availability
without inventing values or reading unrelated baseline climate/world data.

## 10. Platform navigation and responsive layout

The authenticated Platform shell exposes real destinations for Campaigns,
Settings and Logout. A minimal account Settings page was added rather than a
dead or fake link; it shows only existing account/email-verification information
and a real password-reset destination.

PW1 CSS keeps the Workspace in normal document flow and stacks its hero,
switcher, HUD anchors and modules at the mobile breakpoint.

## 11. Browser verification

### Desktop

Verified at 1280 px:

- PLAYER Campaign list contains no “Мои запросы” link;
- “Открыть кампанию” goes directly to Character Workspace;
- no intermediate old Player dashboard appears;
- active Character identity and all approved module slots render;
- two-Character switching persists the chosen Character and returns to the
  Workspace URL;
- the no-assigned-Character state is readable and does not invent modules/data;
- Platform navigation works;
- no fake gameplay values or prohibited wording appears;
- browser console error list is empty.

### Mobile

Verified at 390×844:

- Character identity, switcher, HUD anchors and module cards stack correctly;
- all approved module headings remain readable;
- document width remains inside the viewport;
- no horizontal overflow was detected;
- browser console error list is empty.

### Final compatibility checks

- Direct navigation to the old controlled Player Character URL ended at the
  Campaign Workspace URL, displayed the active Character and contained neither
  old knowledge wording nor ApprovalRequest terminology.
- Direct navigation to the GM ApprovalRequest queue remained successful and
  displayed the GM decision page without Character Workspace leakage.

No browser defect required a code change.

The local test server was stopped. The exact isolated `PW1 Browser Campaign`,
its three memberships, two Characters and the three
`pw1-browser-20260824-*` accounts were deleted. No other development/user data
was targeted.

## 12. Changed PW1 files

- `campaigns/views.py`
- `characters/views.py`
- `characters/templates/characters/character_workspace.html`
- `campaigns/templates/campaigns/campaign_list.html`
- `campaigns/templates/campaigns/campaign_detail.html`
- `templates/campaigns/_campaign_quickbar.html`
- `templates/base.html`
- `accounts/views.py`
- `accounts/urls.py`
- `templates/accounts/account_settings.html`
- `static/css/app.css`
- `characters/tests/test_character_workspace_pw1.py`
- superseded expectations only in
  `characters/tests/test_character_identity_p55.py` and
  `campaigns/tests/test_onboarding_p45.py`
- `docs/PW1_PROGRESS.md`
- `AGENTS.md`
- `WORLD_HANDOFF_v2.md`
- `Codex Handoff — Future Architecture Guardrails.md`
- `Fardecosmia_Master_Roadmap_v1_1.md`

The worktree also contains the previously completed P5.6 changes and its
migration. They were preserved and were not recreated or reinterpreted by PW1.

## 13. Test results

- Focused PW1: **14 tests — OK** (`16.814 s`).
- PW1 + P5.5: **44 tests — OK, skipped=1** (`83.997 s`).
- Related P4/P4.5/P5/P5.5/P5.6/PW1 regression:
  **135 tests — OK, skipped=8** (`244.121 s`).
- Full project suite: **422 tests — OK, skipped=8** (`552.817 s`).
- `python manage.py check`: **no issues**.
- `python manage.py makemigrations --check --dry-run`:
  **No changes detected**.
- `git diff --check`: **passed, exit code 0**. Git emitted only the existing
  Windows LF→CRLF conversion notices; no whitespace errors were reported.

## 14. Schema and migration status

PW1 required no model or schema change and created no PW1 migration.
Migration-drift checking is clean. The uncommitted P5.6 eligibility migration
predates PW1 and remains intentionally preserved in the current worktree.

## 15. Out-of-scope confirmation

PW1 did not begin or implement L1, Notes backend, Party, M2, V1, PW2, Roll20
sync, normalized Character state, XP mechanics, final Soul HUD, Ledger,
Inventory, Quests, Economy, Travel, Apotheosis or C5. No next phase was started
automatically.

