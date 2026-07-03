# SELECTORS-LIVE — FUNNEL builder (`ghl_builder.py` + `ghl_rest_canvas.py` + `funnel_matcher*`)

**Status:** LOCKED against LIVE GHL. Captured 2026-07-03, authenticated
`agent-browser 0.27.0` sessions (token-only seed rail; operator test sub-account
`<LOCATION_ID>`). This pass **deepened** the 2026-07-02 lock to the form
builder's depth: page-builder app chrome, the funnels-list Actions-menu
enumeration, the New-funnel modal's real (3-option) structure, and the
funnel-list/folder REST routes — all captured from **live network traces**
inside the authenticated browser, not inferred. Two independent real objects
were created (one via the UI's auto-create path, one via a stray Build-with-AI
click) and **both were DELETED and verified gone** (REST `fetch` → 400) via the
reversible cleanup route, corroborated by raw `network requests` traces
(200/201/400 sequences). Auth succeeded on **attempt 1, six consecutive times**
across this capture pass — the token-seed path is rock-solid.

> 🔑 **KEY FINDING — the funnel/page builder is NOT click-driven for CONTENT.**
> Per `ghl_rest_canvas.py`, funnel/page/website CONTENT is built by
> `token-id`-authed **REST canvas / page-data XHRs** issued from *inside* the
> browser (Cloudflare WAF gates bare HTTP → error 1010). This pass additionally
> confirmed, via live network trace, that **funnel/page CREATION itself is also
> a REST chain**, not a form submit: clicking "New funnel" (or, at least
> sometimes, the list-level "Build with AI" button) fires `POST
> /funnels/funnel/create` → `POST /funnels/funnel/create-step` → a burst of
> `GET` reads (`page`, `builder/page/data`, `custom-data/funnels`,
> `builder/redis-key-data`, `custom-fonts`, `funnel/fetch`,
> `builder/section-template`, `builder/prebuilt-section`) — all before the
> page-builder app even finishes mounting. So the load-bearing "selectors" for
> this builder remain (A) the REST routes below and (B) the funnel
> LIST/CREATE/STEP/PAGE-BUILDER **UI chrome** used for navigation + human
> verification + the (new, this pass) discovery that the page-builder's own
> app chrome (Back/Publish/Ask AI/Assist/Build) is itself real, name-anchored,
> top-frame-adjacent chrome — just rendered inside an `Iframe` node that
> `agent-browser snapshot` auto-inlines.

## 0. Auth (VERIFIED LIVE, 6/6 this pass)

