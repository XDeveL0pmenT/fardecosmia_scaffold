# P4.5 ACCOUNT ONBOARDING, EMAIL & CAMPAIGN LIFECYCLE REPORT

Date: 2026-08-21  
Status: completed; P5 was not started.

## 1. Changed files

Account domain: `accounts/models.py`, `accounts/forms.py`, `accounts/views.py`,
`accounts/urls.py`, `accounts/middleware.py`, `accounts/admin.py`, and the new
`accounts/services/` package. Campaign lifecycle: `campaigns/models.py`,
`campaigns/forms.py`, `campaigns/views.py`, `campaigns/urls.py`,
`campaigns/admin.py`, and the new `campaigns/services/` package. Configuration,
templates and presentation: `config/settings.py`, `config/urls.py`,
`templates/base.html`, `templates/registration/`, `templates/emails/`,
`campaigns/templates/campaigns/`, `templates/campaigns/_campaign_quickbar.html`,
`static/css/app.css`, `static/js/onboarding.js`, and
`world/templatetags/audit_json.py`. Tests, benchmark and documentation were added
under `accounts/tests/`, `campaigns/tests/`, `scripts/` and `docs/`.

## 2. Migrations

- `accounts.0002_emailverificationchallenge_alter_user_options_and_more`
- `campaigns.0009_campaigninvitation`

Both were applied locally. No fake account, Campaign or invitation data was
inserted.

## 3. Existing accounts.User audit

The pre-migration development database contained two users, both with blank
email, and no non-empty case-insensitive duplicates. Existing users are neither
locked out nor falsely declared verified.

## 4. Email uniqueness strategy

`accounts_user_email_ci_unique` is a conditional database
`UniqueConstraint(Lower("email"))` for non-blank values. The migration performs
a read-only duplicate preflight and fails with an actionable error if cleanup is
required.

## 5. Email normalization

Registration, verification, reset and invitation services share
`normalize_email_address()`: whitespace is stripped and the value is
case-folded. Forms provide friendly duplicate errors; the database remains the
race-safe boundary.

## 6. Verification-state implementation

`User` now stores `email_verified_at`, `verified_email` and
`email_verification_required`. `has_verified_email` is true only when the
current normalized email equals the verified snapshot and a verification time
exists. Changing email invalidates verification.

## 7. Existing-user migration behavior

New fields default to an unverified, legacy-compatible state. Existing rows are
not rewritten. A legacy user may continue using existing memberships, while
normal transactional actions such as Campaign creation require an actually
verified email.

## 8. Superuser compatibility

Staff/superusers are not trapped by onboarding middleware and may retain
administrative compatibility with blank legacy email. This bypass does not add
a campaign role; ordinary campaign authority still comes from membership/access
services.

## 9. EmailVerificationChallenge

The model records user, email snapshot, slow code hash, generation, timestamps,
expiry, send/failure state, attempt counters, verification and consumption.
Admin is read-only.

## 10. Verification-code generation

Codes use `secrets.randbelow(1_000_000)` formatted to exactly six ASCII digits.

## 11. Code hashing

Only Django `make_password()` output is stored. Validation uses
`check_password()`; plaintext code exists only long enough to render the email.

## 12. Expiry/attempt policy

Default lifetime is 600 seconds and the maximum is five attempts. Invalid
attempts and consumed/expired markers commit before a public exception is
raised, preventing transaction rollback from resetting the limiter.

## 13. Resend/rate limiting

Default cooldown is 60 seconds. Resend consumes all previous open challenges,
increments generation and creates one new code. GET never creates/resends a
challenge.

## 14. Registration flow

Public registration uses the existing custom `accounts.User`, Django password
validators and a required email. The account is logged in, marked as requiring
verification and directed to the code screen.

## 15. Unverified-user access policy

Middleware restricts newly registered, verification-required users to login,
logout, verification/reset and invitation-context pages. A safe session `next`
path is restored after verification. Legacy-exempt and staff accounts are not
globally locked out.

## 16. Login behavior

Django authentication remains authoritative. An invitation `next` path is
preserved, and verification middleware returns an unverified invite recipient to
the pending invitation after confirmation.

## 17. Email service/backend

`accounts.services.email` is the only transactional templated-email boundary.
It creates `EmailMultiAlternatives`, masks recipients in logs, omits template
context and provider exception strings, and returns a safe delivery result.

## 18. Development email backend

Default development backend is Django's console backend. Tests use the locmem
backend. No Celery/Redis dependency was added.

## 19. Production SMTP configuration

