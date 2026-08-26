# UX1.3 — Reflection Visual Polish & Stabilization Report

Date: 2026-08-26

Status: complete

This report records the completed frontend-only UX1.3 pass. It is based on
`docs/UX1_3_PROGRESS.md` and the fourteen accepted browser screenshots. No
implementation, browser fixture, test suite or final check was repeated while
preparing this report.

## 1. Scope and preserved contracts

UX1.3 refined the visual language and pointer/focus behavior introduced by
UX1.2 for the Player-facing Character Workspace and private Memory Space.

The phase did not change:

- Django models or migrations;
- views, routes, permissions or CSRF semantics;
- L1 effective-location resolution;
- PW2 atmospheric sampling or ambience data;
- N1 CharacterNote ownership, privacy, escaping or persistence;
- create/edit/release POST behavior;
- progressive no-JavaScript navigation;
- gameplay state or any P6 subsystem.

## 2. UX1.2 problems found

The UX1.2 audit identified several visual owners competing at the same time:

- a standalone full-viewport glow continuously followed global pointer
  coordinates;
- CSS `:hover` and `:focus-within` could claim focus independently;
- JavaScript `.is-focus-target` could claim a separate focus state;
- local node light was baked into the idle material instead of being an active
  state, so it could remain visually present after focus moved;
- delegated pointer movement had no single `activePointerNode` owner and lacked
  complete cancellation/reset handling;
- unrelated polygon lists and large offsets made the Workspace feel randomly
  scattered instead of intentionally asymmetric;
- the large top identity surface still read as a conventional hero card.

Together these defects caused roaming glare, occasional stuck highlights,
ambiguous multiple-focus states and motion that felt mechanically uniform.

## 3. Single-owner Focus state machine

Pointer ownership now has one explicit source of truth:

- at most one `activePointerNode` may exist;
- pointer-enter clears the previous owner before activating the new node;
- pointer-leave clears only when the leaving node still owns pointer focus;
- `activeNode` coordinates the visible node state;
- keyboard focus remains separate and may restore a static accessible focus
  state after pointer ownership ends.

This prevents stale nodes from keeping a pointer light and prevents rapid
A → B → C transitions from creating multiple visual owners.

### Reset hooks and stuck-focus fixes

The focus controller explicitly resets on:

- `pointercancel`;
- pointer leaving the Character surface/window;
- `window.blur`;
- document visibility loss;
- wheel and scroll movement;
- route/page transition;
- coarse-pointer mode changes;
- reduced-motion preference changes.

The scroll race receives additional protection: scroll/wheel immediately
releases the current owner, invalidates cached geometry and suppresses
synthetic pointer re-entry until genuine pointer movement occurs.

## 4. Roaming glare removal

The standalone full-screen moving glare was removed from both Workspace and
Memory markup. The pointer is now an invisible influence rather than a visible
light spot travelling across the page.

The remaining effects are local and bounded:

- node-local refraction follows the pointer only for the active pointer node;
- focused-node scale and clarity respond around the selected surface;
- scene/background layers respond at a lower depth rate;
- idle local-light opacity returns to zero;
- leaving or resetting returns local coordinates to the center and fades the
  highlight away.

Keyboard focus uses a static centered highlight rather than pointer-following
light.

## 5. Motion and easing model

One bounded requestAnimationFrame engine replaces competing movement loops.
Its responses are deliberately separated by depth:

- local reflection responds fastest;
- the selected node responds at a medium rate;
- background and scene depth respond slowest.

The interpolation is exponential and critically damped in feel: it settles
without visible overshoot or bounce and stops scheduling frames after reaching
its target. Page transitions use restrained fade/depth movement instead of
large sliding or spring effects.

## 6. Dark Glass Shards

Workspace surfaces now use a dedicated Dark Glass material rather than generic
`.panel` styling or SaaS-like glass cards.

The material consists of:

- a dark translucent core;
- restrained violet/blue depth;
- one or two readable cold refraction edges;
- softer secondary facets that disappear into the surface;
- no permanent pointer highlight at idle.

Six curated shard silhouettes replace unrelated per-module polygons. The
silhouettes repeat as a coherent visual vocabulary while preserving controlled
asymmetry.

## 7. Controlled Workspace composition

The Workspace no longer behaves like a random scatter or a strict dashboard
grid. It uses stable visual relationships:

- Тиамана / Активные квесты form the first left/right pair;
- Карта / Быт и обязательства form the second pair;
- Удержанные мысли / Apotheosis form the third pair;
- Команда is a wide center anchor;
- Инвентарь is a calm horizontal material band;
- HUD anchors remain visually subordinate beneath the reflection field.

Offsets were reduced so the eye can follow stable left, right and center lines
without losing the asymmetry of the reflection-space concept.

## 8. Identity Anchor

The former large panel-like hero treatment was removed. Character identity is
now embedded into the Reflection scene as a light anchor composed from:

- portrait/sigil;
- Character name;
- short description;
- subtle facets, line and aura details;
- the existing native active-Character switcher.

No identity data or switching behavior was removed.

## 9. Whole-node Notes navigation

The entire main Notes shard is one semantic link to Memory Space. The separate
`Удержать мысль` action remains a sibling action above that stretched link, so
the markup contains no nested anchors.

The main link remains keyboard focusable and exposes the accessible name
`Открыть удержанные мысли`. Preview excerpts are escaped plain text rather
than competing links. During visual acceptance, the quiet visible destination
label was moved away from the lower clipped edge to the safe vertical center
of the shard and confirmed fully visible on desktop and mobile.

## 10. Memory Space and Thought shards

