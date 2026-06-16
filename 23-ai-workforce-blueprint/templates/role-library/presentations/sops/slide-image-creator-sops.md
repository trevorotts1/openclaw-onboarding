# SOPs Mirror -- Slide Image Creator

**Source:** presentations/slide-image-creator.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Per-Slide Prompt Authoring (15-Element Spec)

**When to run:** Phase 2 -- after slides_copy.md is approved by the owner (Phase 1A) and STYLE BLOCK is confirmed.

**Inputs:**
- working/copy/slides_copy.md (approved copy for every slide)
- STYLE BLOCK (brand palette, type system, logo rule, representation ratio)
- working/copy/hook_variants.json

**Steps:**
0. **Read the master SOP Section 7.5 gold-standard exemplar in full before writing your first prompt.** This is the actual prompt that produced the title slide of the QC-9.42 gold-standard reference deck. Study its anatomy: the header block (title, ARCHETYPE / SECTION / LADDER tags, ONE BIG IDEA line), zone percentages, emotionally precise photo direction, exact verbatim copy with per-line font/size/color, the gold rule devices, the logo chip spec, MOOD + LIGHTING, and the closing COLOR VERIFICATION and AVOID blocks. Also read the SECOND exemplar in the appendix of this file (Section 9.5 strengthening, the A2 people-slide exemplar). Your prompts must match their density and structure, adapted to each slide's own archetype and brand variables. Do not write a single prompt before you have read both.
1. For each slide N, create working/prompts/slide-NN-prompt.txt (zero-padded number, e.g., slide-01-prompt.txt). **Line 1 of every prompt declares its archetype**, in the form `[ARCHETYPE A1] [SECTION: ...] [LADDER: ...]` followed by a ONE BIG IDEA line, exactly as the master 7.5 exemplar does. The archetype is taken from the slide's ARCHETYPE field in slides_copy.md (A1-A5 per SOP 9.2).
2. Write the 15-element prompt in this exact order. Each element must be present:
   1. **FORMAT**: "Create a 16:9 presentation slide image at 2K resolution (2560x1440 pixels)."
   2. **BACKGROUND**: "White base background. [Brand accent color] used only as accent elements (no more than 20% of the visual area)."
   3. **HEADLINE VERBATIM**: "The slide headline reads exactly: '[HEADLINE from slides_copy.md]'. This text is the primary typographic element. Place it in [position per thirds grid]."
   4. **TYPOGRAPHY**: "[Font name from STYLE BLOCK] for headlines. [Font name] for body text. Type is [size guidance based on slide section -- e.g., large 60-80pt for hero slides, 40-50pt for content slides]."
   5. **FONT PLACEMENT**: "Headline text is anchored [top-left / center / bottom-left per thirds grid]. Body text [if any] is below the headline with [spacing guidance]. No text appears within 5% of any edge."
   6. **THIRDS GRID**: "Using the rule of thirds: primary visual element in [upper-right / lower-left / center-right] region. Text occupies [upper-left / center-left] region. This creates clear visual tension and hierarchy."
   7. **OBJECT PLACEMENT**: "[Specific objects: product images, icons, diagrams, charts] placed in [specific region]. Objects must not overlap the headline text."
   8. **OVERLAYS**: "**(Density-floor overhaul) There is NO hook footer band. DELETED.** The hook is NEVER rendered as a bottom strip/band on any slide. The hook renders ONLY as the type-dominant content of its 3 to 4 DEDICATED pure-typography slides (treatment_table PURE_TYPE_HOOK: the hook line large over a low-opacity image, nothing else). On every non-hook slide write: 'No text overlays on this slide beyond the headline. No hook footer band.' The old bottom-15%-strip hook rendering produced the reference failure case 40-slide footer-stamping and is banned (AF-I8 / AF-HOOK-2)."
   9. **BRAND PALETTE**: "Primary accent: [HEX1, role from STYLE BLOCK]. Secondary accent: [HEX2, role]. Tertiary: [HEX3, role]. All backgrounds remain white. No dark backgrounds. No navy, black, or charcoal backgrounds unless DARK_OK=true."
   10. **LOGO (image-to-image, density-floor overhaul)**: when LOGO_ON_SLIDES = true, the locked LOGO_URL is passed as the first reference in `input.input_urls` and the prompt names it: 'The first reference image is the company logo: place it [per STYLE BLOCK placement], do not redraw, recolor, or restyle it.' NEVER describe the logo in words for text-to-image generation (that reinvents the mark per slide, the reference failure case logo-mutation defect). One locked mark, composited identically on every slide. See universal-sops/presentation-image-library/SOP-IMG-01 Mode B and presentation-design-system/05-SOP-logo-consistency.md. AF-P9/P10/P11 fail a logo drawn text-to-image or a missing 'do not redraw' instruction; AF-I4/AF-I11 fail a rendered mark that differs from the locked asset."
   11. **PEOPLE (driven by the THREE ENGINES, transplanted from master SOP Section 7.3 element 11; all three required on every people-slide, missing any one is an auto-fail):**
      - **FACIAL EXPRESSION ENGINE:** the face must match what the slide is SAYING. Every person spec includes hair (color, style, length), clothing (color, style, formality), and a facial expression described in terms of the emotion the slide communicates (a pain slide gets a worried, overwhelmed face; a vision slide gets the arrived, relieved smile). The expression is stated in explicit emotion terms, never just "smiling." Use the Expression Vocabulary Table (SOP 9.2 strengthening pack) to pick the exact expression for the slide's emotion. Missing hair, clothing, OR the expression = auto-fail.
      - **AUDIENCE ENGINE:** people match the slide's REPRESENTATION_MIX assignment and AUDIENCE from intake (the representation group, age range, gender mix, and the style of dress for the niche). The diversity spec comes from the STYLE BLOCK representation_ratio (e.g., 70% African American women, 20% African American men, 10% mixed) and the deck-wide ratio is honored across slides, not forced onto every single slide.
      - **WORLD ENGINE (real-world knowledge):** the SETTING matches the industry and the moment. Where would this person actually be: their office, the kitchen table at dinner, the empty classroom at 6am? Every people-slide prompt STATES the real-world setting AND justifies why it fits the slide's one idea. Pull the setting from the Lighting + World Library (SOP 9.3 strengthening pack). A generic studio backdrop where a real-world scene belongs is a defect and an auto-fail.
      - **SHOT layer (taxonomy beneath the engines, not a replacement for them):** under the three engines, also pick the shot framing for the person. Engine A (Single Subject): one person, full-body or three-quarter shot. Engine B (Audience Group): a small group of 2 to 4 people, natural energy, not a posed stock photo. Engine C (Presenter / Speaker): one person presenting or teaching, confident posture, reads as a knowledgeable guide not a salesperson. The shot layer answers "how is the person framed"; the three engines above answer "what does the person feel, who are they, and where are they". Both layers must be present on a people-slide."
   12. **BULLETS** (if slide has bullet points): "Body text bullets are short, no full sentences. Each bullet is max 5 words. Bullets appear as [dot / dash / icon] markers."
   13. **MOOD**: "[Emotional tone for this slide: e.g., aspirational, urgent, celebratory, authoritative]. The visual energy should feel [descriptor] to [target audience descriptor from intake.json]."
   14. **PROFESSIONALISM**: "Production quality: magazine-grade photography or polished digital illustration. No amateur stock photo aesthetic. No watermarks. No blur. Sharp focus on the human subject if people are present."
   15. **CLOSING CONSTRAINTS (AVOID BLOCK)**: "AVOID: dark backgrounds, shadowed images, grainy textures, busy patterns, more than 3 colors, any watermark, any em dash, any text not specified in this prompt, image elements that extend into the border zone."
