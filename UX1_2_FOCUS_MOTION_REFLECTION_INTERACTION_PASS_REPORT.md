# UX1.2 — Focus, Motion & Reflection Interaction Pass — Report

Date: 2026-08-26

## Outcome

UX1.2 is complete as a frontend-only interaction and visual-language pass.
Character Workspace and Personal Character Notes now share a bounded Focus
Field and semi-material Reflection Node language while platform/GM UI keeps its
generic `.panel` and `.button` primitives.

No Character, Notes, location, weather, campaign or permission backend contract
was changed. No schema migration, Player coordinate/weather endpoint or new
gameplay state was introduced.

## Files changed

- `characters/templates/characters/character_workspace.html`
- `characters/templates/characters/_held_thought.html`
- `characters/templates/characters/personal_notes_base.html`
- `characters/templates/characters/personal_note_list.html`
- `characters/templates/characters/personal_note_detail.html`
- `characters/templates/characters/personal_note_form.html`
- `characters/templates/characters/personal_note_release.html`
- `templates/base.html`
- `static/css/app.css`
- `static/js/reflection-focus.js` (new)
- `static/js/held-thoughts.js`
- `characters/tests/test_personal_notes_n1.py`
- `docs/UX1_2_PROGRESS.md`
- `UX1_2_FOCUS_MOTION_REFLECTION_INTERACTION_PASS_REPORT.md` (new)

## Focus Field

`reflection-focus.js` provides a small progressive enhancement for Character
surfaces:

- fine-pointer movement updates a target only;
- one bounded `requestAnimationFrame` loop interpolates toward the target and
  stops after settling;
- separate CSS variables drive background depth, node depth and local light;
- hovered/focused nodes sharpen and scale to `1.045`, while siblings recede to
  `0.985` and reduced opacity;
- visibility loss, coarse pointer and reduced motion reset the effect;
- pointer movement performs no HTTP request and reads no gameplay data.

Real-browser inspection recorded a movement progression from `8.02% / 1.29%`
through `14.26% / 6.54%` and `24.62% / 15.14%` to a settled
`28.75% / 18.56%`, confirming visible interpolation rather than an immediate
decorative jump.

## Reflection Nodes

Workspace modules, Character choices, Inventory and Held Thoughts use their own
Character-facing `reflection-node` primitive. Their restrained polygonal
contours, varied widths, offsets and material accents replace the repeated
stretched oval/blob appearance from UX1.1. Semantic `<article>`, `<section>`,
`<a>`, `<button>` and form elements remain intact.

Platform/GM `.panel` and `.button` styles were not redefined.

## Memory Space

Held Thoughts remain private Character-owned N1 data and now read as one neutral
inner space:

- no PW2 `.ambient-scene` is rendered on Memory pages;
- thought objects have varied contours and positions;
- pointer/focus selects one thought while others dim and recede;
- open, edit and release retain the same Memory background;
- edit and create keep native escaped plain-text controls without generic CRUD
  cards or buttons;
- the two conversational questions remain exactly
  `Желаете дать памятку этой мысли?` and
  `Что вы хотите сохранить в памяти?`;
- Russian input remains immediate; manifestation is a visual class only and
  never replaces the native input value or uses `innerHTML`;
- release remains a secure POST with CSRF and keeps the thought visible behind
  the in-scene confirmation.

## Server-confirmed create lifecycle fix

Browser acceptance found one frontend defect: a newly held thought formed on
the server-confirmed detail route but stayed there rather than returning among
the existing thoughts.

The progressive enhancement now:

1. stores only the completed operation type in `sessionStorage` before native
   form submission;
2. waits for the authoritative POST redirect and detail page;
3. animates the exact created thought into focus;
4. contracts it and uses `location.replace()` to return to the Memory list;
5. identifies the exact thought by its safe route pathname and lets it settle
   visibly among the other thoughts.

Without JavaScript, the original secure POST/redirect/detail flow remains fully
functional. No note content, raw identifier payload or private data is copied
into a Campaign AuditLog.

## Accessibility and motion

- Reflection nodes are keyboard-focusable and retain a visible
  `:focus-visible` ring.
- Links, buttons, inputs and textareas remain native semantic controls.
- Mobile/coarse-pointer CSS removes node and background transforms.
- `prefers-reduced-motion: reduce` disables pointer depth, drift,
  manifestation and spatial transition animations while retaining static
  focus/glow and readable state.

The in-app browser exposed viewport emulation but not reduced-motion media
emulation. Therefore the reduced-motion branch was verified against the live
loaded CSS/JS and focused regression contracts rather than by changing the host
OS preference. The browser's automated Tab dispatch also did not move focus
from an already focused textbox; semantic focus order, native controls,
`tabindex` nodes and focus-visible CSS were verified directly and by tests.

## Browser acceptance

Desktop at 1280x720:

- Workspace live PW2 ambience remained `dawn` + `rain` + `hot`;
- Focus Field movement, inertia, local light and node/sibling depth verified;
- Memory had no PW2 weather layer;
- thought hover, fullscreen focus, edit, Hold steps, Russian manifestation,
  server-confirmed create and release confirmation verified;
- native browser Back restored the Memory list;
- console warnings/errors: none;
- server trace confirmed no requests from pointer movement.

Mobile at 390x844:

- Workspace, Memory list, focused thought and both Hold states verified;
- reflection node transform computed to `none` after pointer movement;
- document horizontal scroll remained zero and scroll width matched the content
  viewport;
- controls and focused states remained reachable and readable.

## Screenshots

Saved outside the repository in:

`C:/Users/Ruslanchik/.codex/visualizations/2026/08/08/019fe2d6-7fe3-7581-90ce-c414511c4091/`

Minimum acceptance set:

- `ux12-workspace-neutral.png`
- `ux12-workspace-node-focused.png`
- `ux12-memory-space-full.png`
- `ux12-thought-hover-focus.png`
- `ux12-thought-fullscreen-full.png`
- `ux12-hold-thought-step-1.png`
- `ux12-hold-thought-step-2.png`
- `ux12-new-thought-among-others.png`
- `ux12-mobile-workspace.png`
- `ux12-mobile-memory-space.png`

Additional captures cover edit, release, manifestation and mobile focused
thought states.

## Verification

- Focused N1/PW2 regression: **45 tests passed**.
- Full Django regression suite: **488 tests passed, 9 skipped**.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: clean; only CRLF conversion notices were printed.
- Schema migrations: none.

## Temporary data cleanup

Only the isolated browser-test Campaign
`c57f8718-50e8-461f-b155-1177af681921` and User `27` were deleted after exact
name/username verification. Campaign cascade removed 15 test-only dependent
rows; the test User delete removed one row. Both exact records now have a count
of zero. Real development Campaign/User data were not touched. The deleted
browser fixtures are not recoverable except by recreating them.

## Scope confirmation

UX1.2 did not start P6 or any gameplay phase. It did not change Notes privacy,
ownership, reassignment, AuditLog exception, CSRF, location resolution, PW2
sampling, atmospheric simulation, character state or permissions.
