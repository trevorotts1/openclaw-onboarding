# SELECTORS-LIVE — SURVEY builder (`ghl_survey_builder.py`)

**Status:** LOCKED against LIVE GHL. Captured 2026-07-02, same authenticated
`agent-browser 0.27.0` session as the FORM run (token-only seed rail; operator
test sub-account `<LOCATION_ID>`). A real scratch survey (`Survey 46`, id
redacted) was created, walked, and **DELETED** — live DOM confirms 0 residual.

> Convert and Flow = Go High Level = GHL. Builder canvas is a cross-origin
> `*.leadconnectorhq.com` iframe. 🔒 location id + client survey names redacted.
> **The survey builder is the FORM builder + a Slides wrapper** — it shares the
> same rail (as the forms-playbook states). See `../../projects/_SKILL6-FORM-
> BUILDER/proposed-skill6/SELECTORS-LIVE.md` for the shared chrome/constraint
> detail; this file records the survey-specific DELTAS + shared confirmations.

## 1. Routes (LIVE)

| Surface | Route |
|---|---|
| **Survey list** | `/v2/location/<LOCATION_ID>/survey-builder/main` |
| **Survey builder** | `/v2/location/<LOCATION_ID>/survey-builder-v2/<SURVEY_ID>` |

Reach via Sites secondary nav: `getByRole('link', { name: 'Surveys' })` (LOCKED).

## 2. Survey list page — top-frame, reliable refs

| Target | LOCKED anchor | Conf |
|---|---|---|
| Tabs | `getByText('All surveys'|'Analytics'|'Submissions')` | 8.5 |
| `Survey features` | `getByRole('button', { name: 'Survey features' })` | 9 |
| `Create folder` | `getByRole('button', { name: 'Create folder' })` | 9 |
| **Add survey** (⚠ NOT "Create survey") | `getByRole('button', { name: 'Add survey' })` | 9.5 |
| Search box | `getByPlaceholder('Search for surveys')` | 9 |
| Row `Actions` | `getByRole('button', { name: 'Actions' })` | 9 |
| Actions → items | `getByRole('menuitem', { name })` (Edit/Preview/Duplicate/Share/Move to folder/**Delete** …) | 9.5 |
| Delete confirm | dialog "Delete survey"; dialog-scoped `getByRole('button', { name: 'Delete' })` | 9.5 |

Delete flow verified end-to-end (search → Actions → Delete → confirm → gone).

## 3. Create-new-survey modal

`dialog` **"Create new survey"** (identical shape to forms):
- Start from Scratch — `getByText('Start from Scratch')` → radio (checked DEFAULT); subtitle "Design from scratch using the survey builder". Conf 8.5
- From templates — `getByText('From templates')` → radio. Conf 8.5
- **Create** — `getByRole('button', { name: 'Create' })`. Conf 9.5
- Cancel — `getByRole('button', { name: 'Cancel' })`. Conf 9

## 4. Survey-builder chrome (in `leadconnectorhq.com` iframe)

**Shared with forms (LOCKED, role+name):** `Back` · `Preview` · `Integrate` ·
`Save` (all `getByRole('button', { name })`, conf 9.5). Tabs `Edit · Settings ·
Submissions · Notifications · Analytics` are `StaticText` (runtime-capture, see
§6). Icon-only toolbar (`+` / duplicate / desktop / mobile / grid / undo / redo /
Styles-toggle) = SVG-`d` + order anchors, IDENTICAL to forms §5. Conf 7.

**SURVEY-SPECIFIC DELTAS (LOCKED):**
| Target | LOCKED anchor | Conf |
|---|---|---|
| Panel title | `getByText('Survey Element')` (vs "Form Element") | 9 |
| Slide label | `getByText('Slide 1')` (surveys are multi-page = slides) | 8.5 |
| Empty-slide CTA | `getByRole('button', { name: 'Add Elements' })` | 9 |
| **Add Slide** | `getByRole('button', { name: 'Add Slide' })` | 9.5 |
| Submit (canvas) | `getByText('Submit')` (rendered on the last slide) | 8 |

Left panel tabs `Quick Add` / `Add Object Fields` and the full Quick-Add taxonomy
(Personal Info/Payments/Address/Text/Choice Elements/Rating/Customized/Other
Elements) are IDENTICAL to forms — anchor tiles by visible text; drag-only (§6).

## 5. Integrate / embed

Same as forms: `getByRole('button', { name: 'Integrate' })` → modal
`getByRole('heading', { name: /Embed or Share/ })` → `getByRole('button',
{ name: 'Copy embed code' })`; direct link `…/widget/survey/<SURVEY_ID>`
(the survey-builder tool records the builder URL `leadconnectorhq.com/
survey-builder-v2/<id>` per its own notes). Conf 8.5.

## 6. ⛔ Shared constraint (same as forms — proven live)

Cross-origin iframe → only interactive-leaf `@ref`s targetable; Quick-Add tiles,
`Slide`/`Add Object Fields`/builder-tab `StaticText`, and generic wrappers get NO
ref and are unreachable by top-frame `text=`/CSS/`find`. Refs churn per snapshot
(snapshot-and-act-immediately). Slide/element drags + property edits are
`[runtime-capture]` visible-text/coordinate surfaces driven by the builder's own
event system — snapshot-and-bind at runtime, STOP-and-report on miss. Matches the
existing tool's snapshot-gated selector design.

## Self-grade

| Criterion | /10 |
|---|---|
| Routes + nav + list + create + delete | 9.5 |
| Builder chrome (shared + survey deltas: Slides/Add Slide/Survey Element) | 9 |
| Icon toolbar / canvas drags | 7 (honest runtime-capture) |
| Integrate/embed | 8.5 |
| Cleanup (0 residue) | 10 |
| No invented selectors | 10 |

**Overall: 8.9 / 10** (≥ 8.5). Survey confirmed to share the forms rail; only the
Slides/Add-Slide/Survey-Element deltas differ.