Memory Space remains a separate neutral inner environment and does not render
PW2 live weather. Its thought field now uses a controlled alternating
two-column constellation instead of dense random placement.

Thoughts use a lighter Dark Glass variant:

- thinner and softer than Workspace nodes;
- four repeated light-shard contours;
- a clearer reading center;
- less stone-like weight;
- visible focus on the selected thought;
- restrained blur, dimming and recession on surrounding thoughts.

Opening a thought, editing it, beginning the two-step Hold Thought flow,
manifesting text, returning a newly-held thought to the constellation and
confirming release all remain inside the same Memory Space presentation.
The underlying N1 route and POST/CSRF contracts are unchanged.

## 11. Desktop browser acceptance

Desktop acceptance confirmed:

- PW2 live `dawn` + `rain` + `hot` ambience remained active on Workspace;
- Memory Space contained no PW2 ambience layer;
- neutral → hover → settled focus had exactly one focused/lit owner;
- the focused node reached a restrained visible scale of approximately 1.022;
- local refraction appeared only on the active node;
- surrounding nodes receded without disappearing;
- rapid A/B switching between thoughts retained one owner;
- scrolling cleared focus and local light immediately and after settling;
- leaving the Character surface returned scene/node depth to idle;
- child text/icon interaction did not create a second owner;
- browser-back returned from focused thought to the constellation;
- Hold Thought steps, Russian input manifestation, newly-held settling and
  release confirmation behaved correctly;
- browser console warnings/errors were absent.

## 12. Mobile behavior

The `390×844` acceptance pass confirmed:

- no horizontal overflow in Workspace or Memory Space;
- scene and node pointer transforms compute to `none`;
- local pointer-light alpha remains zero;
- native links/buttons preserve understandable touch/open behavior;
- fullscreen thought and Hold Thought body states remain within the mobile
  document flow without horizontal clipping;
- the Notes destination label remains inside its shard.

## 13. Reduced motion and accessibility

Mobile/coarse-pointer and `prefers-reduced-motion` rules explicitly disable:

- pointer-driven scene transforms;
- node drift/depth transforms;
- moving local-light behavior;
- manifestation motion;
- spatial page transitions.

Static focus/glow remains available. Native links, buttons and the Character
switcher retain keyboard semantics and visible focus outlines.

The in-app browser used for acceptance could not emulate the operating
system's reduced-motion setting directly. The contract was therefore verified
through the explicit CSS/JavaScript guards and focused regression assertions.

## 14. PW2, N1 and backend boundaries

- PW2 remains the only provider of live Character ambience.
- Workspace retained the shared PW2 presentation path and did not introduce a
  second weather/sky engine.
- Memory Space intentionally remains weather-free.
- N1 privacy, Character ownership, reassignment behavior, escaped plain text
  and AuditLog exception were not changed.
- No pointer movement creates server calls.
- No Player coordinate/weather endpoint was introduced.
- Backend, routing, permission, CSRF and persistence semantics remain intact.

## 15. Files changed

- `characters/templates/characters/character_workspace.html`
- `characters/templates/characters/personal_notes_base.html`
- `characters/tests/test_personal_notes_n1.py`
- `static/css/app.css`
- `static/js/reflection-focus.js`
- `templates/base.html`
- `docs/UX1_3_PROGRESS.md`
- `UX1_3_REFLECTION_VISUAL_POLISH_STABILIZATION_REPORT.md`

## 16. Verification results

- Focused presentation tests: 14 — OK.
- Related N1/PW2 regression: 48 — OK.
- Full Django suite: 491 — OK, 9 expected skips.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: clean; only non-failing CRLF conversion notices.
- Schema migrations created: none.

The first related run found one stale test assertion referring to the removed
`frame` variable. It was updated to assert the bounded `motionFrame` engine;
product behavior had already passed. The final related and full runs were
green.

## 17. Acceptance screenshots

The fourteen accepted screenshots are stored in:

`C:/Users/Ruslanchik/.codex/visualizations/2026/08/08/019fe2d6-7fe3-7581-90ce-c414511c4091/`

1. `ux13-workspace-desktop-neutral.png`
2. `ux13-identity-anchor.png`
3. `ux13-workspace-node-idle.png`
4. `ux13-workspace-node-focused.png`
5. `ux13-workspace-balanced-full.png`
6. `ux13-memory-desktop.png`
7. `ux13-thought-idle.png`
8. `ux13-thought-focused.png`
9. `ux13-thought-fullscreen.png`
10. `ux13-hold-step-1.png`
11. `ux13-hold-step-2.png`
12. `ux13-new-thought-settled.png`
13. `ux13-mobile-workspace.png`
14. `ux13-mobile-memory.png`

Isolated browser fixture Campaign/User data and their dependent Characters,
Notes and snapshot were deleted after acceptance. Existing development data
was not touched.

## 18. Known limitations

- OS-level reduced-motion could not be emulated directly in the in-app browser;
  explicit guards and focused tests cover the required behavior.
- Direct browser-chrome tab switching and `window.blur` could not be observed
  reliably through the in-app harness. Explicit blur/visibility reset hooks are
  implemented and covered by focused regression. Surface leave, scrolling and
  route transition produced no stuck focus in real browser testing.
- No accepted UX1.3 visual, interaction, privacy or security defect remains.

## 19. Scope confirmation

UX1.3 remained frontend-only. It did not start P6 or any other gameplay phase,
and did not introduce Location, Travel, Party, Visibility, Player Map, XP,
Soul HUD, Inventory, Ledger, Quests, Economy, Roll20, Apotheosis or C5 work.

UX1.3 is complete. STOP.
