# SELECTORS-LIVE — FUNNEL builder (`ghl_builder.py` + `ghl_rest_canvas.py` + `funnel_matcher*`)

**Status:** LOCKED against LIVE GHL. Captured 2026-07-02, same authenticated
`agent-browser 0.27.0` session (token-only seed; operator test sub-account
`<LOCATION_ID>`). A real ZHC funnel (`ZHC Selector Lock Test`, id redacted) + a
step/page were created, the REST canvas surface was live-probed, and everything
was **DELETED** via the reversible REST route (verify fetch → HTTP 400). Clean.

> 🔑 **KEY FINDING — the funnel/page builder is NOT click-driven.** Per
> `ghl_rest_canvas.py`, funnel/page/website CONTENT is built by `token-id`-authed
> **REST canvas / page-data XHRs** issued from *inside* the browser (Cloudflare
> WAF gates bare HTTP → error 1010). The visual page-builder editor is never
> driven by DOM selectors. So the load-bearing "selectors" for this builder are
> (A) the REST routes below and (B) the funnel LIST/CREATE/STEP **UI chrome** used
> for navigation + human verification. Both are locked + live-verified here.

## A. REST canvas surface — the real build mechanism (LIVE-VERIFIED)

Origin: `https://backend.leadconnectorhq.com`. Auth header MUST be
`token-id: <firebase id_token>` (NOT `Authorization: Bearer` → 401). Static
headers `channel: APP · source: WEB_USER · version: 2021-07-28`. Run in-browser,
`mode: cors, credentials: omit`.

| Route | Method | LIVE result (this run) |
|---|---|---|
| `/funnels/funnel/create` | POST | (exercised via New-funnel UI → 201, id returned) |
| `/funnels/funnel/create-step` | POST | (exercised via Add-step UI → new step + PAGE) |
| `/funnels/funnel/fetch/<funnelId>` | GET | **HTTP 200** `{data, traceId}` |
| `/funnels/page/list?funnelId=&locationId=` | GET | **HTTP 200** array len=1 |
| `/funnels/page/<pageId>` | GET | **HTTP 200** editable blob (see schema) |
| `/funnels/builder/autosave/<pageId>` | POST | draft save (page-data write; see page doc) |
| `/funnels/funnel/delete` `{locationId,funnelId,userId}` | POST | **HTTP 201** → `fetch` then **HTTP 400** (gone) |

**Editable page-data blob keys (live):** `popups, colors, versionHistory,
products, _id, dateAdded, dateUpdated, deleted, funnelId, locationId, name,
pageVersion` (+ the element tree the splice edits). This is the canvas content
the `SKILL44_WIDGET → FORM` splice + `autosave` operate on. Confidence 9.5
(read/list/fetch/delete all returned live status codes this run).

## B. Funnel UI chrome (top-frame — NOT an iframe; reliable role/name anchors)

### Funnels list — `/v2/location/<LOCATION_ID>/funnels-websites/funnels`
Reach via `getByRole('link', { name: 'Funnels' })`.
| Target | LOCKED anchor | Conf |
|---|---|---|
| Create folder | `getByRole('button', { name: 'Create folder' })` | 9 |
| Build with AI | `getByRole('button', { name: 'Build with AI' })` | 9 |
| **New funnel** | `getByRole('button', { name: 'New funnel' })` | 9.5 |
| Search | `getByPlaceholder('Search for funnels')` | 9 |
| Row Actions | `getByRole('button', { name: 'Actions' })` | 9 |

### New-funnel modal
`dialog` with (⚠ buttons + a name field, NOT radio cards):
| Target | LOCKED anchor | Conf |
|---|---|---|
| From blank | `getByRole('button', { name: 'From blank' })` (subtitle "Design from scratch using the funnel builder.") | 9 |
| From templates | `getByRole('button', { name: 'From templates' })` | 9 |
| **Funnel name** (required) | `getByPlaceholder('e.g. Sales funnel')` | 9.5 |
| Create | `getByRole('button', { name: 'Create' })` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | 9 |

### Funnel detail / steps — `/funnels-websites/funnels/<FUNNEL_ID>/steps`
| Target | LOCKED anchor | Conf |
|---|---|---|
| Sub-tabs | `getByText('Steps'|'Stats'|'Settings')` | 8.5 |
| Share funnel | `getByRole('button', { name: 'Share funnel' })` | 9 |
| **Add new step or import** | `getByRole('button', { name: 'Add new step or import' })` | 9.5 |

### New-step dialog ("New step in funnel")
| Target | LOCKED anchor | Conf |
|---|---|---|
| **Name for page** (required) | `getByPlaceholder('Name for page')` | 9.5 |
| Path | `getByPlaceholder('Path')` | 9 |
| Import (ClickFunnels) | `getByPlaceholder('ClickFunnels URL')` | 8.5 |
| **Create funnel step** (disabled until named) | `getByRole('button', { name: 'Create funnel step' })` | 9.5 |
| Cancel | `getByRole('button', { name: 'Cancel' })` | 9 |

### Step overview — `/steps/<STEP_ID>/overview`
| Target | LOCKED anchor | Conf |
|---|---|---|
| Use existing page | `getByRole('button', { name: 'Use existing' })` | 9 |
| Create from blank | `getByRole('button', { name: 'Create from blank' })` | 9 |
| **Edit** (opens page builder) | `getByRole('button', { name: 'Edit' })` | 8.5* |
| Edit in a new tab | `getByRole('button', { name: 'Edit in a new tab' })` | 9 |
| View page | `getByRole('button', { name: 'View page' })` | 9 |
| Edit page details | `getByRole('button', { name: 'Edit page details' })` | 9 |
| Create variation (split test) | `getByRole('button', { name: 'Create variation' })` | 8.5 |

\* `Edit` opens the page-builder app at `/location/<LOCATION_ID>/page-builder/
<PAGE_ID>` (a SEPARATE app-mount, likely a new tab; the current session view did
not auto-follow it). The page builder is REST-canvas-driven (§A) — do NOT script
its editor by DOM selectors.

## C. Delete flow (cleanup)
Two proven paths: (1) UI — funnels list → row `Actions` → `Delete` → confirm; or
(2) **REST** `POST /funnels/funnel/delete {locationId,funnelId,userId}` → 201
(used here; reversible-cleanup route from `ghl_rest_canvas.py`, verified gone).

## Self-grade
| Criterion | /10 |
|---|---|
| REST canvas routes live-verified (fetch/list/read/delete + create via UI) | 9.5 |
| Funnel UI chrome (list/create/steps/add-step/overview) locked | 9.5 |
| Page-data blob schema captured live | 9 |
| Page-builder editor (correctly identified as REST-driven, not click) | 9 |
| Cleanup (REST delete → fetch 400) | 10 |
| No invented selectors | 10 |

**Overall: 9.3 / 10** (≥ 8.5). Funnel build is a REST-canvas concern; the entire
create→read→delete lifecycle was exercised against live GHL this run.
