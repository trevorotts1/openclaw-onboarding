# SOPs Mirror -- PPTX Assembly Specialist

**Source:** presentations/pptx-assembly-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- PPTX Build with Embedded Speaker Notes

**When to run:** Phase 6 -- after delivery_verified: true in media_library.json.

**Inputs:**
- working/media-library/slide-NN.png (all slides, zero-padded, in order)
- working/copy/presenter_notes.json
- working/copy/mission_prd.json (slide_count_final, deck_slug)

**NATIVE TEXT/ELEMENT OVERLAYS ARE ELIMINATED (Decision 5C — AF-OVERLAY-DELIVERED).**

This role NEVER composites native PPTX text. The legacy `pptx_text_overlays.json` native-text-overlay subsystem (the overlays dict read, the `add_textbox` loop, strike support, the typography-safe assembler spec, the gradient scrim) is REMOVED. Every slide ships as a SINGLE composed gpt-image-2 image with its text baked in by the model; the only legitimate PPTX text part is the off-slide speaker-notes pane.

- If a slide's verbatim text garbles, misspells, or duplicates at image QC, the remedy is NEVER a native overlay. The Slide Image Creator RE-PROMPTS and RE-SEEDS the slide (new prompt, new seed) and re-renders. If the garble PERSISTS after the re-prompt/re-seed loop, it ESCALATES TO A HUMAN — it is never papered over with a native text box.
- The mere PRESENCE of a `pptx_text_overlays.json` file in the run dir at assembly is a hard auto-fail (AF-OVERLAY-DELIVERED). If you find one, HALT, delete it, and route the affected slide back to the re-prompt/re-seed loop.
- A delivered PPTX whose any slide carries a native (non-notes) on-slide text run instead of a composed image is AF-OVERLAY-DELIVERED. `scripts/build_deck.py` enforces this both at preflight (`_chk_no_overlay`) and at the postflight completeness gate.
- The LOGO is the ONLY exception, and it is NOT native text: when the model cannot bake the locked logo cleanly after two image-to-image attempts, the real logo IMAGE is composited onto the slide PNG via the PIL image-composite path (SOP-IMG-05) BEFORE assembly — it is baked into the image, not added as a native PPTX element.

**Steps:**
1. Verify slide count: `ls working/media-library/*.png | wc -l` must equal slide_count_final from mission_prd.json. If it does not, halt and notify the Director.
2. Verify presenter_notes.json has exactly slide_count_final entries. If fewer entries than slides: flag missing notes to the Director. Do not assemble with missing notes.
3. **AF-OVERLAY-DELIVERED guard.** Confirm there is NO `pptx_text_overlays.json` anywhere in the run dir (working/copy/, working/checkpoints/, or the run root). If one exists, HALT: delete it and route the affected slide(s) back to the Slide Image Creator's re-prompt/re-seed loop (then human escalation if garble persists). Native text overlays are eliminated; assembly composites ONLY the single gpt-image-2 image per slide (plus the off-slide speaker-notes pane and, where required, the PIL-composited logo image baked into the PNG per SOP-IMG-05).
3a. **Workspace discipline (AF-DH1 prevention):** Confirm the assembly script path is `working/scripts/assemble_pptx.py`. All intermediate files (prompts, renders, QC logs, manifests, scripts) MUST remain under `working/`. Output PPTX goes to `output/[DECK_SLUG].pptx` and PDF to `output/[DECK_SLUG].pdf`. The assembly script must NEVER hard-code `BUNDLE_DIR = ~/Downloads/<DECK>` or any client delivery path as its working directory -- that path is owned exclusively by Delivery Concierge SOP 9.0. Verify now; refuse to proceed if any of these conditions are violated.
4. Write the assembly script at working/scripts/assemble_pptx.py:
   ```python
   from pptx import Presentation
   from pptx.util import Inches, Pt
   from pptx.dml.color import RGBColor
   import json, os, glob, re

   # Configuration
   SLIDE_WIDTH_INCHES = 13.333
   SLIDE_HEIGHT_INCHES = 7.5
   MEDIA_DIR = "working/media-library"
   NOTES_FILE = "working/copy/presenter_notes.json"
   OVERLAYS_FILE = "working/copy/pptx_text_overlays.json"  # ELIMINATED — present == AF-OVERLAY-DELIVERED (halt)
   OUTPUT_FILE = "output/[DECK_SLUG].pptx"

   prs = Presentation()
   prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
   prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)

   with open(NOTES_FILE) as f:
       notes = {item["slide_number"]: item["presenter_note"] for item in json.load(f)}

   # AF-OVERLAY-DELIVERED: native text overlays are ELIMINATED. The assembler
   # composites ONLY the single composed gpt-image-2 image per slide (all text is
   # baked into the image by the model) plus the off-slide speaker-notes pane. If a
   # pptx_text_overlays.json exists, HALT (do not read it) — it is an auto-fail.
   if os.path.exists(OVERLAYS_FILE):
       raise SystemExit(
           "AF-OVERLAY-DELIVERED: pptx_text_overlays.json is present. The native-text "
           "overlay path is eliminated (Decision 5C). Delete it and re-prompt/re-seed "
           "the affected slide; escalate to a human if garble persists.")

   blank_layout = prs.slide_layouts[6]  # blank layout

   image_files = sorted(glob.glob(os.path.join(MEDIA_DIR, "slide-*.png")),
                       key=lambda x: int(re.search(r'slide-(\d+)', x).group(1)))

   for idx, img_path in enumerate(image_files):
       slide_number = idx + 1
       slide = prs.slides.add_slide(blank_layout)

       # Full-bleed composed image (the ONLY visual on the slide; all text baked in
       # by gpt-image-2, plus the PIL-composited logo image per SOP-IMG-05 when used).
       pic = slide.shapes.add_picture(img_path, Inches(0), Inches(0),
                                      Inches(SLIDE_WIDTH_INCHES), Inches(SLIDE_HEIGHT_INCHES))

       # Speaker notes (off-slide pane — the ONLY legitimate PPTX text part)
       if slide_number in notes:
           notes_slide = slide.notes_slide
           notes_slide.notes_text_frame.text = notes[slide_number]

   os.makedirs("output", exist_ok=True)
   prs.save(OUTPUT_FILE)
   print(f"Saved: {OUTPUT_FILE}")
   ```