Environment variables: `DJANGO_EMAIL_BACKEND`, `DJANGO_EMAIL_HOST`,
`DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`,
`DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS`,
`DJANGO_EMAIL_USE_SSL`, `DJANGO_EMAIL_TIMEOUT`, and
`DJANGO_DEFAULT_FROM_EMAIL`. Default sender is
`Фардекосмия <noreply@localhost>`. Production should select either TLS or SSL,
never both. Safe smoke test: configure a non-production recipient, issue one
verification email, confirm plain/HTML receipt, then inspect masked logs only.

## 20. Email templates

Branded Russian plain-text and HTML templates exist for verification,
invitation and password reset, each with a separate subject template.

## 21. Verification email example

The message identifies Fardecosmia, shows one six-digit code, states the
ten-minute default lifetime and says to ignore an unrequested registration. It
never contains the password.

## 22. Email failure behavior

Provider failure does not return HTTP 500 or expose the provider exception.
Registration keeps the account and consumes the undelivered challenge so a
fresh resend is safe. Invitation creation keeps the valid token and shows its
one-time copy link.

## 23. Password reset

Django's signed, single-use reset-token flow is retained with project templates,
the centralized email boundary and the normal password validators.

## 24. Enumeration protection

Known and unknown reset emails produce the same neutral success page and
redirect behavior. Only active users with usable passwords and verified/admin
contact state receive mail.

## 25. Campaign-list empty state

The empty state now explains that no memberships exist, offers Campaign creation
when allowed, and tells invitees to open the GM-provided link.

## 26. Campaign creation

A verified normal user can create a Campaign through a server-rendered form;
neither Admin nor a global User role is required.

## 27. Campaign transaction

Campaign row, initial membership and `campaign.created` AuditLog entry share one
`transaction.atomic()` service. A forced audit failure rolls back all three.

## 28. Initial GM membership

The creator receives `CampaignMembership.Role.GM`. The Campaign model gained no
second `owner` authority field, and one user may GM multiple campaigns.

## 29. Campaign basic edit

Campaign-scoped GMs may edit only name/description through the lifecycle service.
Changes are locked, validated and audited; simulation fields are not exposed by
this form.

## 30. Campaign deletion policy

No normal hard-delete button/path was added. Campaign deletion is disabled in
the adjusted Admin surface.

## 31. CampaignInvitation

The model stores campaign, normalized recipient, PLAYER-only role, actor label
snapshots, expiry/delivery/acceptance/revocation state and hashed token lookup
metadata.

## 32. Token generation

Invitations use `secrets.token_urlsafe(32)`, providing 32 random bytes and a
high-entropy URL-safe token.

## 33. Token hash/storage

Only the first 16 characters used as a unique lookup prefix and a slow Django
password hash are persisted. Plaintext tokens are absent from DB, sessions and
AuditLog.

## 34. Email binding

Acceptance requires the authenticated account's currently verified normalized
email to exactly match the invitation recipient. Staff status does not bypass
this binding.

## 35. Expiry/revoke

Default lifetime is seven days. Expired, revoked and consumed invites are
rejected. Revocation is POST-only, GM-scoped, locked and audited.

## 36. Duplicate/resend/regenerate behavior

Creating another active invitation for the same campaign/email revokes the old
one and issues a fresh token in a deterministic, campaign-locked operation. A DB
conditional unique constraint permits only one outstanding row.

## 37. Copy-link behavior

The raw link is displayed only in the immediate creation response. Refreshing
the normal members page cannot recover it; a lost link requires a regenerated
invitation.

## 38. Invite email

Plain/HTML invitation messages include inviter label, Campaign name, PLAYER
role, expiry and the absolute link. Provider credentials are never hardcoded.

## 39. Logged-out invite flow

Opening a valid token shows inviter, Campaign, role, expiry/status and clear
login/registration actions without exposing the bound recipient address.

## 40. Invite context preservation

After token validation the session stores only the invitation row ID. Raw token
is not persisted. Registration/login/verification resume through
`/invite/resume/`.

## 41. New-user onboarding from invite

The browser-verified path is: open invite → register matching email → enter one
wrong code → enter correct code → resume invite → accept → player Campaign page
→ Campaign appears in list.

## 42. Existing-user invite

A matching verified existing user may log in and accept directly. A wrong or
unverified account receives a human-readable refusal and no membership mutation.

## 43. Acceptance transaction

Invitation row and Campaign are locked. Membership creation, token consumption
and P3 audit commit atomically. An audit failure rolls the membership and
acceptance marker back.

## 44. Existing-member behavior

A matching user who already belongs to the Campaign is handled idempotently:
the single invitation is consumed, no duplicate membership is created, and the
result is audited as acceptance rather than a second join.

## 45. Members page

GM-only page presents participant names/emails, campaign-local role badges,
explicit actions, the invitation form and recent invitation status history.

