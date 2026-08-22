# ФАРДЕКОСМИЯ — P4.5
## Account Onboarding, Email Verification, Campaign Lifecycle & Membership
### Registration, verified email, password reset, campaign creation, invitations and human-first membership management

> Перед началом перечитать актуальные `AGENTS.md`, `WORLD_HANDOFF_v2.md`, `ARCHITECTURE_GUARDRAILS.md`, `MASTER_ROADMAP.md`, P1/P2, P3 и P4 reports.
>
> P4.5 закрывает текущий user-flow gap: normal user больше не должен зависеть от Django Admin для регистрации, создания кампании и вступления в неё.
>
> НЕ начинать P5 WorldEvent, CharacterKnowledge, M2, Inventory/Purchases, Travel, Character/Fog, C5 и M1.5.

---

# 0. Главная цель

После P4.5 новый человек проходит:

```text
Открывает сайт
↓
Регистрация
↓
Подтверждение email 6-значным кодом
↓
Вход
↓
Ваши кампании
├── Создать кампанию
└── Принять приглашение
```

Создание Campaign:

```text
Campaign
+
CampaignMembership(user=creator, role=GM)
```

создаётся атомарно.

Принятие приглашения:

```text
CampaignMembership(user=invitee, role=PLAYER)
```

создаётся безопасно и без Django Admin.

---

# 1. UX standard

Обязательное правило:

```text
HUMAN FIRST
TECHNICAL SECOND
```

Auth/onboarding UI должен выглядеть как часть Фардекосмии, а не как raw Django forms.

Не показывать обычному пользователю:
- internal field names;
- raw exception text;
- challenge IDs;
- token hashes;
- SMTP details;
- UUIDs;
- `PLAYER/GM` enum values как технические строки.

UI labels — нормальным русским языком.

---

# 2. Registration

Форма:

```text
Имя пользователя
Email
Пароль
Повтор пароля
```

Использовать существующий `accounts.User` и `AUTH_USER_MODEL`.

Обязательно:
- Django password validators;
- CSRF;
- email normalization;
- username validation;
- duplicate handling;
- field-level human-readable errors.

Не создавать второй User model.

---

# 3. Email is required and verified

После P4.5 normal interactive account должен иметь обязательный подтверждённый email.

Не ломать current superuser/admin migration.

Codex должен сначала inspect current `accounts.User`.

Recommended semantics:

```text
registered
↓
email not verified
↓
доступ только к:
- verify email
- resend code
- logout
- limited onboarding
↓
verified
↓
full normal access
```

Prefer explicit verification state (`email_verified_at` nullable timestamp или clean equivalent) rather than abusing `is_active`, если это лучше сохраняет admin/superuser compatibility.

Final choice documented.

---

# 4. Email uniqueness / normalization

Email case-insensitive unique.

```text
User@example.com
user@example.com
```

не могут принадлежать двум аккаунтам.

Создать одну canonical email-normalization helper и использовать её в:
- registration;
- invitations;
- verification;
- future email change.

Prefer DB-level protection where practical in PostgreSQL, with SQLite-compatible local strategy.

Не fabricating emails for existing users.

---

# 5. Login identity

Не менять auth identity без необходимости.

Если current login=username:
- сохранить.

Optional username-or-email login допускается только если cleanly implemented через auth backend и не ломает tests.

Это не blocker.

---

# 6. EmailVerificationChallenge

Добавить model/equivalent:

```text
EmailVerificationChallenge
```

Recommended:

```text
user
email_snapshot
code_hash
created_at
expires_at
attempt_count
max_attempts
last_attempt_at nullable
verified_at nullable
consumed_at nullable
generation/resend metadata if useful
```

Plain code в DB запрещён.

---

# 7. Verification code security

Recommended configurable defaults:

```text
6 digits
10 minutes lifetime
5 attempts
60 seconds resend cooldown
```

Generate cryptographically secure random code.

