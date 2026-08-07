# WORKBOOK PAGE PROMPT TEMPLATE — content-in-image workbook page (kie.ai gpt-image-2)

**Scope:** Presentations department P8.25-WORKBOOK (Feature L2-D redesign). Every
presentation gets a branded, **content-rich** companion workbook: each page image is
designed via kie.ai `gpt-image-2` with the page's **REAL content baked into the image**
(headline, subhead, bullets, question, quote, quiz, affirmation, follow-along, contact),
then assembled into a US-Letter PDF with real AcroForm fields overlaid by
`workbook_builder.py`.

**Why content-in-image (the redesign):** the OLD workbook prompt produced a "BACKGROUND
ONLY" wireframe — a blank shell that read as unfinished and could not stand alone. Per
`WORKBOOK-REDESIGN-PLAN.md` §2, the page's real content is now **designed into the image**
by the text-to-image engine, so the workbook reads as a finished, premium companion. The
answer zones stay visually quiet for the AcroForm overlay. The wireframe directive
("BACKGROUND ONLY", "NO text", "NO labels", "NO words") is **BANNED**: the
`AF-WORKBOOK-PROMPT-NO-CONTENT` gate refuses any prompt that carries it or any page with
zero content strings — the content-empty regression can never spend a paid render.

**Band:** **9,000–18,000 stripped chars** (the Presentations rich-prompt gate; author to
>=9,000; the verbatim content blocks naturally exceed it).

---

## 0. PARAMETERS (fill the {braces} per page)

| Token | Meaning |
|---|---|
| `{ARCHETYPE_ID}` | machine id, e.g. `WORKBOOK-PAGE-TEACH-01` / `COVER` / `QUIZ` |
| `{CLIENT_NAME}` | client/company display name (wordmark + footer) |
| `{PAGE_ROLE}` | the page's workbook role (TEACHING — RULE 1, My Goals, Action Plan…) |
| `{SLIDE_RANGE}` | which deck slides it accompanies (e.g. "deck slide 7") |
| `{GRADE}` | brand grade (e.g. "premium, calm, editorial, sales-focused") |
| `{PRIMARY_HEX}` / `{SECONDARY_HEX}` / `{ACCENT_HEX}` / `{BASE_HEX}` / `{INK_HEX}` | brand palette |
| `{FONT_CHARACTER}` | typography character (e.g. "Montserrat geometric editorial sans") |
| `{HEADLINE}` `{SUBHEAD}` `{BULLETS}` `{QUOTE}` `{QUESTION}` `{AFFIRMATION}` `{QUIZ}` `{FOLLOW_ALONG}` `{CONTACT_LINE}` | the page's **verbatim** content strings |
| `{HEADLINE_SIZE}` `{SUBHEAD_SIZE}` `{BODY_SIZE}` | type sizes in pt |
| `{MOTIF_POSITION}` | top-right \| bottom-left \| above-footer (cycles per page) |

**I2I harmony directive (later pages — MANDATORY when reference images ride `input_urls`):**
> "Use the attached images only as style reference for color grading, lighting, and
> composition — do not copy their subjects, faces, or text."

---

## 1. THE TEMPLATE (author to >=9,000 chars; repeat verbatim structure per page)

