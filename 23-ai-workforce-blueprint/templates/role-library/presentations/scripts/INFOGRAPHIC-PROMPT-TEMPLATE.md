# INFOGRAPHIC PROMPT TEMPLATE — the 15-element contract for the one-page infographic

**Scope:** Presentations department P8.3-INFOGRAPHIC (MASTER-ASSESSMENT-AND-FIX-PLAN.md
Part 8, **FIX 2 — give the infographic a producer**). Every presentation from the
Content-to-Presentation Architect (or any deck whose `deliverable_bundle.checklist_items`
contains `"infographic"`) ships a single branded one-page infographic as
`working/deliverables/infographic.png` — the `infographic_png` deliverable
(102,400-byte floor) that every completeness gate (build_deck DELIVERABLES_REQUIRED,
PIPELINE-MANIFEST deliverables_required, fix_bundle_complete AF-BUNDLE-INCOMPLETE)
requires, and which until FIX 2 had **no producer at all**.

**Who authors this prompt:** role `slide-image-creator` (SOP 9.10), phase 2, after all
regular per-slide prompts are authored (SOP 9.1 complete).

**Who renders it:** `scripts/build_infographic.py` — the deterministic producer
(manifest phase P8.3-INFOGRAPHIC, order 8.3, kind script). It reads this prompt
**VERBATIM**, gates it through the SAME shared rich-prompt gate slide prompts pass,
submits it through the canonical Kie path at 9:16 portrait 1440x2560, poll-downloads,
verifies the PNG magic + 102,400-byte floor, writes the deliverable, and records the
Kie task id in `working/checkpoints/pending_tasks.json`. **The producer never composes
its own prompt. The renderer never silently falls back to a thin prompt.**

**Band:** **9,000–18,000 stripped chars** — the same hard floor (AF-P1) and ceiling
(AF-P2) slide prompts carry. Author to at least 9,000; the spelling-locked checklist
body + full 8-class negative block naturally exceed it. Target 9,000–14,000.

**Orientation (the one deliberate override):** this output is **9:16 portrait
1440x2560 at 2K — NOT a slide.** SOP 9.10 element (a): "Create a 9:16 portrait image at
2K resolution (1440x2560 pixels). This is a one-page infographic, NOT a presentation
slide." Every other rule (layout grid, typography law, palette, logo, negative block,
spelling-lock) is identical to a slide prompt.

---

## 0. PARAMETERS (fill the {braces} before authoring)

| Token | Meaning |
|---|---|
| `{ARCHETYPE}` | `A4` TYPE-DOMINANT PUNCH — a one-page infographic is ONE slide, type-dominant, with an embedded structured list |
| `{CLIENT_NAME}` | client/company display name (wordmark + footer) |
| `{OFFER_NAME}` / `{TRANSFORMATION_PROMISE}` | the deck's core promise — the infographic HEADLINE source |
| `{CHECKLIST_ITEMS}` | each item from `deliverable_bundle.checklist_items`, numbered/checked, **NOT one item** (a single-item list is a director escalation per SOP 9.10) |
| `{FINAL_PRICE}` | the price chip (verbatim, spelling-locked) |
| `{FORMAT}` | `checklist` \| `process` (declared in infographic_status.json step 2) |
| `{PRIMARY_HEX}` / `{SECONDARY_HEX}` / `{ACCENT_HEX}` / `{BASE_HEX}` / `{INK_HEX}` | brand palette, exact hexes |
| `{FONT_CHARACTER}` | typography character (e.g. "Montserrat geometric editorial sans") |
| `{LOGO_PLACEMENT}` | per STYLE BLOCK — typically lower-right, ~9% slide width, 1px gold border, ≥5% from edges |
| `{LOGO_URL}` | the LOCKED logo URL — pass via `input_urls` (Mode B image-to-image), never described in words |
| `{SOURCE_STAT}` | any Category B/C stat from `working/research/brief-[DECK_SLUG].md` (optional, cited) |