Не использовать Python global `random`.

Store hash via Django password hasher or equivalent safe scheme.

Old code invalid after resend/new challenge.

---

# 8. Verification UX

После registration:

```text
Мы отправили код на:
u***@example.com

Код подтверждения
[      ]

[Подтвердить]

Отправить код повторно
```

Use `inputmode=numeric`, `autocomplete=one-time-code`, max length 6.

Wrong code:

```text
Код неверный.
Осталось попыток: 3
```

Expired:

```text
Срок действия кода истёк.
Отправьте новый код.
```

No technical hashes/errors.

---

# 9. Resend/rate limiting

Protect:
- registration abuse;
- resend spam;
- brute-force code attempts.

Minimum:
- per-user resend cooldown;
- attempt limit per challenge;
- duplicate email registration protection.

Optional lightweight per-IP throttling if clean.

Do not add CAPTCHA/external anti-bot provider in P4.5.

GET must not mutate verification state.

---

# 10. Central email service

Create centralized abstraction, e.g.:

```text
accounts/services/email.py
```

Use Django email backend.

Do not scatter provider-specific SMTP calls.

Development:
- console/file backend.

Production:
- SMTP/transactional provider through environment-backed Django settings.

Credentials never in Git/DB/world AuditLog.

---

# 11. Email templates

Use templates:

```text
templates/emails/
  verify_email_subject.txt
  verify_email.txt
  verify_email.html
  campaign_invitation_subject.txt
  campaign_invitation.txt
  campaign_invitation.html
  password_reset_subject.txt
  password_reset.txt
  password_reset.html
```

HTML + plain-text fallback.

Readable Fardecosmia branding, minimal external assets.

Verification mail example:

```text
Фардекосмия

Подтверждение email

Ваш код:
483921

Код действует 10 минут.

Если вы не регистрировались,
просто проигнорируйте письмо.
```

Never email password.

---

# 12. Email sending failure

Do not 500 with SMTP details.

Registration:
```text
Аккаунт создан, но письмо сейчас не удалось отправить.
Попробуйте отправить код повторно.
```

Technical exception logged server-side without code/token/password.

Do not require Celery/Redis in P4.5.

---

# 13. Password reset

Implement branded Django-secure password reset by email.

Flow:

```text
Забыли пароль?
↓
Введите email
↓
нейтральный success response
↓
письмо со secure link
↓
новый пароль
```

For known and unknown email show same response:

```text
Если аккаунт с таким email существует,
мы отправили инструкции по восстановлению.
```

Use password validators.

No raw token UI.

---

# 14. Future email change

Full email-change UI is optional/not required.

Architecture must allow:

```text
new email requested
↓
verify new email
↓
replace account email
```

If email is changed through normal/admin paths, verification must not remain falsely valid.

Document admin behavior.


# 15. Existing "Ваши кампании" page

Preserve current polished style.

Empty state should become actionable:

```text
Пока здесь тихо

Вы ещё не участвуете ни в одной кампании.

[Создать кампанию]
[Присоединиться по приглашению]
```

If there is no generic token-entry flow, second action may explain:

```text
Откройте ссылку, которую прислал Game Master.
```

Do not redesign the whole site.

---

# 16. Campaign creation

Verified normal user can create Campaign.

Minimal form:

```text
Название кампании
Краткое описание — optional
```

Do not expose advanced simulation settings in onboarding.

Transaction:

```text
create Campaign
+
create CampaignMembership(creator, GM)
+
P3 AuditLog
```

all-or-nothing.

No separate `Campaign.owner` unless already part of current domain.

Creator is initial GM through membership.

---

# 17. Campaign defaults

Use existing safe model/service defaults.

Do not invent:
- fake Regions;
- demo lore;
- random players;
- canon date.

Advanced climate/simulation config stays existing GM functionality.

---

# 18. Campaign basic editing

GM can edit basic presentation fields such as:
- name;
- description;
- any existing safe equivalent.