```
[ARCHETYPE WORKBOOK-PAGE-<id>]
DESIGN A SINGLE FULL-BLEED PRINTABLE WORKBOOK PAGE, PORTRAIT, US-LETTER-8.5x11 EQUIVALENT,
3:4 ASPECT, 2K. This is a DESIGNED, CONTENT-RICH workbook page for {CLIENT_NAME} — the
companion to a live presentation. Render the page's REAL content (headline, subhead,
bullets, question, quote, affirmation, quiz, follow-along, contact) baked into the image
by the text-to-image engine, in the brand system below. Every quoted string must be
rendered VERBATIM, letter-for-letter.

=== PAGE ROLE & WHAT THIS PAGE IS FOR ===
This workbook page is: {PAGE_ROLE}. It accompanies {SLIDE_RANGE}. The audience completes it
while following the presentation, so every element supports the spoken content on those
slides. The reader works top-to-bottom: headline, subhead, bullets, then the write-in
answer zones. The page must stand alone as a finished, premium takeaway — never a blank
shell.

=== BRAND LOCKUP ===
Client: {CLIENT_NAME}. Grade: {GRADE}.
Brand palette (use these EXACT hex values, no substitutions):
  Primary {PRIMARY_HEX} — header band + footer rule.
  Secondary {SECONDARY_HEX} — section rules, accent bands, the bullet markers.
  Accent {ACCENT_HEX} — one geometric motif + the emphasis color for key words.
  Base {BASE_HEX} — page background.
  Ink {INK_HEX} — text ink.
Typography character: {FONT_CHARACTER} — the weight ladder is BLACK hero (40-56pt on this
page), ExtraBold subhead (20-26pt), Bold label (14-18pt), Medium body (12-14pt). The client
wordmark/logo appears in the footer band at ~14% opacity, left-aligned, ~2.5in wide. (I2I:
the real logo is attached in input_urls — render it exactly, do not redraw.)

=== PAGE CONTENT (the real content — bake verbatim) ===
HEADLINE (render at {HEADLINE_SIZE}pt, {HEADLINE_POSITION}): "{HEADLINE}"
  — the emphasis word "{EMPHASIS}" is rendered in {ACCENT_HEX}.
SUBHEAD: "{SUBHEAD}"
BULLETS (render as {N} short lines, each preceded by a {SECONDARY_HEX} bullet marker, in the
{ BULLET_ZONE}):
  • "{BULLET_1}"
  • "{BULLET_2}"
  • "{BULLET_3}"
{QUOTE, when present}: a pull-quote panel at {QUOTE_ZONE}: "{QUOTE}" — {QUOTE_ATTRIBUTION}
{QUESTION, when present}: "{QUESTION}" followed by {ANSWER_LINE_COUNT} empty answer lines.
{AFFIRMATION, when present}: "{AFFIRMATION}" in the affirmation panel.
{QUIZ, when present}: each item "{QUIZ_Q}" with options (A) {OPT_A} (B) {OPT_B} (C) {OPT_C}
(D) {OPT_D}.
{FOLLOW-ALONG, when present}: a follow-along strip: "{FOLLOW_ALONG}"

=== VERBATIM + SPELLING-LOCK ===
Render EVERY quoted string above letter-for-letter, exactly as written, spelled exactly,
no paraphrasing, no substitution, no reordering, no typo, no garble, no truncation, no
ellipsis unless in the source. The quoted strings are the ONLY text on this page beyond the
{CLIENT_NAME} wordmark and page number. Text must read exactly as quoted.

=== LAYOUT GRID (fixed per page, per page type) ===
HEADER BAND (top 0-16%): solid {PRIMARY_HEX} band with the page title set in white/ink, and
a thin {ACCENT_HEX} rule at its bottom edge. Reserved: the page title + one client-name form
line (empty zone for an AcroForm text field at header-right).
CONTENT BAND (16-84%): on {BASE_HEX}. The page's content zones — headline block, bullet
list, question + answer lines, quote panel, quiz grid, affirmation panel — laid out on a
thirds grid with 0.6in safe margins. Each ANSWER zone is a flat, quiet, empty shape
(short-answer line / checkbox square / notes panel) with a thin {SECONDARY_HEX} border,
reserved for the AcroForm overlay. Generous negative space; no element collides with
another zone.
FOOTER BAND (84-100%): a hairline {SECONDARY_HEX} rule, the {CLIENT_NAME} wordmark/logo
watermark at left, "{CONTACT_LINE}" small at right, and a page-number zone bottom-right.
Safe margins 0.6in; nothing touches the edges.

=== ANSWER ZONES (reserve each as an empty write-in area; no content inside) ===
1. Header-right: one wide rounded-rectangle {SECONDARY_HEX}-tinted zone for a client-name
   text field.
2. Each answer line: a thin {SECONDARY_HEX} underline ~6.5in wide, no shading, ~0.6in tall.
3. Each checkbox/radio: a small empty {SECONDARY_HEX}-bordered square ~0.25in.
4. Notes / commitment panel: a large plain {BASE_HEX} panel with a thin {SECONDARY_HEX}
   border, interior empty.
Keep every answer zone visually quiet so the AcroForm widget reads clearly.

=== MOTIF ===
One small {ACCENT_HEX} geometric motif at {MOTIF_POSITION}, decorative, thin-line, never
over an answer zone.

=== DO-NOT BLOCK (the 8 defect classes, named — for a CONTENT-BEARING page) ===
1. GARBLED/MISSPELLED TEXT — misspell, garble, phonetic drift, or truncation of any quoted
   string; render every quoted string letter-for-letter, exactly as written.
2. LOGO MUTATION — do not redraw/recolor/restyle the attached {CLIENT_NAME} logo; render it
   exactly as attached.
3. PLACEHOLDER/BRACKET TOKENS — no bracketed token, no "owner to confirm", no TBD, no
   "insert here", no build note, no square brackets around the quoted content.
4. IMAGE NARRATION/PRESENTER/META — no narrator line, no stage direction, no "describe the
   picture" caption, no webinar self-talk, no "this is a workbook page" meta text.
5. ANATOMICAL ARTIFACTS — no people are in frame (representation_mix), so none may appear:
   no fused hands, no malformed anatomy, no distorted facial features, no mismatched eyes.
6. BACKGROUND COMPETING WITH TEXT — no busy/cluttered background, no pattern or texture
   under the text zones; keep generous negative space and high contrast on every quoted
   line; a soft scrim behind text where needed.
7. DEMOGRAPHIC/SKIN-TONE FIDELITY — no demographic default, no skin-tone drift; honor the
   client's captured representation_mix verbatim.
8. CARRIED-FORWARD UNIVERSAL BASELINE — no watermark over content, no emoji, no clipart,
   no default font (Calibri/Arial/Times), no em dash, no system UI artifact, no pure-black
   fill. All text in the {FONT_CHARACTER} family, sizes per the TYPE SPEC.

=== COMPOSITION / TYPE SPEC ===
Thirds grid; the headline is the hero on content pages; reading order = headline → subhead
→ bullets → question/answer → footer. Brand hex: {PRIMARY_HEX}, {SECONDARY_HEX},
{ACCENT_HEX}, {BASE_HEX}, {INK_HEX}. Headline {HEADLINE_SIZE}pt BLACK, subhead
{SUBHEAD_SIZE}pt ExtraBold, body {BODY_SIZE}pt Medium. 8th-row readability: the headline
must still read when the page is shrunk to 25%.

=== QUALITY ===
Crisp 2K edges, flat clean editorial-print aesthetic, professional corporate workbook page,
high information density of DESIGN (content + brand), soft even tone, consistent with the
attached reference page. Portrait 3:4 at 2K. No crop, no letterbox, uniform lighting, no
competing visual firsts. The page reads as a premium, finished companion — not a blank
shell.

=== DETERMINISTIC VARIANT (page {INDEX} of {TOTAL}) ===
Rotate exactly ONE accent placement per page (motif position cycles top-right → bottom-left
→ above-footer). Nothing else rotates: palette, band structure, zone geometry, footer, and
logo placement are identical across pages so the set reads as one designed system.

=== STYLE-REFERENCE DIRECTIVE (I2I pages only, verbatim) ===
Use the attached images only as style reference for color grading, lighting, and composition
— do not copy their subjects, faces, or text.  (Do NOT copy the reference page's baked text.)
```

