# Fardecosmia — instructions for coding agents

## Project goal
Fardecosmia is a Django web application for running a tabletop RPG campaign.
It provides player-facing character/campaign pages and a GM control panel that
simulates world time, regional weather, timed/conditional events and related
campaign state.

## Core stack
- Python 3.12+
- Django 5.2 LTS
- PostgreSQL for production; SQLite is allowed for local bootstrap only
- Server-rendered Django templates first
- Add frontend frameworks only when there is a concrete need

## Authentication and permissions
- The custom user model is `accounts.User` and MUST remain configured through
  `AUTH_USER_MODEL = "accounts.User"`.
- Never encode GM/player role directly on User.
- Campaign-specific role belongs to `campaigns.CampaignMembership`.
- A user may be GM in one campaign and player in another.
- All campaign objects must be access-controlled through campaign membership.
- Global canon writes require the centralized `world.manage_global_canon`
  permission (or superuser); campaign GM status does not grant it.
- Campaign-effective canon must be read through the registered override resolver.
  Campaign overrides never mutate the global base object.

## Roll20 integration
- The group uses Roll20 **D&D 5E Classic / Legacy D&D 5E (2014)**.
- Roll20 remains the source of truth for combat-sheet data.
- Fardecosmia stores campaign/world data and a mirrored normalized character state.
- Keep Roll20-specific data outside `characters.Character`.
- Raw Roll20 fields belong in `Roll20CharacterBinding.raw_attributes`.
- Stable application-facing values belong in `normalized_state`.
- Current sync protocol is `Fardecosmia Roll20 Protocol v1`.
- Support both full `snapshot` syncs and partial `delta` syncs.
- Every incoming event has an idempotent `event_id`.
- Never match Roll20 characters to local characters by name automatically.
  Bind them explicitly by Roll20 character ID.
- Future Django -> Roll20 changes must use queued commands and conflict checks,
  never blind overwrites.

## World simulation
- Campaign time is stored as integer game minutes, not real-world datetime.
- World advancement is a service operation and should remain transactional.
- Advancing time may trigger weather generation, events and later NPC/faction clocks.
- Simulation code belongs in service modules rather than views/models when practical.

## Coding conventions
- Prefer explicit, readable Django code over clever abstractions.
- Keep views thin and business logic in services.
- Use `settings.AUTH_USER_MODEL` or `get_user_model()` instead of importing User
  into unrelated apps.
- Use database constraints for important invariants where possible.
- Keep integration boundaries versioned and testable.
- Do not store external API/device secrets in plaintext; store hashes where possible.
- Validate external JSON payloads before changing campaign state.
- Meaningful user-authored world/campaign mutations must call the centralized
  `world.services.audit.record_audit()` inside the same database transaction.
- Audit history is append-only application data: do not update/delete rows or add
  purge/pruning UI. Generated weather, snapshots and solver timesteps are not
  individual audit actions.
- Audit payloads use explicit domain serializers. Never copy request payloads or
  technical secrets into `before_state`, `after_state` or `metadata`; oversized
  payloads must fail explicitly rather than being silently truncated.
- Campaign approvals use the registered intent handlers in
  `world.services.approvals`; an `ApprovalRequest` is never an arbitrary command
  queue or a substitute for `WorldEvent`.
- Every approval handler must validate and version its payload, provide a
  human-readable presenter with consequences, revalidate current state before
  applying, and enforce campaign-scoped permissions.
- Approval, domain mutation, structured result and P3 audit rows must commit in
  one transaction. `APPROVED` means the domain action succeeded; otherwise the
  request remains pending (or enters the appropriate non-approved terminal state).
- Resolved approval requests are immutable through normal application paths.
  Never add a raw JSON approval-creation UI.
- Never store email-verification codes or campaign-invitation tokens in
  plaintext. Persist only slow hashes plus the minimum lookup metadata.
- Campaign authority remains exclusively in `campaigns.CampaignMembership`;
  verified email, invitation authorship and account staff flags are not campaign
  roles.
- Normal registration, email verification, campaign creation and invitation
  acceptance must remain available without Django Admin.
- Transactional email must go through the centralized accounts email service
  and Django email backend; provider credentials belong only in environment
  configuration.
- A verification code is not an invitation token, and accepting an invitation
  is not an `ApprovalRequest`.
- A campaign must retain at least one GM. Role changes and removals must enforce
  this invariant transactionally.
- Authentication secrets, verification codes, reset tokens and invitation
  tokens must never enter `AuditLog` payloads or summaries.
- Audit an existing `WorldEvent` implementation and its data before changing its
  schema; never replace or reinterpret stored event rows destructively.
- A WorldEvent definition/schedule is mutable planning data. A
  `WorldEventOccurrence` is immutable objective Campaign history. Neither is
  player knowledge, an `AuditLog`, an `ApprovalRequest`, a generic application
  event bus or an event-sourcing store.
- WORLD_TIME one-shot events use the explicit crossing interval `(old, new]` and
  must not be skipped by exact/fast-forward boundaries. Same-time events are
  ordered deterministically by stored ID.
- WorldEvent triggers/effects must be registered, versioned, bounded and
  secret-safe. Never evaluate DB code or apply arbitrary JSON model mutations.
- An event effect, its occurrence and all resulting domain/event audits share
  one transaction and operation ID. A failed effect must leave none of them
  committed.
- Do not couple an effect to atmospheric state inside a skipped interval until
  a future phase explicitly introduces split-at-event simulation boundaries.
- Objective occurrences remain GM-only until a separate CharacterKnowledge or
  publication layer grants player-safe knowledge.

## After changes
Run, when available:

```bash
python manage.py check
python manage.py test
```

For model changes also run:

```bash
python manage.py makemigrations --check --dry-run
```

Do not silently generate production migrations unless the task explicitly asks for them.
