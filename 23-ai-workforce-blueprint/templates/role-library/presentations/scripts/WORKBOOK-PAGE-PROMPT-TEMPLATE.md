# WORKBOOK PAGE PROMPT TEMPLATE — fillable PDF workbook page backgrounds (kie.ai gpt-image-2)

**Scope:** Presentations department Feature L2-D (Gauntlet Loop 2, Feature B). Every
presentation gets a branded, fillable PDF workbook: each page background is image-designed
via kie.ai `gpt-image-2`, then assembled into a US-Letter fillable PDF with real AcroForm
fields overlaid by `workbook_builder.py`.

**Why a template:** the workbook page prompt is a 5,000–19,000-char spec (the research band
for gpt-image-2; author to a target of >=9,000 stripped chars, and <=18,000 if the
Presentations rich-prompt gate is enforced on this run). It must produce a **background-only**
render — NO text, NO labels, NO numbers baked in — because any text the image model draws is
garbled/illegible. The real form content (labels, lines, checkboxes) is overlaid as crisp
AcroForm widgets at assembly time.

**The objective:** a clean, branded visual shell with clearly **reserved, visually-quiet empty
zones** where the AcroForm fields land. Use the model's strength (evocative branded visuals)
and avoid its documented weaknesses (text accuracy, layout precision).

---

## 0. PARAMETERS (fill the {braces} per page)

| Token | Meaning |
|---|---|
| `{CLIENT_NAME}` | Client/company display name for the watermark wordmark |
| `{DECK_SLUG}` | machine slug used for file naming |
| `{PRIMARY_HEX}` | brand primary (header band + footer rule) |
| `{SECONDARY_HEX}` | brand secondary (section accent bands, thin rules) |
| `{ACCENT_HEX}` | brand accent (small geometric motif only) |
| `{BASE_HEX}` | near-white page base / field-zone interior |
| `{INK_HEX}` | near-black ink for hairlines |
| `{FONT_CHARACTER}` | typography character (e.g. clean geometric sans) — visual only, no visible text |
| `{PAGE_ROLE}` | the page's workbook role (Cover, My Goals, Action Plan, Weekly Check-In, Notes…) — drives zone flex only |
| `{MOTIF_POSITION}` | top-right | bottom-left | above-footer (rotates per page for determinism) |

**I2I harmony directive (later pages — MANDATORY when reference images ride `input_urls`):**
> "Use the attached images only as style reference for color grading, lighting, and composition — do not copy their subjects, faces, or text."

---

## 1. THE TEMPLATE (author to >=9,000 chars; repeat verbatim structure per page)