## 46. Promote/demote

PLAYER→GM and GM→PLAYER are campaign-locked service operations with readable
audit diffs. They do not grant/revoke global canon permission.

## 47. Remove player

PLAYER membership removal is audited. The User survives and any owned Character
survives with its nullable owner cleared by the existing model relationship.

## 48. Last-GM invariant

The final GM cannot be demoted or removed. Removing a non-final GM directly is
also refused; the UI requires demotion first, making intent explicit.

## 49. Last-GM concurrency

Services lock the Campaign before counting/changing GM memberships. A dedicated
PostgreSQL-only race test runs two final-GM demotions and requires exactly one to
succeed.

## 50. P2 access integration

All management services call centralized campaign access checks. Canon Editor
alone gains no campaign power, a foreign GM cannot manage another Campaign, and
player-safe landing pages expose no GM tools.

## 51. Permission matrix

| Actor | Register/verify | Create Campaign | View A | Manage/invite A | Accept matching invite | Global canon write |
|---|---:|---:|---:|---:|---:|---:|
| Anonymous | yes | no | no | no | no | no |
| Unverified new user | verification only | no | restricted | no | no | no |
| Verified, no Campaign | n/a | yes | no | no | yes | no |
| Player A | n/a | yes | yes | no | yes | no |
| GM A | n/a | yes | yes | yes | yes | no unless separately permitted |
| GM B | n/a | yes | no | no | yes | no unless separately permitted |
| Canon Editor only | n/a | yes | no | no | yes | yes |
| Canon Editor + GM A | n/a | yes | yes | yes | yes | yes |
| Superuser | compatible | yes | access-service override | access-service override | only matching verified email | yes |

## 52. P3 AuditLog integration

Audited actions: Campaign created/updated, invitation created/revoked/accepted,
member joined/role changed/removed. Each domain mutation and audit row share a
transaction.

## 53. Audit summary readability

Human Russian action labels, summaries and field labels were registered in
`world/templatetags/audit_json.py`. Emails are masked and tokens never appear.

## 54. Account/security-log boundary

Registration, verification attempts, login/logout and password resets do not
create world AuditLog rows. Challenge security timestamps remain in the account
model; ordinary provider failures use application logging.

## 55. Email privacy

Public invitation screens never reveal the bound recipient. Verification and
logs use masked addresses. Full participant email is limited to the GM-only
membership-management surface where it is needed for invitation/account
identification.

## 56. IDOR/security tests

Tests cover foreign GM/player/Canon Editor denial, cross-Campaign membership and
invitation IDs, forged tokens returning 404, wrong verified email, secret-free
AuditLog, CSRF-backed forms and POST-only mutations.

## 57. Registration tests

Coverage includes existing custom User creation, required/canonical unique email,
database case-insensitive uniqueness, password validation, hashing, safe provider
failure and legacy/superuser compatibility.

## 58. Verification tests

Coverage includes hashed code, correct/wrong code, committed attempt counts,
attempt exhaustion, expiry, resend cooldown, old-code invalidation, read-only GET
and email-change invalidation.

## 59. Email tests

Tests assert branded readable subjects/bodies, plain and HTML alternatives,
required code/link, absence of passwords and safe provider-failure responses.

## 60. Password reset tests

Tests assert identical neutral known/unknown responses, valid plain/HTML reset
link, password validators, successful password change, validity of the new
password and invalid/reused token rejection.

## 61. Campaign creation tests

Verified creation, initial GM, no owner field, multiple GM Campaigns, audit,
atomic rollback, edit permissions and unverified/staff behavior are covered.

## 62. Invitation tests

Creation permissions, entropy/hash, email delivery, copy link, fail-soft mail,
replace/revoke/expire/consume, mismatch, atomic audit, existing membership,
GET safety, IDOR and POST-only behavior are covered.

## 63. Full invite-onboarding test

One mandatory automated test covers the complete new-recipient flow, including
session continuation through registration and email verification. The same core
flow was repeated in the local browser against an isolated database.

## 64. Membership tests

GM/player page access, cross-Campaign denial, promote/demote, last-GM protection,
remove-player preservation, uniqueness and GET safety are covered.

## 65. PostgreSQL-only concurrency tests/skips

Three P4.5 row-lock race tests cover final-GM demotion, duplicate acceptance and
duplicate invitation creation. They are explicitly skipped on SQLite because it
has no row-level `SELECT FOR UPDATE`. The full suite has one additional existing
PostgreSQL-only P4 concurrency skip.

## 66. Browser/manual verification