5. Run the assembly script: `python3 working/scripts/assemble_pptx.py`.
6. Verify the output file exists at output/[DECK_SLUG].pptx and is non-empty.
7. Open the PPTX with python-pptx and verify: slide count == slide_count_final, first and last slide images are correct, first slide has a non-empty notes field, AND no slide carries any native on-slide text run (every shape on every slide is a picture; the only text part is the off-slide notes pane). A native on-slide text run is AF-OVERLAY-DELIVERED.
8. Notify the Director that `output/` files are ready (PPTX + PDF). Do NOT copy any file to ~/Downloads or to `delivery/`; Delivery Concierge SOP 9.0 owns final packaging. Touching the delivery directory from this role is an AF-DH1 trigger.

**Outputs:**
- output/[DECK_SLUG].pptx (the assembled deck — image-only slides + off-slide speaker notes; NO native text overlays)
- output/[DECK_SLUG].pdf (the portable-document export, produced in SOP 9.2)

**Hand to:** SOP 9.2 (render to PDF for QC), then after Phase 6 QC passes -- hand to Delivery Concierge (ROLE-13) who runs SOP 9.0 to package the clean client bundle. Do NOT copy output files to Downloads directly.

**Failure mode:** If any slide image file is missing or corrupt: halt. Do not assemble with a gap. Notify the Director: "Assembly blocked: slide-NN.png is missing or corrupt. Media Librarian must re-verify."

Garbled-text remedy (NO native overlay — Decision 5C): if a slide's rendered text garbled or misspelled at Phase 5 image QC, the remedy is the Slide Image Creator's RE-PROMPT / RE-SEED loop (new prompt + new seed, re-render the single composed image), and if the garble PERSISTS, HUMAN ESCALATION. This role NEVER writes or reads a pptx_text_overlays.json and NEVER composites a native text box. If you reach assembly and find a pptx_text_overlays.json present, HALT (AF-OVERLAY-DELIVERED): delete it and route the slide back to the re-prompt/re-seed loop.

**Deterministic-renderer path (`scripts/build_deck.py`) -- automatic per-slide speaker notes:**

When the deck is assembled via the deterministic fleet renderer `scripts/build_deck.py` (the zero-AI-at-runtime path) rather than a hand-written `assemble_pptx.py`, the renderer injects per-slide speaker notes AUTOMATICALLY -- you do NOT hand-build a `presenter_notes.json` for this path. The behavior is:

