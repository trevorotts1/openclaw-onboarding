# SOP -- Branded, Content-Rich Workbook (regular + fillable PDF)  [REPLACES Feature L2-D]

**Cluster:** Presentations — additional deliverable (Gauntlet Loop 2, Feature B, WORKBOOK REDESIGN 2026-08-07).
**Phase:** `P8.25-WORKBOOK` (order 8.25 — after the presenter guide, before GHL upload).
**Owning role:** `pptx-assembly-specialist` (this role already owns reportlab PDF deliverables).
**Executor:** `scripts/workbook_builder.py` (rewritten) + `scripts/workbook_mapper.py` (new).
**Prompt template:** `scripts/WORKBOOK-PAGE-PROMPT-TEMPLATE.md` (rewritten — content-in-image).
**Research:** `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-PDF-RESEARCH.md` (its §4.2 "background only"
conclusion is the piece this SOP supersedes) + `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-REDESIGN-PLAN.md`.

---

## 0. THE DELIVERABLE

A workbook is a **beautifully designed, content-rich companion** to the deck — never a blank
wireframe. The page's real content (headline, bullets, questions, quote, quiz, contact) is
**DESIGNED INTO the image** by kie.ai **gpt-image-2** (or the client's routed Agnes tier),
exactly as the deck's content lives inside its slide images. The AcroForm overlay adds only the
empty write-in zones (answer lines, checkboxes, blanks, commitment panel) on top.

**TWO PDFs ship, always:**
1. **Regular PDF** — `{deck_slug}-WORKBOOK.pdf`: every page image full-bleed on US Letter, **no
   AcroForm fields**. The share/print version; reads as a finished book because the content is
   baked into the pages.
2. **Fillable PDF** — `{deck_slug}-WORKBOOK-FILLABLE.pdf`: the SAME pages with the per-page
   AcroForm fields overlaid from the field manifest. The hand-back version the audience types into.

**A background-only or content-empty page is a FAILURE, not a build.** The wireframe regression
is structurally impossible — the process gate in §5 rejects the old directive and OCR-verifies
every page's content before the phase attests.

## 1. WHEN IT RUNS

`P8.25-WORKBOOK` runs after `P8.2-GUIDE` (order 8.25) and before `P9.2-GHL-UPLOAD` (order 8.9).
It consumes the deck-pipeline sources (all already produced; nothing new to author):

| Source | Path (run dir) | What it contributes |
|---|---|---|
| Deck copy ledger | `working/copy/sp_structure.json` (signature) **or** `working/copy/slides.json` (general) | per-slide title/body/tags/phase/label/hook/case_study |
| Copy ledger (slides_copy) | `working/copy/slides_copy.md` | HEADLINE / EMPHASIS / SUBHEAD / SUPPORTING / PRESENTER NOTE / ARC / PROOF USED |
| Arc allocation | `working/copy/arc_allocation.json` | per-slide arc band (Avatar / Story / Teaching / Pitch) |
| Spoken speech | `working/deliverables/PRESENTERS-SPEECH.md` | the verbatim quotes + follow-along prompts source |
| Speech spec | `working/deliverables/speech_spec.json` | deck_title, hook, tone, owner/company name, word budgets |
| Intake | `working/copy/intake.json` | client_name, offer_name, transformation_promise, audience, cta_action, final_price, brand.palette, logo_image_path |
| Typography system | `working/typography/type_layout_system.md` | locked weight ladder, font family |
| Design brief | `working/research/design-brief-*.md` | locked brand palette hexes, art direction |
| Brand ledger | `working/brand/casting_ledger.json` | representation_mix (people / no people) |
| Render record | `working/checkpoints/process_manifest.json` (P4-RENDER resultUrls) | harmony reference URLs for I2I |
| Client logo | intake `brand.logo_image_path` / brand working dir | the real logo image for `input_urls` (I2I only — never T2I a logo) |

It produces:
- `working/deliverables/{deck_slug}-WORKBOOK.pdf` — regular (share/print) workbook
- `working/deliverables/{deck_slug}-WORKBOOK-FILLABLE.pdf` — fillable workbook
- `working/checkpoints/workbook.json` — the build+verify(+upload) record (both PDFs, content gate, GHL urls)

## 2. THE PIPELINE (six steps)

1. **MAP** (`workbook_mapper.py`, new) — deterministically build `workbook.json` from the deck
   ledgers (§1): the page list (page-type taxonomy: Cover, Roadmap, Avatar, Story, one Teaching
   page per step/rule, Quotes, Questions, Quiz, Action Plan, Contact), each page's verbatim
   `content_strings[]`, and each page's `fields[]` field manifest in the design image's pixel
   space (2016x2688 for 3:4 @ 2K). The mapper is a **pure function of the sources** — it never
   paraphrases and never invents content. Every string placed on a page is pulled verbatim from a
   source file. This is what makes the content gate in §3/§5 enforceable.
2. **PROMPT** (per page) — fill the `WORKBOOK-PAGE-PROMPT-TEMPLATE.md` content-in-image skeleton
   with that page's real content + the brand palette + the logo reference. The prompt MUST contain
   every `content_string` verbatim (mirrors `build_deck.py`'s AF-P-VERBATIM discipline).
3. **DESIGN** (kie gpt-image-2, two-phase harmony-first) — page 1 is T2I (the brand-template
   page); every later page is I2I referencing page-1 + the real client logo + the deck render
   record URLs in `input_urls` (max 16). Prompts are **9,000-18,000 stripped chars**
   (the Presentations rich-prompt gate, NOT the lax 5,000-19,000 research band) and are
   **content-bearing**: the page's real text is baked into the image, never left out.
   Submit all tasks first (20/10s token bucket), then poll + download each.
4. **ASSEMBLE-REGULAR** (reportlab) — every PNG drawn full-bleed (center-crop-to-fill) onto US
   Letter (612x792 pt), **NO AcroForm fields** -> `{deck_slug}-WORKBOOK.pdf`.
5. **ASSEMBLE-FILLABLE** (reportlab) — the SAME PNGs with the AcroForm fields overlaid from the
   field manifest -> `{deck_slug}-WORKBOOK-FILLABLE.pdf`. **CRITICAL:**
   `c.acroForm.extras["NeedAppearances"] = "true"` — the STRING literal, NOT Python `True` (a
   Python bool serializes as `True` and corrupts the PDF).
6. **VERIFY + UPLOAD** — pypdf verifies BOTH outputs (§3), including the OCR content gate; then
   upload BOTH to GHL via the shared `ghl_media` REST path
   (`ghl_media.upload_media(..., require_png=False)`).

## 3. VERIFICATION (pypdf + OCR content gate — the process gate's teeth)

`verify_pdf` runs on BOTH outputs and asserts the **dual contract**:

- `verify_regular(out_regular, expected_pages)`: page count == manifest page count; pypdf reads
  back real pages (bytes > threshold, NOT a flat fill).
- `verify_fillable(out_fillable, expected_pages, expected_fields)`: pages == manifest count;
  every manifest field present; `/AcroForm/NeedAppearances == true` (string gotcha held);
  read-back field TYPES (/Tx, /Btn, /Ch).

**Content gate (new, the anti-wireframe teeth):**

```
verify_content(manifest, out_regular):
  for each page:
    assert page.content_strings[] non-empty            # the mapper MUST attach content
    render the page region to pixels (PyMuPDF get_pixmap or pdftoppm)
    OCR-read the page and assert EVERY content_string present (whitespace-normalised)
      → AF-WORKBOOK-EMPTY: any page whose OCR finds < 100% of its content_strings FAILS
  assert page.content_strings[] were present in the page's prompt (prompt-side check, §5)
```

Because the content is baked into the image, OCR readback (the department's existing
`prompt_gate.ocr_readback`) proves the content survived the render — a bare wireframe cannot pass
(it has zero content strings to find). This is the same proof `build_deck.py` runs on every slide
(AF-OCR-READBACK / AF-P-VERBATIM).

## 4. FIELD MANIFEST

Each page in the workbook manifest declares its AcroForm fields in the design image's pixel space
(2016x2688 for 3:4 @ 2K). Assembly maps px -> PDF points (scale + y-flip from the top-down image
coords to the bottom-up PDF coordinate system). Supported field types: `text`, `textarea`
(`multiline`), `checkbox`, `choice`/`listbox` (options), and `radio` (quiz options). The design
reserves an empty, quiet zone for each field so the widget lands on a clean write-in area — the
current template's zone system, kept, but now *under* the content that is baked into the image.

**reportlab 4.4.10 gotcha:** `choice()` raises `UnboundLocalError` when the field has an empty
value — always pass a non-empty default (the first option) so the option list lands.

## 5. THE PROCESS GATE (fail-closed; the wireframe cannot regress)

Four mandated lockstep steps, exactly the SOP-SLIDE-06-EXTENSION-AND-SYNC wiring:

| # | Step | File | Enforced by |
|---|---|---|---|
| i | Manifest: add `autofails[]` rows for the three AF codes + bump `manifest_version` | `PIPELINE-MANIFEST.json` | sync_check A4/B2 |
| ii | Executor gate: the prompt-side content gate (`_assert_content_in_prompt`) + the OCR content gate (`verify_content`) | `workbook_builder.py` (the declared executor's own gate) | sync_check A1/A2/A3/B1 |
| iii | Ruleset: the three Section-5 rows below | MASTER ruleset | sync_check A4/B2 |
| iv | Tests: present/absent + content-gate cases | `test_workbook_builder.py` / `test_preflight.py` | the suite must stay green |

**The new AF codes (Section-5 rows):**

| Code | Stage | Level | Trigger | Detection |
|---|---|---|---|---|
| **AF-WORKBOOK-PROMPT-NO-CONTENT** | P8.25-WORKBOOK prompt | DECK | a workbook page prompt carries the wireframe directive ("BACKGROUND ONLY", "NO text", "NO labels", "NO words") OR is missing any of the page's `content_strings[]` verbatim | `workbook_mapper._assert_content_in_prompt(page, prompt)`: rejects the prompt pre-submit (fail-closed — no wireframe page is ever rendered). The wireframe-language scan is a literal ban; the verbatim check mirrors build_deck's AF-P-VERBATIM. |
| **AF-WORKBOOK-EMPTY** | P8.25-WORKBOOK postflight | DECK | a rendered page's OCR read-back finds < 100% of that page's `content_strings[]` (a bare wireframe has zero content to find) | `workbook_builder.verify_content` (§3): render each page to pixels and OCR-read back every content string; any page under 100% FAILS and the phase does not attest. |
| **AF-WORKBOOK-BOTH** | P8.25-WORKBOOK postflight | DECK | either the regular or the fillable PDF is missing / zero-byte / fails pypdf read-back (pages + fields + NeedAppearances) | `phase_verifiers._verify_workbook` extended: both `*-WORKBOOK.pdf` AND `*-WORKBOOK-FILLABLE.pdf` must exist, be non-trivially sized, and pypdf must read the expected pages/fields; the fillable must read `/NeedAppearances true`. |

**The fail-closed property:** step (ii)'s prompt gate runs **before any paid render** — a wireframe
prompt is refused and the build stops, so the "background-only" regression cannot even spend
credits. Step iii's postflight OCR gate runs **after** render — it catches any page the model
rendered blank or garbled. Both must pass for the phase to attest. A wireframe page fails BOTH
gates (it has no content strings), which is exactly the invariant that makes the old failure mode
structurally impossible.

## 6. RULES

- **Model sovereignty:** gpt-image-2 ONLY (or the client's routed Agnes tier inside a Presentations
  run) — never substitute another model inside a Presentations run.
- **CONTENT-IN-IMAGE is mandatory.** The wireframe language ("BACKGROUND ONLY", "NO text",
  "NO labels") is **BANNED** in page prompts (AF-WORKBOOK-PROMPT-NO-CONTENT).
- Content is **VERBATIM from the deck ledgers** — never paraphrased, never invented
  (AF-WORKBOOK-EMPTY enforces the read-back).
- Logo rides `input_urls` (I2I) — **never T2I a logo**.
- **Never print a credential value.** `KIE_API_KEY` is read like `kie_generate.py` (env first,
  then the client's standard secrets stores).
- **No browser / no UI automation for GHL** — REST media path only.
- **BOTH deliverables must exist + verify before the phase attests** (AF-WORKBOOK-BOTH).
- **Operator credits for tests; never a client.** A sample workbook is built on the operator
  account and saved to `~/Downloads`. No client messaging.
- The workbook does NOT go through `build_deck.py` and is NOT a deck render. It does NOT call the
  dead `/api/v1/image/gpt-image` endpoint.

## 7. VERIFY (operator smoke on a sample)

```bash
python3 scripts/workbook_builder.py --run-dir <sample-run-dir> \
    --out ~/Downloads/WORKBOOK-SAMPLE.pdf --no-upload
```

Expect: BOTH PDFs exist; the OCR content gate PASSes on every page (100% of content_strings read
back); pypdf reads back the fillable with `N` pages, `M` fields, `/NeedAppearances true`. The
offline self-test (`--selftest`) stays offline-deterministic.

## 8. HANDBACK

After a successful build+verify(+upload), the run's `working/checkpoints/workbook.json` records:
`workbook_pdf` + `workbook_pdf_bytes` (regular), `workbook_fillable_pdf` + `workbook_fillable_bytes`
(fillable), `workbook_pages`, `workbook_fields`, `workbook_field_names`, `need_appearances`,
per-page OCR content-gate results, and (when uploaded) both `workbook_ghl_url` /
`workbook_ghl_file_id` + `workbook_fillable_ghl_url` / `workbook_fillable_ghl_file_id`.
