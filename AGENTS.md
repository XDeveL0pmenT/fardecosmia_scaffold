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