3. Verify character count of the completed prompt. Target: 5,000-7,500 characters. Minimum: 1,500. Maximum: 15,000. If under 1,500, the prompt is too sparse -- expand the MOOD, PEOPLE, and OBJECT PLACEMENT elements. If over 15,000, trim the AVOID block and MOOD sections.
4. Verify: is the HEADLINE VERBATIM text exactly as it appears in slides_copy.md? Copy-paste, do not paraphrase.
5. Verify: no em dashes in the prompt. (The word "em-dash" or "--" in the AVOID block is acceptable as a prohibition, not a usage.)
6. Verify: BACKGROUND is white base unless DARK_OK = true.
7. After all slides are written, run a batch self-check:
   a. Count: all 15 elements present in every prompt (if any are missing, the prompt fails the SOP).
   b. Character count in range for every prompt.
   c. No em dashes.
   d. No dark backgrounds (unless DARK_OK flag is set).

**Outputs:**
- working/prompts/slide-NN-prompt.txt (one file per slide, zero-padded)

**Hand to:** QC Specialist -- Presentations (Phase 3 prompt QC gate)

**Failure mode:** If the STYLE BLOCK is missing or incomplete (e.g., no HEX codes), halt. Do not invent brand colors. Notify the Director: "Phase 2 blocked -- STYLE BLOCK is missing [specific fields]. Brand Steward must complete before prompts can be written."

