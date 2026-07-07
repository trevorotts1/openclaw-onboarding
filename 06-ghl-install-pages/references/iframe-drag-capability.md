# Cross-origin iframe drag capability (`ghl_iframe_drag.py`)

**Status:** LIVE (v1.0.0). Shared, reusable, builder-agnostic. Wired into the FORM
builder and the SURVEY builder; ready to wire into the PAGE/FUNNEL "Code" element
drag.

## The problem this solves

Every GHL (Convert and Flow) visual builder renders inside a **cross-origin
iframe** embedded in the `app.convertandflow.com` shell:

| Builder | Iframe host / path | Selector preset |
|---|---|---|
| Forms | `leadgen-apps-form-survey-builder.leadconnectorhq.com/form-builder-v2/<id>` | `iframe[src*="form-builder-v2"]` |
| Surveys | `leadgen-apps-form-survey-builder.leadconnectorhq.com/survey-builder-v2/<id>` | `iframe[src*="survey-builder-v2"]` |
| Pages / Funnels (Code element) | `page-builder.leadconnectorhq.com` | `iframe[src*="page-builder"]` |

`agent-browser` (the Skill-6 PRIMARY engine, pinned 0.27.0) auto-inlines the
iframe's **accessibility** tree into a top-frame snapshot and gives CDP `@ref`s to
real interactive ARIA leaves (buttons/textboxes/links/menuitems) — those work. But
the **drag-source tiles** (Quick-Add field tiles, Add-Object-Field rows) are
NON-interactive `generic`/`StaticText` nodes with **no ref**, and neither `text=` /
CSS / `find text` NOR the `frame` verb can reach across the cross-origin boundary
to grab them.

**Verified live** (SELECTORS-LIVE-form.md §7, re-verified against a two-origin
fixture during this fix):

- `agent-browser frame @eN` only re-scopes the **read-only** a11y snapshot. After
  switching, `eval` STILL runs in the top frame (`document.getElementById` of an
  in-iframe node returns `false`), and `find` / `drag` / `get` STILL bind to the
  top frame. `eval` has no `--frame` flag. So **agent-browser 0.27.0 has no working
  frame-scoping primitive for LOCATING or DRAGGING a non-interactive element inside
  a cross-origin child frame.**

This is a "cannot LOCATE the source across a cross-origin iframe" problem, not a
"drag is unsupported" problem. The build correctly STOPPED-and-reported rather than
fake a success — that fail-closed behavior is preserved; only the underlying reach
limitation is fixed.

## The fix (hybrid: agent-browser PRIMARY + Playwright for the drag only)

Everything agent-browser already does well stays on agent-browser (the
Firebase-token login injection, navigation, button/field clicks, waits, fills,
snapshots). Playwright's ONLY job is the frame-scoped coordinate-drag step:

1. agent-browser owns + drives the ONE seeded, logged-in Chromium (the SINGLETON
   POOLED BROWSER gateway). Its CDP endpoint is read with `get cdp-url`.
2. Playwright `connect_over_cdp(<cdp_url>)` ATTACHES to that SAME already-running,
   already-authenticated Chromium — **one browser, one login, zero duplicate
   auth** (the Firebase-token login is tool-agnostic; nothing here re-logs-in).
3. `page.frame_locator(<iframe_selector>).locator(<source>).bounding_box()`
   resolves TRUE page/viewport coordinates for the tile **even across the
   cross-origin boundary** — bounding-box math is not blocked by same-origin
   policy; only scripted DOM access is.
4. The drag is a RAW page-level synthetic MOUSE sequence: `mouse.move` (source) →
   `mouse.down` → many INTERPOLATED `mouse.move` steps toward the target → settle →
   `mouse.up`. Raw pointer input is NOT tied to any specific JS event a developer
   chose to listen for, so it drives GHL's own pointer-distance drag sensor
   **regardless of whether the builder uses the native HTML5 Drag-and-Drop API or a
   custom mousedown-based dragger**, and it crosses the iframe boundary the way a
   real human mouse would. `>= 20` interpolated moves are required (gates.json
   `playwright_fallback_recipes.code_element_drag_drop`); a single down→up move does
   NOT trip the sensor.

## Public API

`tools/ghl_iframe_drag.py`:

- `coordinate_drag(cdp_url, *, iframe_selector, source, target, url_marker=None,
  verify_text=None, interpolated_moves=24, move_interval_ms=16, ...)` — attach over
  CDP, drag inside the iframe, verify placement, detach. Returns a receipt.
