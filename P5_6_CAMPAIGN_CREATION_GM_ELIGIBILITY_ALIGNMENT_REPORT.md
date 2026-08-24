# P5.6 — Campaign Creation & GM Eligibility Alignment

Date: 2026-08-23

## 1. Scope and outcome

P5.6 closes the two authorization gaps inherited from P4.5:

1. a verified ordinary User can no longer create a Campaign;
2. a Campaign GM can no longer promote an arbitrary PLAYER to GM without a
   separate global trust decision.

The phase does not add a global role field to User. `CampaignMembership`
remains the source of truth for the role and authority a User holds inside each
Campaign.

## 2. Exact GM eligibility model

Trusted-GM eligibility is the direct individual Django permission:

```text
campaigns.create_campaign_as_gm
```

`has_gm_eligibility(user)` returns true only when the account is authenticated,
active, and either:

- is a superuser; or
- directly owns that permission through `User.user_permissions`.

A permission inherited from a Django Group deliberately does not count. The
existing `world.manage_global_canon` permission, staff status, verified email,
invitation authorship and Campaign membership also do not imply eligibility.
No `User.is_gm` field was introduced.

## 3. Grant and revoke authority

Only an active superuser may call the supported
`campaigns.services.eligibility.set_gm_eligibility()` boundary. UserAdmin exposes
grant/revoke actions only to a superuser. The trusted-GM permission is excluded
from the generic `user_permissions` selector so it cannot be changed through an
unaudited alternate admin path; non-superusers also receive read-only Group,
permission and superuser fields.

Grant and revoke lock the target User row and run atomically. Repeating the
same desired state is a no-op and does not create audit noise. Superuser
eligibility is inherent; an attempt to revoke it is rejected.

## 4. Campaign creation rules

Normal application creation requires both:

- trusted-GM eligibility (or superuser status); and
- the existing verified transactional-email condition.

The service reloads and locks the creator User before evaluating both rules,
then creates the Campaign, its initial GM membership and the P3 audit entry in
one transaction. An ordinary verified User is denied by the service, sees an
invitation-first empty state, has no create link, and cannot bypass the rule by
posting directly to the create endpoint. An eligible but unverified User is
still sent through email verification.

Django CampaignAdmin creation is a superuser-only diagnostic/recovery path.
Eligible non-superusers use the normal application flow.

## 5. PLAYER -> GM promotion

The target membership must belong to the same locked Campaign and its current
target User must be globally eligible at the moment of promotion. The service
locks Campaign, Membership and target User rows and validates the policy inside
the transaction. This rule applies even when the actor is a Campaign GM or a
superuser; superuser authority to trust the account is exercised separately by
granting eligibility.

The Campaign member page bulk-resolves eligibility without a query per row.
Eligible PLAYER memberships expose the existing promotion POST action;
ineligible ones render a disabled “Нет права Game Master” control. A forged POST
is revalidated and rejected server-side.

The existing last-GM invariant and Campaign-scoped role authorization remain
unchanged.

## 6. Revocation semantics

Revoking eligibility is prospective. It does not rewrite or delete an existing
GM `CampaignMembership`; that User retains authority in Campaigns where the GM
role already exists, including the ability to satisfy the last-GM invariant.
Revocation immediately prevents creation of another Campaign. If that existing
GM is later demoted to PLAYER, promotion back to GM is blocked until a
superuser grants eligibility again.

This behavior avoids destructive role mutation while making the global trust
policy effective for all new grants of GM authority.

## 7. Data migration

`campaigns.0011_gm_eligibility_p56` adds the model permission and performs a
forward-only preservation migration:

- every distinct User with an existing GM CampaignMembership receives the
  direct permission;
- PLAYER-only users receive nothing;
- Campaign and CampaignMembership rows are not changed;
- `bulk_create(..., ignore_conflicts=True)` makes the grant idempotent;
- ContentType and Permission are obtained/created explicitly so the migration
  also works while constructing a fresh test database before `post_migrate`;
