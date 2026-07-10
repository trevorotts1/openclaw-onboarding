# SELECTORS-LIVE — COURSE builder (`ghl_course_builder.py`)

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

## 1. VERIFIED shared-rail facts

| Fact | Anchor | Conf | Source |
|---|---|---|---|
| Left-rail **Memberships** entry (StaticText) | `getByText('Memberships')` | 8.0 | form-click-map; spec §5 |
| ZHC naming on the course name | `ensure_zhc_name` → `ZHC <name>` | — | skill convention |
| Search-first idempotency on the list page | pattern (forms/surveys locked) | — | F14 |
| Media is **never** browser-routed — lesson media = ghl_media CDN URL inserted as a link/embed | — | — | spec §5.2 content-law; `ghl_media` |
| Publish gated by `may_publish` (default DRAFT) | plan-level gate | — | funnel publish-guard parity |

## 2. CAPTURE-PENDING targets

| Surface | Target | Capture recipe (ordered fallbacks) |
|---|---|---|
| Route | courses list route (Memberships → Courses/Products) | reach via `getByText('Memberships')` + Courses tab; **never** deep-link |
| Route | outline-builder route + `COURSE_ID` shape | capture from `location.href` / iframe `.src` |
| List | search box placeholder | `getByPlaceholder('Search…')` |
| List | Create-Course button **name** (UNKNOWN) | `getByRole('button',{name:/Create\|Add\|New.*(Course\|Product)/})` → `getByText` |
| List | row Actions → Delete → confirm | `Actions` → `menuitem 'Delete'` → dialog `Delete` |
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