---

## 2. VERIFICATION GATE (before any submit)

Every workbook page prompt MUST clear:

1. **`workbook_builder._assert_content_in_prompt(page, prompt)`** — the
   **AF-WORKBOOK-PROMPT-NO-CONTENT** fail-closed PRE-SUBMIT gate. It REFUSES (RuntimeError,
   named AF-WORKBOOK-PROMPT-NO-CONTENT) when ANY of:
   - the prompt carries the literal wireframe directive (`BACKGROUND ONLY`, `NO text`,
     `NO labels`, `NO words`, `NO placeholder content`, …) — the old background-only
     language is banned by construction;
   - the page carries **ZERO content strings** (`content` block empty / absent) — the
     content-empty regression, blocked so it cannot spend a paid render;
   - any of the page's `content_strings` is **NOT baked into the prompt verbatim**
     (whitespace-normalised) — mirrors build_deck's AF-P-VERBATIM.
   Wired at the top of `submit_page()` (transport) AND in `main()` before design.
2. **`prompt_gate.verify_prompt(prompt, slide_id=...)`** — the shared Presentations rich
   gate: >=9,000 and <=18,000 stripped chars, structural blocks (`[ARCHETYPE ...]` /
   `DO-NOT BLOCK` / `Do not `), 8-class negative block, spelling-lock, HEX palette,
   type-size token, composition token, >=220 distinct words. The `[ARCHETYPE ...]` line is
   the structural-block anchor.