P3 audit with human summary.

Do not add normal hard-delete Campaign button in P4.5.

Campaign deletion/archive needs separate high-impact design later.

---

# 19. Membership management page

Campaign GM gets:

```text
Участники
```

Readable UI:

```text
Руслан
Game Master

Артём
Игрок
[Сделать Game Master] [Удалить]
```

Preserve only existing roles:

```text
CampaignMembership.PLAYER
CampaignMembership.GM
```

No new role taxonomy.

---

# 20. CampaignInvitation

Add secure invitation model:

```text
CampaignInvitation
```

Recommended fields:

```text
campaign
email_normalized
role
created_by
created_at
expires_at
token_hash
token lookup prefix/id if needed
accepted_at nullable
accepted_by nullable
revoked_at nullable
use_count / consumed marker
```

P4.5 recommended invitation role:
```text
PLAYER only
```

Promotion to GM is a separate explicit action.

This prevents privilege escalation by accidental invite.

---

# 21. Invitation token

Invitation uses high-entropy secret URL token.

Never:

```text
/invite/123
```

as sole secret.

Store only token hash.

Plain token exists only when generated and inside outbound link.

Verification code and invite token are different mechanisms:
- email verify = short code;
- campaign invite = high-entropy URL secret.

---

# 22. Invite email

GM enters email:

```text
player@example.com
```

Email contains:
- campaign name;
- inviter display name;
- role "Игрок";
- safe invite URL;
- expiration.

No GM secrets/campaign world state.

---

# 23. Invite flow — logged out

Invite GET can be pre-auth because token is capability secret.

Show only minimal safe info:

```text
Вас пригласили в кампанию «...»
Приглашает: ...
Роль: Игрок

[Войти]
[Зарегистрироваться]
```

Do not expose roster/regions/audit.

Acceptance itself requires POST after auth/verification.

---

# 24. Invite context preservation

Critical:

```text
invite link
↓
register/login
↓
email verification
↓
return to invitation
↓
accept
```

Do not lose invite context.

Use safe session/`next` flow.

Prevent open redirect.

---

# 25. Email-bound invitation

Invitation sent to:

```text
player@example.com
```

can be accepted only by verified account whose normalized email matches.

If existing account:
- user explicitly accepts.

If no account:
- user registers with same email;
- verifies;
- returns;
- accepts.

Forwarding email to unrelated account must not bypass binding.

Reusable/general invite links are future feature, not P4.5.

---

# 26. Invitation expiry/revoke

Recommended default:
```text
7 days
```
as configurable technical value.

Expired page:
```text
Это приглашение больше не действует.
Попросите Game Master отправить новое.
```

GM can revoke pending invite.

Single-use recommended.

After acceptance token no longer works.

---

# 27. Duplicate invites

Avoid multiple active invites for same:

```text
campaign + normalized email
```

Service should deterministically:
- reuse/resend;
- or revoke/replace.

Document final behavior.

No email spam.

---

# 28. Invite sending failure

Preferred semantics:
- invitation DB row remains valid;
- UI clearly reports mail failure;
- GM can regenerate/resend/copy a new link as designed.

Do not claim email was sent when provider failed.

Because plaintext token is not stored, old link cannot be reconstructed later.

Safe UX:
- show copy link immediately after generation;
- if lost, regenerate/reissue invitation.

Do not persist plaintext token just for convenience.

---

# 29. Invitation acceptance transaction

Atomic:

```text
validate token
validate not expired/revoked/consumed
validate verified email match
validate no existing membership
create PLAYER CampaignMembership
mark invite consumed/accepted
P3 AuditLog
commit
```

If membership already exists:
```text
Вы уже состоите в этой кампании.
```

No raw unique-constraint error.

---

# 30. Membership removal

GM can remove PLAYER.

This removes access membership only.

Do not:
- delete User;
- delete Character automatically;
- delete campaign history.