- reverse is intentionally a no-op, because removing permissions that may have
  become an explicit trust decision would be destructive.

The migration was applied to the development database. The pre-existing one
Campaign and two memberships remained present. Its existing GM received direct
eligibility; the PLAYER-only User did not.

## 8. AuditLog actions

P5.6 adds:

- `account.gm_eligibility_granted`;
- `account.gm_eligibility_revoked`.

They store a stable User ID/label and before/after eligibility boolean, without
email, permission internals or authentication secrets. Existing actions remain
in use:

- `campaign.created` for atomic Campaign creation;
- `campaign_member.role_changed` for an actual membership role transition.

No-op eligibility and no-op role requests do not create new audit rows.

## 9. Concurrency and locking

The supported write paths serialize on relevant rows:

- grant/revoke: target User;
- Campaign creation: creator User;
- role transition: Campaign, target CampaignMembership and target User;
- existing Character/membership-removal and last-GM protections remain in
  their existing transactional service boundaries.

A PostgreSQL-only transaction regression covers concurrent eligibility
revocation and PLAYER -> GM promotion. SQLite skips this proof because it does
not provide equivalent row-lock behavior.

## 10. UI and browser/manual verification

Browser verification used isolated temporary accounts and a temporary Campaign.
The following paths were checked:

- ordinary verified User: invitation-first Campaign index, no create link;
- direct GET to Campaign creation: redirect plus human-readable denial;
- eligible verified GM: visible create action and accessible creation form;
- Campaign members: ineligible PLAYER has one disabled promotion control and
  no active promotion link;
- desktop and 390×844 mobile views: no tested console errors and no horizontal
  overflow.

The isolated temporary Campaign and four browser-only Users were deleted after
verification. No pre-existing development data was deleted.

## 11. Tests and validation

Focused P5.6 tests cover ordinary/forged creation denial, eligible creation,
verified-email composition, superuser compatibility, direct-vs-group permission
provenance, separation from global canon authority, grant/revoke and no-op audit
semantics, User/Campaign admin restrictions, promotion/revocation behavior,
preservation migration and the PostgreSQL concurrency case.

Recorded results:

- focused P5.6: 13 tests, OK, 1 PostgreSQL-only skip;
- P4.5 regression: 27 tests, OK, 3 expected skips;
- P5.5 passed in the combined compatibility run; the single obsolete P4.5 UI
  assertion found there was updated to the intentional disabled state;
- final combined P4.5/P5/P5.5/P5.6 regression: 97 tests in 225.227 s,
  OK, 7 expected skips;
- full regression suite: 408 tests in 528.095 s, OK, 8 expected skips;
- `manage.py check`: no issues (0 silenced);
- `makemigrations --check --dry-run`: `No changes detected`;
- `git diff --check`: exit 0; only the repository's normal LF-to-CRLF
  working-copy warnings were emitted.

## 12. Files

Implementation:

- `campaigns/models.py`;
- `campaigns/migrations/0011_gm_eligibility_p56.py`;
- `campaigns/services/eligibility.py`;
- `campaigns/services/lifecycle.py`;
- `campaigns/services/memberships.py`;
- `campaigns/views.py`;
- `accounts/admin.py`;
- `campaigns/admin.py`;
- Campaign list/create/member templates.

Tests:

- `campaigns/tests/test_gm_eligibility_p56.py`;
- `campaigns/tests/test_onboarding_p45.py`.

Documentation:

- `AGENTS.md`;
- `WORLD_HANDOFF_v2.md`;
- `Codex Handoff — Future Architecture Guardrails.md`;
- `Fardecosmia_Master_Roadmap_v1_1.md`;
- `docs/P56_PROGRESS.md`;
- this report.

## 13. Scope preservation

P5.6 did not implement or begin PW1, L1, Notes, Party, M2, V1,
Roll20/normalized Character work, XP, Inventory, Economy, Travel or C5. It did
not alter email-verification cryptography, invitation semantics, WorldEvent,
ApprovalRequest, weather/climate physics, or the CampaignMembership role model.
