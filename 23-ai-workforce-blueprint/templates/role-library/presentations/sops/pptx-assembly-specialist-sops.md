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

**Typography-safe assembler requirement:**

Every overlay text box added in this SOP must comply with all six rules of SOP 9.4 (Typography-Safe Assembler Spec): (1) no spAutoFit; (2) fixed-box dimensions; (3) rendered-height asserted before insertion; (4) bottom-anchoring for price and hook entries; (5) collision assert after all overlays for a slide are written; (6) bottom-up gradient scrim inserted before the text box on photographic backgrounds. See SOP 9.4 for the full implementation. These rules are not optional. Assembly halts on any assert failure.

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

### SOP 9.4 -- Typography-Safe Assembler Spec

**When to run:** Apply these rules on EVERY overlay text box added during SOP 9.1 and SOP 9.3. These rules are not optional and are not waivable by any downstream role. They exist because the absence of these rules produced the colliding 5-box text stack on Corey's deck -- the defining P2 defect. Text-in-image is the rule for webinar decks; overlay is a per-element fallback only. When overlay IS used, every rule below applies with no exception.

**Inputs:**
- working/copy/pptx_text_overlays.json (each entry defines the overlay to apply)
- working/brand/style_block.md (for font family, weight, and color matching)
- output/pdf-pages/ (rendered PDF pages for rendered-height measurement and collision checking)

**Rule 1 -- autofit BANNED (no spAutoFit):**

No text box added by this assembler may contain a `spAutoFit` OOXML element. `spAutoFit` allows PowerPoint to expand the text box to fit its content, which destroys fixed geometry and causes boxes to collide. The correct OOXML for a locked text box is `noAutofit`. After writing each text box, open the python-pptx shape XML and assert that no `<a:spAutoFit/>` is present. If it is found: remove it and replace with `<a:noAutofit/>` via direct OOXML manipulation.

```python
from lxml import etree

def enforce_no_autofit(txBox):
    """Remove spAutoFit and set noAutofit on a text frame body properties."""
    txPr = txBox.text_frame._txBody.get_or_add_txPr()
    # Remove any existing spAutoFit
    for child in list(txPr):
        if child.tag.endswith('}spAutoFit'):
            txPr.remove(child)
    # Ensure noAutofit is present
    nsmap = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    noAutofit = etree.SubElement(txPr, '{%s}noAutofit' % nsmap)
```

Call `enforce_no_autofit(txBox)` immediately after creating each text box.

**Rule 2 -- fixed-box sizing:**

Every overlay text box must have explicit, fixed width and height values sourced from pptx_text_overlays.json. Never infer or auto-size a dimension. The `left`, `top`, `width`, and `height` fields in pptx_text_overlays.json are in Inches and are the contract. If any field is missing or zero: halt and notify the Director. Do not assemble with an underspecified overlay entry.

**Rule 3 -- rendered-text-height measurement:**

After writing each overlay text box and before saving the final PPTX, measure the rendered height of the text content to confirm it fits within the declared box height. Use python-pptx's text frame paragraph and run APIs to compute approximate rendered height:

```python
def estimate_rendered_height_inches(overlay_entry):
    """Estimate the rendered height of the text given font size and box width.
    Returns height in inches. Uses a conservative line-height multiplier."""
    font_size_pt = overlay_entry.get("font_size_pt", 36)
    box_width_inches = overlay_entry["width"]
    text = overlay_entry["text"]
    # Approximate characters per line (72 pt per inch; Montserrat at given size)
    chars_per_line = max(1, int(box_width_inches * 72 / (font_size_pt * 0.55)))
    line_count = max(1, -(-len(text) // chars_per_line))  # ceiling division
    line_height_inches = (font_size_pt * 1.2) / 72
    return line_count * line_height_inches

def assert_text_fits(overlay_entry):
    estimated = estimate_rendered_height_inches(overlay_entry)
    declared = overlay_entry["height"]
    if estimated > declared * 1.1:  # 10% tolerance
        raise AssertionError(
            f"COLLISION ASSERT FAILED: slide {overlay_entry['slide_number']} "
            f"text '{overlay_entry['text'][:30]}' estimated height {estimated:.2f}in "
            f"exceeds declared box height {declared:.2f}in. "
            f"Update pptx_text_overlays.json with a taller box or shorter text before assembly."
        )
```

