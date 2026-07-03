# SELECTORS-LIVE — PAGE / WEBSITE builder + page-install path (`ghl_rest_canvas.py` / `ghl_builder.py`)

**Status:** LOCKED against LIVE GHL (§A–§C, 2026-07-02) + LOCKED against LIVE
GHL (§D session-lifecycle hazards, 2026-07-03). §A–§C captured 2026-07-02, same
authenticated `agent-browser 0.27.0` session (token-only seed; operator test
sub-account `<LOCATION_ID>`). A real ZHC website (`ZHC Selector Lock Web`, id
redacted) + a page (`ZHC Test Page`) were created, the **page-install `autosave`
write** was live-executed (HTTP 201), and everything was **DELETED** via REST
(verify fetch → HTTP 400). GHL left clean.

> ⚠️ **2026-07-03 run status — CHECKPOINT, not a full re-deepen.** This run set
> out to add the missing depth (page-builder app chrome, Settings/SEO/Stats
> sub-tabs, Actions-menu enumeration, template gallery) by creating a fresh
> scratch website+page. Auth was live-verified TWICE (attempt 1 both times, no
> UI login, no 2FA — see §D). Mid-session, `browser_manager.sh`'s circuit
> breaker tripped (6 `agent-browser open`s / 7200s window on the `default`
> location bucket — real threshold, see §D.4) and wrote the DURABLE box-wide
> PARK marker (`~/.openclaw/workspace/.park/workforce-build.parked`), which
> REFUSES every subsequent `bm_ensure`-gated call fleet-wide (incl. the box's
> `*/15` resume cron) until an **operator** runs `scripts/unpark-build.sh`. Per
> the operator's own STOP-and-report doctrine this run stopped rather than
> route around the breaker. **No scratch website/page was ever created** (0
> live objects made, 0 to delete, 0 residue by construction). §D below is 100%
> live-verified new depth (session-lifecycle/navigation hazards — genuinely
> useful and previously undocumented). §E lists what is still NOT captured
> pending a follow-up run post-unpark. Nothing in §A–§C was changed or
> re-verified this run; it stands as originally locked.

> 🔑 Same KEY FINDING as funnels: the page/website builder is **REST-canvas
> driven, not click-driven** (`ghl_rest_canvas.py`). The page-install =
> `token-id`-authed `GET /funnels/page/<id>` (read blob) → JSON splice
> (`SKILL44_WIDGET → FORM`) → `POST /funnels/builder/autosave/<pageId>` (draft
> save), all in-browser (Cloudflare WAF gates bare HTTP). The visual page-builder
> editor is NOT scripted by DOM selectors. Websites are funnels of type website —
> **same `/funnels/*` routes**.

## A. Page-install REST path — LIVE-VERIFIED this run

Origin `https://backend.leadconnectorhq.com`; header `token-id: <firebase
id_token>` (Bearer → 401); static `channel: APP · source: WEB_USER · version:
2021-07-28`; in-browser `mode: cors, credentials: omit`.

| Route | Method | LIVE result |
|---|---|---|
| `/funnels/page/list?funnelId=&locationId=` | GET | **HTTP 200** (n=1 after add page) |
| `/funnels/page/<pageId>` | GET | **HTTP 200**, `pageVersion` = **number** (1) |
| **`/funnels/builder/autosave/<pageId>`** | POST | **HTTP 201** → `{pageDataUrl:"funnel/<f>/page/<p>/page-data-<uuid>", pageDataDownloadUrl:"https://firebasestorage…"}` |
| `/funnels/funnel/delete` `{locationId,funnelId,userId}` | POST | **HTTP 201** → fetch **HTTP 400** (gone) |