**Verbatim source (never paraphrase):** `working/copy/slides_copy.md` (approved copy),
intake.json (`OFFER_NAME`, `TRANSFORMATION_PROMISE`, `FINAL_PRICE`, `checklist_items`),
the STYLE BLOCK. The infographic **distills** the deck's core promise + checklist — it
does not invent copy.

---

## 1. THE TEMPLATE — the 15-element contract (SOP 9.1 elements 1–15, with the SOP 9.10 infographic-specific rules)

Author to >=9,000 chars. Every element present, in this exact order. Each verbatim
string carries its spelling-lock sentence immediately after it.

```
[ARCHETYPE A4] [SECTION: ONE-PAGE INFOGRAPHIC] [LADDER: TYPE-DOMINANT PUNCH + EMBEDDED STRUCTURED LIST]
ONE BIG IDEA: {TRANSFORMATION_PROMISE} — one vertical page the audience keeps.

=== 1. FORMAT ===
Create a 9:16 portrait image at 2K resolution (1440x2560 pixels). This is a one-page
infographic, NOT a presentation slide. Full-bleed vertical poster. The page reads top to
bottom in one pass: promise headline, the checklist/framework, the price chip, the footer.

=== 2. BACKGROUND ===
White base background. {ACCENT_HEX} used only as accent elements (no more than 20% of the
visual area) — section rules, check badges, the price chip. {BASE_HEX} for the quiet
content panels. No dark background, no navy/black/charcoal fill (DARK_OK=false on the
infographic).

=== 3. HEADLINE VERBATIM (SPELLING-LOCK — element a of SOP 9.10) ===
The headline reads exactly: "{TRANSFORMATION_PROMISE}". This text is the primary
typographic element. Place it in the upper third per the thirds grid.
Render this exact string, letter-for-letter, correctly spelled, with no added, dropped,
doubled, or substituted characters: "{TRANSFORMATION_PROMISE}". Do not alter, misspell,
duplicate, abbreviate, translate, or garble any character of it.
The ONLY baked text is the verbatim copy below (headline, checklist items, price line,
one footer line) plus the {CLIENT_NAME} wordmark and the logo chip. NEVER bake a scene or
image description as the headline, and no "webinar" word, no narrator line, no stage
direction, no "[bracketed token]", no "owner to confirm", no "TBD" as rendered copy.

=== 4. TYPOGRAPHY LAW (designed type, never basic) ===
One typeface family: {FONT_CHARACTER}. Hierarchy by WEIGHT, never by mixing typefaces.
Headline and giant numbers in {FONT_CHARACTER} Black; checklist items in ExtraBold;
kicker/price labels in Bold (gold, letter-spaced); footer line in Regular. Every text line
declares its exact weight AND a large pt size relative to the 2560px height: hero headline
62-86pt, checklist items 24-28pt, price chip 34-42pt, kicker label ~13pt, footer 11-13pt.
The typography is designed INTO the image as part of the composition (text baked into the
pixels as rendered designed type), not a basic font dropped on top. Basic or default fonts
(Calibri, Arial, Times, system default) are forbidden.

=== 5. FONT PLACEMENT (type-dominant punch) ===
Type-dominant: the headline dominates the upper third; the checklist occupies the middle
band on a quiet {BASE_HEX} panel; the price chip sits in the lower third; the logo chip is
bottom-right. The page is one designed vertical poster — never a slide cropped to
portrait. No text within 5% of any edge. No hook refrain and no italic tertiary breathing
line (this is not a hook slide and the type card does not call for them).

=== 6. THIRDS GRID ===
Using the rule of thirds: the vertical thirds divide the poster into the promise zone
(upper third), the checklist zone (middle third), and the close zone (lower third: price
chip + footer). Text and badges align to the grid; no element crosses a third boundary
mid-line.

=== 7. OBJECT PLACEMENT ===
Check/step badges: a gold check-mark or numbered badge to the LEFT of each checklist row,
in {ACCENT_HEX}, aligned to the grid. Price chip: a {SECONDARY_HEX} bordered panel in the
lower third. Logo: the LOCKED reference logo at {LOGO_PLACEMENT} — do not redraw, recolor,
or restyle it (Mode B, image-to-image, `input_urls` first entry). Objects never overlap
the headline or any checklist row text.

=== 8. OVERLAYS ===
No text overlays on this page beyond the verbatim copy and the {CLIENT_NAME} wordmark. No
hook footer band, no translucent strip, no "{FORMAT}" label drawn over the artwork.

=== 9. BRAND PALETTE ===
Primary accent: {PRIMARY_HEX} — header band + footer rule. Secondary: {SECONDARY_HEX} —
section rules, badge borders, the price chip panel. Accent: {ACCENT_HEX} — one geometric
motif, the check badges, the emphasis words in the checklist. Base: {BASE_HEX} — the
content panel behind the checklist. Ink: {INK_HEX} — all text ink. White base background
throughout. No dark or navy backgrounds.

=== 10. LOGO (ONE locked mark, image-to-image) ===
The first reference image is the company logo (Mode B, `gpt-image-2-image-to-image`,
LOGO_URL as the first entry of `input_urls`): place it {LOGO_PLACEMENT}; do not redraw,
recolor, restyle, reinterpret, or invent it — reproduce the supplied mark pixel-for-pixel.
The only mark on the page is the supplied reference logo. NEVER describe the logo in words
for a text-to-image generation.

=== 11. PEOPLE (no people — this is a type-dominant poster) ===
No people are in frame and none may appear: no faces, no anatomical forms, no fused hands,
no malformed anatomy, no distorted facial features. The page communicates through the
designed type and the checklist structure, not through a person. (The
representation_mix from the casting ledger is honored elsewhere; this page carries none
because it depicts no people — state that explicitly, do not default.)

=== 12. BULLETS / CHECKLIST BODY (element c of SOP 9.10 — the body of the page) ===
Each checklist item is a numbered or checked row in {FONT_CHARACTER} ExtraBold, 24-28pt,
with a gold check-mark or numbered badge to the left. Items are max 5 words each; no full
sentences. SPELLING-LOCK EACH ITEM VERBATIM, in this exact form, immediately after the
item:
Render this exact string, letter-for-letter, correctly spelled, with no added, dropped,
doubled, or substituted characters: "{CHECKLIST_ITEM_1}". Do not alter, misspell,
duplicate, abbreviate, translate, or garble any character of it.
(Repeat the spelling-lock sentence after every checklist item. Never skip them to save
space — the structured body is what expands the prompt past the 9,000-char floor.)

=== 13. MOOD (one felt beat) ===
{A MOOD: aspirational / clarifying / confident}. This one-page infographic carries the
deck's core promise as a single felt beat — READABLE IN 2 SECONDS without narration. The
visual energy feels {described} to {target audience from intake.json}. The page is a
takeaway the audience keeps: clear, designed, premium.

=== 14. PROFESSIONALISM (the standalone-art gate, SOP 9.6) ===
Production quality: this page must read as a finished, gallery-grade STANDALONE PIECE OF
ART, complete on its own with no other slide for context. Intentional art direction
(focal hierarchy, negative space, depth of field in the type hierarchy), premium editorial
design (never stock, clipart, or cartoon), the large creative typography composed INTO the
image as part of the composition (not pasted on top). Magazine-grade. No watermarks. No
blur. No "just a background with text". This image is one you could frame and hang.

=== 15. CLOSING CONSTRAINTS (the MANDATORY PAIRED NEGATIVE-PROMPT BLOCK, SOP 9.8) ===
DO-NOT BLOCK (the 8 defect classes, named — one imperative sentence each; every critical
negative has its positive twin stated earlier in this prompt):
1. GARBLED/MISSPELLED TEXT — Do not misspell, garble, phonetically drift, or truncate any
   quoted string; render every quoted string letter-for-letter, exactly as written
   (positive twin: element 3 + the per-item spelling-locks).
2. LOGO MUTATION — Do not invent, redesign, or substitute any logo, monogram, icon, leaf,
   sprout, tree, mountain, badge, roundel, or tagline lockup; the only mark on the page is
   the supplied reference logo (positive twin: element 10, Mode B).
3. PLACEHOLDER/BRACKET TOKENS — Do not render any bracketed token, "owner to confirm",
   "insert", "TBD", "placeholder", "client win", "endorsement", "real result", "to
   supply", or "pending" as copy; every string is the client's approved verbatim copy
   (positive twin: element 3).
4. IMAGE NARRATION/PRESENTER/META — Do not render a narrator line, a stage direction, a
   "describe the picture" caption, a webinar self-talk line, or any meta text about the
   infographic itself; the page carries only the approved copy (positive twin: elements 3
   and 8).
5. ANATOMICAL ARTIFACTS — Do not render any person, face, fused hand, malformed anatomy,
   distorted facial feature, mismatched eye, or distorted teeth; no anatomy appears on
   this type-dominant poster (positive twin: element 11).
6. BACKGROUND COMPETING WITH TEXT — Do not use a busy, cluttered, or high-detail
   background, and do not place pattern or texture under any text zone; keep generous
   negative space and a soft {BASE_HEX} scrim behind the checklist so every quoted line
   reads at full contrast (positive twin: elements 2 and 7).
7. DEMOGRAPHIC/SKIN-TONE FIDELITY — Do not bake a demographic default, an inferred
   demographic, or any skin-tone/skin-tone-drift directive into this page (no
   representation_mix, no lighten/ashen/desaturate language); this poster depicts no
   people, so no demographic assignment applies (positive twin: element 11).
8. CARRIED-FORWARD UNIVERSAL BASELINE — Do not use a watermark, emoji, clipart, Calibri,
   Arial, Times New Roman, a system default font, a UI artifact, an em dash, or a
   pure-black fill anywhere; all text is in the {FONT_CHARACTER} family at the TYPE SPEC
   sizes (positive twin: elements 4 and 9).
Do not substitute, omit, reorder, or shorten any verbatim string. Do not letterbox, crop,
or upscale-compress the page. Do not add a second page, a fold line, or a QR placeholder.
```