3. **`workbook_builder._assert_prompt_band(prompt, page_id)`** — the executor's own band
   floor/ceiling wrapper around the above.

Prove it with the shared gate module (this is the same gate `kie_generate.py` calls):
```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "scripts")
import workbook_builder as wb
import prompt_gate as pg

brand = {"primary": wb.DEFAULT_PRIMARY, "secondary": wb.DEFAULT_SECONDARY,
         "accent": wb.DEFAULT_ACCENT, "base": wb.DEFAULT_BASE, "ink": wb.DEFAULT_INK}
content = {
    "headline": "Rule 1 - Name the offer in one sentence",
    "subhead": "If they cannot say what it is, they cannot say yes.",
    "bullets": [
        "A one-sentence offer forces a decision.",
        "Clarity beats complexity.",
        "The friction to buy is what kills the deal.",
    ],
    "affirmation": "My offer in one sentence is:",
}
prompt = wb.build_page_prompt(page_role="TEACHING - RULE 1", motif_position="top-right",
                              brand=brand, client_name="ACME", is_i2i=True, page_index=3,
                              page_count_total=9, content=content)
wb._assert_content_in_prompt({"id": "TEACH-01", "content": content}, prompt)  # no raise
pg.verify_prompt(prompt, slide_id="TEACH-01")                                  # no raise
print("PASS: content-in-image prompt clears AF-WORKBOOK-PROMPT-NO-CONTENT + rich gate")
PY
```
**Guard adversarial proofs** (the suite covers these — `tests/test_workbook_builder.py`):
- a page with ZERO content strings → `_assert_content_in_prompt` raises
  AF-WORKBOOK-PROMPT-NO-CONTENT (the background-only regression);
- a prompt carrying `BACKGROUND ONLY` / `NO text` / `NO labels` → raises, even when content
  is attached;
- a prompt missing one content string verbatim → raises (mirrors AF-P-VERBATIM).

**Stripped-char counting:** strip code fences and Markdown backticks before measuring the
9,000–18,000 band; a rendered prompt (the JSON-escaped string actually sent to kie.ai) is
measured raw.

---

## 3. CONCRETE EXAMPLE — a Rule-1 teaching page (§2.4 of the redesign)

The teaching page for Rule 1 accompanies deck slide 7. The mapper's content strings are
pulled verbatim from `working/copy/slides_copy.md` (SLIDE 7) and the speech; the palette is
the deck's real brand (`#F5EDE3` base / `#C0653C` terracotta accent / `#C9A227` money
accent / `#3D2B1F` ink; Montserrat; no people). The exact generated prompt for this page is
produced by `build_page_prompt(...)` with the content block in the verification snippet
above — it lands ~9,500 chars and carries every content string verbatim, then passes
`AF-WORKBOOK-PROMPT-NO-CONTENT` and the full rich gate.

---

## 4. FILE REFERENCES

- Executor: `scripts/workbook_builder.py` (this directory) — `build_page_prompt`,
  `_assert_content_in_prompt`, `_page_content_strings`.
- Redesign spec: `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-REDESIGN-PLAN.md` (§2 skeleton,
  §4.2 gate).
- Sample deliverable: `~/Downloads/WORKBOOK-SAMPLE.pdf`.
- Research (full API + stack decision): `~/Downloads/GAUNTLET-LOOP-WORK/WORKBOOK-PDF-RESEARCH.md`.