---

### SOP 9.2 -- The Five Proven Archetypes, Thirds-Grid, and Composition

**When to run:** Within SOP 9.1 -- applied during step 1 (archetype declaration on line 1) and steps 6-7 (THIRDS GRID and OBJECT PLACEMENT elements).

**Inputs:**
- The slide's ARCHETYPE field (A1-A5) from slides_copy.md (assigned in Phase 1)
- Slide type and section derived from arc_allocation.json section label
- Subject matter (people-focused, text-focused, or diagram-focused) derived from slides_copy.md

**THE FIVE PROVEN ARCHETYPES (primary, transplanted from master SOP Section 7.2; the deck is built on exactly these five, rotated):**

The proven QC-9.42 deck was built on exactly FIVE layout archetypes, rotated across all slides. Every slide in Phase 1 is assigned one archetype (recorded in its slides_copy.md entry), and the prompt declares its archetype in its FIRST line. Rotating five strong layouts beats inventing a new layout per slide: the deck stays coherent AND varied.

| Code | Archetype | Layout definition | Best for |
|---|---|---|---|
| A1 | FULL-BLEED PHOTO + HEADLINE OVERLAY | One emotionally precise photo fills the frame; a soft white-to-transparent gradient scrim sweeps one region (typically the bottom 25 to 30%, heaviest on one side); the text group sits on the scrim with a kicker label, headline, sub-head, and thin gold rule | Future-pacing, vision slides, story beats, BUILDUP slides before drops, section moments with high emotion |
| A2 | PHOTO ONE SIDE + TEXT OPPOSITE | Vertical split, roughly 45/55: a person or scene occupies one side; the opposite side is clean base color carrying the full text group (kicker, headline, sub, body lines, rules) | Origin story, authority, testimonials, objection handling, teach slides featuring a person |
| A3 | PHOTO-TOP / DATA-BOTTOM | Horizontal split: full-width photo band on top (40 to 58%), separated by a clean full-width 3px gold rule, with a data/type zone below on the base color carrying a giant number or structured data. State the zone PERCENTAGES numerically (e.g., "top 58% photo band, bottom 42% type zone") | Painful Math, big numbers, stats, before/after rows, stack tables, proof metrics |
| A4 | TYPE-DOMINANT PUNCH (+ optional image band) | Typography IS the slide: an enormous headline or number dominates; optional supporting photo band on top or behind; price tag motifs and strikethrough ladders live here | Big Bold Promise, ANCHOR, every price DROP, the FINAL price reveal, commitment and recap punches, hook slides, big numbers |
| A5 | PORTRAIT / SELFIE (image-to-image) | The client's REAL founder portrait (supplied photo passed as an additional input image via gpt-image-2-image-to-image) drives the slide; text group beside or below | Host intro, "I'm you" slides, guarantee (founder holding certificate), final push direct-to-camera |

**Composition language inside each archetype:** zones are described in PERCENTAGES of the frame ("top 58% photo band," "bottom 42% type zone") PLUS thirds language for element placement within zones. Both are required on every prompt.

**Per-archetype mini-templates (the 10-line skeleton each prompt fills in; signature moves are mandatory):**

