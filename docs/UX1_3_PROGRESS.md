# UX1.3 — Reflection Visual Polish & Stabilization — Progress

Updated: 2026-08-26

## Scope guard

- Frontend-only continuation of the existing UX1.2 Character Workspace and
  Memory Space implementation.
- Preserve PW2 ambience, L1 location resolution, N1 privacy/ownership/forms,
  server routes, permissions, CSRF and progressive no-JavaScript behavior.
- No models, migrations, backend services, gameplay data or P6 work.

## Current status

UX1.3 implementation is complete on top of the completed, uncommitted UX1.2
worktree. Existing UX1.2 changes remain the preserved baseline. Browser
acceptance, regression and final checks are complete. The standalone final
report has not yet been created; work is paused by explicit user instruction
immediately after this checkpoint.

## Milestones

### 1. Focus bug audit — completed

- Read the complete UX1.3 specification.
- Read `docs/UX1_2_PROGRESS.md` and
  `UX1_2_FOCUS_MOTION_REFLECTION_INTERACTION_PASS_REPORT.md`.
- Audited all current Workspace/Memory templates, `reflection-focus.js`,
  `held-thoughts.js` and the relevant Reflection/Memory CSS.
- Confirmed the visual defect has three interacting causes:
  - a standalone full-viewport glow is permanently visible and follows the
    global pointer coordinates;
  - CSS `:hover`/`:focus-within` and the JS `.is-focus-target` class can all
    independently claim visual focus;
  - local node light is part of the idle background instead of a stateful
    overlay, so it can look active after JS focus has moved.
- Confirmed current pointer handling depends on delegated `pointermove`, lacks
  explicit `pointercancel`, `window.blur`, out-of-window and route-transition
  resets, and has no single `activePointerNode` owner.
- Confirmed current desktop module offsets and eight unrelated polygon lists
  produce more random movement than controlled asymmetry.

### 2. Focus state machine — completed

- Replaced delegated pointer ownership with one explicit
  `activePointerNode`/`activeNode` state.
- A new pointer-enter clears the previous node before activating the current
  node; pointer-leave clears only the node that still owns pointer focus.
- Added resets for pointer cancellation, surface/window leave, window blur,
  visibility loss, scrolling, route transition, coarse-pointer change and
  reduced-motion change.
- One bounded RAF engine now uses independent response constants for fast local
  light, medium node depth and slower scene depth. The response is exponential,
  settles without overshoot and stops scheduling frames when settled.
- The standalone full-viewport moving glare was removed from Workspace and
  Memory markup; local light defaults to zero and is owned by the active node.
- Browser stress exposed and then verified the scroll race guard: wheel/scroll
  immediately releases the active node, suppresses synthetic re-entry until
  real pointer movement, and leaves no stale local light.

### 3. Dark Glass material — completed

- Added six curated shard silhouettes instead of per-module random polygons.
- Added a dark translucent core, restrained depth layer and one/two cold
  refraction edges using bounded pseudo-elements.
- Pointer-positioned reflection is absent at idle and appears only for the
  active pointer node; keyboard focus retains a static center highlight.

### 4. Workspace composition + Identity Anchor — completed

- Rebalanced modules into three stable left/right pairs, a wide central Team
  anchor and a calm horizontal Inventory band.
- Removed the panel-like hero material while retaining portrait, name,
  description and the native Character switcher in a lighter scene anchor.

### 5. Notes whole-node navigation — completed

- The main Notes surface is now one semantic link to Memory Space.
- The separate Hold action remains a sibling link above the stretched primary
  link; there are no nested anchors and the primary route remains keyboard
  focusable.
- Preview excerpts are plain escaped text rather than competing nested links.
- Desktop browser verification confirmed that clicking the Notes surface opens
  Memory Space; the shortened visible label no longer clips while the full
  accessible name remains `Открыть удержанные мысли`.

### 6. Memory polish — completed

- Replaced random dense placement with a controlled alternating two-column
  constellation and four repeated light-shard contours.
- Idle thoughts are softer/thinner than Workspace nodes; focus/recession and
  the existing full-thought/create/release scenes remain intact.

### 7. Motion/easing — completed

- Reduced transitions to short fade/depth motion without large slide or spring
  overshoot and retained the UX1.2 server-confirmed creation lifecycle.
- Mobile/coarse-pointer and reduced-motion overrides explicitly remove pointer
  transform/light behavior while preserving static outlines.

### 8. Desktop stress verification — completed

- Verified live PW2 rain/dawn/hot ambience remains present on Workspace and is
  absent from Memory Space.
- Neutral -> hover -> settled focus was inspected: one focused/lit owner,
  visible 1.022 scale, local refraction and sibling recession.
- Rapid A/B pointer movement across thoughts repeatedly retained exactly one
  owner; scrolling cleared focus/light immediately and after settling.