---

## 2. VERIFICATION GATE (before any submit — the producer runs this, prove it yourself)

Two gates, both mechanically enforced by `build_infographic.py`:

1. **`resolve_prompt()` (SOP 9.10 step 4/5)** — the file must exist at
   `working/prompts/infographic-prompt.txt`, be >=9,000 chars, and be read VERBATIM.
2. **`prompt_gate.prompt_problems()` (SOP 9.10 step 5 — the SHARED rich-prompt gate).**
   The SAME accumulating gate slide prompts pass. A prompt that would be refused for a
   slide is refused for the infographic — one gate, both formats. It checks:
   - length band 9,000–18,000 stripped chars (AF-P1 / AF-P2),
   - structural blocks: `[ARCHETYPE` / `DO-NOT BLOCK` / `Do not ` (AF-P1),
   - the 8-class paired negative block, one imperative each (AF-P13),
   - a per-string spelling-lock directive on every verbatim string (AF-P14),
   - prompt density: brand palette HEX (#RRGGBB), an explicit type-size token (e.g.
     `24-28pt`), a composition/zone token (thirds grid, zone, safe margin, quadrant),
     >=220 distinct words (AF-P-DENSITY),
   - no demographic default landmine (AF-R3, e.g. "default demographic"), no dead
     endpoint fragment, no em dash usage (the universal baseline class lists 'em dash').
   The gate-hard **submit** phase additionally rides `ensure_english_pin` (the English /
   Latin anti-garble pin) on the payload — belt-and-braces, same as every slide render.

