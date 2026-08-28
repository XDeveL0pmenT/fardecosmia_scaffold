# UX1.4 — Reflection Radial Composition progress

## Scope

Current milestone: **Turn 1 — Radial Composition only**.

Explicitly excluded from this turn:

- GIF/aura assets;
- radial connectors;
- Soul HUD redesign;
- Money HUD redesign;
- backend, models, routing, permissions or migrations;
- Turn 2 and Turn 3;
- full Django test suite.

## Baseline verified

- Read `AGENTS.md`.
- Read `docs/UX1_3_PROGRESS.md`.
- Read `UX1_3_REFLECTION_VISUAL_POLISH_STABILIZATION_REPORT.md`.
- Read the complete UX1.4 specification.
- Audited the current Character Workspace template, UX1.3 Reflection/Focus CSS and
  `static/js/reflection-focus.js`.
- `git status --short` before implementation contained only the untracked UX1.4
  specification file.
- Existing UX1.3 Dark Glass material, single-owner Focus Field, Notes whole-node
  navigation and PW2 ambience are the baseline and must be preserved.

## Planned Turn 1 changes

- Replace the active Character hero composition with a centered, non-action
  `character-core`.
- Make the Character name use Variant B: visually quiet at rest and revealed on
  hover/keyboard focus without layout shift.
- Place the existing Dark Glass nodes at stable semantic desktop anchors around
  the core.
- Keep a one-column, Character-first mobile composition.
- Keep the existing Character switcher as a quiet native fallback outside the
  central identity core.
- Leave the existing HUD placeholders structurally unchanged; they are not part
  of Turn 1.

## Changed files

- `docs/UX1_4_PROGRESS.md` — created before implementation.
- `characters/templates/characters/character_workspace.html` — active Character
  hero removed; non-action Character Core added inside the Reflection field;
  existing nodes and Inventory placed in the same radial scene; quiet native
  Character switcher retained outside the Core; PW2 include and Notes routes
  preserved.
- `static/css/app.css` — added Turn 1 radial grid, centered Core, Variant B name
  manifestation, balanced desktop anchors and Character-first mobile fallback.
- `templates/base.html` — bumped the CSS cache key to
  `ux14-radial-turn1-1`.
- `characters/tests/test_personal_notes_n1.py` — updated the reflection-node
  presentation count for the new Core and added a focused radial/Core/no-active-
  hero assertion.
- `docs/ux1_4_acceptance/turn1-desktop-idle.png` — desktop idle acceptance.
- `docs/ux1_4_acceptance/turn1-desktop-core-focus.png` — desktop Core focus and
  Variant B name acceptance.
- `docs/ux1_4_acceptance/turn1-mobile-390x844.png` — mobile vertical fallback.

## Verification status

- Implementation: complete for Turn 1 only.
- `manage.py check`: passed before browser verification.
- Focused PW1/PW2/N1 run initially exposed one obsolete node-count expectation
  and one mistyped test-class selector in the command. The node-count expectation
  was updated from seven to eight focusable nodes because Character Core is now a
  focusable Reflection node; no product regression was present.
- Correct focused `PersonalNotePresentationTests`: **15 tests — OK**.
- Final focused PW1/PW2/N1 rerun:
  `CharacterWorkspacePW1Tests` + `CharacterAmbiencePW2Tests` +
  `PersonalNotePresentationTests` — **44 tests, OK**.
- Browser desktop `1280×720`: radial anchors are stable and balanced; Character
  Core is centered; no node intersections; active Character hero is absent.
- Variant B: computed name opacity is `0.045` at idle and `1` on Core focus;
  focus also applies the existing `is-focus-target` owner and portrait scale.
- Notes whole-node link still covers the complete Notes shard and opens the
  existing `/thoughts/` route; the separate Hold action remains intact.
- PW2 ambient scene remains mounted. No new weather endpoint or simulation call
  was introduced.
- Mobile `390×844`: Character Core appears first, followed by the required
  vertical node order; document width is `377px` for a `390px` viewport, so no
  horizontal overflow; the small Character name remains visible at `0.92`.
- Browser console warnings/errors: none.
- GIF count on Workspace: zero. No GIF, connector, Soul HUD or Money HUD work was
  started.
- Isolated browser fixture was removed by exact campaign UUID and username after
  verification. The temporary local server is no longer listening.