1. **Auto-discovery (non-fatal).** Before assembling, `build_deck.py` searches, in order, for the presenter speech at: `working/presenter-speech/speech.md`, `working/delivery/PRESENTERS-SPEECH.md`, `working/presenter-speech/PRESENTERS-SPEECH.md`, and finally `PRESENTERS-SPEECH.md` in the bundle directory. The FIRST file found wins.
2. **Phase ordering is tolerated.** The deck render is Phase 4; the presenter speech is a Phase 9 artifact written by the Presenters Speech Writer. So at render time the speech is FREQUENTLY absent. When no speech file is found, the renderer logs a clear "no presenter speech found yet ... rendering WITHOUT per-slide notes (non-fatal)" message and assembles the deck with no notes. **A missing speech NEVER blocks the render.** Per-slide notes are a best-effort enrichment, not a render gate. (The full bundle is still enforced separately by the postflight AF-BUNDLE-COMPLETE gate, which requires the speech artifacts to exist before the run can be reported "done.")
3. **`parse_speech_chunks` -- the two marker forms.** When a speech IS found, `build_deck.parse_speech_chunks(speech_text)` splits it into `{slide_no: spoken_text}`. It recognises BOTH per-slide marker forms, anchored to the start of a line, case-insensitive:
   - a markdown heading: `## Slide 7` (1-3 leading `#`s -- `# Slide 7` / `### Slide 7` all match), and
   - an inline marker: `SLIDE 7` (no heading hashes).
   For each marker, the spoken text is everything from the END of the marker/title line up to the start of the next marker (or end of file), stripped of surrounding whitespace. The marker line itself (including any slide title after the number) is a structural cue and is NOT spoken text -- it is dropped. If the same slide number appears more than once, the LAST occurrence wins.
4. **Injection.** For every rendered slide whose ordinal has a non-empty parsed chunk, the renderer sets `slide.notes_slide.notes_text_frame.text` to that chunk. A slide with no chunk gets no notes part at all (never an empty injection).
5. **Mismatch policy (safe in both directions).** Chunk count and slide count need not match. EXTRA chunks (a slide number in the speech that the deck does not contain) are simply skipped -- they match no slide. Deck slides with NO chunk are left with empty/absent notes. A count mismatch is never an error and never halts assembly.

This path is reconciled by `scripts/sync_check.py`: `parse_speech_chunks` is registered in `PIPELINE-MANIFEST.json` under the `P8-ASSEMBLE` phase `emits.checks`, and `sync_check` fails the lockstep gate (drift A8) if that symbol is renamed or removed from `build_deck.py` without updating the manifest.

**REQUIRED -- PER-SLIDE SPEAKER NOTES IN THE NOTES PANE (the self-coaching .pptx; QC enforcement: AF-EMPTY-NOTES-PANE at closeout).**

The shipped `.pptx` must carry, in each slide's NATIVE NOTES pane, that slide's talking points (mirrored from the presenter speech / Presenter Guide), so the FILE ITSELF is self-coaching when opened in PowerPoint. This is in ADDITION to the Presenter Guide PDF. The mechanic is the `slide.notes_slide.notes_text_frame.text` injection above; this rule mandates the OUTCOME.

- **Phase-ordering note (not a render gate).** Because the presenter speech is a later-phase (Phase 9) artifact, the notes pane is FREQUENTLY empty at the Phase-4 render and that is non-fatal at render time (per the auto-discovery rule above). The notes-pane requirement is enforced at CLOSEOUT, after the speech exists: by final delivery, the re-assembled / finalized `.pptx` must have a non-empty notes pane on every audience-facing content slide.
- **Verify (AF-EMPTY-NOTES-PANE).** At closeout, open the final `.pptx` and confirm every content slide's notes pane is non-empty (read `slide.notes_slide.notes_text_frame.text` per slide; structural/section-divider slides with no spoken line are exempt). A final delivery whose content slides ship with empty notes panes (the speech existed but was never injected) fails AF-EMPTY-NOTES-PANE; re-run the deterministic assembly with the speech present so the notes are injected, then re-verify.

---

### SOP 9.2 -- Export the Deck to Portable-Document Format (System-Wide Delivery Output + Final QC)

**System-wide rule:** EVERY deck the system produces emits a portable-document-format (`.pdf`) export ALONGSIDE the `.pptx`, so a recipient without PowerPoint can open the deck. The portable-document export is a REQUIRED, verified DELIVERY output of every assembly run, not merely a transient QC artifact. The same export ships to the client and feeds the per-page PNGs the QC Specialist reads. This applies to ALL decks fleet-wide.