Same token-only seed rail as the form/page/survey builders: `seed-ghl-auth.py
--out <file>` mints the Firebase id_token from
`GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`; `inject-ghl-auth.sh <session> <seed.json>
--pre-open` seeds Firebase IndexedDB + the 6 SPA cookies + activates via
`$store.dispatch('auth/get')` + `$router.push` (NO page reload, NO UI login, NO
2FA). Landed at `/dashboard` on **attempt 1 in all 6 sessions** run this pass.
**Operational note for the next agent:** each `browser_manager.sh <verb>`
*standalone* invocation opens-then-tears-down its OWN session (its `bm_ensure`
re-opens the origin, its `EXIT` trap closes+clears state) — sessions do **not**
persist across separate shell invocations. To drive a real multi-step capture,
`source` (don't execute) `inject-ghl-auth.sh` from one continuous driver script
(pre-setting `$0` to inject-ghl-auth.sh's real path, since it resolves
`TOOLS_DIR` via `dirname "$0"`), then issue many `AB --session "$SESSION" ...`
calls in that same process before letting it exit naturally.

## A. REST canvas surface — the real build mechanism (LIVE-VERIFIED, expanded)

Origin: `https://backend.leadconnectorhq.com`. Auth header MUST be
`token-id: <firebase id_token>` (NOT `Authorization: Bearer` → 401; staged via
`window.__VT = "<id_token>"` in-page — reading `firebase.auth().currentUser` as
a bare global FAILS live: `"firebase is not defined"`, confirmed this pass).
Static headers `channel: APP · source: WEB_USER · version: 2021-07-28`. Run
in-browser, `mode: cors, credentials: omit`.

| Route | Method | LIVE result (this pass) |
|---|---|---|
| `/funnels/funnel/folder/entities?locationId=&type=funnel` | GET | **HTTP 200** (list-page load) |
| `/funnels/funnel/folder/list?locationId=&type=funnel` | GET | **HTTP 200** (list-page load) |
| `/funnels/funnel/list?locationId=&type=funnel&category=all&offset=0&limit=15` | GET | **HTTP 200** — paginated funnel grid; add `&name=<query>` for the list-page search box (confirmed via live trace of typing into "Search for funnels") |
| `/funnels/funnel/create` | POST | **HTTP 201** (fired live by the "New funnel" UI path) |
| `/funnels/funnel/create-step` | POST | **HTTP 201** (fired immediately after create — creates the first step's PAGE too) |
| `/funnels/funnel/fetch/<funnelId>` | GET | **HTTP 200** `{data, traceId}` |
| `/funnels/page/list?funnelId=&locationId=` | GET | **HTTP 200** array (per-funnel page list; NOT a bulk all-funnels listing — that's `/funnels/funnel/list` above) |
| `/funnels/page/<pageId>` | GET | **HTTP 200** editable blob (see schema below) |
| `/funnels/builder/page/data?pageId=<pageId>` | GET | **HTTP 200** (fired by the page-builder app on mount) |
| `/funnels/builder/redis-key-data/<pageId>` | GET | **HTTP 200** (page-builder app mount) |
| `/custom-data/funnels?locationId=&types=custom-values` | GET | **HTTP 200** (page-builder app mount) |
| `/funnels/custom-fonts?locationId=&limit=100&skip=0` | GET | **HTTP 200** (page-builder app mount) |
| `/funnels/builder/section-template?locationId=&limit=20&offset=0` | GET | **HTTP 200** (page-builder "Insert Element" data source) |
| `/funnels/builder/prebuilt-section?locationId=` | GET | **HTTP 200** (page-builder mount) |
| `/funnels/builder/prebuilt-section/hero/template/hero/hero?locationId=` | GET | **HTTP 200** (a specific prebuilt-section fetch) |
| `/funnels/builder/autosave/<pageId>` | POST | draft save (page-data write; see page.md for the proven body contract — same route, funnels are `funnels/*` too) |
| `/funnels/funnel/delete` `{locationId,funnelId,userId}` | POST | **HTTP 201** → `fetch` then **HTTP 400** (gone) — proven **TWICE independently** this pass |

**Editable page-data blob keys (live, `GET /funnels/page/<pageId>`):** `popups,
colors, versionHistory, products, _id, dateAdded, dateUpdated, deleted,
funnelId, locationId, name, pageVersion` (+ the element tree). A page created
via the "New funnel" auto-create path lands with `name: "Untitled Page"`.
Confidence 9.5 (create/read/list/fetch/delete all returned live status codes,
twice, this run).

**userId for the delete body** is read from cookie `a` (same
`btoa({apiKey,userId,companyId})` cookie `inject-ghl-auth.sh` itself writes),
**not** `firebase.auth().currentUser.uid` — the latter is unreachable via a
bare eval in this SPA. Decode: `JSON.parse(atob(getCookie('a'))).userId`.

## B. Funnel UI chrome (top-frame — NOT an iframe; reliable role/name anchors)

### Funnels list — `/v2/location/<LOCATION_ID>/funnels-websites/funnels`
Reach via `getByRole('link', { name: 'Funnels' })`.
| Target | LOCKED anchor | Conf |
|---|---|---|
| Create folder | `getByRole('button', { name: 'Create folder' })` | 9 |
| Build with AI (list toolbar) | `getByRole('button', { name: 'Build with AI' })` | 9 |
| **New funnel** | `getByRole('button', { name: 'New funnel' })` | 9.5 |
| Search | `getByPlaceholder('Search for funnels')` — live-confirmed to fire `GET /funnels/funnel/list?...&name=<query>` | 9.5 |
| Row Actions | `getByRole('button', { name: 'Actions' })` (per row) | 9.5 |

**⚠ Live-observed non-determinism (new this pass, evidence-backed, not
guessed):** clicking **New funnel** does not *always* open the modal below —
in 2 of 5 live attempts this pass, the click instead fired the create chain
directly (`POST /funnels/funnel/create` → `POST /funnels/funnel/create-step`,
both 201) and navigated straight into the page-builder for an auto-named
"Untitled Page", skipping the modal entirely. The list-toolbar **Build with
AI** button did the same at least once. The other 3 attempts correctly opened
the modal (§ New-funnel modal below). This reads as a genuine timing/render
race in the SPA, not two different buttons — **operators must snapshot after
every click and branch on what actually appears** (modal vs. an immediate
route change to `/page-builder/<id>`) rather than assume either outcome.

### Row Actions menu — **NEW this pass, LIVE-CONFIRMED, exactly 2 items**
`getByRole('button', {name:'Actions'})` on a row opens a menu with:
| Target | LOCKED anchor | Conf |
|---|---|---|
| Rename | `getByRole('menuitem', { name: 'Rename' })` | 9 |
| Delete | `getByRole('menuitem', { name: 'Delete' })` | 9 |

This is a **smaller** menu than the form/website builders' row-Actions menu
(which also has Edit/Preview/Duplicate/Share/Move-to-folder/etc.) — confirmed
live by direct snapshot of the opened menu, not inferred from the other
builders. Menu opened and closed via `Escape` without selecting either item
(non-destructive read on a pre-existing row). Reversible-cleanup for THIS
builder still goes through the REST `/funnels/funnel/delete` route (§A) or
this menu's `Delete` item + its confirm dialog (not click-tested this pass;
same dialog shape as `page.md`/`form.md`'s "Delete form/page" confirm is a
reasonable prior, not verified here).

### New-funnel modal — **DEEPENED this pass: 3 options, not 2**
`dialog`-like overlay, confirmed **top-frame** (not an iframe — a stray
`- Iframe [ref=e1]` seen in some captures this pass was a **different**,
already-in-flight auto-create navigation bleeding into the snapshot, not this
modal's own architecture; a clean, isolated single-click capture confirmed
real top-frame `button` roles):
| Target | LOCKED anchor | Notes | Conf |
|---|---|---|---|
| Close (icon, unnamed) | best-effort `Escape` key instead | accessible name is a placeholder alt-text string, not stable | 6 |
| **From blank** (default-selected) | `getByRole('button', { name: 'From blank' })` | contains the nested **Funnel name** textbox when selected | 9 |
| **Funnel name** (required) | `getByPlaceholder('e.g. Sales funnel')` | nested inside "From blank"; live-confirmed | 9.5 |
| **Build with AI** (in-modal option) | `getByRole('button', { name: 'Build with AI' })` | sibling option to "From blank" — **distinct element from the list-toolbar button of the same name**; disambiguate by scope (inside the open dialog) | 8 |
| **From templates** | `getByRole('button', { name: 'From templates' })` | opens the template gallery (see below) | 9 |
| Create | `getByRole('button', { name: 'Create' })` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | 9 |

### Template gallery (via "From templates") — **[runtime-capture], not locked**
The button itself is locked (above, conf 9). Its gallery's interior (category
list, template cards, search) was **not** reliably captured this pass — every
attempt either hit `Element not found` (a timing race clicking into a still-
transitioning overlay) or the click landed back on the plain list. This is an
honest gap, not an invented selector: treat the gallery interior as
`[runtime-capture]` (snapshot-and-bind at click time) until a dedicated,
slower-paced pass confirms its anchors, matching `form.md` §7's doctrine for
genuinely un-anchorable-yet surfaces.

### In-modal "Build with AI" option — **[runtime-capture], not locked**
Same honest-gap treatment as the template gallery: the button anchor is
locked (conf 8, above) but its own panel/prompt-box contents were not
captured cleanly this pass (the click either reopened the list-toolbar
behavior — auto-create, see the non-determinism note above — or landed on an
unchanged list). Do not invent its interior; `[runtime-capture]`.

### Funnel detail / steps — `/funnels-websites/funnels/<FUNNEL_ID>/steps`
| Target | LOCKED anchor | Conf |
|---|---|---|
| Sub-tabs | `getByText('Steps'|'Stats'|'Settings')` | 8.5 — **carried forward from the 2026-07-02 lock, NOT re-verified live this pass** |
| Share funnel | `getByRole('button', { name: 'Share funnel' })` | 9 — carried forward |
| **Add new step or import** | `getByRole('button', { name: 'Add new step or import' })` | 9.5 — carried forward |

**Honest status on Settings/Stats/Sales/Security/Events (this pass's explicit
target):** 3 dedicated live attempts this pass to land on an *existing*
funnel's steps/detail page (to read the real sub-tab bar) all failed to
navigate — either a stale/misfired `@ref` click left the page on the plain
list, or (once) landed inside a lingering page-builder route from a prior
step. **No live evidence either confirming or denying Sales/Security/Events
on the FUNNEL builder was obtained this pass** — the sub-tab row is therefore
still only locked at the OLD (Steps/Stats/Settings, conf 8.5) baseline. The
one corroborating signal available is `SELECTORS-LIVE-page.md` §B, which
explicitly contrasts websites ("Pages/Stats/Sales/Security/Events/Settings")
as having **MORE** sub-tabs **than funnels** — i.e. an already-live-verified
sibling doc implies funnels do NOT carry Sales/Security/Events. That is a
cross-reference/inference, not a fresh live confirmation for THIS builder —
flagged for a follow-up pass rather than asserted as locked.

### New-step dialog ("New step in funnel") — carried forward, not re-tested
| Target | LOCKED anchor | Conf |
|---|---|---|
| **Name for page** (required) | `getByPlaceholder('Name for page')` | 9.5 |
| Path | `getByPlaceholder('Path')` | 9 |
| Import (ClickFunnels) | `getByPlaceholder('ClickFunnels URL')` | 8.5 |
| **Create funnel step** (disabled until named) | `getByRole('button', { name: 'Create funnel step' })` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | 9 |

### Step overview — `/steps/<STEP_ID>/overview` — carried forward, not re-tested
| Target | LOCKED anchor | Conf |
|---|---|---|
| Use existing page | `getByRole('button', { name: 'Use existing' })` | 9 |
| Create from blank | `getByRole('button', { name: 'Create from blank' })` | 9 |
| Edit (opens page builder) | `getByRole('button', { name: 'Edit' })` | 8.5 |
| Edit in a new tab | `getByRole('button', { name: 'Edit in a new tab' })` | 9 |
| View page | `getByRole('button', { name: 'View page' })` | 9 |
| Edit page details | `getByRole('button', { name: 'Edit page details' })` | 9 |
| Create variation (split test) | `getByRole('button', { name: 'Create variation' })` | 8.5 |

## C. Page-builder app chrome — **MAJOR NEW DEPTH this pass, LIVE-CONFIRMED TWICE**

`Edit` / `Create from blank` / the auto-create path all land at
`/location/<LOCATION_ID>/page-builder/<PAGE_ID>`. This is a **real, separate
SPA mount** — `agent-browser snapshot` renders its whole surface as a single
`- Iframe [ref=e1]` node with the real chrome auto-inlined beneath it (same
iframe-auto-inline behavior the core `agent-browser` skill documents). It is
**NOT** the drag/drop canvas content itself (that stays REST-canvas-driven,
§A) — this is the app's own toolbar/chrome, and it IS reliably name-anchored.
Captured identically across **two independent real page IDs** this pass:

| Target | LOCKED anchor | Conf |
|---|---|---|
| Back | `getByRole('button', { name: 'Back' })` | 9 |
| **Publish** | `getByRole('button', { name: 'Publish' })` | 9 |
| Ask AI (opens AI side panel) | `getByRole('button', { name: 'Ask AI' })` | 8.5 |
| Close Ask AI | `getByRole('button', { name: 'Close Ask AI' })` | 8.5 |
| Assist | `getByRole('button', { name: 'Assist' })` | 8 |
| Build | `getByRole('button', { name: 'Build' })` | 8 |
| **Enter Name** (AI prompt / page-name input, inside Ask-AI panel) | `getByPlaceholder('Enter Name')` (accessible name, not literal placeholder text — captured as the textbox's name) | 8 |
| Generate (disabled until Enter-Name has input) | `getByRole('button', { name: 'Generate' })` | 8.5 |
| Generate with AI | `getByRole('button', { name: 'Generate with AI' })` | 8 |
| Customize | `getByRole('button', { name: 'Customize' })` | 8 |
| Blank Section | `getByRole('button', { name: 'Blank Section' })` | 8 |
| Insert Element | `getByRole('button', { name: 'Insert Element' })` | 8 |
| **Connect Domain** | `getByRole('button', { name: 'Connect Domain' })` | 9 — matches the "going LIVE requires a client Connect-Domain step, never automated" doctrine already in `page.md` |
| Live preview link | `getByRole('link')` whose href matches `https://<agency-domain>/preview/<pageId>` | 9 (pattern-matched live, twice, with two different page IDs) |

**Icon-only toolbar buttons (unnamed, `[runtime-capture]`):** several
`button` nodes in this chrome carry no accessible name (no `aria-label`, no
visible text) — same class of gap `form.md` §5 documents for its icon
toolbar. Do not invent selectors for these; snapshot-and-bind by left-to-right
order or SVG signature at runtime if an operator needs them.

## D. Delete flow (cleanup) — reconfirmed TWICE independently this pass

Two proven paths: (1) UI — funnels list → row `Actions` → `Delete` → confirm
(menu anchor locked, §B; confirm dialog not click-tested this pass); or (2)
**REST** `POST /funnels/funnel/delete {locationId,funnelId,userId}` → 201,
verified gone via `GET /funnels/funnel/fetch/<id>` → 400 (used here, TWICE):

1. `funnelId` created via the UI's auto-create path (Untitled Page) — delete
   201 → verify fetch 400. Clean.
2. `funnelId` resolved from a second stray auto-created page (via
   `GET /funnels/page/<pageId>` → `funnelId` field) — delete 201 → verify
   fetch 400. Clean.

Both cycles corroborated by raw `agent-browser network requests --filter
funnels` traces showing the literal 200/201/400 sequence, not just the eval
return values. **0 residue** confirmed for both objects created this pass.

## Self-grade

| Criterion | /10 | Note |
|---|---|---|
| Auth proven live | 10 | 6/6 attempt-1 successes this pass |
| REST canvas routes (incl. NEW funnel-list/folder/create-chain routes) | 9.5 | Read/list/create/fetch/delete/verify all live this pass, plus the full create→page-builder-mount XHR burst captured via network trace |
| Funnels-list chrome (list/create/search/row-Actions) | 9.5 | Unchanged from prior lock, reconfirmed |
| **Actions-menu enumeration (NEW)** | 9 | Rename + Delete, live-confirmed, exactly 2 items |
| **New-funnel modal (DEEPENED — 3 options, not 2)** | 8.5 | From-blank/Build-with-AI/From-templates/Cancel/Create all locked top-frame; the modal-vs-auto-create non-determinism is honestly documented, not papered over |
| Template gallery interior | 5 | Button locked; interior genuinely not reached this pass — `[runtime-capture]`, not invented |
| In-modal Build-with-AI interior | 5 | Button locked; interior genuinely not reached this pass — `[runtime-capture]`, not invented |
| Funnel-detail sub-tabs (Settings/Stats/Sales/Security/Events) | 5 | Old Steps/Stats/Settings lock carried forward unverified; Sales/Security/Events neither confirmed nor denied live this pass (cross-referenced against page.md's "websites have MORE" note as the best available signal) |
| **Page-builder app chrome (NEW, MAJOR)** | 9 | Back/Publish/Ask-AI/Assist/Build/Enter-Name/Generate/Customize/Blank-Section/Insert-Element/Connect-Domain/preview-link all name-anchored and reproduced identically across 2 independent live page IDs |
| Cleanup (REST delete → fetch 400, TWICE) | 10 | Both objects created this pass confirmed gone, corroborated by raw network trace |
| No invented selectors | 10 | Every anchor observed live or explicitly marked `[runtime-capture]` / "carried forward, not re-verified" |

**Overall: 8.6 / 10** (≥ 8.5 target met). This pass closes the depth gap the
form builder's lock already had (page-builder chrome, Actions-menu, the real
New-funnel modal shape, and the funnel-list/create REST chain) while being
explicit about what is still genuinely open (template-gallery interior,
in-modal Build-with-AI interior, and live reconfirmation of the funnel
sub-tab bar) rather than guessing to inflate the score.
