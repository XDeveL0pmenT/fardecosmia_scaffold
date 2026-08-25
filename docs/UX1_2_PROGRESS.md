# UX1.2 — Focus Field & Living Memory — Progress

Updated: 2026-08-25

## Current status

UX1.2 started from the committed UX1.1 baseline (`711f9d6`). The worktree was
clean before this checkpoint was created.

UX1.2 is complete. Browser acceptance, related regression, the full suite,
release checks, screenshot capture and isolated-data cleanup all finished.

## Completed

- Read the complete UX1.2 specification from the supplied attachment.
- Re-read the required current project context:
  - `AGENTS.md`;
  - `Fardecosmia_Player_Experience_Architecture_v1.md`;
  - `PW1_CHARACTER_WORKSPACE_SHELL_REPORT.md`;
  - `PW2_LIVE_CHARACTER_AMBIENCE_REPORT.md`;
  - `N1_PERSONAL_CHARACTER_NOTES_REPORT.md`.
- Confirmed the phase is frontend-only and must preserve all existing backend,
  security, privacy, ownership, location and atmosphere contracts.
- Confirmed generic `.panel` / `.button` remain platform/GM primitives and must
  not become the primary Character-facing visual language.
- Audited the committed UX1.1 frontend:
  - Workspace modules already avoid generic `.panel`, but their large oval
    radii, repeated minimum heights and uniform blur still read as blobs/cards;
  - Character actions already use `reflection-action` / `memory-action`;
  - Held Thoughts use a neutral Memory background and do not render the PW2
    ambient component;
  - Notes routes are ordinary secure server-rendered GET/POST endpoints with
    CSRF and correct no-JS behavior;
  - current Notes detail/edit/release are separate page layouts, with no shared
    pointer focus engine or route-continuity treatment;
  - the existing typing effect uses the native textarea and already respects
    IME/reduced-motion, so it can be refined rather than replaced;
  - current success messages are rendered by the Platform shell and need to be
    visually suppressed only inside the private Memory surface.
- Chosen implementation boundary:
  - a small shared `reflection-focus.js` progressive enhancement;
  - CSS variables and transform/opacity layers only, with an animation frame
    loop that stops after the pointer target settles;
  - server routes/forms/history remain authoritative and usable without JS;
  - short exit/arrival classes provide scene continuity without a SPA or a
    second ambience engine.
- Reflection Node redesign completed:
  - Workspace nodes now use restrained clipped contours, distinct per-module
    geometry, natural content height and a less mechanical 12-column rhythm;
  - Tiamana, quests, map, life, party, thoughts, Apotheosis and inventory have
    related but semantically different material treatments;
  - Character choices and inventory use the same Character-facing primitive;
  - modules are keyboard-focusable and retain semantic article/section markup;
  - generic `.panel` / `.button` remain unchanged for Platform/GM surfaces.
- Shared Focus Field completed in `static/js/reflection-focus.js`:
  - fine-pointer movement updates target coordinates only;
  - a bounded `requestAnimationFrame` interpolation stops once settled;
  - CSS variables drive separate background, node and local-light depths;
  - node hover/focus sharpens the target and gently recedes siblings;
  - no server call, atmosphere change or per-frame layout read loop exists;
  - touch and reduced-motion paths disable pointer movement.

## In progress

- None.

## Not started

- None inside UX1.2 scope.

## Further completed work

- Memory Space redesign and interactions are implemented:
  - thought objects use compact varied contours rather than capsules;
  - selected thoughts expand into a central focus state while the same neutral
    Memory depth remains present;
  - create/edit/release use focused Memory layouts with native links/forms,
    CSRF and server-authoritative POST behavior unchanged;
  - short progressive exit/arrival states preserve browser history and no-JS
    navigation;
  - successful hold/edit uses a server-confirmed arrival animation and private
    Memory pages suppress only the generic Platform success toast;
  - release confirmation keeps the selected thought visible behind the
    question;
  - typing manifestation still uses the native textarea, handles composition
    and does not delay keystrokes.