Call `assert_text_fits(overlay_entry)` before adding each overlay. If the assertion fails: halt assembly and report the specific slide and entry. Never proceed with an overflow entry.

**Rule 4 -- bottom-anchoring (grow UP into reserved headroom):**

Overlay text boxes that contain price copy, hook lines, or struck-through prices must be bottom-anchored. This means the text is pinned to the bottom of its declared box and grows upward into the reserved headroom above it. This prevents the text from colliding with slide content below the box. To bottom-anchor in python-pptx:

```python
from pptx.enum.text import PP_ALIGN
from lxml import etree

def bottom_anchor_textbox(txBox):
    """Set vertical anchor to bottom so text grows upward into headroom."""
    txPr = txBox.text_frame._txBody.get_or_add_txPr()
    # Set anchor to bottom
    txPr.set('anchor', 'b')
    # Also set anchorCtr to false (no vertical centering)
    txPr.set('anchorCtr', '0')
```

Apply bottom-anchoring to every price or hook overlay. For non-price body-text overlays, anchoring is left at the default (top) unless the overlay entry specifies `"anchor": "bottom"`.

**Rule 5 -- build-time collision assert (FAILS LOUD):**

After all overlays are written and before the PPTX is saved, run the collision assert on the composed slide. The collision assert checks that no two overlay text boxes on the same slide have overlapping bounding rectangles. A collision is defined as any two boxes whose rectangles intersect by more than 2pt (0.028 inches) in either axis.

```python
def assert_no_overlay_collisions(overlays_for_slide, slide_number):
    """Assert no two overlay boxes on the same slide collide.
    overlays_for_slide: list of overlay dicts with left/top/width/height in Inches."""
    boxes = [(o["left"], o["top"], o["left"] + o["width"], o["top"] + o["height"])
             for o in overlays_for_slide]
    TOLERANCE = 0.028  # inches (approx 2pt)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax1, ay1, ax2, ay2 = boxes[i]
            bx1, by1, bx2, by2 = boxes[j]
            x_overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
            y_overlap = max(0, min(ay2, by2) - max(ay1, by1))
            if x_overlap > TOLERANCE and y_overlap > TOLERANCE:
                raise AssertionError(
                    f"COLLISION ASSERT FAILED on slide {slide_number}: "
                    f"overlay box {i+1} ('{overlays_for_slide[i]['text'][:20]}') "
                    f"collides with overlay box {j+1} ('{overlays_for_slide[j]['text'][:20]}'). "
                    f"Overlap: {x_overlap:.3f}in x {y_overlap:.3f}in. "
                    f"Update pptx_text_overlays.json to resolve before assembly."
                )
```

Call `assert_no_overlay_collisions(overlays[slide_number], slide_number)` for every slide that has overlays, immediately before saving. If the assert fails: halt with the specific slide and collision detail. Never save a PPTX with a known collision.

**Rule 6 -- bottom-up gradient scrim (replaces the flat 50% slab):**

When a native text overlay is applied on top of a photographic background image, a readability scrim must be inserted between the background image and the text box. The scrim is a bottom-up gradient: fully transparent at the top, transitioning to a semi-opaque dark fill (rgba 0,0,0,0.65) at the bottom. This matches the Lyric gold-standard visual treatment (controlled typography) and replaces any flat 50%-opacity slab that earlier assembler versions used.

To insert a gradient scrim in python-pptx (direct OOXML):