Audit human-readable.

---

# 31. Promote/demote

GM can promote:
```text
Игрок → Game Master
```

with clear warning that user gains full GM rights for that Campaign.

GM can demote GM only if another GM remains.

No global Canon Editor permission is granted.

---

# 32. Last-GM invariant

Mandatory:

```text
Every active Campaign must retain >= 1 GM membership.
```

Cannot:
- remove last GM;
- demote last GM.

Human error:

```text
В кампании должен остаться хотя бы один Game Master.
```

Service-level transaction/locking required.

Concurrent two-GM demotions/removals must not orphan campaign on PostgreSQL.

---

# 33. Membership uniqueness

One user max one membership per Campaign.

Ensure DB constraint if not already present.

Invitation acceptance relies on it.

---

# 34. Permission rules

GM A:
- manage Campaign A members/invites.
- cannot manage B.

Player:
- cannot manage members/invites.

Canon Editor-only:
- no Campaign authority.

Superuser:
- central bypass.

CampaignMembership remains source of truth.

---

# 35. Player experience after P4.5

PLAYER does not suddenly receive GM tools.

Player can:
- see campaign in "Ваши кампании";
- open player-safe campaign landing;
- view own P4 requests where permitted.

Future Character/Knowledge/Quests fill product later.

P4.5 goal is to remove onboarding dead-end, not implement all player gameplay.

---

# 36. Human-first pages

Registration:
```text
Создать аккаунт
...
[Создать аккаунт]
```

Verification:
```text
Подтвердите email
Код отправлен на u***@example.com
```

Login:
```text
Войти
Забыли пароль?
Нет аккаунта? Зарегистрироваться
```

Campaign create:
```text
Создать кампанию
Название
Описание
```

Members:
```text
Участники кампании
```

Invitation:
```text
Вас пригласили в кампанию ...
```

No raw Django/admin styling.

---

# 37. Mobile/responsive

All new pages must work on narrow/mobile widths.

No wide technical tables.

Use existing card/stacked pattern.

---

# 38. Accessibility basics

Use:
- proper labels;
- field-associated errors;
- autocomplete `username`, `email`, `new-password`;
- `one-time-code`;
- keyboard-friendly controls;
- non-color-only statuses.

---

# 39. P3 AuditLog boundary

Audit campaign-side meaningful actions:

```text
campaign.created
campaign.updated
campaign_invitation.created
campaign_invitation.revoked
campaign_member.joined
campaign_member.role_changed
campaign_member.removed
```

Human summaries, e.g.:

```text
Создана кампания «...».
Игрок ... присоединился к кампании.
Роль ... изменена: Игрок → Game Master.
```

Do NOT put into world AuditLog:
- verification attempts;
- password reset tokens;
- login failures;
- SMTP errors;
- security codes.

Those belong to security/application logging.

---

# 40. P4 interaction

Do not route:
- campaign creation;
- invite acceptance;
- normal role changes

through ApprovalRequest.

Invite already expresses GM permission + user consent.

P4 remains available for future sensitive domain workflows.

---

# 41. User email privacy

Do not expose full member email to ordinary players.

GM management UI may show member email when needed.

Audit summary can mask invitation email where appropriate:

```text
p***@example.com
```

Do not leak verification/invite tokens into AuditLog.

---

# 42. Email enumeration

Password reset MUST use neutral response.

Registration duplicate email may use explicit message for usability if project chooses.

Document policy.

---

# 43. CSRF / GET safety

All mutations POST:
- register;
- verify;
- resend;
- campaign create/edit;
- invite create/revoke;
- invite accept;
- role change;
- member removal;
- reset submit.

GET read-only.

Invite GET displays intent only.

---

# 44. Services

Preferred boundaries:

```text
accounts/services/registration.py
accounts/services/email.py
accounts/services/verification.py

campaigns/services/lifecycle.py
campaigns/services/invitations.py
campaigns/services/memberships.py
```