Prove the template clears it with the shared module (this is exactly what the producer
calls — no special-casing):

```python
import sys
sys.path.insert(0, "scripts")
import prompt_gate as pg
import build_infographic as bi

prompt = open("working/prompts/infographic-prompt.txt").read().strip()
assert len(prompt) >= bi.PROMPT_CHAR_FLOOR, "under the 9,000-char hard floor (AF-P1)"
problems = pg.prompt_problems(prompt)   # empty list = clears the whole gate
assert not problems, "rich-prompt gate: " + "; ".join(problems)
print("PASS: infographic prompt clears the shared rich-prompt gate",
      f"({len(prompt):,} chars, {len(prompt.split()):,} words)")
```

Wait — no "em-dash" usage in the prompt body. The word "em dash" is permitted ONLY as a
prohibition inside the negative block. Check with a human eye, then run the one-liner
above.

**Stripped-char counting:** strip code fences and Markdown backticks before measuring the
9,000–18,000 band; a rendered prompt (the JSON-escaped string actually sent to kie.ai) is
measured raw.

---

## 3. CONCRETE EXAMPLE — a converter-origin checklist infographic (the deck-12 fixture)

A converter-origin deck with `checklist_items` built from the content-to-presentation
pass: `OFFER_NAME = "The Clarity System"`, `TRANSFORMATION_PROMISE = "From scattered
ideas to a clear, sellable offer in one sitting"`, `FINAL_PRICE = "$497"`, a brand
palette `#F5EDE3` base / `#C0653C` terracotta accent / `#C9A227` money accent / `#3D2B1F`
ink, Montserrat. The checklist items (5): "Name the offer", "Price the outcome",
"Remove the friction", "Write one proof line", "Say yes comfortably". A page 3-level
design: promise headline (upper third), the five checklist rows with gold check badges
(middle band on a `#F5EDE3` panel), the `$497` price chip + footer + logo chip (lower
third).

