# Фардекосмия — Master Roadmap v1.1
## Revised after P5.5 and Player Experience architecture review

Статусы:
- [x] завершено
- [ ] запланировано
- [~] проектируется / требует решения

---

# 0. Product & architecture principles

- [x] Canon → Campaign Override foundation.
- [x] Campaign-scoped roles.
- [x] AuditLog foundation.
- [x] ApprovalRequest foundation.
- [x] WorldEvent definition/occurrence foundation.
- [x] Character identity/player-control foundation.
- [x] Player Experience Architecture v1 defined.
- [ ] Player-facing world follows Visibility/Discovery rules rather than objective GM truth.
- [ ] Fardecosmia authoritative for persistent progression/economy/inventory/world-facing Character state.
- [ ] Roll20 authoritative for battle-runtime/combat representation where appropriate.
- [ ] Normal Character movement occurs through domain movement/Travel rather than free GM dragging.

---

# 1. Climate & environment

- [x] C1 — Stellar & Ympha Climate Forcing.
- [x] C2 — Dynamic Ocean & Water Vapor.
- [x] C2.5 — Ocean Fast-Forward Accuracy.
- [x] C3 — Clouds / Physical Precipitation / Human Conditions.
- [x] C3.5 — Performance / Region Climate Autoconfiguration.
- [x] C4 — Atmospheric Circulation & Terrain Dynamics.
- [x] C4.1 — Precipitation Regression Audit/Fix.
- [x] C4.2 — Current Precipitation / Point Sampling Audit.

## Later

- [ ] C5 — Surface & Biome Feedbacks.
  - land-surface thermal response;
  - physical diurnal cycle;
  - soil/rock heat storage;
  - albedo;
  - roughness;
  - vegetation/moisture feedback;
  - evapotranspiration.
- [ ] C6 — Severe Weather.
- [ ] C7 — Catastrophes.

---

# 2. Region & Atlas

- [x] R1 — Region Weather Semantics & Lifecycle.
- [x] M1 — Leaflet Planetary Atlas Migration.
- [ ] M2 — Countries / Settlements / Roads / POI.
- [ ] M3 — Regional & Local Maps.
- [ ] M4 — Player Map / Exploration / current visibility.
- [ ] M5 — Travel Map / routes.
- [ ] M6 — Dynamic World Layers / hazards / wars / events.

---

# 3. Core Platform

- [x] P1 — Canon / Campaign Overrides.
- [x] P2 — Roles & Permissions.
- [x] P3 — AuditLog.
- [x] P4 — ApprovalRequest.
- [x] P4.5 — Registration / Email / Campaign Lifecycle.
- [x] P4.5.1 — Email verification resend countdown.
- [x] P5 — WorldEvent Foundation.
- [x] P5.5 — Character Identity & Player Workspace Foundation.

---

# 4. P5.6 — Campaign Creation & GM Eligibility Alignment

- [x] Ordinary newly registered User cannot create Campaign.
- [x] Ordinary User can join only through invitation.
- [x] Add/confirm global trusted GM-eligibility permission without `User.is_gm`.
- [x] Only superuser can grant/revoke GM eligibility.
- [x] Campaign creation requires GM eligibility or superuser.
- [x] Revisit PLAYER→GM promotion so ordinary Campaign GM cannot bypass global GM trust policy.
- [x] Preserve CampaignMembership as campaign-local role authority.
- [x] Update onboarding/empty-state UI.
- [x] Regression-test P4.5/P5/P5.5 access paths.

Recommended Codex reasoning: **HIGH**.

---

# 5. PW1 — Character Workspace Shell

- [x] Player Campaign Index becomes active Character Workspace.
- [x] Minimal Platform bar: Campaigns / Settings / Logout.
- [x] Main layout: Тиамана, active Quests, Map, Быт/Обязательства, Party, Notes, Apotheosis slot, quick Inventory.
- [x] Persistent XP HUD integration boundary.
- [x] Persistent Money HUD integration boundary.
- [x] Remove Player-facing «Мои запросы» queue.
- [x] Player actions use world/action wording, not ApprovalRequest wording.
- [x] Use P5.5 active Character context.
- [x] Responsive 390px layout.
- [x] Do not fabricate unfinished module data.

Recommended Codex reasoning: **HIGH**.

---

# 6. L1 — Character Location / Initial Placement

- [x] Durable Character location.
- [x] Initial placement only while Character has no position.
- [x] No normal free GM teleport control.
- [x] Central effective-location service.
- [x] Party/Travel can later become effective position source during active travel.
- [x] C4.2 sampler integration boundary without starting PW2/weather.
- [x] Audit meaningful setup/change atomically at Campaign world time.
- [x] Player-safe disclosure without raw coordinates or GM atlas leakage.
- [x] Fardecosmia planetary coordinates with canonical longitude seam.

Recommended Codex reasoning: **HIGH**.

---

# 7. N1 — Character & Party Notes