**When to run:** Immediately after the PPTX is built (SOP 9.1 complete).

**Inputs:**
- output/[DECK_SLUG].pptx

**Steps:**
1. Convert the PowerPoint file to a portable-document-format file using LibreOffice Impress in headless mode (the same LibreOffice headless convert path the design-intelligence-library uses, cited in `45-design-intelligence-library/library/_system/PPT-ANALYSIS-SOP.md`):
   ```bash
   soffice --headless --convert-to pdf --outdir output/ output/[DECK_SLUG].pptx
   ```
   This produces output/[DECK_SLUG].pdf -- the delivery export, not a throwaway. The `soffice` binary is the same LibreOffice the Capacity & Reliability Engineer verifies at Step 0.5.
2. Verify the PDF was created and is non-empty.
3. **Documented fallback if `soffice` is unavailable** (record which path succeeded in render_log.json `pdf_export_tool`): (a) try the `libreoffice --headless --convert-to pdf` alias (cited in `45-design-intelligence-library/library/_system/PPT-ANALYSIS-SOP.md`, which uses `libreoffice --headless --convert-to pdf`); (b) if no LibreOffice binary exists, write a multi-page PDF from the ordered slide PNGs using a Python image-to-PDF library already on the box (for example, Pillow `Image.save(..., save_all=True)`) -- an image-only portable-document export that still opens without PowerPoint (slides are already image-only by construction — Decision 5C); (c) if no path produces a non-empty PDF, HALT delivery, flag the Director and Capacity & Reliability Engineer, and request LibreOffice be installed. Never deliver a deck without its portable-document export; the system-wide rule is not waivable.
4. Extract PDF pages to PNG using pdftoppm (for QC):
   ```bash
   pdftoppm -png -r 100 output/[DECK_SLUG].pdf output/pdf-pages/slide
   ```
   This produces output/pdf-pages/slide-000001.png through slide-NNNNNN.png.
5. Verify: PDF page count matches slide_count_final AND the PPTX slide count. If the PDF has fewer pages than expected (LibreOffice sometimes drops slides with very large images), flag to the Director and do not deliver until counts match.
6. Write a render_log.json to output/render_log.json: `{ "pptx_path": "...", "pdf_path": "...", "pdf_is_delivery_output": true, "pdf_export_tool": "soffice|libreoffice|pillow-image-pdf", "page_count": N, "slide_count_final": N, "pptx_slide_count": N, "counts_match": true, "rendered_at": "ISO timestamp" }`.
7. Run the assembly quality gate (Gate 6): assert BOTH output/[DECK_SLUG].pptx and output/[DECK_SLUG].pdf exist, are non-empty, and have matching page/slide counts. Halt delivery on any failure.
8. Send the PDF path and the pdf-pages directory to the QC Specialist for Phase 6 QC; the `.pptx` and `.pdf` together travel to the Media Librarian / Delivery Concierge as delivery outputs.

**Outputs:**
- output/[DECK_SLUG].pdf (REQUIRED delivery output, ships alongside the .pptx; also feeds QC)
- output/pdf-pages/slide-NNNNNN.png (one file per slide, for QC)
- output/render_log.json (records `pdf_is_delivery_output` and `pdf_export_tool`)

**Hand to:** QC Specialist -- Presentations (Phase 6 final deck QC); both files to the Media Librarian / Delivery Concierge for delivery.

**Failure mode:** If `soffice` is not installed: run the documented fallback chain in step 3 (libreoffice alias, then Pillow image-to-PDF) and flag to the Director and Capacity & Reliability Engineer. If no path can produce a non-empty portable-document export, HALT delivery and request LibreOffice be installed; never deliver a `.pptx` without its `.pdf` (the system-wide rule).

---

### SOP 9.3 / 9.4 -- ELIMINATED (Decision 5C, AF-OVERLAY-DELIVERED)

The former SOP 9.3 (Native-Text Overlay Fallback) and SOP 9.4 (Typography-Safe
Assembler Spec) are **removed**. The native PPTX text/element-overlay path no
longer exists: there is no `pptx_text_overlays.json`, no `add_textbox` loop, no
strike support, no rendered-height/collision asserts, and no gradient scrim. Every
slide is a SINGLE composed gpt-image-2 image with its text baked in by the model;
the only legitimate PPTX text part is the off-slide speaker-notes pane.