An isolated migrated SQLite database and synthetic accounts were used on
`127.0.0.1:8765`. Registration, verification feedback, Campaign creation,
invitation mail/link, logged-out invite, context resume, acceptance, list/detail,
promotion, demotion and final-GM refusal were verified. Browser console: zero
warnings/errors. The temporary server/settings/database were removed afterward.
Password-reset mutation and player removal were exercised by integration tests;
the browser run did not alter those final synthetic states separately.

## 67. 5-second readability acceptance

YES for registration, verification, Campaign empty state, invite and members
screens: each page names the current task, required next action, relevant role
and consequence without requiring raw IDs or JSON.

## 68. Mobile verification

Verified at 390×844. Initial audit found a 498 px horizontal layout caused by
the decorative orbit. Mobile `.auth-intro` now clips that decoration; repeat
measurement reports no horizontal overflow. Campaign cards and registration
form remain readable and touch actions stack appropriately.

## 69. Query counts

Rollback-only benchmark with 12 Campaign memberships: Campaign list = 6 SQL
queries. Members page with 21 members and 25 invitations = 9 SQL queries. Counts
include authentication/context middleware and remain independent of row count;
no template N+1 was found.

## 70. Performance

Development-machine medians over five rollback-only runs, email network mocked:

| Operation | Median |
|---|---:|
| Registration excluding network | 782.29 ms |
| Email verification | 549.17 ms |
| Campaign creation | 1.18 ms |
| Invitation creation | 552.85 ms |
| Invitation acceptance | 557.03 ms |

The ~0.55–0.78 second operations are intentionally dominated by Django slow
password hashing for passwords/codes/tokens, not ORM iteration.

## 71. Tests added

Forty P4.5 tests were added across account onboarding and Campaign lifecycle,
including three PostgreSQL-only concurrency cases.

## 72. Full test result

`python manage.py test --verbosity 1`: **334 passed, 4 skipped**, 342.855 s.
This equals the required 294-test baseline plus 40 P4.5 tests.

## 73. manage.py check

`python manage.py check`: no issues, zero silenced.

## 74. makemigrations --check --dry-run

Result: `No changes detected`.

## 75. M1 regression

M1/Leaflet tests are included in the passing full suite. No atlas service,
coordinate model or map persistence behavior was changed by P4.5.

## 76. R1 regression

R1 region weather lifecycle tests are included in the passing full suite. No
point/area/current/stale weather semantics were changed.

## 77. Atmosphere scope confirmation

AtmosphericGrid, WeatherState, RegionAreaWeatherState, solver coefficients,
snapshots, C1–C4.2 and fast-forward logic were not modified.

## 78. P4 regression

ApprovalRequest handler registry, state machine, decisions, permissions and
audit transaction semantics remain unchanged and pass their existing tests.
Invitation acceptance is intentionally not an ApprovalRequest.

## 79. WORLD_HANDOFF update

Both handoff files now record P4.5 completion, verified-email/contact semantics,
secure invites, CampaignMembership authority, last-GM invariant and the
security-vs-world-audit boundary.

## 80. AGENTS update

Agent rules now prohibit plaintext verification/invitation credentials, keep
normal onboarding independent of Admin, require centralized email, preserve
CampaignMembership authority/last GM and ban auth secrets from AuditLog.

## 81. Guardrails update

Future guardrails explicitly distinguish verification code, invitation token
and ApprovalRequest, and prohibit ad-hoc role/secret/email architectures.

## 82. Master Roadmap status

P4.5 is marked complete. P5 remains the next named Core Platform phase and was
not started automatically.

## 83. Known limitations

Email delivery is synchronous; no queue/retry dashboard exists. Console backend
is development-only. PostgreSQL concurrency cases must run in the production CI
environment. Invitations support only a single email-bound PLAYER recipient.

## 84. Future email-change path

Model-level email change safely invalidates verification, but no normal profile
UI for changing email was added. A future flow should reauthenticate, issue a
new challenge and preserve the old verified contact until confirmation policy is
defined.

## 85. Future notifications

No notification preferences, inbox or asynchronous delivery jobs were added.
They may consume the central email service later without changing campaign role
authority.

## 86. Future reusable invites

Reusable/public links were intentionally excluded. Any future implementation
needs separate audience, quota, expiry, revocation, abuse and audit rules; it
must not weaken the current email-bound path.

## 87. Future Character onboarding

No Character was auto-created from an account or invitation. Character ownership,
knowledge, Roll20 binding and character-builder flows remain future independent
domains.

## 88. Confirmation no P5/CharacterKnowledge/M2/Inventory/Travel/C5 was started

Confirmed. P4.5 changed only account onboarding, transactional email, Campaign
lifecycle/invitations/memberships, their presentation, tests and documentation.
No P5, CharacterKnowledge, M2, Inventory, Travel or C5 implementation began.