## Personal
- [ ] Belong to Character.
- [ ] Current controller only.
- [ ] GM has no ordinary read access.
- [ ] Persist across reassignment.
- [ ] Human notebook UI.

## Party
- [ ] Belong to Party.
- [ ] Visible to current Party members.
- [ ] Separate from personal notes.

Recommended Codex reasoning: **MEDIUM/HIGH**.

---

# 8. P6 — Party Foundation

- [ ] Character can belong to max one active Party.
- [ ] Party identity/members.
- [ ] Invitations/consent.
- [ ] ApprovalRequest orchestration remains backend-only.
- [ ] Party Index card shows only portrait + name.
- [ ] No HP/AC/money/inventory leakage.
- [ ] Team Quest hooks.
- [ ] Party Notes hooks.
- [ ] Travel/location hooks.
- [ ] Future meaningful shared storage hook.

Recommended Codex reasoning: **VERY HIGH**.

---

# 9. V1 — Visibility & Discovery Foundation

Replaces the old immediate K1 CharacterKnowledge plan.

- [ ] Discoverable locations.
- [ ] POI visibility.
- [ ] map exploration.
- [ ] Quest visibility.
- [ ] WorldEvent publication/visibility.
- [ ] Player search/encyclopedia filtering hooks.
- [ ] Never expose hidden-field existence through `???`.
- [ ] No generic modeling of every rumor/thought.
- [ ] Subjective RP remains Notes/narrative.

Recommended Codex reasoning: **VERY HIGH**.

---

# 10. M2 — Countries / Settlements / Roads / POI

- [ ] Countries/borders/capitals.
- [ ] Cities/villages/forts/ports.
- [ ] Roads/passes/POIs/sea routes.
- [ ] Population/races.
- [ ] Campaign Override policies.
- [ ] Visibility/Discovery integration.
- [ ] Atlas vector layers.

M2 and V1 may be designed together where their data contracts meet.

Recommended Codex reasoning: **VERY HIGH**.

---

# 11. PW2 — Live Character Ambience / M4 Player Map

## PW2
- [ ] Effective Character location → C4.2 environment sampler.
- [ ] RegionalSky.
- [ ] Biome/World Data context.
- [ ] Day/night brightness.
- [ ] Ympha red lighting.
- [ ] clouds/rain/snow/fog.
- [ ] heat/cold ambience.
- [ ] reduced motion/accessibility.
- [ ] no random fake weather.

## M4
- [ ] Character/Party position.
- [ ] Discovery/exploration/current visibility.
- [ ] revealed POI only.
- [ ] Player-safe WorldEvent/Quest layers.

Recommended Codex reasoning: **HIGH** for PW2, **VERY HIGH** for M4.

---

# 12. CH1 — Normalized Character State & Roll20 Authority Split

- [ ] Re-audit existing Roll20 integration.
- [ ] Define Fardecosmia-authoritative persistent fields.
- [ ] Define Roll20-authoritative battle-runtime fields.
- [ ] Stable normalized schema.
- [ ] Explicit Roll20 ID binding only.
- [ ] Conflict/revision rules.
- [ ] Fardecosmia→Roll20 queued commands.
- [ ] Roll20→Fardecosmia battle-runtime updates where required.

Recommended Codex reasoning: **VERY HIGH**.

---

# 13. XP1 / T1 — Experience & Тиамана

## XP1
- [ ] XP transaction history.
- [ ] Quest reward XP.
- [ ] GM XP grant.
- [ ] threshold calculation.
- [ ] Level-up trigger.
- [ ] XP HUD.
- [ ] email notification hook.

## T1 — Тиамана
- [ ] stats/progression UI.
- [ ] class progression.
- [ ] level-up choices.
- [ ] automatic transition after threshold.
- [ ] level-up sound.
- [ ] resulting mechanics sync toward Roll20.

Recommended Codex reasoning: **HIGH** for XP1, **VERY HIGH** for T1.

---

# 14. E1 — Currency & Ledger

- [ ] currencies.
- [ ] Character financial account.
- [ ] immutable transactions.
- [ ] balance integrity.
- [ ] GM grants.
- [ ] Quest rewards.
- [ ] purchases/refunds.
- [ ] Money HUD.
- [ ] history + AuditLog.

Recommended Codex reasoning: **VERY HIGH**.

---

# 15. I1 — Inventory & Storage

- [ ] Item definitions / instances.
- [ ] Character Inventory = abstract storage «при себе».
- [ ] Index quick list shows only items with Character.
- [ ] Full Inventory page.
- [ ] Equipment.
- [ ] Capacity/weight rules.
- [ ] Backpack/chest may modify capacity without automatic nested storage.
- [ ] Separate meaningful stores: House / Party / Vehicle / Shop.
- [ ] Transfers between meaningful stores.
- [ ] AuditLog.

Recommended Codex reasoning: **VERY HIGH**.

---

# 16. Q1 — Quest Foundation

- [ ] personal quests.
- [ ] party quests.
- [ ] objectives/stages.
- [ ] active vs completed history.
- [ ] deadlines.
- [ ] XP/Ledger/Inventory rewards.
- [ ] WorldEvent links.
- [ ] Player visibility rules.

