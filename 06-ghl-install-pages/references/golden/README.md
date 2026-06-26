# Golden References — Skill 6 GHL Page Data

These files are the AUTHORITATIVE live-captured page-data blobs from Trevor's BlackCEO LLC
test location (`Mct54Bwi1KlNouGXQcDX`). They were fetched via the GoHighLevel internal
REST API (`GET /funnels/page/<id>?locationId=<loc>`) on 2026-06-26, render-verified
(HTTP 200 + marker in rendered body), and committed as the canonical reference for
`new_page_blob()` in `tools/ghl_rest_canvas.py` (B1 fix).

## Files

| File | What it is |
|---|---|
| `funnel-optin.page-data.json` | Live page-data blob for funnel optin page `0JQUYDGAjSPmdZcCuQDi`. Render-verified HTTP 200 + `MBSS-FUNNEL-OPTIN-v1-20260622-135617` in body. |
| `website-page.page-data.json` | Live page-data blob for website home page `5ZhuqVIP1hNFqEZuHoR0` (type:website funnel). Render-verified HTTP 200 + `MBSS-WEB-HOME-v1-20260622-135617` in body. |
| `PROVENANCE.json` | Full capture metadata: location, funnel id, page id, capture date, render check evidence, and AUTHORITATIVE colors JSON path. |
| `README.md` | This file. |

## CRITICAL: Where colors lives (authoritative)

The GoHighLevel renderer reads colors from `general.general.colors` — an 18-entry array
of `{label, value}` objects:

```json
"general": {
  "general": {
    "colors": [
      {"label": "Transparent", "value": "transparent"},
      {"label": "Primary",     "value": "#37ca37"},
      {"label": "Secondary",   "value": "#188bf6"},
      {"label": "White",       "value": "#ffffff"},
      ...18 total entries...
    ]
  }
}
```

The CSS variables required for the renderer are in `pageStyles` (TOP-LEVEL key in the blob,
NOT `settings.pageStyles` which is empty) — a `:root{}` string that maps every `--primary`,
`--secondary`, etc. variable. Both must be present or the renderer throws
`Cannot read properties of undefined (reading 'colors')`.

`defaultSettings.colors` does NOT exist in any fetched page blob. Do not invent that path.

## How B1 uses these

`tools/ghl_rest_canvas.py` `new_page_blob()` loads `funnel-optin.page-data.json` as the
structural template for funnel pages and `website-page.page-data.json` for website pages.
The content element (`rawCustomCode`) is replaced with the build's actual HTML fragment.
The `general.general.colors`, `pageStyles` (top-level), and
`settings.settings.typography.colors` blocks are carried over unchanged — they are what
makes the page renderable.

## Render verification protocol

A golden is only trusted if:
1. `GET /preview/<page_id>` returns HTTP 200
2. The marker string appears in the rendered body (not just in stored bytes)
3. No `Cannot read properties of undefined` in the rendered body

All goldens in this directory have passed all three checks (see `PROVENANCE.json`).
A golden that has not passed render verification is not golden and must not be committed.
