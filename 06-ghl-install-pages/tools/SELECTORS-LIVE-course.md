# SELECTORS-LIVE — COURSE builder (`ghl_course_builder.py`)

> ## ✅ PHASE B — LIVE PROOF / LOCKED (2026-07-10)
> A full LIVE run on the operator test location (operator-owned; location id masked — fleet-wide repo)
> created a scratch object with the fixed `ghl_ab_executor.py`, recorded + read back every in-area
> anchor, then cleaned it (course DELETED 0-residue; group DEACTIVATED). The in-area anchors are now
> **status:locked** in `selectors-live-communities-courses.json` (`_phase_b_live_proof`). Real-flow
> corrections vs. the earlier OBSERVED values are captured there. Still capture-pending (documented,
> not-yet-needed): `create_page.privacy_switch` / `create_modal.product_type` / `outline.lesson_body_editor`.
> The CAPTURE-PENDING prose below is retained as historical context.


**Status:** ⚠️ **CAPTURE-PENDING** (NOT yet locked). The live selector-capture run
for courses has **not** been performed — same block as the community doc (operator
box PARKED + 39 concurrent browser processes; SERIAL singleton; un-park is
operator-only; auth itself is healthy). Per **D8 (zero invented selectors)** this doc
records ONLY VERIFIED shared-rail facts + the capture procedure. The builder loads
`selectors-live-communities-courses.json`, where every in-area target is
`status:"capture-pending"` and a REQUIRED capture-pending anchor makes the live build
STOP-and-report (never guesses CSS).

> Convert and Flow = Go High Level = GHL. Courses live in the left-rail **Memberships**
> area (VERIFIED — `references/form-click-map.md`; spec §5.2). 🔒 ids/names redacted.

## Phase A (2026-07-10) — LIVE-READY (same branch as the community doc)

Branch `skill6-community-course-live-ready` (offline code) made the course builder
agent-browser 0.27.0 driveable: (a) every click/fill routes through
`tools/ghl_ab_executor.py` (Playwright anchor → `find …`/native `.click()`); (b) list-scan
idempotency (search box optional, not required); (d) **course cleanup is a TRUE delete** —
see the discovery below.

### Discovery — courses have a full CRUD API (unlike communities)

The Skill-36 Tier-2 (588-tool) community-MCP list ships **`create_course`,
`create_course_category/offer/post/product/importer`, `get_course(s)/...`,
`update_course/...`, and `delete_course`, `delete_course_category`, `delete_course_post`,
`delete_course_offer`, `delete_course_product`** (verified in
`36-ghl-mcp-setup/ghl-mcp-setup-full.md`). So:
- **Cleanup**: courses support true 0-residue delete — the row "More actions" → Delete
  (UI, observed) OR the `delete_course` API. The zero-residue proof is scoped **here**.
- **Create rail (Phase B note)**: per spec §3, if a real create tool exists the router
  should flip primary to it and the browser flow becomes the fallback. GHL-LOOKUP-SOP
  warns Tier-2 community-MCP create/delete tools **may be unverified shells** — so a
  Phase B probe must confirm `create_course`/`delete_course` are real endpoints before
  flipping. `ghl_object_router.py` is a PROTECTED file (not edited in Phase A); this is
  recorded as a Phase B decision, not silently applied.

## 1. VERIFIED shared-rail facts

| Fact | Anchor | Conf | Source |
|---|---|---|---|
| Left-rail **Memberships** entry (StaticText) | `getByText('Memberships')` | 8.0 | form-click-map; spec §5 |
| ZHC naming on the course name | `ensure_zhc_name` → `ZHC <name>` | — | skill convention |
| Search-first idempotency on the list page | pattern (forms/surveys locked) | — | F14 |
| Media is **never** browser-routed — lesson media = ghl_media CDN URL inserted as a link/embed | — | — | spec §5.2 content-law; `ghl_media` |
| Publish gated by `may_publish` (default DRAFT) | plan-level gate | — | funnel publish-guard parity |

## 2. CAPTURE-PENDING targets

| Surface | Target | OBSERVED value / capture recipe |
|---|---|---|
| Route | courses list route | **OBSERVED** `/v2/location/<LOC>/memberships/courses/products-v2` |
| Route | outline-builder route + `COURSE_ID` shape | capture from `location.href` / iframe `.src` |
| List | search box (OPTIONAL — not required, fix b) | **OBSERVED** `getByPlaceholder('Search Courses')` |
| List | Create-Course button | **OBSERVED** `getByRole('button',{name:'Create New'})` |
| List | row Actions → Delete → confirm (**true delete**, fix d) | **OBSERVED** row "More actions" menu → `menuitem 'Delete'` → dialog `Delete` (`exec:native`) |
| Modal | course name input | `getByPlaceholder('Course name')` → dialog `textbox` |
| Modal | product-type picker (ASSUMED present) | `getByText('Course')` — capture whether a type choice is even shown |
| Modal | Create confirm | `getByRole('button',{name:'Create'})` |
| Outline | **Add Module** (GHL may call it "Category"/"Section") | `getByRole('button',{name:'Add Module'})` → `getByText('Add Category'\|'Add Section')` → `+` (SVG path-d) |
| Outline | module title input | `getByPlaceholder('Module title')` → inline row textbox |
| Outline | **Add Lesson** ("Add Post"/"Add Video" in some builds) | `getByRole('button',{name:'Add Lesson'})` → `getByText` variants → `+` in module |
| Outline | lesson title input | `getByPlaceholder('Lesson title')` → inline row textbox |
| Outline | lesson body/RTE editor | RTE/CodeMirror in the lesson panel — set via `.setValue()` in-frame, **never** key-by-key; media inserted as a **CDN link** |

## 3. §capture_procedure (run to LOCK)

1. Confirm the box is FREE and NOT parked (as in the community doc §3.1); else STOP.
2. Token-only seeded session (headless, singleton) to the operator **test**
   sub-account via `ghl_form_builder._seed_and_land`; confirm logged-in.
3. Left-rail **Memberships** → Courses/Products tab → record the list route + search box.
4. Create **one scratch course** `ZHC Capture Probe`; record every create-modal anchor
   + whether a product-type choice appears + the Create button role+name; capture
   `COURSE_ID` + the preview URL shape.
5. In the outline builder record: Add-Module label + title input; Add-Lesson label +
   title input; the lesson body editor kind (RTE vs CodeMirror) and how media inserts
   (link/embed — confirm no upload widget is required); the per-lesson **Save** anchor
   + how a saved lesson appears in the outline snapshot (the read-back for `_verify_outline`).
6. **DELETE** the scratch course (search → Actions → Delete → confirm); snapshot proves
   **0 residue**.
7. Flip each target in `selectors-live-communities-courses.json` → `locked` with its
   real anchor + `conf`; update §2. Self-grade ≥ 8.5.

## Self-grade (of THIS capture-pending scaffold)

| Criterion | /10 |
|---|---|
| Honesty (no invented selectors; block stated) | 10 |
| VERIFIED shared-rail facts + content-law cited | 9 |
| Capture procedure completeness (LOCK-ready, incl. per-lesson read-back) | 9 |
| In-area coverage | n/a — deferred to capture by design |

**Overall (scaffold): honest CAPTURE-PENDING.** Builder (with resumable per-lesson
receipts) + QC gate are complete and proven in dry-run/selftest; the live path
STOP-and-reports at the first capture-pending REQUIRED anchor until LOCKED.