On Character Index show only active personal/team quests.

Recommended Codex reasoning: **VERY HIGH**.

---

# 17. E2 — Purchases / Transfers

- [ ] shops / settlement context.
- [ ] item/quantity/price.
- [ ] ApprovalRequest where policy requires.
- [ ] Ledger + Inventory atomic apply.

Recommended Codex reasoning: **VERY HIGH**.

---

# 18. E3 — Recurring Economy & Lifestyle

- [ ] lifestyle.
- [ ] housing.
- [ ] recurring services.
- [ ] world-time billing.
- [ ] every crossed billing boundary on skip.
- [ ] insufficient funds.
- [ ] overdue obligations.
- [ ] explicit debt/liability.
- [ ] GM financial alerts.
- [ ] TimeAdvanceReport/WorldEvent hooks where meaningful.

Recommended Codex reasoning: **VERY HIGH**.

---

# 19. E4 — Employment & Side Jobs

- [ ] work contracts.
- [ ] recurring wages.
- [ ] quality checks.
- [ ] payout bands.
- [ ] normalized Character skill integration.
- [ ] missed-work handling.
- [ ] future Travel/activity/location availability.

Recommended Codex reasoning: **VERY HIGH**.

---

# 20. TR1 — Travel Engine

- [ ] destination selection.
- [ ] route / real distance.
- [ ] terrain / roads / biome / weather.
- [ ] transport / speed.
- [ ] provisions/water.
- [ ] time and route-derived checks.
- [ ] consequences.
- [ ] Party travel.
- [ ] ApprovalRequest orchestration where required.
- [ ] Character/Party position changes through Travel.
- [ ] WorldEvent departure/arrival.
- [ ] no free normal GM dragging.

Recommended Codex reasoning: **VERY HIGH**.

---

# 21. Apotheosis / Craft

## A1 — Apotheosis Design Phase
- [~] requires separate product/game-design discussion before implementation.

## Craft / Inventor
- [ ] recipes/projects/materials/tools.
- [ ] skills/time/cost/quality.
- [ ] failures/prototypes.
- [ ] Inventory/Economy integration.

Recommended Codex reasoning after design: **VERY HIGH**.

---

# 22. Encyclopedia / Navigation / Chronology

- [ ] navigation shell.
- [ ] player-safe search.
- [ ] breadcrumbs/related entities.
- [ ] races/biomes/magic/Lumen/Noctis/astronomy/items/equipment/weapons/traits/bestiary.
- [ ] chronology + WorldEventOccurrence.
- [ ] Visibility/Discovery filtering Player-side.

---

# 23. GM Dashboard

- [ ] Approval queue.
- [ ] Characters/Parties.
- [ ] active Travel/Quests.
- [ ] AuditLog/WorldEvents.
- [ ] weather/hazard alerts.
- [ ] unresolved financial obligations.
- [ ] player positions.
- [ ] quick GM actions.

Player does NOT inherit this queue/dashboard model.

---

# 24. Current recommended sequence

```text
[x] C1–C4.2
[x] R1
[x] M1
[x] P1/P2
[x] P3
[x] P4
[x] P4.5 / P4.5.1
[x] P5
[x] P5.5
[x] UX1 — Player Experience Architecture (design)

[x] P5.6 — Campaign Creation & GM Eligibility Alignment
[x] PW1 — Character Workspace Shell
[x] L1 — Character Location / Initial Placement
[ ] N1 — Personal Notes Foundation
[ ] P6 — Party Foundation
[ ] M2 + V1 — Geography + Visibility/Discovery foundations
[ ] PW2/M4 — Live Character ambience + Player Map
[ ] CH1 — Normalized Character/Roll20 authority layer
[ ] XP1/T1 — XP + Тиамана
[ ] E1 — Ledger
[ ] I1 — Inventory & Storage
[ ] Q1 — Quests
[ ] E2 — Purchases
[ ] E3 — Recurring Economy & Lifestyle
[ ] E4 — Employment & Side Jobs
[ ] TR1 — Travel Engine
[ ] M3 — Regional/Local Maps
[ ] Encyclopedia/navigation/player-safe search
[ ] Character Builder
[ ] Apotheosis design + Craft/Inventor
[ ] Chronology
[ ] GM Dashboard
[ ] C5/C6/C7 when gameplay foundations justify them
```

Order after M2/V1 may be adjusted by actual dependencies.

---

# 25. Before each phase

- [ ] reread AGENTS/WORLD_HANDOFF/Guardrails/Roadmap;
- [ ] audit existing implementation before replacement;
- [ ] identify migration/data preservation risk;
- [ ] define source-of-truth ownership;
- [ ] define Player vs GM visibility;
- [ ] define human-first UI;
- [ ] add focused tests;
- [ ] run appropriate regression;
- [ ] use checkpoint/progress file for long Codex phases;
- [ ] update docs after completion;
- [ ] stop without starting next phase automatically.