- Garbled / misspelled text is fixed ONLY by the Slide Image Creator's re-prompt /
  re-seed loop (new prompt + new seed, re-render the composed image), then HUMAN
  ESCALATION if it persists. A native text overlay is never the remedy.
- The mere presence of a `pptx_text_overlays.json` file at assembly, or any native
  (non-notes) on-slide text run in the delivered PPTX, is a hard auto-fail
  (AF-OVERLAY-DELIVERED), enforced by `scripts/build_deck.py` `_chk_no_overlay` at
  preflight and at the postflight completeness gate.
- The LOGO fallback is NOT native text: when the model cannot bake the locked logo
  cleanly, the real logo IMAGE is composited onto the slide PNG via the PIL
  image-composite path (SOP-IMG-05) BEFORE assembly — baked into the image, not
  added as a native PPTX element.

---


### SOP 9.5 -- Infographic PNG Export (infographic_png deliverable)

**When to run:** After SOP 9.2 (PDF export complete) AND only when `working/checkpoints/infographic_status.json` exists with `status: "ready"`. This SOP is CONDITIONAL -- it fires exclusively on runs where the Slide Image Creator produced a QC-passed `working/deliverables/infographic.png` (converter-origin runs and any deck with `deliverable_bundle.checklist_items` in intake.json). Skip this SOP and record `infographic_export_skipped: true` in render_log.json when `infographic_status.json` is absent or `status != "ready"`.

**Why this SOP exists:** `PIPELINE-MANIFEST.json` lists `infographic_png` as a required deliverable for converter-origin decks (key: `infographic_png`; note: "produced by infographic-checklist role"). The Slide Image Creator owns production (SOP 9.10); this role owns the verified copy into the delivery path, identical to how the PDF export is a separate verified step from assembly.

**Inputs:**
- working/checkpoints/infographic_status.json (`status: "ready"`, `deliverable_path: "working/deliverables/infographic.png"`)
- working/deliverables/infographic.png (QC-passed portrait infographic image)

**Steps:**
1. Read `working/checkpoints/infographic_status.json`. Confirm `status == "ready"` and `qc_passed == true`. If either is false or the file is absent: skip this SOP (record `infographic_export_skipped: true` in render_log.json) and notify the Director: "infographic_status.json missing or not ready -- SOP 9.5 skipped. If this run requires an infographic, route back to Slide Image Creator SOP 9.10."
2. Verify the source file exists and is non-empty:
   ```bash
   ls -lh working/deliverables/infographic.png
   ```
   The file must exist and show a non-zero size (expect >= 100KB for a 2K-resolution render). A missing or zero-byte file is a halt condition.
3. Copy to the output directory alongside the PPTX and PDF:
   ```bash
   cp working/deliverables/infographic.png output/infographic.png
   ```
4. Verify the copy succeeded:
   ```bash
   ls -lh output/infographic.png
   ```
   The output file must exist and have the same size as the source (within 1 byte; a size mismatch indicates a corrupt copy).
5. Update `output/render_log.json` to add the infographic record:
   ```json
   {
     "infographic_path": "output/infographic.png",
     "infographic_size_bytes": N,
     "infographic_export_tool": "cp",
     "infographic_qc_passed": true,
     "infographic_exported_at": "ISO timestamp"
   }
   ```
   Merge this into the existing render_log.json object (do not overwrite the PPTX/PDF fields).
6. Notify the Director: "output/infographic.png exported and verified ([SIZE]). Ready for Delivery Concierge."

**Outputs:**
- output/infographic.png (delivery-ready copy of the QC-passed infographic)
- output/render_log.json (updated with infographic_path, infographic_size_bytes, infographic_qc_passed)

**Hand to:** Delivery Concierge (SOP 9.0 / AF-DH1) -- the Delivery Concierge adds `infographic.png` to the five-file client package whitelist for converter-origin runs and copies it into `delivery/[DECK_SLUG]-FINAL/`. This role does NOT copy to delivery/; that is Delivery Concierge territory (AF-DH1 rule).

**Failure mode:** If the copy fails (disk full, permission error): halt and notify the Director immediately. Do NOT proceed to delivery with a missing infographic on a run where `infographic_status.json` declares it required. If the source file is zero bytes despite `status: "ready"` in infographic_status.json, flag to the Director AND the Slide Image Creator: "infographic.png is zero bytes -- Slide Image Creator must re-run SOP 9.10 before export."

---