**A1 mini-template (FULL-BLEED PHOTO + HEADLINE OVERLAY):**
```
1  Line 1 tags: [ARCHETYPE A1] [SECTION: ...] [LADDER: ...] + ONE BIG IDEA line.
2  Canvas + base: 16:9, 2K, white/off-white base. NO black backgrounds anywhere.
3  Full-bleed photo brief: the emotionally precise scene that TELLS the one idea.
4  Photo emotional brief: the face/scene emotion in explicit terms (Facial Expression Engine).
5  Scrim direction + coverage %: soft white-to-transparent gradient scrim over the bottom 25-30%, heaviest on the [left/right] side, stated as a coverage percentage.
6  Text-group position: kicker label + headline + sub-head sit ON the scrim, in the [lower-left/lower-right] third.
7  Verbatim copy: every line quoted exactly, per-line font/weight/size/hex/alignment.
8  Brand devices: thin gold rule beneath the kicker; gold rule under the headline if used.
9  Logo chip spec + MOOD + LIGHTING paragraph (from the World/Lighting library).
10 COLOR VERIFICATION block + AVOID block.
```

**A2 mini-template (PHOTO ONE SIDE + TEXT OPPOSITE):**
```
1  Line 1 tags + ONE BIG IDEA line.
2  Canvas + base + NO black backgrounds.
3  Split ratio 45/55 stated numerically; declare WHICH side carries the person and WHY (e.g., person on the left 45% because the eye reads them first, then lands on the promise text on the right 55%).
4  Person brief via the three engines: hair + clothing + explicit expression (Facial Expression Engine), representation group (Audience Engine), real-world setting + justification (World Engine).
5  Base-color devices on the text side: kicker label, gold rule, body-line spacing on the clean base color.
6  Text group on the opposite side: kicker + headline + sub + body lines, in thirds.
7  Verbatim copy: every line quoted exactly, per-line font/weight/size/hex/alignment.
8  Brand devices: gold kicker rule, divider rules, any chips.
9  Logo chip spec + MOOD + LIGHTING paragraph.
10 COLOR VERIFICATION block + AVOID block.
```

**A3 mini-template (PHOTO-TOP / DATA-BOTTOM):**
```
1  Line 1 tags + ONE BIG IDEA line.
2  Canvas + base + NO black backgrounds.
3  Zone percentages stated NUMERICALLY: top X% photo band, bottom Y% type/data zone (X+Y=100, photo band 40-58%).
4  Photo band brief: the documentary-premium scene that carries the proof or context.
5  The 3px full-width gold rule as the divider between the photo band and the data zone.
6  Data hero at 3x scale: the giant number or structured data dominates the bottom zone, the hero number set roughly 3x the size of any supporting line.
7  Verbatim copy: hero number + label + supporting line, per-line font/weight/size/hex/alignment.
8  Brand devices: gold rule divider, any data chips or table rules.
9  Logo chip spec + MOOD + LIGHTING paragraph.
10 COLOR VERIFICATION block + AVOID block.
```

**A4 mini-template (TYPE-DOMINANT PUNCH):**
```
1  Line 1 tags + ONE BIG IDEA line.
2  Canvas + base + NO black backgrounds.
3  The TYPE EVENT: state what the typographic event is (an enormous headline, a hero number, a price). Type IS the slide.
4  Optional supporting photo band (top or behind) if used, stated with coverage %.
5  Tag motif IF this is a ladder slide: the white hang-tag with a gold border carrying the price (SOP 9.5).
6  Negative space as a FEATURE: state the breathing room around the type as intentional, not empty.
7  Verbatim copy: headline/number + sub + tertiary, per-line font/weight/size/hex/alignment.
8  Brand devices: gold breathing rules, kicker, banner box if a section opener.
9  Logo chip spec + MOOD + LIGHTING paragraph.
10 COLOR VERIFICATION block + AVOID block.
```

**A5 mini-template (PORTRAIT / SELFIE, image-to-image):**
```
1  Line 1 tags + ONE BIG IDEA line.
2  Canvas + base + NO black backgrounds.
3  Reference-image instruction (CRITICAL): state explicitly "the second reference image is the founder; her likeness drives the portrait" (the first reference is the logo). This is the gpt-image-2-image-to-image path; the founder portrait URL is passed in input.input_urls.
4  Wardrobe + backdrop pulled from the brand grammar (brand colors, the niche dress, the real-world setting per the World Engine).
5  Person brief via the three engines: hair + clothing + explicit expression, representation, real-world setting + justification.
6  Text-group position: kicker + headline + sub beside or below the portrait, in thirds.
7  Verbatim copy: every line quoted exactly, per-line font/weight/size/hex/alignment.
8  Brand devices: gold kicker rule, dividers, any chips.
9  Logo chip spec + MOOD + LIGHTING paragraph.
10 COLOR VERIFICATION block + AVOID block.
```