```
DESIGN A PRINTABLE WORKBOOK PAGE BACKGROUND, PORTRAIT, US-LETTER-8.5x11 EQUIVALENT (3:4 ASPECT).

This is the BACKGROUND ONLY for a fillable PDF form page in a client workbook. Generate the
visual shell — NO words, NO labels, NO numbers, NO placeholder content anywhere. All form
content will be overlaid later as crisp, real form fields. The page must read as a premium,
clean, professionally-branded worksheet with clearly reserved EMPTY ZONES for those fields.

=== BRAND LOCKUP ===
Client: {CLIENT_NAME}. Industry: professional services. Grade: premium, calm, trustworthy.
Brand palette (use these EXACT hex values, no substitutions):
  Primary: {PRIMARY_HEX} — header band and footer rule only.
  Secondary: {SECONDARY_HEX} — section accent bands and thin rules.
  Accent: {ACCENT_HEX} — one small geometric motif (thin corner brace or small circle) only.
  Base: {BASE_HEX} (near-white) — page background and every field-zone interior.
  Ink: {INK_HEX} (near-black) — very light hairline rules, at most 8% opacity.
Typography character: {FONT_CHARACTER}, used only as a visual system — no visible text.
Logo treatment: the {CLIENT_NAME} wordmark appears ONLY as a LOW-OPACITY watermark in the
  footer band, ~14% opacity, left-aligned, ~2.5in wide. Do not place it anywhere else.
  (On the image-to-image path, the real page-1 reference is attached — preserve its palette,
  lighting, and composition; do not copy any baked text.)

=== LAYOUT GRID (fixed per page) ===
The page divides top-to-bottom into three bands:
  HEADER BAND (top 0-15%): a solid {PRIMARY_HEX} color block, or a clean flat header with a
    thin {ACCENT_HEX} underline rule at its bottom edge. Empty and quiet — reserved for the
    page title and a client-name form line.
  FIELD BAND (15-85%): on {BASE_HEX}. Contains ONLY the empty field zones described below.
    Flat, even color. No patterns, no photos, no gradients that fight text.
  FOOTER BAND (85-100%): a hairline rule in {SECONDARY_HEX}, the low-opacity wordmark
    watermark at left, and an EMPTY rectangular zone at bottom-right reserved for a
    page-number form field.
Safe margins: 0.6in on all four sides. Nothing touches the edges.

=== EMPTY FIELD ZONES (reserve exactly these; each a clean flat shape, no content) ===
1. Header-right: one wide rounded-rectangle zone, {SECONDARY_HEX} at 8% tint, ~4.5in wide
   x 0.5in tall — reserved for a client-name text field. Quiet, no shading inside.
2. Field band, top row: three evenly spaced empty box rows, each {SECONDARY_HEX} at 5% tint
   with a thin {SECONDARY_HEX} bottom rule, ~6.5in wide x 0.6in tall each — reserved for
   short-answer lines. The interior of each must be plain, uniform, empty.
3. Field band, middle: two larger empty panels side by side, ~3.1in wide x 2.2in tall each,
   plain {BASE_HEX} with a thin {SECONDARY_HEX} border and softly rounded corners — reserved
   for check-list / short-note zones. Interiors empty and uniform.
4. Field band, bottom-left: one large empty notes panel ~4.2in wide x 3.0in tall, plain
   {BASE_HEX} with a thin {SECONDARY_HEX} border — reserved for a long-answer multiline
   field. Interior empty.
This page's workbook role is {PAGE_ROLE}; vary zone emphasis only in the direction of that
role (e.g. a Weekly Check-In page may widen zone 3). Leave every zone CLEAR and VISUALLY
QUIET for text overlay. Do not decorate inside any zone.

=== MOTIF (consistent every page, small) ===
One small {ACCENT_HEX} geometric motif per page, placed at {MOTIF_POSITION}. It is
decorative only, thin-line, never over a field zone.

=== NEGATIVE DIRECTIVES ===
No text, no words, no letters, no numbers, no labels, no placeholder glyphs, no characters,
no people, no hands, no photos, no busy textures, no gradients crossing a field zone, no
shadow over any field zone, no watermark over any field zone, no watermark in the header,
no clip-art, no clutter, no noise, no vignetting over the field band. Flat, clean, minimal,
corporate. Do not write any words inside the reserved zones. Do not draw letters in any
font. No misspelled or garbled words anywhere (there must be no words to garble). Do not
redraw, recolor, restyle, or reinterpret the attached reference brand mark. No emoji, no
clipart, no default-font UI artifacts, no pure-black fills.

=== QUALITY ===
Crisp 2K edges, flat clean vector-flat aesthetic, professional corporate workbook page,
extremely high information density of DESIGN (not content), soft even tone, consistent with
the attached reference page. Portrait 3:4. Do not crop or letterbox.

=== STYLE REFERENCE DIRECTIVE (I2I pages only — verbatim) ===
Use the attached images only as style reference for color grading, lighting, and composition
— do not copy their subjects, faces, or text.
```

---

## 2. VERIFICATION GATE (before any submit)

A workbook page prompt MUST clear at least the **universal-safe** prompt floor
(`prompt_gate.verify_prompt_minimal`: no dead endpoint fragment, non-empty) and SHOULD clear
the full Presentations rich gate (`prompt_gate.verify_prompt`: >=9,000 chars, <=18,000,
structural blocks `[ARCHETYPE ...]` / negative block / `Do not `, 8-class negative-block,
spelling-lock, HEX palette, type-size token, composition token, >=220 distinct words). The
workbook prompts above include a `[ARCHETYPE ...]`-style header (the `DESIGN A PRINTABLE
WORKBOOK PAGE BACKGROUND...` role line) — treat it as the structural-block anchor.

Prove it with the shared gate module (this is the same gate `kie_generate.py` calls):
```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "scripts")
import prompt_gate as pg
text = open("scripts/WORKBOOK-PAGE-PROMPT-TEMPLATE.md").read()
try:
    pg.verify_prompt(text)          # full rich gate (9,000-18,000 band)
    print("PASS full rich gate")
except pg.PromptGateError as e:
    print("FAIL:", e)
PY
```
Every page prompt must clear at least `prompt_gate.verify_prompt_minimal` (non-empty +
no dead-endpoint fragment); when the run enforces the Presentations rich gate
(`KIE_PROMPT_GATE=presentations`), it must clear `prompt_gate.verify_prompt` in full.

**Stripped-char counting:** strip code fences and Markdown backticks before measuring the
5,000–19,000 band; a rendered prompt (the JSON-escaped string actually sent to kie.ai) is
measured raw.

---

## 3. FILE REFERENCES

- Executor: `scripts/workbook_builder.py` (this directory).
- Sample deliverable: `~/Downloads/WORKBOOK-SAMPLE.pdf`.
- Research (full API + stack decision): `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-PDF-RESEARCH.md`.
