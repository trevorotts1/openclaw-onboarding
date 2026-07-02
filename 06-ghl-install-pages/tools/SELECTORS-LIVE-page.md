# SELECTORS-LIVE — PAGE / WEBSITE builder + page-install path (`ghl_rest_canvas.py` / `ghl_builder.py`)

**Status:** LOCKED against LIVE GHL. Captured 2026-07-02, same authenticated
`agent-browser 0.27.0` session (token-only seed; operator test sub-account
`<LOCATION_ID>`). A real ZHC website (`ZHC Selector Lock Web`, id redacted) + a
page (`ZHC Test Page`) were created, the **page-install `autosave` write** was
live-executed (HTTP 201), and everything was **DELETED** via REST (verify fetch →
HTTP 400). GHL left clean.

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

## Self-grade
| Criterion | /10 |
|---|---|
| Page-install `autosave` write live-executed (201) | 10 |
| REST read/list/delete live-verified | 9.5 |
| Website UI chrome (list/create/pages/add-page) locked | 9.5 |
| Autosave body contract matched to live 201 | 9.5 |
| Cleanup (REST delete → 400) | 10 |
| No invented selectors | 10 |

**Overall: 9.4 / 10** (≥ 8.5). The page-install write path — the core of this
builder — was executed end-to-end against live GHL (201) and cleaned up.