**Recurring brand devices (the proven deck's visual grammar, specify them explicitly in every prompt):**
- Kicker label: small all-caps letter-spaced label in gold or pink above the headline, with a short gold rule beneath it.
- Gold 3px full-width rule as the divider between photo and type zones.
- Color roles: gold = money, value, and dividers; pink/accent = action, emphasis words, and urgency; charcoal = headlines (never pure black backgrounds).
- Price tag motif: drops are rendered as a large white hang-tag shape with a gold border; old prices struck through with a DRAWN line in the brand accent (SOP 9.5); the new price glowing in accent at the bottom of the tag.
- Section progress labels on section-opener slides ("SECTION 3 OF 7", "SECRET #1" in a filled accent banner box).
- Logo on a white chip (~9% of slide width, subtle 1px gold border) in the same corner on every slide.
- Compliance line: any results/income claim slide carries a small italic disclaimer in the lower margin.

**FALLBACK slide-type table (use ONLY when a slide does not map cleanly to one of the five archetypes; pick the nearest archetype after using this to reason about composition):**

| Generic slide type | Default thirds-grid | Nearest proven archetype |
|---|---|---|
| Hero (hook, close, CTA) | text upper-left, large visual or person in right two-thirds | A4 (type punch) or A1 (full-bleed) |
| Content (mechanism, how-it-works) | text left half, diagram or illustration right half | A2 (photo one side + text) |
| Proof (testimonials, results) | person image left-center, quote text right-center | A2 (photo + text) |
| Price-drop | large price number centered and dominant, minimal other elements | A4 (type punch + tag motif) |
| Transition (section dividers) | centered single element, white space dominant | A4 (type punch, banner box) |

**Steps:**
1. Read the slide's ARCHETYPE field (A1-A5) from slides_copy.md. Declare it on line 1 of the prompt per SOP 9.1 step 1.
2. Open the matching per-archetype mini-template above and fill in its 10 lines, INCLUDING every signature move for that archetype (A1 scrim direction + coverage %; A2 the 45/55 split + which side carries the person + why; A3 the numeric zone percentages + the 3px divider + the data hero at 3x scale; A4 the type event + tag motif if a ladder slide + negative space as a feature; A5 the reference-image instruction + wardrobe/backdrop from brand grammar).
3. State zones in PERCENTAGES and element placement in THIRDS. Write the thirds-grid assignment into element 6 and the object placement into element 7.
4. If the slide does not map cleanly to one of the five archetypes, use the FALLBACK slide-type table to reason about composition, pick the nearest proven archetype, and declare that archetype on line 1 (never invent a sixth layout).
5. Verify: the headline text region and the primary visual region do not overlap. If they would overlap based on the composition plan, adjust the visual region.

**Outputs:**
- Archetype declaration on line 1; thirds-grid and object placement written into prompt elements 6 and 7; the archetype's signature moves present in the prompt body

**Hand to:** SOP 9.1 (these elements are written as part of the overall prompt)

**Failure mode:** If the slide content does not map cleanly to any of the five archetypes, use the FALLBACK table to pick the nearest archetype and add a note to the prompt: "Composition reasoned from fallback table; nearest archetype is [A1-A5]; image may need adjustment." Never invent a sixth archetype.

---

### SOP 9.2 strengthening -- Expression Vocabulary Table (the Facial Expression Engine's lexicon)

**When to run:** Within SOP 9.1 element 11, whenever the Facial Expression Engine needs the exact expression for a slide's emotion. The expression must match what the slide SAYS.

| Slide emotion | Expression to write (explicit terms) |
|---|---|
| Pain | brow tension, distant gaze, jaw set; the 2am-spreadsheet face |
| Recognition | eyes lifting, the "that's me" half-smile |
| Vision / future-pace | relieved, arrived, soft confident smile, shoulders down |
| Authority | direct to camera, settled, certain, no grin |
| Celebration | open-mouth joy, motion, hands up |
| Urgency / close | leaning in, serious warmth, hand extended |

Rule: never write "smiling" alone. Pick the row matching the slide's emotion and write the explicit expression terms. A smiling face on a pain slide is an auto-fail at image QC (master SOP 10.3 criterion 9). The expression on the face must match what the slide is saying.

---

### SOP 9.3 -- White-Base and Brand-Palette Application

**When to run:** Within SOP 9.1 -- applied during elements 2 and 9 (BACKGROUND and BRAND PALETTE).

**Inputs:**
- STYLE BLOCK (3 hex codes with roles, DARK_OK flag)
- intake.json (DARK_OK field, if present)

**Steps:**
1. Read the DARK_OK flag from intake.json. Default is false (white base required).
2. If DARK_OK = false:
   a. Element 2: "White base background. [PRIMARY_HEX] used only as accent elements. No more than 20% of visual area may be non-white."
   b. Element 9: list all 3 hex codes with their STYLE BLOCK roles (e.g., "Primary: #C4A44D [gold, headlines and CTA accents]. Secondary: #1A2B4C [navy, used for text only]. Tertiary: #FFFFFF [white, background -- dominant]").
   c. Explicitly prohibit navy, charcoal, black, and any dark background in element 15 (AVOID block).
3. If DARK_OK = true:
   a. Element 2: "Dark background permitted. Use [PRIMARY_HEX] as the dominant background. White text only."
   b. Element 9: list all 3 hex codes with dark-mode roles.
   c. Note in element 15: "Dark background is intentional per client instruction."
4. Write a COLOR VERIFICATION comment at the end of the prompt: "// COLOR VERIFICATION: PRIMARY=[HEX1], SECONDARY=[HEX2], TERTIARY=[HEX3], DARK_OK=[true/false]"

**Outputs:**
- Elements 2 and 9 of the prompt + COLOR VERIFICATION comment

**Hand to:** SOP 9.1

**Failure mode:** If STYLE BLOCK has fewer than 3 hex codes, halt and notify the Brand Steward and Director. Write `[COLOR PENDING]` in elements 2 and 9.

---

### SOP 9.3 strengthening -- Lighting + World Library (the World Engine's settings)

**When to run:** Within SOP 9.1 element 11, whenever the World Engine needs a real-world setting and lighting for a people-slide. The setting comes from the audience's real world, and the prompt STATES WHY the setting fits the slide's one idea.

**The lighting + world library (pick the row that fits the slide's idea, then justify it in the prompt):**

| Setting / lighting | Where it fits |
|---|---|
| Premium daylight studio | clean authority slides, recap punches, neutral teach slides |
| Golden-hour through real windows | vision/future-pace, story beats, the "this is what full looks like" moment |
| Bright editorial interior | proof slides, testimonials, modern-business energy |
| Soft morning kitchen light | the at-home buyer, the 6am-before-work moment, relatable pain or recognition |
| Clean overcast exterior | journey/roadmap slides, "the road ahead", honest neutral mood |

Rules:
- Settings come from the AUDIENCE'S real world (per the World Engine), not a generic studio backdrop where a real scene belongs.
- The prompt STATES the setting AND justifies WHY it fits the slide's one idea (e.g., "soft morning kitchen light, because this is the exact moment our audience feels the pain, before the day starts").
- A generic studio backdrop where a real-world scene belongs is a defect and an auto-fail at image QC.

---

### SOP 9.4 -- People (Three Engines + Shot Layer), Overlays, and Logo

**When to run:** Within SOP 9.1 -- applied during elements 10, 11, and 8 (LOGO, PEOPLE, OVERLAYS).

**Inputs:**
- STYLE BLOCK (representation_ratio, logo_placement_rule)
- working/copy/hook_variants.json (for overlay text)
- Slide type and section (from arc_allocation.json)

**Steps (People -- Element 11):**
1. The three engines are the authority for every people-slide and are written in element 11 per SOP 9.1: the FACIAL EXPRESSION ENGINE (hair + clothing + explicit expression from the Expression Vocabulary Table, SOP 9.2 strengthening), the AUDIENCE ENGINE (representation group, age range, gender mix, niche dress per the STYLE BLOCK ratio), and the WORLD ENGINE (real-world setting + justification from the Lighting + World Library, SOP 9.3 strengthening). All three are mandatory; missing any one is an auto-fail.
2. Beneath the three engines, pick the SHOT framing layer for this slide:
   - Shot A (Single Subject): one person, full-body or three-quarter shot.
   - Shot B (Audience Group): a small group of 2 to 4 people representing the STYLE BLOCK ratio, natural energy, not a posed stock photo.
   - Shot C (Presenter / Speaker): one person presenting or teaching, confident posture, reads as a knowledgeable guide not a salesperson.
3. Match the shot to the slide section: Hook/Close use Shot A or C. Proof slides use Shot A (testimonial subject). Audience/problem slides use Shot B. Speaker slides use Shot C. The shot layer answers "how is the person framed"; the three engines answer "what they feel, who they are, where they are".
4. Write the people description with BOTH layers present: the three engines first (expression, representation, world), then the shot framing.
5. Verify: representation ratio is honored across the deck as a whole. The Brand Steward tracks deck-level ratios; at the slide level, use the per-engine spec.

**Steps (Logo -- Element 10; density-floor overhaul: image-to-image, one locked mark):**
1. Read the logo_placement_rule from the STYLE BLOCK. Typical rule: "Logo in lower-right corner, approximately 9% of slide width on a white chip with a 1px gold border, no less than 40px from any edge, never recolored or distorted."
2. When LOGO_ON_SLIDES = true, write element 10 to PASS the locked LOGO_URL as the first reference in `input.input_urls` and name it in the prompt: "The first reference image is the company logo: place it [per the rule], do not redraw, recolor, or restyle it." NEVER text-to-image the mark. One locked asset, composited identically on every slide (the anti-mutation path; SOP-IMG-01 Mode B, design-system/05). If the logo carries text and it garbles twice on render, composite it natively at Phase 6 (master SOP 7.4 extended to the logo).

**Steps (Overlays -- Element 8; density-floor overhaul: NO hook footer band):**
1. **There is NO hook footer band.** The hook is NEVER rendered as a bottom strip/band on any slide. The hook renders ONLY as the type-dominant content of its 3 to 4 DEDICATED pure-typography slides (the treatment_table PURE_TYPE_HOOK rows: the verbatim hook line large over a low-opacity image, printed once, nothing else). The old bottom-15%-band rendering is DELETED (it produced the reference failure case 40-slide footer-stamping; AF-I8 / AF-HOOK-2 now auto-fail it).
2. On a dedicated hook slide, write the hook as the hero: "The verbatim hook line '[CANONICAL HOOK]' set very large in BLACK weight, centered, over a single low-opacity (8 to 15%) image; '[emphasis word(s)]' in [accent]; no other copy, no footer band, no second idea, printed exactly once."
3. On every non-hook slide write: "No text overlays on this slide beyond the headline. No hook footer band."
4. No overlays may cover the logo placement zone.

**Outputs:**
- Elements 8, 10, and 11 written into the prompt

**Hand to:** SOP 9.1

**Failure mode:** If STYLE BLOCK has no representation_ratio, use this default: 60% Black/Brown subjects, 30% other POC, 10% white, gender parity. Document the default in a comment in the prompt: `// REPRESENTATION: using default ratio (no STYLE BLOCK ratio specified)`.

---

### SOP 9.4 strengthening -- Density Calibration

**When to run:** Within SOP 9.1 step 3, when verifying the character count of every completed prompt.

**Inputs:**
- The completed prompt
- The master SOP Section 7.5 gold-standard exemplar (the density reference)

**Steps:**
1. Every prompt TARGETS 5,000 to 7,500 characters, calibrated against the master 7.5 exemplar (and the second A2 exemplar in Section 9.5 strengthening) as the density reference. The exemplars show what a fully art-directed prompt looks like; match that level.
2. If a prompt comes in UNDER 3,500 characters, trigger a self-check: is the BACKGROUND characterized beyond one word? Is the EXPRESSION written in explicit emotion terms? Is every OBJECT placed (box, banner, rule, chip, tag)? Is the MOOD + lighting stated? A thin prompt usually means one of these four was skimped.
3. Pad with SPECIFICITY, never filler. Add real art direction (a precise scene detail, a per-line font/size/hex, the exact setting and its justification, the strike rendered as a drawn object). Never pad with repeated boilerplate or vague adjectives to hit a number.
4. Hard limits still apply: under 1,500 characters is an auto-fail at prompt QC; over 15,000 is an auto-fail (the SOP maximum, a 5,000-char safety margin below the API ceiling of 20,000).

**Outputs:**
- Every prompt in the 5,000 to 7,500 target band (or a documented reason it sits outside, within the 1,500 to 15,000 hard range)

**Hand to:** SOP 9.1 step 3 verification

**Failure mode:** If a prompt cannot reach 3,500 characters with genuine specificity, the slide's spec is probably too thin (a near-empty transition slide). Confirm the slide truly needs that little; if so, document it. Never inflate with filler to pass the count.

---

### SOP 9.5 -- Drawn-Strikethrough and Struck-Text Handling

**When to run:** For any slide in the price-drop section that requires a visual strikethrough (e.g., striking through the anchor price when revealing the drop price).

**Inputs:**
- price_ladder.json (anchor price, drop prices, drop slide numbers)
- slides_copy.md (for the specific slide's copy)

**Steps:**
1. Identify whether the current slide is a PRICE DROP slide (per price_ladder.json drop slide numbers).
2. Render the drop on the PRICE-TAG MOTIF: a large white hang-tag shape with a border in the brand accent (gold), positioned per the slide's A4 layout. Old prices sit on the tag; the new price glows in accent at the bottom of the tag.
3. For price-drop slides that show both the OLD price (struck) and the NEW price:
   a. Instruct the image model with the DRAWN-LINE strike (replaces any "hand-drawn red diagonal" language): "The old price [ANCHOR or PRIOR DROP price] appears in muted charcoal/gold on the white hang-tag, with a single clean DRAWN straight line in the brand accent ([BRAND_ACCENT hex]) through the center of the numerals, the line slightly wider than the text. It is a drawn object, not a font strikethrough style and not a diagonal scribble. The crossed-out price is visually smaller than the new price."
   b. The new (current drop) price: "The new price [DROP_PRICE] appears in a larger, bolder font, [BRAND_ACCENT or PRIMARY HEX], glowing at the bottom of the hang-tag. Size contrast: new price is approximately 1.5x the size of the struck price."
   c. If there is also a payment plan on this slide: "A smaller line below the new price reads: 'or [N] payments of $[INSTALLMENT]' in a lighter weight of [font]."
4. Verify: the struck price on this slide matches the PREVIOUS drop price (or ANCHOR_PRICE for Drop 1) in price_ladder.json exactly.
5. Verify: the new (unhurt) price on this slide matches price_ladder.json for this drop number exactly.
6. Write steps 2-3 into element 7 (OBJECT PLACEMENT) and element 3 (HEADLINE VERBATIM) of the prompt, overriding the standard placement for price-drop slides.
7. **Two-failed-attempts fallback (the native PPTX text overlay):** after TWO failed render attempts on any text element (the verbatim price or strike garbled twice at image QC), trigger the native PPTX text overlay fallback. Regenerate the slide WITHOUT the failing text element, and record the struck/replacement text in working/checkpoints/pptx_text_overlays.json so the PPTX Assembly Specialist adds it as a native text box at Phase 6. For a struck price, set `"strike": true` on the entry. Example entry: `{ "slide": "slide-65", "text": "$1,000", "strike": true, "color": "[BRAND_ACCENT]", "note": "old price, strike line failed render x2" }`. This is the documented fallback for ANY slide whose verbatim text fails twice on render (master SOP Section 7.4 and 10.1).

**Outputs:**
- Price-drop slide prompts with the price-tag motif, the drawn-line strike, and new-price formatting instructions
- working/checkpoints/pptx_text_overlays.json entries (with `strike:true` for struck prices) when the two-failed-attempts fallback is triggered

**Hand to:** QC Specialist (for Phase 3 prompt QC, which checks price-drop slides against price_ladder.json); PPTX Assembly Specialist (for any pptx_text_overlays.json fallback entries)

**Failure mode:** If a price-drop slide's copy in slides_copy.md shows a price that does not match price_ladder.json, halt and flag to the Director: "Price discrepancy on slide N -- slides_copy.md shows $X but price_ladder.json shows $Y. Offer Price Strategist must resolve before prompt can be written."

---
