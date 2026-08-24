# P5.6 — Campaign Creation & GM Eligibility Alignment — Progress

Last updated: 2026-08-23

## Completed work

- Read the current `AGENTS.md` in full.
- Read `Fardecosmia_Player_Experience_Architecture_v1.md` in full.
- Read `Fardecosmia_Master_Roadmap_v1_1.md` in full.
- Read `WORLD_HANDOFF_v2.md` in full.
- Read `Codex Handoff — Future Architecture Guardrails.md` in full.
- Confirmed phase boundary: P5.6 only; PW1, Notes, Party, M2, V1,
  Roll20, Ledger, Inventory, Travel and C5 must not start.
- Captured initial worktree state: only the two newly supplied architecture
  documents were untracked before P5.6 work.
- Located the existing P4.5 campaign creation and membership-role flows.
- Completed the pre-change implementation audit:
  - `Campaign` has no trusted-GM permission yet;
  - `create_campaign()` checks only transactional-email verification and then
    atomically creates Campaign + first GM membership + AuditLog;
  - campaign-list/create UI derives access from email verification only;
  - any Campaign GM can currently promote any same-Campaign PLAYER to GM;
  - last-GM locking and member-removal preservation already exist;
  - invitations are PLAYER-only and independent from ApprovalRequest;
  - CampaignMembership remains the only campaign-local role source;
  - Campaign admin has a separate creation path that must be aligned too.
- Captured a secret-free development-data baseline: 5 users, 2 verified users,
  1 Campaign, 2 memberships (1 GM, 1 PLAYER), 1 distinct existing GM user,
  and 0 historical role-change audit rows.
- Chosen non-destructive policy design:
  - dedicated `campaigns.create_campaign_as_gm` permission;
  - no `User.is_gm` field;
  - direct user-permission eligibility (group grants do not count);
  - superuser-only grant/revoke service and admin actions;
  - campaign creation requires eligibility plus existing email rule;
  - PLAYER → GM requires eligible target, even when initiated by Campaign GM;
  - existing GM users receive the explicit permission in a forward-only data
    migration so current trusted operators are not silently locked out.
- Implemented the central policy in `campaigns.services.eligibility`:
  direct individual permission, bulk eligibility lookup, creation gate,
  superuser-only audited grant/revoke and User-row locking.
- Added `Campaign.Meta.permissions` entry
  `campaigns.create_campaign_as_gm`.
- Added migration `campaigns.0011_gm_eligibility_p56` with an idempotent
  ContentType/Permission bootstrap and forward-only preservation grant for
  users who already have at least one GM membership.
- Enforced eligibility in the normal campaign-creation service/view, PLAYER →
  GM promotion service, Campaign admin creation path, and User admin controls.
- Added superuser-only audited UserAdmin actions; group-derived permission does
  not count and the dedicated permission is excluded from the raw permission
  widget.
- Updated campaign-list/create/member UI with invitation-first ordinary-user
  empty states and an explicit disabled promotion state.
- Updated P4.5 test setup so historical campaign-creation tests explicitly model
  an eligible creator rather than relying on verified email as authority.
- Added focused P5.6 tests for security, IDOR-adjacent forged POST, permission
  provenance, admin bypass, promotion, revocation, data migration and a
  PostgreSQL-only revoke/promotion race.
- Applied `campaigns.0011_gm_eligibility_p56` to the development database.
  The existing Campaign and both existing memberships were preserved; the
  existing GM received direct eligibility and the PLAYER-only user did not.
- Completed browser/manual verification with isolated temporary data:
  - an ordinary verified user sees invitation-first UI and no create link;
  - direct create-page access redirects with a human-readable denial;
  - an eligible GM sees and can open campaign creation;
  - an ineligible PLAYER has a disabled GM-promotion control;
  - desktop and 390×844 mobile layouts have no console errors or horizontal
    overflow in the tested P5.6 paths.
- Removed the isolated browser Campaign and four browser-only users after the
  verification; no pre-existing development data was deleted.

## Changed files

- `campaigns/models.py` and `campaigns/migrations/0011_gm_eligibility_p56.py`
  — trusted-GM permission plus preservation data migration.
- `campaigns/services/eligibility.py` — centralized eligibility policy and
  audited superuser-only grant/revoke boundary.
- `campaigns/services/lifecycle.py` and
  `campaigns/services/memberships.py` — atomic creation/promotion enforcement.
- `campaigns/views.py`, `accounts/admin.py`, `campaigns/admin.py` — HTTP/admin
  enforcement and supported eligibility controls.
- Campaign list/create/members templates — invitation-first and disabled-state
  UX.
- `campaigns/tests/test_gm_eligibility_p56.py` and
  `campaigns/tests/test_onboarding_p45.py` — focused and compatibility tests.
- `docs/P56_PROGRESS.md` — resumable checkpoint.

## Tests

- Previous completed repository baseline from P5.5: 395 tests, skipped=7.
- Focused P5.6: 13 tests, `OK (skipped=1)`, 16.380 s.
- Initial focused run exposed a fresh-database ContentType timing issue in the
  data migration; migration was made idempotent and the rerun passed.
- P4.5 regression: 27 tests, `OK (skipped=3)`, 49.589 s.
- P5.5 tests passed in the combined P4.5/P5.5 regression run; the only failure
  was one obsolete P4.5 UI expectation, which was updated for the intentional
  disabled-promotion state.
- Final combined P4.5/P5/P5.5/P5.6 regression after browser verification and
  documentation: 97 tests in 225.227 s, `OK (skipped=7)`.
- Full regression suite: 408 tests in 528.095 s, `OK (skipped=8)`.
- `manage.py check`: no issues (0 silenced).
- `makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: exit 0; only LF-to-CRLF working-copy warnings.
- Final development-data check: 5 users, 1 Campaign, 2 memberships, 1 GM;
  migration `0011_gm_eligibility_p56` is applied, the existing GM is eligible,
  and no PLAYER-only account is eligible.

## Known issues / audit leads

- The revoke/promotion concurrency regression is PostgreSQL-only and is
  intentionally skipped on the local SQLite test backend.
- No browser/manual P5.6 defect remains open.

## Exact next step

Perform only the final diff/status review, deliver the P5.6 report and stop.
PW1 and every other subsequent phase remain unstarted.