- Three acceptance screenshots saved under `docs/ux1_4_acceptance/`.
- Final `manage.py check`: no issues.
- Final `git diff --check`: clean (only Git's informational LF/CRLF warnings).
- Final worktree contains only the intended Turn 1 template/CSS/cache-key/test/
  checkpoint/screenshot changes plus the user-supplied untracked UX1.4
  specification.

## Exact next step

## Turn 1.1 — Elastic Radial Geometry Polish

### Baseline

- User visual acceptance of Turn 1 is not complete.
- Read `UX1_4_Turn_1_1_Elastic_Radial_Geometry_Polish.md` completely.
- Current worktree before Turn 1.1 contained only the new untracked Turn 1.1
  specification; the completed Turn 1 implementation is the code baseline.
- `reflection-focus.js` does not cache individual node rectangles. It reads the
  active node rectangle on pointer activity. Only the field bounds are cached,
  and viewport scroll already invalidates them.

### Selected elastic approach

- Keep semantic CSS Grid anchors; do not introduce absolute/random placement.
- Move Inventory to its own fifth bottom row so it can be a wide horizontal
  bottom anchor and cannot crowd the Core.
- Add a separate bounded radial geometry controller with one scheduled
  calculation on initial layout, relevant `ResizeObserver` notifications and
  viewport resize.
- The controller derives independent horizontal and vertical clearances from
  the rendered field/node dimensions and writes CSS custom properties only when
  rounded values actually change. It does not run a permanent animation loop.
- Mobile bypasses the controller and remains normal vertical document flow.

### Turn 1.1 status

- Implementation: complete.
- `static/js/reflection-radial-layout.js` owns elastic geometry. It performs one
  scheduled measurement at initial layout, then responds only to relevant
  `ResizeObserver`, media-query and viewport-resize notifications. There is no
  permanent RAF loop and unchanged rounded geometry is not rewritten.
- Independent radius variables are calculated as:
  - `--radial-radius-x` from available field width;
  - `--radial-radius-y` from the tallest rendered outer node;
  - `--radial-core-column` from field width within a bounded central safe-zone.
- Stable CSS Grid areas preserve all semantic angles. Natural grid row sizing
  handles real content height, while the calculated gaps expand/contract the
  ring without absolute positioning or random scatter.
- Inventory now occupies a dedicated fifth bottom row, is a horizontal material
  shard, and is separated from the Core. Its preview uses
  `data-preview-row-cap="4"`, clips excess without a nested scrollbar and is ready
  for a future bounded I1 preview without creating fake items.
- Notes preview uses the same generic bounded-preview contract with two rows.
- All workspace shards use percentage-aware inner padding independent of their
  decorative silhouette. Apotheosis has a deeper dedicated safe-zone, reserved
  icon area, wrapping title and bounded readable description width.
- `reflection-focus.js` was not redesigned. It now only invalidates its cached
  field rectangle on `reflectiongeometrychange`/viewport resize; individual node
  rectangles continue to be read from actual current geometry.
- Mobile explicitly clears elastic variables and grid areas and remains normal
  one-column document flow.

### Turn 1.1 verification

- `python manage.py check`: no issues.
- Targeted `PersonalNotePresentationTests` + `CharacterAmbiencePW2Tests`:
  **30 tests, OK**.
- `git diff --check`: clean (only informational LF/CRLF warnings).
- Quick browser sanity, no screenshots saved as required:
  - desktop `1280×720`: controller ready, geometry `29:27:192`, no node
    intersections, Inventory is `456×144` and starts 399 px below the Core,
    Apotheosis text remains inside its shard with 314 px readable width;
  - resized desktop `900×720`: geometry recalculated to `20:24:170`;
  - mobile `390×844`: elastic data removed, one `347px` column, natural DOM
    order, no horizontal overflow;
  - browser console warnings/errors: none.
- Browser sanity exposed and fixed one mobile cascade defect where desktop
  `grid-area: inventory` created implicit columns after the earlier mobile reset.
- Isolated browser fixture was deleted by exact campaign UUID and username;
  temporary server is no longer listening.
- No screenshots were created for Turn 1.1.
- No backend, model, migration, GIF, connector, Soul HUD or Money HUD work was
  performed.

### Exact next step

**STOP after Turn 1.1.** Await user visual acceptance or further Turn 1 polish.
Do not begin Turn 2, GIF integration, connectors or HUD work without explicit
continuation.

## Turn 1.1 acceptance revision — true elliptical radial placement

### Why the previous approach was superseded

- The adaptive-gap CSS Grid implementation was technically safe but did not pass
  visual acceptance: its semantic rows and columns still read as a grid.
- That desktop positioning method is now superseded. CSS Grid remains only as
  the mobile normal-flow fallback and is no longer the desktop anchor source.

### Implemented geometry

- `static/js/reflection-radial-layout.js` now owns deterministic polar placement.
- Character Core is the mathematical center of the scene.
- Node center positions use the requested elliptical formula:
  `x = centerX + radiusX * cos(angle)` and
  `y = centerY + radiusY * sin(angle)`.
- Angles are stable constants:
  - Party `-90°`;
  - Lifestyle `-45°`;
  - Quests `0°`;
  - Apotheosis `45°`;
  - Inventory `90°`;
  - Notes `135°`;
  - Tiamana `180°`;
  - Map `225°`.
- The solver measures each real shard with `offsetWidth` plus the larger of
  `offsetHeight`/`scrollHeight`. It increases the minimum safe ellipse radii when
  a shard grows, while leaving every angle unchanged.
- The bounded collision pass checks node-to-Core and node-to-node rectangles.
  Horizontal radius remains within the available field width; vertical radius
  and total field height grow as required by real content.
- Desktop CSS consumes the calculated per-node top/left custom properties. It
  does not use Grid rows/columns, random scatter or manually tuned individual
  offsets as the positioning source.
- The existing `ResizeObserver` remains event-driven: one scheduled animation
  frame coalesces a notification batch. There is no permanent animation loop.
- Geometry changes still emit `reflectiongeometrychange`, preserving the UX1.3
  Focus Field bounds invalidation contract.
- At `760px` and below the controller clears all inline radial geometry; the
  existing one-column mobile Grid/normal flow remains authoritative.

### Preserved contracts

- Inventory preview remains bounded to four rows.
- Notes preview remains bounded.
- Apotheosis keeps its dedicated content safe-zone.
- UX1.3 single-owner Focus state machine and Dark Glass material are unchanged.
- PW2 ambience and Notes whole-node navigation are unchanged.
- No GIF assets, connectors, Soul HUD, Money HUD, backend, routing, model or
  migration work was started.

### Acceptance-revision changed files

- `static/js/reflection-radial-layout.js` — replaced desktop Grid-gap geometry
  with the deterministic elliptical solver.
- `static/css/app.css` — desktop ready-state now uses calculated absolute node
  centers; mobile flow remains unchanged.
- `characters/tests/test_personal_notes_n1.py` — focused presentation assertions
  cover polar trigonometry, fixed angles, radius/node-position variables,
  `ResizeObserver` and absence of an interval loop.
- `docs/UX1_4_PROGRESS.md` — records the superseded approach and current source
  of truth.

### Targeted verification

- `manage.py check`: no issues.
- `PersonalNotePresentationTests` + `CharacterAmbiencePW2Tests`:
  **30 tests, OK**.
- Targeted browser check only; no screenshots were created:
  - desktop `1280×720`: `radiusX = 378px`, `radiusY = 891px`, no node or Core
    intersections and no horizontal overflow;
  - normalized ellipse angles were exactly `-90, -45, 0, 45, 90, 135, 180,
    225` degrees (the browser's equivalent `-180°` representation for Tiamana
    was normalized to `180°`);
  - resized desktop `1000×720`: radii recalculated to `299px × 833px`, with no
    intersections and no horizontal overflow;
  - mobile `390×844`: ready-state and inline radii were cleared, zero nodes were
    absolutely positioned, one `347px` column remained in natural order, with no
    horizontal overflow.
- Browser console was clean during the desktop sanity check.
- The isolated browser fixture was deleted by exact campaign UUID and username;
  no temporary server remains listening.
- No full suite was run, as explicitly required.

### Exact next step after acceptance revision

**STOP.** Await user visual acceptance. Do not start Turn 2, GIF integration,
connectors, HUD work or any backend/gameplay phase.

## Turn 2A — Character Core Aura & Reflection Connectors

### Scope and accepted baseline

- Turn 2A only is complete. Turn 2B was not started.
- The user-accepted optical radial geometry is the visual baseline. Its anchors,
  proportions, Character Core position and radial solver were not changed.
- This milestone adds presentation only: a Core aura, decorative connector layer,
  connector geometry and a small focus-state notification extension.
- No models, migrations, permissions, routes, Character ownership, Notes privacy,
  L1/PW2 semantics, atmospheric calculation or gameplay state changed.

### Exact existing assets

- White Character rupture/glitch aura used in Turn 2A:
  `static/gifs/giphy (3).gif` (`434×434`, 48 frames).
- Thin white connector texture used in Turn 2A:
  `static/gifs/ezgif-22ce4fcd901dc090.gif` (`199×297`, 91 frames).
- Chromatic circular Soul burst reserved for Turn 2B:
  `static/gifs/giphy (2).gif` (`500×500`, 48 frames).
- Existing white/transparent Soul-sigil candidate:
  `static/images/ы.png`; its violet variant is `static/images/ы1.png`.
  Neither was integrated in Turn 2A.
- Authoritative precipitation assets confirmed but deliberately not integrated
  before Turn 2B:
  `static/gifs/rain.gif` and
  `static/gifs/placidplace-snow-16036.gif`.
- No asset was copied, renamed, converted, re-rendered, embedded or modified.

### Character Core aura

- The template renders the white glitch GIF as a decorative `img` behind the
  portrait, with empty alt text, `aria-hidden`, `draggable=false` and no pointer
  events.
- Desktop idle opacity is `0.34`; Core hover/keyboard/single-owner focus raises
  it to `0.43` with a small eased scale/clarity increase.
- The existing Variant B identity behavior remains authoritative: portrait and
  Character name still respond through the existing Core focus selectors.
- Mobile uses a smaller `166px`, quieter `0.22` aura (`0.29` focused).
- Reduced motion hides the animated aura; the existing static Core facet/ring
  material remains as the non-animated identity fallback.

### Connector implementation

- `static/js/reflection-connectors.js` creates exactly eight decorative lines
  for Party, Map, Lifestyle, Tiamana, Quests, Notes, Apotheosis and Inventory.
- The layer has `aria-hidden` and `pointer-events:none`; it is not interactive,
  navigation, a graph API, a skill tree or gameplay state.
- Geometry is calculated from actual rendered Core/aura and target shard
  rectangles:
  - Core/target centers provide `dx`, `dy`, distance and `atan2` angle;
  - projected half-extents trim the line past the aura edge and before the shard
    body;
  - CSS custom properties receive start point, length and rotation.
- The connector GIF remains thin (`14px`) and is stretched predominantly along
  its calculated length inside a rotated container.
- The connector controller listens to the existing
  `reflectiongeometrychange`, initial render, media-query changes and viewport
  resize. Work is coalesced into one scheduled animation frame; there is no
  permanent layout loop, `setInterval`, fetch or server request.
- The accepted `reflection-radial-layout.js` and its manually tuned optical
  anchors were not changed.

### Focus integration

- `reflection-focus.js` remains the sole owner of pointer/keyboard focus.
- A small `reflectionfocuschange` notification is dispatched only when that
  existing owner changes or clears. It does not create a second state machine.
- `reflection-connectors.js` consumes the notification from the outer Focus
  Field and maps the active node to the matching decorative thread.
- Idle opacity is `0.09`; the one linked connector uses `0.27`.
- When Character Core owns focus, no individual link is selected and all eight
  connectors quietly rise to `0.16`.
- Existing sibling recession, node local-light, reset hooks and single-owner
  classes are unchanged.

### Responsive and reduced-motion behavior

- At `760px` and below connectors are hidden and the accepted normal-flow mobile
  Workspace remains unchanged.
- Reduced motion hides the animated connector texture but keeps a faint static
  linear thread fallback. Presentation meaning does not depend on GIF motion.
- The reduced-motion browser profile was not active on the development machine;
  the fallback contract is covered by focused source/CSS assertions.

### Changed files

- `characters/templates/characters/character_workspace.html` — decorative aura,
  connector layer/asset URL and connector script include.
- `static/js/reflection-connectors.js` — bounded event-driven connector geometry
  and focus presentation.
- `static/js/reflection-focus.js` — small focus-owner change notification only.
- `static/css/app.css` — aura/connector layers, tuning knobs, mobile and reduced-
  motion behavior.
- `templates/base.html` — Turn 2A CSS cache key.
- `characters/tests/test_personal_notes_n1.py` — accepted optical-anchor baseline
  assertions plus bounded Turn 2A presentation contract.
- `docs/UX1_4_PROGRESS.md` — this checkpoint.

### Verification

- `manage.py check`: no issues.
- Focused `PersonalNotePresentationTests` + `CharacterAmbiencePW2Tests`:
  **31 tests, OK**.
- After correcting the focus-event listener boundary discovered by browser
  sanity, the final dedicated Turn 2A presentation test was rerun:
  **1 test, OK**.
- Quick browser sanity, with no screenshots:
  - desktop `1280×720`: radial and connectors ready; eight of eight lines
    visible; idle opacity `0.09`; aura opacity `0.34`; no horizontal overflow;
  - Party pointer focus: exactly one Focus node and exactly one linked connector,
    with key `party` and opacity `0.27`;
  - Character Core keyboard-equivalent focus: exactly one focused node, no
    individual connector, all eight connectors at `0.16`, aura at `0.43`;
  - resize to `1000×720`: connector geometry key changed and all eight lines were
    recalculated without horizontal overflow;
  - mobile `390×844`: connector layer hidden, connector-ready state cleared,
    zero absolutely positioned nodes and no horizontal overflow;
  - browser console warnings/errors: none.
- The isolated browser fixture was deleted by exact Campaign UUID and username.
  The temporary local server is no longer listening.
- No screenshots or full suite were run, as required by the quota guard.

### Exact next step

**STOP after Turn 2A.** Turn 2B may begin only after explicit user continuation.
Turn 2B scope is Soul HUD, Money HUD and shared authoritative Region + Character
rain/snow GIF restoration. Do not begin Turn 3 or any gameplay/backend phase.

## Turn 2B — Persistent HUD & Authoritative Weather GIF Restoration

### Scope and preserved baseline

- Turn 2B is complete. Turn 3 was not started.
- The accepted radial geometry, all eight node anchors, Character Core position
  and size, Core aura, connector geometry/lengths, UX1.3 Focus Field, Dark Glass
  shards, Inventory preview and Notes preview/navigation were not changed.
- This milestone is frontend presentation only. It adds a viewport-persistent
  Soul/Money HUD and restores the supplied rain/snow GIFs through the existing
  shared ambience component.
- No backend, model, migration, permission, route, weather solver, sampling,
  gameplay or persistence semantics changed.

### Persistent Character HUD

- The HUD is rendered after the radial `<main>` and remains inside the existing
  outer Focus Field only. It is not a radial node, is not observed by the radial
  layout solver and cannot participate in connector or focus ownership.
- Desktop placement is viewport-persistent:
  - Soul: bottom-left, `116×116px`, `18px` safe inset;
  - Money: top-right, minimum `104×52px`, below the platform top bar.
- Mobile `390×844` placement remains compact and clear of the shell:
  - Soul: `78×78px`, `8px` bottom/left inset;
  - Money: minimum `76×40px`, `74px` from the top and `8px` from the right.
- The Soul presentation layers the existing chromatic burst
  `static/gifs/giphy (2).gif` behind the white sigil
  `static/images/ы.png`. The burst is deliberately quiet (`0.34` desktop,
  `0.27` mobile) and the static sigil remains primary.
- Reduced motion hides the animated Soul burst and preserves the sigil plus a
  static ring, so the HUD remains identifiable without motion.
- Money uses a compact Dark Glass shard and deliberately renders `◇ —`: no fake
  balance, currency, XP, level or progression was invented.
- Both HUD elements are pointer-transparent presentation landmarks. Their
  accessible text explicitly says that progression/balance is not yet
  manifested.

### Shared authoritative precipitation presentation

- Region detail and Character Workspace still render the same
  `world/_ambient_layers.html` component and use the same
  `AmbientPresentation` opacity tokens.
- Normal-motion rain now uses the supplied `static/gifs/rain.gif`.
- Normal-motion snow now uses the supplied
  `static/gifs/placidplace-snow-16036.gif`.
- GIF visibility remains wholly controlled by authoritative
  `--ambient-rain-opacity`, `--ambient-snow-opacity` and
  `data-precipitation-kind`; no CSS class or JavaScript invents precipitation.
- Dry scenes retain the shared DOM layers but both authoritative opacities are
  zero, so no rain or snow is visible.
- Reduced motion replaces both animated GIF surfaces with quiet CSS gradient
  fallbacks while retaining the same authoritative opacity variables.
- No second weather renderer, Player weather endpoint, sampler branch or
  cumulative-precipitation interpretation was introduced.

### Turn 2B changed files

- `characters/templates/characters/character_workspace.html` — moved the HUD
  outside the radial scene and added the persistent Soul/Money presentation.
- `static/css/app.css` — persistent desktop/mobile/reduced-motion HUD styles and
  shared rain/snow GIF surfaces with reduced-motion fallbacks.
- `templates/base.html` — CSS cache key advanced to `ux14-turn2b-1`.
- `characters/tests/test_character_ambience_pw2.py` — focused shared
  precipitation asset/fallback contract.
- `characters/tests/test_personal_notes_n1.py` — focused HUD placement and
  no-fabricated-state contract.
- `docs/UX1_4_PROGRESS.md` — this checkpoint.
- The pre-existing modified `static/gifs/giphy (3).gif` remained untouched in
  Turn 2B.

### Verification

- `python manage.py check`: no issues.
- Focused `PersonalNotePresentationTests` + `CharacterAmbiencePW2Tests`:
  **32 tests, OK**.
- Quick targeted browser sanity, no screenshots:
  - desktop `1280×720`: HUD computed `position: fixed`, is outside both
    `.reflection-radial-scene` and `[data-radial-layout]`; Soul and Money occupy
    the intended opposite viewport corners; no horizontal overflow;
  - Character rain: `data-precipitation-kind=rain`, rain opacity `0.5851`, rain
    GIF loaded, snow opacity `0`;
  - Character snow: `data-precipitation-kind=snow`, snow opacity `0.6144`, snow
    GIF loaded, rain opacity `0`;
  - Character dry: kind `none`, both precipitation opacities `0`;
  - Region rain/snow/dry produced the same respective kinds, GIF URLs and
    authoritative opacities through the shared Region ambience component;
  - mobile `390×844`: HUD remains fixed outside the radial scene, Soul and Money
    use their compact positions, rain remains authoritative and there is no
    horizontal overflow;
  - browser console warnings/errors: none.
- The development browser profile reports `prefers-reduced-motion: false`.
  Reduced-motion behavior was therefore verified through focused source/CSS
  assertions rather than claimed as an active runtime profile.
- The temporary server was stopped. Exactly six isolated browser-test Campaigns
  and the single exact temporary user were deleted; real development data was
  not touched.
- No full suite, screenshots or migration command were run, per Turn 2B scope.

### Tuning knobs and known limits

- Soul footprint, burst/sigil sizes and burst opacity are isolated under
  `.character-soul-hud*`; Money footprint is isolated under
  `.character-money-hud*`.
- Rain tile size is `480×480px`; snow scales between `720px` and the source
  `1176px` width. Authoritative intensity remains independent of these visual
  sizing knobs.
- HUD values remain intentionally unavailable placeholders until a dedicated
  source-of-truth phase defines Soul progression and money.

### Exact next step

**STOP after Turn 2B.** Await explicit user acceptance. Do not begin Turn 3,
Soul/XP gameplay, economy, backend work or any other gameplay phase.

## Turn 3 — Motion & Transition Polish

### Start checkpoint

- Status: implementation not started; Turn 2B is the accepted source of truth.
- Scope is presentation-only: short Workspace/Memory manifestation, route-safe
  native-link exits, coherent Focus/connector timing, HUD manifestation and
  mobile/reduced-motion stabilization.
- Accepted radial anchors/solver, Core size and position, aura size, connector
  geometry and trimming, Dark Glass shapes, Inventory placement, HUD placement,
  PW2 authority and N1 semantics are frozen unless a direct technical defect is
  proven.
- Required files and the complete Turn 3 specification have been read; current
  Workspace, Memory templates and frontend controllers are being audited before
  implementation.
- No backend, models, permissions, routing, migrations, gameplay values or
  weather calculation may change.

### Files changed in Turn 3 so far

- `docs/UX1_4_PROGRESS.md` — start checkpoint only.

### Verification so far

- No Turn 3 tests or browser checks have run yet.
- The prior Turn 2B focused baseline remains **32 tests, OK** with
  `manage.py check` clean.

### Exact next step

Audit the current Workspace/Memory DOM and existing frontend motion ownership,
then implement a small dedicated progressive-enhancement transition controller
without changing the accepted geometry or backend contracts.

### Implementation milestone

- Added `static/js/reflection-transitions.js` as the sole owner of Character-
  facing entrance/exit presentation. Native links remain authoritative and the
  controller intercepts only eligible same-origin GET anchors marked with
  `data-character-transition`.
- The previous route-delay block was removed from `reflection-focus.js`; its
  single-owner attention state machine, pointer batching and reset hooks remain
  otherwise unchanged.
- Workspace manifestation waits for the accepted desktop radial solver's
  `reflectiongeometrychange` readiness signal. It does not read node geometry,
  alter anchors or add a permanent animation loop.
- Timing is bounded: Core first, connectors next, 40–45ms spatial node wave,
  HUD last; the scene settles within about 855ms. Route exit is 180ms with a
  1200ms failed-navigation cleanup.
- PW2 ambience is outside the animated Character surface, so rain/snow/fog do
  not restart, fade out or gain duplicate layers during manifestation.
- Memory receives a short neutral header/thought/focus manifestation. Existing
  thought open, conversational Hold/Edit and secure POST/Release flows remain
  native; newly held thought motion was softened and shortened to 620ms.
- Mobile keeps normal vertical geometry and uses a compact 10–40ms wave with
  all modules available within about 580ms. Connectors remain hidden.
- Reduced motion bypasses link delay and entrance orchestration entirely; the
  existing static aura/connector/Soul/weather fallbacks remain authoritative.

### Turn 3 files changed at this milestone

- `static/js/reflection-transitions.js` — new bounded transition controller.
- `static/js/reflection-focus.js` — navigation ownership removed; Focus remains.
- `static/js/held-thoughts.js` — gentler 620–680ms new-thought settling constants.
- `static/css/app.css` — manifestation, coherent focus timing, route continuity,
  Memory/HUD motion, mobile and reduced-motion boundary.
- `characters/templates/characters/character_workspace.html` — transition
  controller include only.
- `characters/templates/characters/personal_notes_base.html` — same controller
  include for the existing unified Memory Space.
- `templates/base.html` — CSS cache key `ux14-turn3-1`.
- `characters/tests/test_personal_notes_n1.py` — focused ownership, timing,
  native-route and reduced-motion assertions.
- `docs/UX1_4_PROGRESS.md` — milestone checkpoint.

### Current verification state

- Implementation complete.
- `python manage.py check`: no issues.
- Focused `CharacterWorkspacePW1Tests` + `CharacterAmbiencePW2Tests` +
  `PersonalNotePresentationTests`: **47 tests, OK**.
- `git diff --check`: clean (only informational LF/CRLF warnings).
- Browser verification has not run yet.
- Exact next step: create isolated browser fixtures and perform only the Turn 3
  desktop/mobile/rain/dry/navigation/Memory/keyboard sanity required by the
  specification; create no screenshots and run no full suite.

### Browser verification milestone

- Desktop Workspace cold load: Core, connectors, nodes and HUD manifest in the
  intended short sequence; all root entrance classes are removed after 920ms.
- Rain continuity: authoritative rain opacity stayed exactly `0.5851` at the
  beginning, middle and end of Workspace manifestation. The shared PW2 layer is
  outside the animated surface and never flashed off/on.
- Dry Character: precipitation kind remained `none`; rain and snow opacities
  remained `0` throughout entrance.
- Rapid Map → Lifestyle → Map pointer handoff retained exactly one Focus owner
  and one correctly matched connector on every sample. Core focus retained one
  owner, zero individually linked connectors, the all-thread Core state, aura
  and Variant B name manifestation.
- Keyboard `:focus-visible` presentation remains available. A real gap was found
  for Escape in Memory focus scenes; the dedicated transition controller now
  routes Escape through the existing `a[data-memory-close]`. Release Escape was
  retested and returned to the same thought detail without submitting the POST.
- Workspace → Memory, Memory → Workspace, thought opening and browser Back all
  used native URLs. Back restored a fully visible Workspace with no stuck exit,
  opening or Focus classes.
- Memory has zero PW2/weather layers. Header and thought shards manifest softly;
  thought opening preserves one selected source while surrounding thoughts
  recede.
- Hold Thought step 1/step 2, Russian typing manifestation and secure create POST
  passed. The created thought reached the existing detail and returned to the
  same field.
- Browser QA exposed a CSS specificity conflict where the generic Memory entrance
  could mask `memory-thought-join-field`. The final cascade now preserves the
  dedicated 620ms new-thought animation while other thoughts remain at opacity
  `0.5`; the special class clears afterward.
- Release confirmation remained a CSRF-protected POST scene with the selected
  canonical thought shape and no horizontal overflow; it was not submitted.
- Mobile `390×844`: connectors remain hidden, zero nodes are absolutely
  positioned, vertical DOM order is preserved, compact HUD positions are
  unchanged, rain stays at `0.5851` and horizontal overflow is zero. Memory list
  and focused thought also fit without overflow.
- Development browser reports `prefers-reduced-motion: false`; runtime emulation
  is not available through the selected browser capability. Reduced-motion was
  therefore verified through the existing CSS contract, transition-controller
  bypass and focused source tests, not claimed as an active visual profile.
- Browser console warnings/errors: zero.
- No screenshots were created.

### Exact next step after browser milestone

Close the temporary browser tab, reset its viewport, stop the local server,
delete only the exact isolated Turn 3 fixtures, then rerun the directly affected
N1 presentation tests, `manage.py check`, `git diff --check`, update this
checkpoint and STOP without a full suite.

### Turn 3 final targeted verification

- Browser tab closed and explicit viewport override reset.
- Temporary Django server stopped; port `8765` is no longer part of the test
  session.
- Deleted only Campaigns
  `c3140000-0000-4000-8000-000000000001` and
  `c3140000-0000-4000-8000-000000000002` plus exact user
  `ux14_turn3_browser`; verification returned zero remaining matching rows.
- After browser-found fixes, final directly affected
  `PersonalNotePresentationTests`: **18 tests, OK**.
- Final `python manage.py check`: no issues.
- Final `git diff --check`: clean (only informational LF/CRLF warnings).
- Intended Turn 3 worktree:
  - modified `characters/templates/characters/character_workspace.html`;
  - modified `characters/templates/characters/personal_notes_base.html`;
  - modified `characters/tests/test_personal_notes_n1.py`;
  - modified `docs/UX1_4_PROGRESS.md`;
  - modified `static/css/app.css`;
  - modified `static/js/held-thoughts.js`;
  - modified `static/js/reflection-focus.js`;
  - modified `templates/base.html`;
  - new `static/js/reflection-transitions.js`.
- No screenshots, migrations or full suite were created/run.
- No backend, models, permissions, routes, weather authority, N1 privacy or
  gameplay state changed.

### Exact next step / STOP

**STOP after Turn 3 targeted verification.** Await user visual acceptance. Do
not start the UX1.x full-suite closure or P6, M2/V1, XP1, Tiamana, Ledger,
Inventory I1, Quests, Travel, Apotheosis mechanics or C5 automatically.

## Turn 3 focused regression patch — Persistent HUD containing block

### Root cause and fix

- Confirmed the regression was structural rather than a Soul/Money styling
  defect: `.character-persistent-hud` used `position: fixed` while remaining a
  descendant of `[data-character-surface="workspace"]` / the outer Focus Field.
- Turn 3 applies `transform: scale(0.996)` to that surface during the 180ms
  native-route exit. A transformed ancestor therefore became the containing
  block for the supposedly viewport-fixed HUD and made it visually shrink and
  move with the Character scene.
- Added a neutral `.character-workspace-page-shell`. The Focus/transition
  surface now closes immediately after the Character Workspace `<main>`, while
  `.character-persistent-hud` is its sibling inside the page shell.
- Updated the viewport anchoring selector to
  `.character-workspace-page-shell > .character-persistent-hud`. Soul/Money
  sizes, offsets, assets and visuals were not changed. The HUD remains outside
  radial layout, Focus ownership and route-transition transforms/filters.

### Files changed by this patch

- `characters/templates/characters/character_workspace.html` — non-transformed
  page shell and HUD moved outside the Character transition/Focus surface.
- `static/css/app.css` — direct-child viewport HUD contract moved from the
  Focus Field to the page shell; no HUD dimensions or positions changed.
- `characters/tests/test_personal_notes_n1.py` — affected presentation test now
  asserts the structural boundary and the new CSS ownership selector.
- `docs/UX1_4_PROGRESS.md` — this checkpoint.

### Targeted verification

- Affected presentation test
  `test_ux14_turn2b_hud_is_persistent_outside_radial_scene_without_fake_state`:
  **1 test, OK**.
- Real-browser desktop telemetry sampled the actual Workspace → Memory exit at
  roughly 10–12ms intervals from 0 through 170ms. Every sample retained:
  - HUD: `position: fixed`, `transform: none`, viewport rect
    `1265×720 @ (0,0)`;
  - Soul: `116×116 @ (18,586)`;
  - Money: `104×52 @ (1141,90)`;
  - `hud.closest("[data-character-surface]") === null`.
- Memory → Workspace entrance samples from 0 through 760ms retained the exact
  same HUD/Soul/Money rects and transforms.
- Workspace → Memory → browser Back restored the same viewport-fixed rects
  with no stuck route classes and no browser console warnings/errors.
- Temporary Campaign `c314f100-0000-4000-8000-000000000001` and user
  `ux14_turn3_hud_browser` were deleted; both verification counts are zero.
- The temporary local server is stopped and port `8765` is not listening.
- Full suite was intentionally not run.

### Exact next step / STOP

**STOP after the requested Persistent HUD regression patch.** Do not change
accepted radial geometry, connectors, weather, Soul/Money visuals or begin any
new phase automatically.