Adapt to current project layout.

Views remain thin.

---

# 45. Existing-user / superuser compatibility

Codex must audit current DB/schema.

No migration should unexpectedly lock out current superuser.

If current superuser lacks verified email:
- safe bypass/admin compatibility;
- or explicit migration/admin verification path.

Existing normal users need documented migration policy.

Do NOT fabricate email addresses or silently claim ownership without a deliberate choice.

---

# 46. Email change invalidates verification

If verified email A changes to B through supported edit path:
```text
verification must reset
```

Admin behavior must be considered.

Do not allow verified flag/timestamp to remain valid for a different address unless explicit superuser override.

---

# 47. No background worker requirement

Synchronous email is acceptable at current scale.

No Celery/Redis just for P4.5.

Future notification queue separate.

---

# 48. Future notification foundation

Email infrastructure should be reusable for:
- approval notifications;
- session reminders;
- account security;
- campaign event notifications.

P4.5 implements only:
- verification;
- invitation;
- password reset.

No marketing/newsletters.

Verified email is not marketing consent.


# 49. Required browser/manual flow

New user:
1. register;
2. invalid password presentation;
3. registration succeeds;
4. verification email captured by dev backend;
5. wrong code;
6. resend;
7. old code invalid;
8. correct code;
9. campaigns empty state.

Campaign:
10. create Campaign;
11. creator is GM;
12. members page;
13. create invitation;
14. copy/send link.

Invitee:
15. open link logged out;
16. register from invite;
17. verify;
18. return to invite;
19. accept;
20. campaign appears.

Membership:
21. promote player;
22. demote when another GM exists;
23. reject last-GM demotion/removal;
24. remove player;
25. revoke pending invite.

Password:
26. password reset request;
27. dev email;
28. reset link;
29. login with new password.

No console errors.


# 50. 5-second readability acceptance

Before closing P4.5, manual YES required:

Registration:
- obvious what to enter and why.

Verification:
- obvious where code was sent and what to do.

Campaign list:
- obvious how to create/join.

Invite:
- obvious who invites, to which Campaign, role, next action.

Members:
- obvious who is GM/player and what actions are available.

If not, refine UI despite green backend tests.


# 51. Required tests — registration/verification

1. creates existing `accounts.User`.
2. email required.
3. canonical normalization.
4. case-insensitive duplicate rejected.
5. password validators applied.
6. challenge created.
7. plaintext code absent from DB.
8. verification email sent.
9. unverified access restricted per final policy.
10. correct code verifies.
11. wrong code increments attempts.
12. attempt limit invalidates.
13. expired rejected.
14. resend cooldown.
15. old code invalid after resend.
16. GET does not mutate.
17. email change invalidates verification where applicable.


# 52. Required tests — email/reset

1. verification subject/body readable.
2. plain text version.
3. HTML version where intended.
4. code included.
5. password never included.
6. invite email contains link.
7. provider failure handled without 500/security leak.
8. known reset email → neutral success + message.
9. unknown reset email → same neutral success.
10. valid reset token sets password.
11. validators apply.
12. reused/invalid token rejected.
13. new password works.


# 53. Required tests — Campaign creation

1. verified normal user can create.
2. Campaign + GM membership atomic.
3. creator is GM.
4. no second owner authority system introduced.
5. P3 audit created.
6. rollback if membership/audit fails.
7. user may GM multiple campaigns.
8. unverified user denied according to final policy.


# 54. Required tests — invitation

1. GM can create.
2. Player cannot.
3. Canon Editor-only cannot.
4. token high entropy.
5. DB stores only hash.
6. email sent.
7. bound to normalized email.
8. expired rejected.
9. revoked rejected.
10. consumed rejected.
11. wrong verified email rejected.
12. matching verified account accepted.
13. membership + consume + audit atomic.
14. existing membership gracefully handled.
15. duplicate active invite deterministic.
16. GET does not accept/mutate.
17. invite context survives auth/verification.
18. plaintext token absent from AuditLog.