- Pointer leaving the Character surface returns scene and node depth to idle.
- Open, browser-back, edit-compatible detail scene, Hold Thought step 1/2,
  Russian text manifestation, newly-held return and release confirmation were
  exercised without changing backend/POST/CSRF behavior.
- Visual QA found the quiet Notes destination label intersecting the lower
  clipped edge. It now sits on the safe vertical center of the shard, remains
  fully visible on desktop/mobile and keeps the whole-surface accessible link.
- Browser console returned no errors or warnings.

### 9. Mobile/reduced-motion verification — completed

- At `390×844`, Workspace and Memory Space have no horizontal overflow.
- Mobile computed scene/node transforms are `none` and local light alpha is
  zero; touch/open states remain native links/buttons.
- Mobile detail and Hold Thought body step fit the viewport flow without
  horizontal clipping.
- Keyboard-accessible native controls retain visible focus outlines. The
  reduced-motion contract is covered structurally and by focused tests:
  pointer depth/light and spatial/manifestation animations are disabled while
  the static focus outline remains.
- Fourteen required acceptance screenshots were saved under the Codex
  visualizations workspace. Isolated fixture Campaign/User data and all
  dependent test notes/characters/snapshot were deleted; no existing
  development data was touched.

### 10. Regression and final report — regression/checks completed, report pending

- Related N1/PW2 regression: 48 tests — OK.
- Full Django suite: 491 tests — OK, 9 expected skips.
- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: clean; only Git line-ending conversion notices.
- No schema migration was created and no backend/domain contract changed.
- The requested standalone UX1.3 report file has not yet been created.

## Changed files in UX1.3

- `characters/templates/characters/character_workspace.html`
- `characters/templates/characters/personal_notes_base.html`
- `templates/base.html`
- `static/js/reflection-focus.js`
- `static/css/app.css`
- `characters/tests/test_personal_notes_n1.py`
- `docs/UX1_3_PROGRESS.md` (new)

## Structural verification

- Recovered the interrupted mechanical CSS move before continuing.
- Confirmed cascade order: PW1/N1 base -> UX1.2 -> UX1.3.
- `UX1.3` marker count: exactly 1; both UX1.2 sections remain present.
- CSS brace counts: `1285` opening / `1285` closing.
- Mobile/coarse-pointer and reduced-motion blocks are top-level and closed.
- Removed invalid CSS custom-property multiplication from transforms.
- `git diff --check`: clean; only Git CRLF conversion notices.

## Tests

- Initial related N1/PW2 run: 48 tests, one stale JS implementation assertion
  failed; product behavior passed.
- Updated that assertion from the removed `frame` variable to the bounded
  `motionFrame` engine.
- Focused presentation suite: 14 tests — OK.
- `manage.py check` — OK at implementation checkpoint.
- Final related N1/PW2 regression: 48 tests — OK.
- Final full regression: 491 tests — OK, skipped=9.
- Final `manage.py check`: OK.
- Final migration dry-run: no changes detected.
- Final `git diff --check`: clean apart from non-failing CRLF notices.

## Known issues

- The in-app browser does not emulate OS-level reduced-motion in this run; the
  behavior is instead enforced by explicit media-query/JS guards and focused
  regression assertions.
- Direct OS/browser-chrome tab-switch and `window.blur` observation could not
  be completed reliably through the in-app browser harness. The implementation
  contains explicit blur/visibility reset hooks and focused regression coverage;
  no stuck focus was observed in the supported surface-leave/scroll/route tests.
- No accepted UX1.3 visual, interaction or security defect remains after the
  Notes-label correction and targeted desktop/mobile recheck.

## Focused Memory polish patch — completed

- Scope remained frontend-only; no backend, model, permission, route, schema or
  business-logic contract changed.
- Root cause of the first-thought rectangle: the newly created/first thought can
  retain programmatic keyboard focus, while the shared `.reflection-node`
  focus rule supplied a rectangular outer `box-shadow`. Its original first-card
  silhouette also had the least pronounced corners, which amplified the defect.
- `held-thought` focus/hover ownership now uses clipped inset light plus
  shape-aware `drop-shadow`; the card, `::before` and `::after` share the same
  polygon and the container clips/isolate its glass layers.
- The first thought now has an explicit angular shard silhouette, without a
  rectangular highlight or mask.
- Release confirmation was changed from a rectangular overlapping panel into a
  centered glass shard in the same Memory Space stage. The scene dim/blur is a
  single fixed layer; the selected thought remains a clipped shard behind it.
- Targeted browser acceptance passed for first-thought hover/focus and the
  open/release confirmation scene. The confirmation fits a 1280×720 viewport,
  has no horizontal overflow, and retains POST + CSRF semantics.
- Focused presentation regression: 14 tests — OK.
- Full suite was intentionally not repeated for this narrow CSS-only patch.
- Patch files: `static/css/app.css`, `templates/base.html`, and this checkpoint.

## Exact next step

Focused UX1.3 Memory polish is complete. Report the targeted result and STOP.
Do not begin P6 or any other gameplay phase.
