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

## How B1 uses these (reconciled 2026-07 — U23/B-U9 golden/SKILL.md drift closure)

**`new_page_blob()` does NOT load these files at build time.** It is a **pure,
self-contained** function (`tools/ghl_rest_canvas.py`, see the `_FLAT_*`
constants and the function's own docstring: "ASSEMBLED FROM THE INLINED
`_FLAT_*` / `_CC_*` constants (NOT loaded from a golden file — `_load_golden`
is a separate function...)") — no file I/O, no `references/golden/` read, on
every build. This is the SAME statement `SKILL.md`'s Phase-5 section makes
("pure, self-contained function... does NOT load from `references/golden/`
at build time") — this file previously said the opposite ("loads
`funnel-optin.page-data.json` as the structural template"), which was STALE
and is corrected here so the two docs agree.

What these files actually ARE, and how they're actually used:
- **Provenance record.** The `_FLAT_THEME_COLORS` / `_FLAT_PAGE_STYLES` /
  `_FLAT_SECTION_*` constants `new_page_blob()` assembles from were
  originally EXTRACTED from these exact live-captured blobs (see "CRITICAL:
  Where colors lives" above) — this directory is the audit trail proving
  those inlined constants trace back to a real, render-verified GoHighLevel
  page, not an invented shape.
- **`tools/ghl_rest_canvas.py::_load_golden(surface)`** is a separate,
  independent helper that CAN load either file from disk on demand (e.g. for
  a future re-capture/regen or comparison tool) — it exists in the module but
  is not called by `new_page_blob()` or anywhere else in the production build
  path today.
- **Re-capture reference.** If the live GoHighLevel page-data shape ever
  changes, this directory (plus the 5-step capture procedure `_load_golden`'s
  own error message points to) is where a fresh golden gets captured and
  the `_FLAT_*` constants get re-derived from it.

## Render verification protocol

A golden is only trusted if:
1. `GET /preview/<page_id>` returns HTTP 200
2. The marker string appears in the rendered body (not just in stored bytes)
3. No `Cannot read properties of undefined` in the rendered body

All goldens in this directory have passed all three checks (see `PROVENANCE.json`).
A golden that has not passed render verification is not golden and must not be committed.