- Added focused frontend contracts to the existing N1 presentation tests.
- Focused N1/PW2 regression: **45 tests — OK**.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- Browser acceptance already completed for:
  - desktop live Workspace at 1280x720;
  - PW2 `live` ambience with `dawn`, `rain` and `hot` tokens;
  - pointer focus values changing to `28.76% / 70.50%` over the Notes node;
  - focused node scale `1.045`, sibling scale `0.985` and sibling opacity
    `0.61`, confirming visible layered attention/recession;
  - neutral Memory Space with six varied thought objects and no
    `.ambient-scene` weather component;
  - no horizontal overflow in the desktop checks.
- Saved current screenshots:
  - `ux12-workspace-hover.png`;
  - `ux12-memory-space.png`.
- Completed the remaining real-browser acceptance:
  - thought hover produces a clear focus/recession relationship;
  - thought open retains the Memory background and expands into central focus
    rather than a generic detail card;
  - edit remains in the same focused scene with prefilled native plain-text
    controls and no `.panel` / `.button` primitives;
  - Hold Thought step 1 and step 2 transition inside the same dimmed scene;
  - Russian text input remains immediate, while `is-manifesting` appears and
    settles without mutating the entered value;
  - release renders as an in-scene `alertdialog` with a POST form and CSRF; no
    destructive release was submitted during browser acceptance;
  - browser Back restores the Memory list from an opened thought;
  - mobile 390x844 Workspace, Memory list, focused thought and both Hold states
    have no horizontal document scroll; node transforms compute to `none`;
  - console warnings/errors are empty;
  - Memory pages contain no PW2 `.ambient-scene`, while Workspace retains the
    previously confirmed live PW2 ambience.
- Browser acceptance found and fixed one frontend-only lifecycle defect:
  - a newly held thought formed on its server-confirmed detail route but stayed
    there instead of returning to the field;
  - the progressive enhancement now lets the confirmed thought contract,
    replaces the detail history entry with the Memory list, and identifies the
    exact new thought by its route pathname so it visibly settles among the
    existing thoughts;
  - no-JS routing, backend redirect, POST, CSRF and privacy behavior remain the
    authoritative fallback.
- Reduced-motion behavior is locked by the loaded CSS/JS contract and focused
  tests: pointer depth, drift, manifestation and spatial transition animations
  are disabled while static focus/glow remains. The in-app browser does not
  expose a reduced-motion media emulation capability, so this branch was
  verified from the live loaded assets rather than by changing OS preferences.
- Keyboard semantics were checked through native links/buttons/inputs,
  `tabindex="0"` reflection nodes and the `:focus-visible` treatment. The
  in-app browser's Tab dispatch did not move focus from an already focused
  textbox, so browser automation could not provide a reliable focus-ring
  screenshot; the underlying semantic/focus contracts remain covered by the
  focused presentation tests.

## Known issues

- The original browser-test snapshot fingerprint had to be refreshed after
  static World Data lazy initialization; this affected only the isolated
  temporary Campaign and now produces the intended live PW2 tokens.
- Browser-created notes are isolated inside the temporary UX1.2 Campaign and
  were removed with that Campaign during final cleanup.
- Isolated cleanup deleted only Campaign
  `c57f8718-50e8-461f-b155-1177af681921`, User `27` and their test-only
  dependencies. Both exact records now have a remaining count of zero.

## Final verification

- Related N1/PW2 regression: **45 tests — OK**.
- Full Django suite: **488 tests — OK, skipped=9**.
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: clean (only the repository's existing CRLF conversion
  notices were printed).
- Browser console warnings/errors: none.
- Pointer movement generated no HTTP requests; the development-server trace
  contains only explicit route navigations/forms and static asset loads.
- Screenshots were saved outside the repository under the current Codex
  visualization directory.

## Exact next step

Stop after the UX1.2 report. Do not begin P6 or another gameplay phase.