**Autosave POST body contract (from `ghl_rest_canvas.py::autosave_body`, matches
the live 201):**
```json
{ "funnelId": "<funnelId>", "pageData": <page-data blob>,
  "pageVersion": <n+1 NUMBER>, "pageType": "draft",
  "manualSave": true, "integrations": {} }
```
- `pageVersion` MUST be numeric (n+1); a UUID 422s ("pageVersion must be a
  number") — confirmed the live record's `pageVersion` is a number.
- `pageType:"draft"` keeps it UNPUBLISHED (live pointer never moves) → the
  byte-identical round-trip used here is safe/reversible.
- Going LIVE needs a CLIENT "Connect Domain" step — never automated; automation
  only ever produces `/preview/<pageId>` URLs (residual from the solver doc).

**Editable page-data blob keys (live):** `popups, colors, versionHistory,
products, _id, dateAdded, dateUpdated, deleted, funnelId, locationId, name,
pageVersion` (+ the element tree the splice mutates). Confidence 9.5.

## B. Website UI chrome (top-frame — reliable role/name anchors)

### Websites list — `/v2/location/<LOCATION_ID>/funnels-websites/websites`
Reach via `getByRole('link', { name: 'Websites' })`.
| Target | LOCKED anchor | Conf |
|---|---|---|
| Create folder | `getByRole('button', { name: 'Create folder' })` | 9 |
| Build with AI | `getByRole('button', { name: 'Build with AI' })` | 9 |
| **New website** | `getByRole('button', { name: 'New website' })` | 9.5 |
| Search | `getByPlaceholder('Search for websites')` | 9 |
| Row Actions | `getByRole('button', { name: 'Actions' })` | 9 |

### New-website modal (same shape as New-funnel)
| Target | LOCKED anchor | Conf |
|---|---|---|
| From blank | `getByRole('button', { name: 'From blank' })` | 9 |
| From templates | `getByRole('button', { name: 'From templates' })` | 9 |
| **Website name** | `getByPlaceholder('e.g. Sales website')` | 9.5 |
| Create | `getByRole('button', { name: 'Create' })` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | 9 |

### Website detail / pages — `/funnels-websites/websites/<WEBSITE_ID>/pages`
| Target | LOCKED anchor | Conf |
|---|---|---|
| Sub-tabs (websites have MORE than funnels) | `getByText('Pages'|'Stats'|'Sales'|'Security'|'Events'|'Settings')` (top-frame clickable, ref'd) | 8.5 |
| Share website | `getByRole('button', { name: 'Share website' })` | 9 |
| **Add new page** | `getByRole('button', { name: 'Add new page' })` | 9.5 |

### New-page dialog ("New step in funnel" — shared with funnel steps)
| Target | LOCKED anchor | Conf |
|---|---|---|
| **Name for page** (required) | `getByPlaceholder('Name for page')` | 9.5 |
| Path | `getByPlaceholder('Path')` | 9 |
| Import (ClickFunnels) | `getByPlaceholder('ClickFunnels URL')` | 8.5 |
| **Create funnel step** (disabled until named) | `getByRole('button', { name: 'Create funnel step' })` | 9.5 |

Page row → `Actions` → `Edit` opens the page-builder app at
`/location/<LOCATION_ID>/page-builder/<PAGE_ID>` (separate app-mount / new tab).
Do NOT script the editor by DOM selectors — use the REST canvas (§A).

## C. Delete flow
UI (list → row `Actions` → `Delete` → confirm) OR **REST** `POST
/funnels/funnel/delete {locationId,funnelId,userId}` → 201 (used here; verified
fetch → 400).

## D. Session-lifecycle / navigation hazards — LIVE-VERIFIED 2026-07-03 (NEW)

Driving this exact builder end-to-end (auth → navigate → build → capture →
delete) crosses several tool-layer traps that are NOT specific to the page
builder's DOM but WILL break any live run of it. All four were hit and
confirmed live this run, on the operator's own test sub-account, via the same
`agent-browser 0.27.0` singleton.

### D.1 `browser_manager.sh` single-shot verbs silently wipe the session
`browser_manager.sh {eval|snapshot|open|wait|find|fill}`, run **standalone**
(not via `ghl_form_builder.py`'s Python driver), each independently call
`bm_ensure` then install `trap _bm_teardown EXIT`. When THAT invocation's shell
process exits, the trap fires `agent-browser close --session <name>` **AND**
`agent-browser state clear <name>` — closing the page **and wiping cookies +
IndexedDB**. Confirmed live: one `browser_manager.sh eval -- 'window.location.href'`
call after a good auth landing (`app:/dashboard`) silently downgraded the very
next login-check to `login:/` (a real Sign-in form, password input present).
**Implication:** for any multi-step live drive, call the `agent-browser` binary
**directly** (`agent-browser --headed false --session <name> <verb> ...`,
matching `ghl_form_builder.py::_ab()` exactly) for every step AFTER the initial
`inject-ghl-auth.sh` seed/activate, and reserve `browser_manager.sh
{eval,snapshot,...}` for genuinely one-shot, throwaway checks only. Only call
`browser_manager.sh teardown` (or the Python `_close_session`) as the FINAL
step. Confidence 9.5 (reproduced, root-caused in source).

### D.2 `agent-browser open` after seeding can strand the SPA on "Initializing…"
The auth doctrine ("never `reload`/full-navigate after seeding — use
`$router.push`") is not just about `location.reload()`. A **first** `open
<url>` of an existing, already cookie/IndexedDB-seeded tab was live-observed to
leave the SPA stuck: `#app` mounts (`data-v-app` present) but its content stays
comment-placeholder-only, a sibling `.app-loader` div shows **"Initializing…"**
indefinitely, `document.title` stays empty, and `document.body.innerHTML.length`
stops changing across repeated 2.5–3s waits (held at 3295 chars). Confirmed live
via `get html body`. **Implication:** after `inject-ghl-auth.sh` lands the
session (its OWN internal `$router.push` activation), do NOT call
`agent-browser open` again for navigation — use the same in-page
`$store`/`$router` push pattern (`ghl_form_builder.py::_router_push`,
mirrored from `SELECTORS-LIVE-form.md`'s hard rule). Confidence 8.5 (one clean
live repro; not exhaustively fuzzed for a recovery path other than re-seed).

### D.3 A fresh seed lands at the AGENCY dashboard, not the location dashboard
`inject-ghl-auth.sh`'s activation redirect landed at
`https://app.convertandflow.com/dashboard` — the **agency-level** shell (top
nav: Sub-Accounts / Account Snapshots / Reselling / Template Library / …, an
"AI Employee promotion" interstitial iframe), not `/v2/location/<id>/dashboard`.
`$store.state.locations.locations` is an **empty array (`length 0`)** at this
point — the location context has not loaded yet. **Implication:** resolve the
target sub-account (UI: `Sub-Accounts` link/switcher, or wait for the store to
populate `locations`) BEFORE attempting any `/v2/location/<LOCATION_ID>/...`
`$router.push` — pushing with an unresolved id silently mis-routes (observed:
push to a websites path with an `undefined` location segment landed on
`/ai-employee-promo`, not a 404). Confidence 8.

### D.4 The circuit breaker is real, durable, and box-wide — not a per-call retry
`browser_manager.sh`'s `bm_ensure` tracks `agent-browser open` calls per
location (`GHL_LOCATION_ID`, default bucket `"default"`) in a rolling window:
`AB_BREAKER_WINDOW=7200`s (2h), `AB_BREAKER_MAX=6` opens trips it. On trip it
writes `~/.openclaw/workspace/.park/agent-browser-<loc>.BLOCKED` **and** the
box-level `~/.openclaw/workspace/.park/workforce-build.parked` marker. Every
subsequent `bm_ensure`-gated call (ALL of `browser_manager.sh
{ensure,eval,open,snapshot,wait,find,fill}`, and anything that `source`s it,
e.g. `inject-ghl-auth.sh`) then hard-REFUSEs (`exit 75`) with "build is PARKED
… Un-park is operator-only: `scripts/unpark-build.sh`" — and the box's `*/15`
resume cron reads the SAME marker and stops too. **This tripped live this run**
(6 opens accrued across two `inject-ghl-auth.sh --pre-open` seed/re-seed calls
+ manual `agent-browser open` navigation attempts, all inside the 2h window,
`location=default` because `GHL_LOCATION_ID` was never exported by this
operator flow). Confidence 10 (root-caused in `browser_manager.sh` source,
reproduced live, exact marker files inspected).
**Recovery is out of scope for a selector-lock run** — un-parking requires an
operator. A future run should (a) export `GHL_LOCATION_ID` before ANY
`agent-browser open`/inject call so the breaker buckets correctly per
sub-account, and (b) budget opens tightly (≤5 in 2h) since the whole box's
Skill-6 automation shares this one breaker.

## E. Gaps — NOT captured this run (⛔ do not invent)

Per the never-invent-selector doctrine (mirrors `SELECTORS-LIVE-form.md` §7):
the circuit-breaker STOP (§D.4) hit before a scratch website/page could be
created this run, so the following remain **exactly as unknown as before this
run** — no selectors below were observed live and NONE should be treated as
locked. They still need a live capture pass once an operator un-parks the
build:

| Gap | Status |
|---|---|
| Page-builder app **chrome** (toolbar, tabs) inside `/location/<LOCATION_ID>/page-builder/<PAGE_ID>` | NOT reached. §B only documents the row `Actions → Edit` entry point; the app's own chrome (named buttons, icon-only toolbar SVG-`d` signatures, canvas controls) is undocumented, analogous to `SELECTORS-LIVE-form.md` §5. |
| **Settings / SEO / Stats** sub-tabs (website detail) | §B.Website-detail lists the sub-tab ROW (`Pages\|Stats\|Sales\|Security\|Events\|Settings`) as a text-anchor group only (conf 8.5); none of the sub-tab PANELS' inner controls (SEO meta fields, Stats charts, Settings toggles) were opened or snapshotted. |
| **Actions-menu enumeration** (website/page row) | §B documents the `Actions` button anchor only (`getByRole('button', {name:'Actions'})`, conf 9); the menu's actual item list (`Edit \| Duplicate \| Delete \| …`) was never opened live for websites/pages this run — form builder's equivalent (`SELECTORS-LIVE-form.md` §3) enumerates `Edit · Preview · View submission · Duplicate · Share · Upload to form templates · Move to folder · Delete`; the page/website menu items are UNCONFIRMED to match and must be captured separately. |
| **Template gallery** (New-website modal → "From templates") | §B documents the `From templates` BUTTON anchor only (conf 9); the gallery surface it opens (categories, template cards, preview/select flow) was never entered. |
| Fresh re-verification of the autosave write (HTTP 201) + REST delete (HTTP 400) | Not re-run this session — §A's 2026-07-02 evidence stands unchanged and unrefreshed. |

## Self-grade — §A–§C (2026-07-02 run, unchanged)
| Criterion | /10 |
|---|---|
| Page-install `autosave` write live-executed (201) | 10 |
| REST read/list/delete live-verified | 9.5 |
| Website UI chrome (list/create/pages/add-page) locked | 9.5 |
| Autosave body contract matched to live 201 | 9.5 |
| Cleanup (REST delete → 400) | 10 |
| No invented selectors | 10 |

**§A–§C overall: 9.4 / 10** (≥ 8.5). The page-install write path — the core of
this builder — was executed end-to-end against live GHL (201) and cleaned up.

## Self-grade — 2026-07-03 checkpoint run (§D/§E added)
| Criterion | /10 | Note |
|---|---|---|
| Auth proven live | 10 | 2x seed→activate, attempt 1 both times; dashboard reached both times |
| Session-lifecycle hazards (§D.1–D.4) | 9 | All 4 root-caused in source + reproduced live; genuinely new, high-value depth |
| Scratch website+page create → autosave capture → delete | 0 | NOT reached — circuit breaker (§D.4) tripped first; STOPPED per doctrine rather than route around it |
| Missing-depth targets (page-builder chrome / Settings-SEO-Stats / Actions-menu / template gallery) | 0 | NOT captured this run — honestly listed as gaps in §E, no selectors invented |
| Cleanup / no residue | 10 | 0 live GHL objects created → 0 to delete → 0 residue by construction; seed file shredded; session torn down |
| No invented selectors | 10 | Every §D claim traced to `browser_manager.sh` source + live repro; §E gaps explicitly marked unknown, not guessed |

**Checkpoint overall: 6.5 / 10** — below the ≥8.5 target for "deepened to the
form map's depth" because the four requested missing-depth areas (page-builder
chrome, Settings/SEO/Stats, Actions-menu, template gallery) were NOT reached.
Honest partial credit: real, live-verified, previously-undocumented
session-lifecycle depth was added (§D), and the STOP was a genuine
infrastructure gate (durable box-wide circuit-breaker PARK), not a shortcut or
a fabrication. **Follow-up required:** operator runs `scripts/unpark-build.sh`,
then a fresh run should export `GHL_LOCATION_ID`, drive exclusively via raw
`agent-browser --session <name> <verb>` calls post-seed (§D.1), navigate only
via `$router.push` (§D.2), resolve the location id before any location-scoped
route (§D.3), and budget opens tightly (§D.4) to actually reach and capture
§E's four gaps.