# 55. Critical end-to-end invitation test

```text
GM creates invite for new@email
↓
new user opens invite
↓
registers with same email
↓
verifies email
↓
invite context preserved
↓
accepts
↓
CampaignMembership PLAYER exists
↓
campaign appears in user's list
```

This is mandatory.


# 56. Required tests — memberships

1. GM sees management page.
2. Player denied.
3. GM A denied B.
4. PLAYER→GM works.
5. GM→PLAYER works if another GM remains.
6. remove PLAYER works.
7. last GM demotion rejected.
8. last GM removal rejected.
9. membership uniqueness.
10. role change audited.
11. removal audited.
12. User not deleted.
13. Character not auto-deleted.


# 57. Concurrency

PostgreSQL-important tests:
- concurrent invite acceptance cannot duplicate membership;
- concurrent last-GM changes cannot orphan campaign;
- duplicate invite creation safe.

SQLite may skip locking-specific test with explicit report, as in P4.

Service invariants still covered locally.


# 58. Permission matrix

Include:

```text
Anonymous
Unverified user
Verified user no campaign
Player A
GM A
GM B
Canon Editor only
Canon Editor + GM A
Superuser
```

Operations:
- register;
- verify;
- create Campaign;
- view/manage A;
- create invite A;
- accept invite;
- promote/remove member;
- manage B;
- global canon access.

Report final matrix.


# 59. Regression baseline

P4 baseline:

```text
294 tests passed
```

All existing tests remain green.

Must not change:
- AtmosphericGrid;
- WeatherState;
- RegionAreaWeatherState;
- C1–C4.2;
- R1;
- M1;
- P1/P2 access semantics;
- P3 audit semantics;
- P4 ApprovalRequest semantics.


# 60. Performance/report

Measure:
- registration service excluding network;
- verification;
- Campaign create;
- invite create;
- invite accept;
- campaigns page query count;
- members/invites page query count.

No climate benchmark required.

No N+1.


# 61. Production email configuration

Implementation report must state:
- Django email backend used;
- required env variable names;
- DEFAULT_FROM_EMAIL;
- TLS/SSL strategy;
- dev backend;
- how to smoke-test safely.

Never include real credentials.

Do not hardcode Gmail/provider credentials.


# 62. Migrations

P4.5 explicitly authorizes migrations for:
- email verification state;
- EmailVerificationChallenge;
- CampaignInvitation;
- email uniqueness/indexes;
- membership constraints if missing.

Apply locally.

No fake users/campaigns/invites data migration.

Migration must treat existing users safely.


# 63. Documentation updates

After success:

WORLD_HANDOFF:
```text
P4.5 completed
next P5 WorldEvent
```

Add:
- verified email = transactional contact foundation;
- normal user can create Campaign;
- creator becomes GM through CampaignMembership;
- invitations are secure email-bound single-use tokens;
- last GM invariant;
- account/security activity != world AuditLog.

AGENTS:
```text
Never store verification codes/invite tokens plaintext.
Campaign authority remains CampaignMembership.
Normal onboarding must not require Django Admin.
Email goes through centralized service/backend.
```

Guardrails:
```text
Verification code != invitation token.
Invite acceptance != ApprovalRequest.
Last GM cannot be removed/demoted.
No auth secrets/tokens in AuditLog.
```

Update roadmap only after acceptance.


# 64. Acceptance Criteria

P4.5 complete when:

