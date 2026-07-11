# TECHNIQUES — Driving a cross-origin-iframe drag/drop widget

**Read this FIRST when a builder canvas is a cross-origin iframe** (GHL form + survey
builders). It is the generalized, durable version of the 2026-07-10 survey bring-up
one-off (`synth_drag.js`), baked INTO the skill. Reusable code:
`tools/ghl_iframe_dragdrop.py` (JS emitters + a ladder orchestrator) and
`tools/ghl_ab_executor.py` (native `.click()` resolver for ref-less chrome).

---

## 1. DETECTION — you are facing a cross-origin-iframe drag widget when

- Top-frame text/ref locators return **"Element not found"** for things you can SEE.
- The canvas ORIGIN differs from the app shell — e.g.
  `leadgen-apps-form-survey-builder.leadconnectorhq.com` mounted inside
  `app.convertandflow.com`.
- The a11y snapshot shows interactive refs ONLY for chrome buttons (Save / Preview /
  Integrate / Add Elements / Add Slide) while **panel tabs** ("Quick Add", "Add
  Object Fields") are ref-less `StaticText` and **tiles** are `generic > image +
  StaticText`.
- Inside the frame `document.querySelectorAll('[draggable=true]').length === 0` →
  a **pointer-driven Sortable / Vue-draggable** widget, NOT HTML5 DnD.

`ghl_iframe_dragdrop.detect_js()` returns this signature
(`{draggable, cross_origin_iframe, sortable_style}`).

---

## 2. THE TECHNIQUE LADDER (in order — cheapest first)

1. **`agent-browser drag <srcText> <dstText>`** — text-locator drag across the
   AUTO-INLINED frame (agent-browser ≥ 0.27.0). **PROVEN**: the form builder's
   `_place_*` calls drove real Anthology form builds on this exact iframe host.
   Code: `IframeDragDrop.text_locator_drag`.
2. **In-frame bounding-box interaction** — for ref-less nodes, compute
   `getBoundingClientRect()` and dispatch a native `.click()` (panel-tab switch) or an
   interpolated `pointerdown → N×pointermove → pointerup` sequence at real coords
   (coordinate drag), with a trailing HTML5 `dragstart/dragover/drop` fallback.
   Code: `IframeDragDrop.tab_click` / `.coord_drag` (`tab_click_js` / `coord_drag_js`).
   Donor: `survey-bringup/synth_drag.js`.
3. **CDP into the iframe's OWN target** — discover via `agent-browser get cdp-url` +
   `/json` (`type:"iframe"`, url match), then `Runtime.evaluate` INSIDE the frame:
   call the widget's framework method (e.g. Pinia store `handleDropAndMoveSurvey`) or
   mutate store state (`state.app.slides[n].slideData`) directly, then click the
   builder's OWN **Save** so the app serializes. This is required for any check that
   reads the widget store — **top-frame `agent-browser eval` cannot reach a
   cross-origin store**, only snapshot/`find`/`drag` cross the frame. Donor:
   `survey-bringup/cdp.py`, `probe_pinia.js`, `probe_drop.js`.
4. **CDP trusted input** — `Input.dispatchMouseEvent` / `dispatchDragEvent`
   interpolated sequences at page-global coords (frame rect offset applied), for
   widgets that check `isTrusted`. Equivalently Playwright frame-scoped `dragTo` on
   the same CDP endpoint.
5. **LAST RESORT — bypass the canvas** (the SPA's internal write API). **Verify
   first, ALWAYS** — see §3. No public API may exist for the asset class (true for
   surveys); the internal route is app-version-coupled.

**Smoke-test-first doctrine:** before trusting a full run, drive ONE tile drag and
prove it landed via the **iframe-aware snapshot delta** (the tile text appears more
times after than before). A CLI "✓ Done" that placed nothing is a FALSE PASS — the
snapshot/store delta is the only honest arbiter. If the single drag walls, fall back
to §3/§5, never a blind write. Code: `ghl_survey_builder._p2_smoke_test_drag`.

---

## 3. CAPTURE-GATED internal write (rung 5 — the anti-blind-POST rule)

There is NO public survey-build API and the save route is the SPA's internal,
app-version-coupled endpoint. NEVER POST to a guessed endpoint. Instead:

1. **Capture the builder's OWN Save request** via CDP `Network` (`cdp.py
   capture-save`): `Network.enable` → click the ref'd Save → record every
   POST/PUT/PATCH whose URL contains `/surveys`. Persist `{method, url, headers-of-
   interest, postData}` to `<evidence_root>/routing/survey-save-capture.json` (SCRUB
   the token value).
2. Re-GET the asset (proven read path) and confirm `updatedAt` advanced → the write
   endpoint + body shape are now RECEIPTED.
3. Only THEN compose + write. `ghl_survey_rest.survey_save_route(capture)` derives the
   origin/path/verb from that receipt ONLY — it raises `CaptureRequired` for a
   missing/blind route. The rest lane's preflight (`P5:rest_write_proven`) refuses to
   run without the receipt file.
4. Re-GET and `verify_roundtrip` (semantic diff of slide/logic counts). Any diff =
   FAIL the build (no false "done").

Reference schema for the compose step is READ off an existing built asset
(`GET backend.leadconnectorhq.com/surveys/<id>` with the agency Firebase/owner
`token-id` when the PIT is scope-denied — observed: PIT → `401 IAM` on the same route
the owner token reads fine).

---

## 4. PITFALLS (all live-verified)

- **Full `open`/reload bounces a token-seeded session to login** → in-app
  `$router.push` ONLY (never `open` after a seed).
- Top-frame locators never cross the frame boundary — **but the iframe `.src`
  attribute IS parent-readable cross-origin** (that's where the asset id lives:
  `_capture_survey_id` / `_capture_form_id`).
- Only role=button chrome gets a11y refs — **plan for StaticText tabs** (`tab_click`).
- **Stage JWTs via a python-written JS file** (`ghl_rest_canvas.stage_token_js` →
  `window.__VT`), never inline in JS source or bash `${VAR@Q}` (zsh mangles it → a
  spurious 401 that looks exactly like an auth failure).
- Bare-HTTP to `*.leadconnectorhq.com` needs a **real browser User-Agent** or
  Cloudflare 1010s (run the fetch INSIDE the seeded agent-browser session).
- `Authorization: Bearer <idToken>` is the WRONG scheme on SPA routes (401) — the
  header is **`token-id`**.
- **Watch the browser-open circuit breaker**: opens are precious (6 opens → box-level
  PARK). Opens are precious; evals are free.

---

## 5. Asset distribution note

Builder output on a TEMPLATE location is fleet-distributed via **snapshots**
(surveys/forms are snapshot asset categories) — build once, snapshot-push; never
re-drive the canvas per client box.
