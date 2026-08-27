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
