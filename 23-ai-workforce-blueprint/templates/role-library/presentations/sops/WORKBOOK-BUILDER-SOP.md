# SOP -- Fillable PDF Workbook (Feature L2-D)

**Cluster:** Presentations — additional deliverable (Gauntlet Loop 2, Feature B).
**Phase:** `P8.25-WORKBOOK` (order 8.25 — after the presenter guide, before GHL upload).
**Owning role:** `pptx-assembly-specialist` (this role already owns reportlab PDF deliverables).
**Executor:** `scripts/workbook_builder.py`.
**Prompt template:** `scripts/WORKBOOK-PAGE-PROMPT-TEMPLATE.md`.
**Research:** `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-PDF-RESEARCH.md`.

---

## 0. WHAT THIS DELIVERABLE IS

Every presentation gets a **branded, fillable PDF workbook** — a second client deliverable
alongside the deck. Each page background is image-designed via kie.ai **gpt-image-2**
(`gpt-image-2-text-to-image` for the brand-template page, `gpt-image-2-image-to-image` for
every later page), then the pages are assembled into a US-Letter fillable PDF with real
**AcroForm fields** overlaid by reportlab.

The workbook is an ADDITIONAL deliverable. It does NOT replace any of the nine required
build deliverables; it rides the same run dir and is uploaded to GHL through the shared
media path.

## 1. WHEN IT RUNS

`P8.25-WORKBOOK` runs after `P8.2-GUIDE` (order 8.25) and before `P9.2-GHL-UPLOAD`
(order 8.9). It consumes:
- `working/copy/intake.json` — brand palette + client name + deck slug
- `renders/slide-01.png` — the deck's brand template render (harmony reference)
- `working/checkpoints/process_manifest.json` — P4-RENDER render record (resultUrls)

It produces:
- `working/deliverables/{deck_slug}-WORKBOOK.pdf` — the fillable workbook
- `working/checkpoints/workbook.json` — the build+verify(+upload) record

## 2. THE PIPELINE (five steps inside the executor)

1. **Design (kie.ai gpt-image-2, two-phase harmony-first):**
   - Phase A renders the brand-template page (`t2i`, 3:4, 2K). Its resultUrl becomes the
     harmony reference.
   - Phase B renders every later page via `i2i` with that reference (+ the deck's render
     record URLs) in `input_urls`. Both phases submit ALL tasks first (20/10s token
     bucket), then poll + download each. Prompts are 5,000-19,000 chars (target >=9,000)
     and **background-only** — no text baked (text garble risk).
2. **Assemble (reportlab):** each PNG is drawn full-bleed (center-crop-to-fill) onto a US
   Letter page (612x792 pt), and AcroForm fields (textfields/checkboxes/choices) are
   overlaid from the per-page field manifest. **CRITICAL:** `c.acroForm.extras["NeedAppearances"]
   = "true"` — the STRING literal, NOT Python `True` (a Python bool serializes as `True`
   and corrupts the PDF).
3. **Verify (pypdf):** read back the page count + field count + `/NeedAppearances true`.
   Assembly does NOT pass unless pypdf confirms a real fillable form.
4. **Upload (GHL):** the workbook PDF is posted via the shared `ghl_media` path
   (`ghl_media.upload_media(..., require_png=False)`) — the workbook is not named
   `*-FINAL.pdf` and is not a deck artifact, so it flows through the non-deck media path.
5. **Record:** `working/checkpoints/workbook.json` is written with the build+verify(+upload)
   record.

## 3. FIELD MANIFEST

Each page in the workbook manifest declares its AcroForm fields in the design image's pixel
space (2016x2688 for 3:4 @ 2K). Assembly maps px -> PDF points (scale + y-flip from the
top-down image coords to the bottom-up PDF coord system). Supported field types: `text`,
`textarea` (`multiline`), `checkbox`, `choice`/`listbox` (options).

**reportlab 4.4.10 gotcha:** `choice()` raises `UnboundLocalError` when the field has an
empty value — always pass a non-empty default (the first option) so the option list lands.

## 4. RULES

- **Model sovereignty:** gpt-image-2 ONLY. Never substitute another model inside a
  Presentations run.
- **Never print a credential value.** `KIE_API_KEY` is read like `kie_generate.py`
  (env first, then the client's standard secrets stores).
- **No browser / no UI automation for GHL** — only the REST media path.
- **Prompts are background-only.** The form labels/content are real AcroForm widgets, never
  baked into the image.
- **Operator credits for tests; never a client.** A sample workbook is built on the operator
  account and saved to `~/Downloads`. No client messaging.
- The workbook does NOT go through `build_deck.py` and is NOT a deck render. It does NOT
  call the dead `/api/v1/image/gpt-image` endpoint.

## 5. VERIFY (operator smoke on a sample)

```bash
python3 scripts/workbook_builder.py --run-dir <sample-run-dir> \
    --out ~/Downloads/WORKBOOK-SAMPLE.pdf --no-upload
```

Expect: pypdf reads back the workbook with `N` pages, `M` fields, `/NeedAppearances true`.
The offline self-test (`--selftest`) exercises prompt band + rich gate + assembly +
read-back with no network spend.

## 6. HANDBACK

After a successful build+verify(+upload), the run's `working/checkpoints/workbook.json`
records: `workbook_pdf`, `workbook_pdf_bytes`, `workbook_pages`, `workbook_fields`,
`workbook_field_names`, `need_appearances`, `status`, and (when uploaded)
`workbook_ghl_url` / `workbook_ghl_file_id`.