1. Normal user can register without Admin.
2. Email required.
3. Case-insensitive email uniqueness.
4. Verification state implemented.
5. Secure 6-digit challenge.
6. Code stored hashed.
7. Expiry/attempt limits/resend cooldown work.
8. Old code invalid after resend.
9. Unverified access policy works.
10. Central email service exists.
11. Dev email backend works.
12. Production SMTP config documented.
13. Branded email templates exist.
14. Password reset works safely.
15. Password reset avoids enumeration.
16. Current superuser/admin still works.
17. Existing users handled safely.
18. Verified normal user can create Campaign.
19. Creator atomically becomes GM.
20. Campaign creation audited.
21. "Ваши кампании" empty state is actionable.
22. GM membership page exists.
23. GM can invite by email.
24. Invite token high entropy.
25. Token stored hashed.
26. Invite is email-bound and single-use.
27. Expiry/revoke work.
28. Invite context survives registration/login/verification.
29. Correct verified email can accept.
30. Wrong email cannot.
31. Acceptance atomically creates PLAYER membership.
32. Acceptance audited.
33. Existing member handled gracefully.
34. Duplicate active invites handled.
35. GM can promote/demote/remove.
36. Last GM cannot be removed/demoted.
37. Cross-campaign access denied.
38. Canon Editor-only gains no Campaign authority.
39. Player emails not unnecessarily exposed.
40. GET remains read-only.
41. Human-first auth/invite/member UI passes manual review.
42. Mobile layouts readable.
43. Existing 294 tests pass.
44. New auth/email/invite/membership tests pass.
45. M1/R1/Atmosphere/P4 unchanged.
46. P5/CharacterKnowledge/M2/Inventory/Travel/C5 not started.


# 65. P4.5 IMPLEMENTATION REPORT

After implementation STOP and return:

```text
P4.5 ACCOUNT ONBOARDING, EMAIL & CAMPAIGN LIFECYCLE REPORT

1. Changed files
2. Migrations
3. Existing accounts.User audit
4. Email uniqueness strategy
5. Email normalization
6. Verification-state implementation
7. Existing-user migration behavior
8. Superuser compatibility
9. EmailVerificationChallenge
10. Verification-code generation
11. Code hashing
12. Expiry/attempt policy
13. Resend/rate limiting
14. Registration flow
15. Unverified-user access policy
16. Login behavior
17. Email service/backend
18. Development email backend
19. Production SMTP configuration
20. Email templates
21. Verification email example
22. Email failure behavior
23. Password reset
24. Enumeration protection
25. Campaign-list empty state
26. Campaign creation
27. Campaign transaction
28. Initial GM membership
29. Campaign basic edit
30. Campaign deletion policy
31. CampaignInvitation
32. Token generation
33. Token hash/storage
34. Email binding
35. Expiry/revoke
36. Duplicate/resend/regenerate behavior
37. Copy-link behavior
38. Invite email
39. Logged-out invite flow
40. Invite context preservation
41. New-user onboarding from invite
42. Existing-user invite
43. Acceptance transaction
44. Existing-member behavior
45. Members page
46. Promote/demote
47. Remove player
48. Last-GM invariant
49. Last-GM concurrency
50. P2 access integration
51. Permission matrix
52. P3 AuditLog integration
53. Audit summary readability
54. Account/security-log boundary
55. Email privacy
56. IDOR/security tests
57. Registration tests
58. Verification tests
59. Email tests
60. Password reset tests
61. Campaign creation tests
62. Invitation tests
63. Full invite-onboarding test
64. Membership tests
65. PostgreSQL-only concurrency tests/skips
66. Browser/manual verification
67. 5-second readability acceptance
68. Mobile verification
69. Query counts
70. Performance
71. Tests added
72. Full test result
73. manage.py check
74. makemigrations --check --dry-run
75. M1 regression
76. R1 regression
77. Atmosphere scope confirmation
78. P4 regression
79. WORLD_HANDOFF update
80. AGENTS update
81. Guardrails update
82. Master Roadmap status
83. Known limitations
84. Future email-change path
85. Future notifications
86. Future reusable invites
87. Future Character onboarding
88. Confirmation no P5/CharacterKnowledge/M2/Inventory/Travel/C5 was started
```

Stop after report.