The prompt above, with those {braces} filled and the five per-item spelling-lock
sentences, lands ~10,500 chars — comfortably inside the 9,000–18,000 band, carrying every
verbatim string with its lock, the full 8-class negative block, the `#RRGGBB` hexes,
`24-28pt` type-size tokens, thirds-grid composition tokens, and >400 distinct words. It
clears `prompt_gate.prompt_problems()` with an empty list and is submitted VERBATIM by
`build_infographic.py` at 9:16 1440x2560 (t2i; the logo rides Mode B `input_urls` when
LOGO_ON_SLIDES=true).

**What the producer writes on success** (the FIX 2 proof, QC.md FIX 2):
- `working/deliverables/infographic.png` — exists, >=102,400 bytes, PNG magic first 4
  bytes `\x89PNG`,
- `working/checkpoints/pending_tasks.json["infographic"].task_id` — the Kie task id,
- status + warning records in `working/checkpoints/infographic_status.json`,
- and the bundle gate (fix_bundle_complete) no longer names `infographic_png` as missing.

---

## 4. FILE REFERENCES

- Producer: `scripts/build_infographic.py` (this directory) — `resolve_prompt`,
  `submit_task`, `poll_task`, `download_image`, `verify_png`,
  `working/checkpoints/pending_tasks.json["infographic"]`.
- Authoring SOP: role `slide-image-creator.md` SOP 9.1 (15-element spec, elements 1–15)
  and `sops/slide-image-creator-sops.md` SOP 9.10 (one-page infographic: elements a–e,
  steps 1–9) + SOP 9.8 (the paired 8-class negative block).
- Shared gate: `scripts/prompt_gate.py` (PROMPT_CHAR_FLOOR=9000, PROMPT_CHAR_CEILING=18000,
  REQUIRED_STRUCTURAL_BLOCKS, NEGATIVE_BLOCK_CLASS_TOKENS, SPELLING_LOCK_TOKENS,
  PROMPT_COMPOSITION_TOKENS, FORBIDDEN_DEMOGRAPHIC_DEFAULTS, verify_prompt/prompt_problems).
- Renderer precedence: `scripts/build_deck.py` (the canonical slide path this mirrors) —
  DELIVERABLES_REQUIRED + PROMPT_CHAR_FLOOR + AF-P-VERBATIM + pending_tasks U028 shape.
- Manifest floor: `PIPELINE-MANIFEST.json` `infographic_png` min_bytes 102,400.
- Master plan: `MASTER-ASSESSMENT-AND-FIX-PLAN.md` Part 8 FIX 2 (P8.3-INFOGRAPHIC, order
  8.3, kind script, budget 30).
