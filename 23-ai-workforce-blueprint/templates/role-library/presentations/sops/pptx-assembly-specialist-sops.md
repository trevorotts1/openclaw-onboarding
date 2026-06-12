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
- working/copy/pptx_text_overlays.json (optional -- but required when any slide's text render failed twice during Phase 5; see strike support below)
- working/copy/mission_prd.json (slide_count_final, deck_slug)

**Strike-capable overlay support:**

pptx_text_overlays.json entries may contain a `strike: true` property on any run. This is the documented fallback for struck-through prices that failed two render attempts in Phase 4/5 (per master SOP Section 7.4). The assembly script must handle the `strike` property on every run-level entry and apply the correct OOXML attribute to the text run.

Each entry in pptx_text_overlays.json follows this schema:
```json
{
  "slide_number": 51,
  "text": "$2,500",
  "left": 2.1,
  "top": 1.8,
  "width": 3.0,
  "height": 0.8,
  "font_name": "Montserrat Black",
  "font_size_pt": 48,
  "font_color_hex": "888888",
  "bold": true,
  "strike": true
}
```
When `strike: true`: the run's OOXML `<a:rPr>` must include `strike="sngStrike"`. This is set via `run.font._rPr.set("strike", "sngStrike")` in python-pptx (direct XML manipulation, since python-pptx has no high-level strike API as of v1.x).

When `strike: false` or the property is absent: do not set the strike attribute.

When to write a new pptx_text_overlays.json entry:
- During Phase 5 QC: if a text element (especially a struck-through old price) fails to render correctly on two consecutive generation attempts, the QC Specialist or Slide Image Creator writes an entry to pptx_text_overlays.json with the text, position, font spec, and `strike: true` (for struck prices). This role reads those entries at assembly time.
- The Slide Image Creator regenerates the slide WITHOUT the failing text element; this role applies it natively during assembly.

**Steps:**
1. Verify slide count: `ls working/media-library/*.png | wc -l` must equal slide_count_final from mission_prd.json. If it does not, halt and notify the Director.
2. Verify presenter_notes.json has exactly slide_count_final entries. If fewer entries than slides: flag missing notes to the Director. Do not assemble with missing notes.
3. Check for pptx_text_overlays.json. If it exists, read it and log how many entries contain `strike: true`. These are struck-price overlays and require special handling.
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
   OVERLAYS_FILE = "working/copy/pptx_text_overlays.json"
   OUTPUT_FILE = "output/[DECK_SLUG].pptx"

   prs = Presentation()
   prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
   prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)

   with open(NOTES_FILE) as f:
       notes = {item["slide_number"]: item["presenter_note"] for item in json.load(f)}

   overlays = {}
   if os.path.exists(OVERLAYS_FILE):
       with open(OVERLAYS_FILE) as f:
           for item in json.load(f):
               sn = item["slide_number"]
               if sn not in overlays:
                   overlays[sn] = []
               overlays[sn].append(item)

   blank_layout = prs.slide_layouts[6]  # blank layout

   image_files = sorted(glob.glob(os.path.join(MEDIA_DIR, "slide-*.png")),
                       key=lambda x: int(re.search(r'slide-(\d+)', x).group(1)))

   for idx, img_path in enumerate(image_files):
       slide_number = idx + 1
       slide = prs.slides.add_slide(blank_layout)

       # Full-bleed image
       pic = slide.shapes.add_picture(img_path, Inches(0), Inches(0),
                                      Inches(SLIDE_WIDTH_INCHES), Inches(SLIDE_HEIGHT_INCHES))

       # Native text overlays (if any) -- supports multiple overlays per slide + strike property
       if slide_number in overlays:
           for overlay in overlays[slide_number]:
               txBox = slide.shapes.add_textbox(
                   Inches(overlay["left"]), Inches(overlay["top"]),
                   Inches(overlay["width"]), Inches(overlay["height"])
               )
               tf = txBox.text_frame
               para = tf.paragraphs[0]
               run = para.add_run()
               run.text = overlay["text"]
               run.font.size = Pt(overlay.get("font_size_pt", 36))
               run.font.bold = overlay.get("bold", True)
               if overlay.get("font_name"):
                   run.font.name = overlay["font_name"]
               if overlay.get("font_color_hex"):
                   hex_color = overlay["font_color_hex"].lstrip("#")
                   run.font.color.rgb = RGBColor(
                       int(hex_color[0:2], 16),
                       int(hex_color[2:4], 16),
                       int(hex_color[4:6], 16)
                   )
               # Strike support: apply sngStrike via direct OOXML manipulation
               if overlay.get("strike"):
                   rPr = run.font._rPr
                   rPr.set("strike", "sngStrike")

       # Speaker notes
       if slide_number in notes:
           notes_slide = slide.notes_slide
           notes_slide.notes_text_frame.text = notes[slide_number]

   os.makedirs("output", exist_ok=True)
   prs.save(OUTPUT_FILE)
   print(f"Saved: {OUTPUT_FILE}")
   ```
5. Run the assembly script: `python3 working/scripts/assemble_pptx.py`.
6. Verify the output file exists at output/[DECK_SLUG].pptx and is non-empty.
7. Open the PPTX with python-pptx and verify: slide count == slide_count_final, first and last slide images are correct, first slide has a non-empty notes field.
8. For any slide with a `strike: true` overlay entry: open the corresponding slide in the rendered PDF (SOP 9.2) and visually confirm the struck text appears with the strikethrough line.

**Outputs:**
- output/[DECK_SLUG].pptx (the assembled deck, with all native overlays and struck-price overlays applied)
- pptx_text_overlays.json (written by QC Specialist / Slide Image Creator during Phase 5; read here; this role does not write it, it reads it)

**Hand to:** SOP 9.2 (render to PDF for QC), then after Phase 6 QC passes -- hand to Media Librarian / GHL Updater SOP 9.6 (Final Deck Delivery) or ROLE-13 Delivery Concierge if that role exists.

**Failure mode:** If any slide image file is missing or corrupt: halt. Do not assemble with a gap. Notify the Director: "Assembly blocked: slide-NN.png is missing or corrupt. Media Librarian must re-verify."

Native text overlay fallback trigger: if two render attempts on any text element both fail Phase 5 image QC (text garbled, struck price not rendered cleanly), the QC Specialist or Slide Image Creator must write the failed element to pptx_text_overlays.json with the correct `strike` flag BEFORE assembly begins. If this role reaches assembly and discovers that a slide's image has a missing text element that is not covered by an overlay entry, halt and notify the Director: the fallback entry was not written.

---

### SOP 9.2 -- Render to PDF for Final QC

**When to run:** Immediately after the PPTX is built (SOP 9.1 complete).

**Inputs:**
- output/[DECK_SLUG].pptx

**Steps:**
1. Convert PPTX to PDF using LibreOffice Impress headless:
   ```bash
   soffice --headless --convert-to pdf --outdir output/ output/[DECK_SLUG].pptx
   ```
   This produces output/[DECK_SLUG].pdf.
2. Verify the PDF was created and is non-empty.
3. Extract PDF pages to PNG using pdftoppm:
   ```bash
   pdftoppm -png -r 100 output/[DECK_SLUG].pdf output/pdf-pages/slide
   ```
   This produces output/pdf-pages/slide-000001.png through slide-NNNNNN.png.
4. Verify: page count from pdftoppm matches slide_count_final. If the PDF has fewer pages than expected (LibreOffice sometimes drops slides with very large images), flag to the Director.
5. Write a render_log.json to output/render_log.json: `{ "pptx_path": "...", "pdf_path": "...", "page_count": N, "slide_count_final": N, "counts_match": true, "rendered_at": "ISO timestamp" }`.
6. Send the PDF path and the pdf-pages directory to the QC Specialist for Phase 6 QC.

**Outputs:**
- output/[DECK_SLUG].pdf
- output/pdf-pages/slide-NNNNNN.png (one file per slide)
- output/render_log.json

**Hand to:** QC Specialist -- Presentations (Phase 6 final deck QC)

**Failure mode:** If `soffice` is not installed: flag to the Director and Capacity & Reliability Engineer. The C&RE should have verified LibreOffice is available in the Step 0.5 capacity probe. If LibreOffice is genuinely unavailable, notify the operator and request it be installed before assembly proceeds.

---

### SOP 9.3 -- Native-Text Overlay Fallback

**When to run:** Only when working/copy/pptx_text_overlays.json exists AND contains entries. This is a fallback for cases where the image generation produced text that failed QC and native PPTX text overlays are the approved workaround.

**Inputs:**
- working/copy/pptx_text_overlays.json
- working/brand/style_block.md (for font and color matching)

**Steps:**
1. Read pptx_text_overlays.json. Each entry: `{ "slide_number": N, "text": "...", "left": Inches, "top": Inches, "width": Inches, "height": Inches, "font_name": "...", "font_size_pt": N, "font_color_hex": "...", "bold": true }`.
2. For each entry, verify the font_name matches the STYLE BLOCK headline font. If it does not, flag to the Brand Steward to update the overlay entry.
3. Apply the overlays in the assembly script (already included in SOP 9.1 step 3 via the `overlays` dict).
4. After assembly, verify the overlay appears correctly on the rendered PDF page for each affected slide. Visual check: the text is legible, matches the font spec, and does not overlap the logo placement zone.
5. If an overlay is visually misaligned: adjust the Inches values in pptx_text_overlays.json and re-assemble. Record the adjustment in a comment in pptx_text_overlays.json.

**Outputs:**
- PPTX with native text overlays applied on affected slides
- pptx_text_overlays.json updated with any positional adjustments

**Hand to:** QC Specialist (Phase 6 QC, which will check overlay appearance in the rendered PDF)

**Failure mode:** If a native text overlay is required but pptx_text_overlays.json is missing or the affected slide is not in the overlays file: flag to the Director. The QC Specialist flagged the text failure in Phase 5 -- the Slide Image Creator must either fix the prompt and re-generate, or provide an overlay entry. Do not assemble a slide with missing text without explicit operator authorization.

---