- `drive_drag(page, ...)` — the load-bearing core (operates on any Playwright-`page`
  surface; shared by the live path and the self-test).
- `iframe_selector_for("form" | "survey" | "page_code")` — known selector presets.
- `IframeDragError` — fail-closed exception (unlocatable source/target, null box,
  missing page/frame, Playwright absent, or an unverified placement). NEVER fakes a
  placement.

Locator spec grammar (small on purpose — GHL tiles are located by visible text):
`text=Foo` (default), `exact=Foo`, `css=SEL`, or a bare `Foo` (treated as `text=`).

## How the builders call it

- **Form builder** (`ghl_form_builder.py`): `_perform_iframe_drag(session, tile,
  drop_anchor, verify_text=...)` at the F5 (Quick-Add) and F6 (Add-Object-Fields)
  drag sites. On any failure it raises `StopAndReport` (preserving fail-closed).
- **Survey builder** (`ghl_survey_builder.py`): `_perform_iframe_drag(session,
  field_row, target_slide, verify_text=...)` in `_p2_pull_object_fields`. On any
  failure it raises `RuntimeError` (STOP).

Both read the CDP url from the live session via the managed glue (`get cdp-url`) —
no raw agent-browser spawn (satisfies the SINGLETON POOLED BROWSER managed-only
guard).

## Headless (D6)

This capability NEVER opens a visible window. The live path attaches to
agent-browser's already-headless Chromium over CDP. The self-test's own browser
uses `launch_persistent_context(..., headless=True)` — never a bare `launch()`,
never `headless=False`.

## Dependency footprint (scoped to Skill 6)

- Python **Playwright** (`pip install playwright && python3 -m playwright install
  chromium`). Verified present on the operator box (1.58.0 + chromium headless
  shell). agent-browser stays the PRIMARY engine for everything else — Playwright
  is used ONLY for the frame-scoped drag.
- When Playwright is absent, `coordinate_drag` raises `IframeDragError("playwright-
  unavailable", ...)` and the builders STOP-and-report with install instructions
  (never a silent or fake success).

## Proof / self-tests

- `python3 tools/ghl_iframe_drag.py --selftest` — dep-free structural proof
  (coordinate math, interpolation count, locator dispatch, fail-closed on null box
  / unverified placement / no-Playwright). CI-safe (no browser/network).
- `python3 tools/ghl_iframe_drag.py --live-selftest` — real Playwright vs a LOCAL
  two-origin fixture (a mousedown-based drag source inside a genuine cross-origin
  iframe). Proves the exact mechanism end-to-end, headless; fails closed on an
  absent tile. Reports UNAVAILABLE (exit 2) — not a false pass — when Playwright is
  absent.
- `tests/test_ghl_iframe_drag.py` — pytest regression suite (hermetic mocks + a
  Playwright-gated live case that is skipped cleanly when Playwright is absent).

## Audit of other Skill-6 iframe surfaces

| Surface | Cross-origin iframe drag? | Status |
|---|---|---|
| Form builder Quick-Add / Object fields | YES | **FIXED** (wired) |
| Survey builder Object fields | YES (same host) | **FIXED** (wired) |
| Page/Funnel "Code" element tile | YES (`page-builder.leadconnectorhq.com`) | NOTED — page/funnel CONTENT is created via `ghl_rest_canvas.py` (REST JSON, no drag), so there is no active live-drag call today. gates.json documents the Code-element drag as a Playwright-fallback recipe; wire it to `coordinate_drag(iframe_selector=iframe_selector_for("page_code"), ...)` when that path goes live. |
| In-iframe field PROPERTY panel edits, builder TAB switches, inline title rename | Not drag — a related cross-origin element-reach limitation | NOTED (out of scope for this fix). These are handled today as `[runtime-capture]` best-effort via the a11y snapshot; if a future need requires reliable reach, the same CDP+Playwright frame-scoped `frame_locator` approach in this module can locate/click them (extend with a `frame_click` helper). Not fixed in this pass. |

## Smoke-test labeling convention (for the separate live verifier)

The live end-to-end smoke test runs separately (a Sonnet verifier), against the
operator-authorized account. Any asset it creates as proof (a throwaway
form/survey) **MUST be unambiguously labeled** so it can never be mistaken for a
real business asset, e.g.:

    TEST - OpenClaw Skill6 Verification - DO NOT USE

and must be **deleted** at the end of the run (the builders already delete their
scratch asset in `finally`). Never leave a test asset behind under a client's real
account.