```python
from lxml import etree
from pptx.util import Inches

def add_gradient_scrim(slide, overlay_entry, slide_height_inches=7.5):
    """Add a bottom-up gradient scrim behind an overlay text box.
    The scrim covers the lower portion of the slide where the text sits."""
    # Scrim occupies the lower 40% of the slide height by default,
    # or the height of the text box plus 0.5in padding, whichever is larger.
    text_bottom = overlay_entry["top"] + overlay_entry["height"]
    scrim_height = max(slide_height_inches * 0.40,
                       slide_height_inches - overlay_entry["top"] + 0.5)
    scrim_top = slide_height_inches - scrim_height
    scrim_left = 0.0
    scrim_width = 13.333  # full slide width

    # Add a rectangle shape covering the scrim area
    from pptx.util import Inches, Emu
    scrim = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(scrim_left), Inches(scrim_top),
        Inches(scrim_width), Inches(scrim_height)
    )
    scrim.line.fill.background()  # no border

    # Apply linear gradient fill via direct OOXML
    spPr = scrim._element.spPr
    # Remove any existing fill
    for child in list(spPr):
        if child.tag.endswith('}solidFill') or child.tag.endswith('}gradFill') or child.tag.endswith('}noFill'):
            spPr.remove(child)

    nsmap = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    gradFill = etree.SubElement(spPr, '{%s}gradFill' % nsmap)
    gsLst = etree.SubElement(gradFill, '{%s}gsLst' % nsmap)

    # Stop 1: top of scrim = fully transparent (alpha 0)
    gs0 = etree.SubElement(gsLst, '{%s}gs' % nsmap, pos='0')
    srgbClr0 = etree.SubElement(gs0, '{%s}srgbClr' % nsmap, val='000000')
    alpha0 = etree.SubElement(srgbClr0, '{%s}alpha' % nsmap, val='0')

    # Stop 2: bottom of scrim = semi-opaque dark (alpha 65%)
    gs1 = etree.SubElement(gsLst, '{%s}gs' % nsmap, pos='100000')
    srgbClr1 = etree.SubElement(gs1, '{%s}srgbClr' % nsmap, val='000000')
    alpha1 = etree.SubElement(srgbClr1, '{%s}alpha' % nsmap, val='65000')

    # Linear gradient direction: 90 degrees (top to bottom)
    lin = etree.SubElement(gradFill, '{%s}lin' % nsmap, ang='5400000', scaled='0')

    # Send scrim to back (behind the text box, in front of the image)
    slide.shapes._spTree.remove(scrim._element)
    # Insert after the background image but before text boxes
    slide.shapes._spTree.insert(2, scrim._element)
```

Call `add_gradient_scrim(slide, overlay_entry)` for every overlay entry that sits over a photographic background (all standard slide images in the webinar deck pipeline qualify). Call it before writing the text box on the same slide, so the z-order places the scrim behind the text but in front of the image.

**Steps:**
1. Before writing any overlay text box: call `assert_text_fits(overlay_entry)`. Halt if it fails.
2. Add the gradient scrim via `add_gradient_scrim(slide, overlay_entry)`.
3. Add the text box with fixed dimensions from the overlay entry.
4. Call `enforce_no_autofit(txBox)` immediately after creating the text box.
5. Apply bottom-anchoring via `bottom_anchor_textbox(txBox)` for price and hook overlays (or any entry with `"anchor": "bottom"`).
6. After all overlays for a slide are written: call `assert_no_overlay_collisions(overlays[slide_number], slide_number)`. Halt if it fails.
7. Continue to the next slide. Do not save the PPTX until all slides pass both asserts (text-fits and no-collision).

**Outputs:**
- working/scripts/assemble_pptx.py (updated to include all six typography-safe rules)
- output/[DECK_SLUG].pptx (assembled with no spAutoFit, no collisions, gradient scrims applied)

**Hand to:** SOP 9.2 (render to PDF) and then QC Specialist -- Presentations for Phase 6 QC

**Failure mode:** Any assert failure in Rules 3, 5, or the autofit check is a hard stop. Do not proceed. Notify the Director with the exact slide number, the failing rule, and the specific measurement that caused the failure. The Director must update pptx_text_overlays.json or escalate to the Slide Image Creator for a re-render. Never bypass the assert. Never deliver a PPTX with a known collision or overflow.

---
