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

**STOP after Turn 1.** Await explicit user visual acceptance or requested polish.
Do not begin UX1.4 Turn 2, GIF integration or HUD work without explicit user
continuation.
