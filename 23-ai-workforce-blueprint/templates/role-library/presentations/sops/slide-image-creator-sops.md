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
- the GROUNDED_CONTENT variable from intake.json (the client's book / message / offer / methodology) plus any deep-research grounding routed into the image brief: the concrete moments, settings, and props from THIS client's actual method that the imagery must depict (P6 grounding; the World Engine consumes it). If GROUNDED_CONTENT is blank, flag the operator and do not invent a generic stand-in for the client's method.

**Steps:**
0. **Read the master SOP Section 7.5 gold-standard exemplar in full before writing your first prompt.** This is the actual prompt that produced the title slide of the QC-9.42 Lyric deck. Study its anatomy: the header block (title, ARCHETYPE / SECTION / LADDER tags, ONE BIG IDEA line), zone percentages, emotionally precise photo direction, exact verbatim copy with per-line font/size/color, the gold rule devices, the logo chip spec, MOOD + LIGHTING, and the closing COLOR VERIFICATION and AVOID blocks. Also read the SECOND exemplar in the appendix of this file (Section 9.5 strengthening, the A2 people-slide exemplar). Your prompts must match their density and structure, adapted to each slide's own archetype and brand variables. Do not write a single prompt before you have read both.
1. For each slide N, create working/prompts/slide-NN-prompt.txt (zero-padded number, e.g., slide-01-prompt.txt). **Line 1 of every prompt declares its archetype**, in the form `[ARCHETYPE A1] [SECTION: ...] [LADDER: ...]` followed by a ONE BIG IDEA line, exactly as the master 7.5 exemplar does. The archetype is taken from the slide's ARCHETYPE field in slides_copy.md (A1-A5 per SOP 9.2).
2. Write the 15-element prompt in this exact order. Each element must be present:
   1. **FORMAT**: "Create a 16:9 presentation slide image at 2K resolution (2560x1440 pixels)."
   2. **BACKGROUND**: "White base background. [Brand accent color] used only as accent elements (no more than 20% of the visual area)."
   3. **HEADLINE VERBATIM**: "The slide headline reads exactly: '[HEADLINE from slides_copy.md]'. This text is the primary typographic element. Place it in [position per thirds grid]."
   4. **TYPOGRAPHY (carry the full TYPOGRAPHY LAW from the STYLE BLOCK, SOP 9.4 of the Brand Steward; designed type, never basic):** "One typeface family ([family from STYLE BLOCK -- default Montserrat]); hierarchy by WEIGHT, never by mixing typefaces. Headlines and giant numbers in [family] Black; sub-headlines and body beats in [family] ExtraBold; gold all-caps letter-spaced kicker labels in [family] Bold; section labels and subheads in [family] SemiBold; tertiary breathing lines in [family] Medium italic; footnotes in [family] Regular. Every text line in this prompt declares its exact weight AND a large pt size relative to slide height: giant numbers 110-150pt, hero 2-line headline 62-86pt, secondary headline 42-62pt, sub-headline 24-32pt, body beat 17-22pt, tertiary italic 16-19pt, kicker label ~13pt, footnote 11-13pt. The typography is DESIGNED INTO the image as part of the composition (text baked into the pixels as rendered designed type), not a basic font dropped on top. Basic or default fonts (Calibri, Arial, Times, system default) are forbidden." Never write a font name without an accompanying weight and large pt size; "Montserrat Bold" with no size is insufficient.
   5. **FONT PLACEMENT (the canonical hierarchy stack):** "Text reads top to bottom in the canonical stack: gold all-caps letter-spaced kicker label -> thin gold breathing rule -> massive charcoal Black 2-line headline (dominates the zone, the first thing the eye reads) -> raspberry/Secondary ExtraBold sub-headline -> a second thin gold rule (premium paired-rule framing around the core message) -> charcoal body beat -> italic tertiary breathing line -> logo chip bottom-right. Headline text is anchored [top-left / center / bottom-left per thirds grid]. No text appears within 5% of any edge." Not every slide uses every rung, but the order is fixed; the giant charcoal Black headline always dominates."
   6. **THIRDS GRID**: "Using the rule of thirds: primary visual element in [upper-right / lower-left / center-right] region. Text occupies [upper-left / center-left] region. This creates clear visual tension and hierarchy."
   7. **OBJECT PLACEMENT**: "[Specific objects: product images, icons, diagrams, charts] placed in [specific region]. Objects must not overlap the headline text."
   8. **OVERLAYS**: "[If this slide has a hook text overlay per hook_variants.json]: A translucent [brand color] strip runs [horizontally / diagonally] at the bottom third of the image. White text on the strip reads: '[HOOK VARIANT TEXT]'. [If no overlay]: No text overlays other than the headline."
   9. **BRAND PALETTE**: "Primary accent: [HEX1, role from STYLE BLOCK]. Secondary accent: [HEX2, role]. Tertiary: [HEX3, role]. All backgrounds remain white. No dark backgrounds. No navy, black, or charcoal backgrounds unless DARK_OK=true."
   10. **LOGO**: "[Logo placement per STYLE BLOCK rule -- typically lower-right corner, small, consistent size]."
   11. **PEOPLE (driven by the THREE ENGINES, transplanted from master SOP Section 7.3 element 11; all three required on every people-slide, missing any one is an auto-fail):**
      - **FACIAL EXPRESSION ENGINE:** the face must match what the slide is SAYING. Every person spec includes hair (color, style, length), clothing (color, style, formality), and a facial expression described in terms of the emotion the slide communicates (a pain slide gets a worried, overwhelmed face; a vision slide gets the arrived, relieved smile). The expression is stated in explicit emotion terms, never just "smiling." Use the Expression Vocabulary Table (SOP 9.2 strengthening pack) to pick the exact expression for the slide's emotion. Missing hair, clothing, OR the expression = auto-fail.
      - **AUDIENCE ENGINE:** people match the slide's REPRESENTATION_MIX assignment and AUDIENCE from intake (the representation group, age range, gender mix, and the style of dress for the niche). The diversity spec comes from the STYLE BLOCK representation_ratio (e.g., 70% African American women, 20% African American men, 10% mixed) and the deck-wide ratio is honored across slides, not forced onto every single slide.
      - **WORLD ENGINE (real-world knowledge):** the SETTING matches the industry and the moment. Where would this person actually be: their office, the kitchen table at dinner, the empty classroom at 6am? Every people-slide prompt STATES the real-world setting AND justifies why it fits the slide's one idea. Pull the setting from the Lighting + World Library (SOP 9.3 strengthening pack). A generic studio backdrop where a real-world scene belongs is a defect and an auto-fail. The World Engine is also where GROUNDING lives: the scene, props, and moment must depict a concrete moment from THIS client's method (the GROUNDED_CONTENT variable: their book, message, offer, or methodology), not a generic stand-in. Stock-generic imagery that depicts no concrete moment from the client's actual method is an auto-fail at the image-grounding gate (QC final-deck grounding criterion). Carry GROUNDED_CONTENT into both the photo brief and the object placement so the slide shows the client's real thing, not an interchangeable stock scene.
      - **SHOT layer (taxonomy beneath the engines, not a replacement for them):** under the three engines, also pick the shot framing for the person. Engine A (Single Subject): one person, full-body or three-quarter shot. Engine B (Audience Group): a small group of 2 to 4 people, natural energy, not a posed stock photo. Engine C (Presenter / Speaker): one person presenting or teaching, confident posture, reads as a knowledgeable guide not a salesperson. The shot layer answers "how is the person framed"; the three engines above answer "what does the person feel, who are they, and where are they". Both layers must be present on a people-slide."
   12. **BULLETS** (if slide has bullet points): "Body text bullets are short, no full sentences. Each bullet is max 5 words. Bullets appear as [dot / dash / icon] markers."
   13. **MOOD (one felt beat per slide -- SEE):** "[Emotional tone for this slide: e.g., aspirational, urgent, celebratory, authoritative]. This slide carries its OWN felt emotional moment (a Significant Emotional Experience), readable in 2 seconds without narration. The visual energy should feel [descriptor] to [target audience descriptor from intake.json]."
   14. **PROFESSIONALISM (the standalone-art gate, SOP 9.6):** "Production quality: this slide must read as a finished, gallery-grade STANDALONE PIECE OF ART, complete on its own with no other slide for context. Intentional art direction (focal hierarchy, negative space, depth of field), premium lifestyle-documentary photography (never stock, clipart, or cartoon), directional warm lighting, a clear hero subject, and the large creative typography composed INTO the image as part of the composition (not pasted on top). Magazine-grade. No amateur stock photo aesthetic. No watermarks. No blur. Sharp focus on the human subject if people are present. This image is one you could frame and hang. A slide that is 'just a background with text' is a defect." A composition that only works as part of the sequence fails the standalone test.
   15. **CLOSING CONSTRAINTS (AVOID BLOCK)**: "AVOID: dark backgrounds, pure black backgrounds, shadowed images, grainy textures, busy patterns, more than 3 colors, any watermark, any em dash, any text not specified in this prompt, image elements that extend into the border zone, basic or default fonts (Calibri, Arial, Times, system default), any text rendered without a designed weight and large size, a flat type treatment with no hierarchy, and any 'background with text dropped on top' that fails the standalone-art test."
3. Verify character count of the completed prompt. Target: 5,000-7,500 characters. Minimum: 1,500. Maximum: 15,000. If under 1,500, the prompt is too sparse -- expand the MOOD, PEOPLE, and OBJECT PLACEMENT elements. If over 15,000, trim the AVOID block and MOOD sections.
4. Verify: is the HEADLINE VERBATIM text exactly as it appears in slides_copy.md? Copy-paste, do not paraphrase.
5. Verify: no em dashes in the prompt. (The word "em-dash" or "--" in the AVOID block is acceptable as a prohibition, not a usage.)
6. Verify: BACKGROUND is white base unless DARK_OK = true.
7. After all slides are written, run a batch self-check:
   a. Count: all 15 elements present in every prompt (if any are missing, the prompt fails the SOP).
   b. Character count in range for every prompt.
   c. No em dashes.
   d. No dark backgrounds (unless DARK_OK flag is set).
   e. Grounding: every image depicts a concrete moment from THIS client's method (the GROUNDED_CONTENT variable), not a generic stock scene. A slide whose imagery is interchangeable with any other brand fails the image-grounding gate at QC.
   f. TYPOGRAPHY LAW (SOP 9.6 / brand-steward SOP 9.4): every text line names its exact weight AND a large pt size; the one-family weight map is honored (Black for headlines and giant numbers, ExtraBold for subs and body beats, Bold for gold caps labels); the prompt states the type is designed INTO the image. No prompt names a basic or default font (Calibri, Arial, Times, system default) and none names a font with no per-line size. Any such prompt is an AUTO-FAIL.
   g. STANDALONE ART (SOP 9.6): every prompt directs a finished gallery-grade standalone composition (art direction + hero subject + typography composed into the image + its own felt emotional beat). No prompt produces "just a background with text". A slide that would only work as part of the sequence fails the standalone-art gate.

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

**THE THIRDS SYSTEM (required design rule and required prompt element):** Every prompt must declare which third of the frame holds each key element. The frame is divided into a 3x3 grid: upper / middle / lower third vertically, and left / center / right third horizontally. This creates nine intersection zones, and the most powerful focal points sit at the four intersections of the inner lines (upper-left, upper-right, lower-left, lower-right). Rules:
- Every prompt states which third holds the HEADLINE (e.g., "headline anchored to the lower-left third").
- Every prompt states which third holds the PRIMARY SUBJECT or visual element (e.g., "subject positioned at the upper-right third intersection").
- Every prompt states which zone holds SUPPORTING ELEMENTS (e.g., "logo chip at lower-right; supporting copy in the center-left zone").
- "Centered" alone is not thirds language and is an auto-fail at Prompt QC (AF-P6). Centering as an intentional design choice must be described as "centered on the vertical axis in the middle third, with deliberate symmetry as the composition anchor."
- On every people-slide, the person's EYE LINE or face falls at or near a thirds-grid intersection. Declaring this in the prompt is mandatory.

**IMAGE LAYERING AND DEPTH (required on every prompt):** Every slide prompt must specify all three depth layers explicitly. The image model cannot infer depth -- you must direct it. The three layers:
- FOREGROUND: what is closest to the viewer? (A blurred edge element, a prop, negative space, a design device -- or stated as "no foreground element, the subject IS the near plane.")
- MIDGROUND: the primary subject. Separated from the background by depth of field (soft background blur) OR by a lighting story (rim light, scrim, or exposure falloff behind the subject). Separation is required -- a subject that merges with the background is a composition defect.
- BACKGROUND: the environmental context (the real-world setting per the World Engine). Typically softer focus, lower contrast, or lighter exposure than the midground subject.
- Typography and design devices (gold rules, kicker labels, overlays) are the FRONT LAYER -- they sit above the photo layers in z-order and are rendered as designed elements, not embedded in the scene.
- Subject separation method (required statement in the prompt): "Subject is separated from the background by [rim light and soft background blur / a natural exposure falloff / a shallow depth of field producing a bokeh background / the scrim gradient masking the background transition]. The background reads as environmental context, not a seamless studio backdrop."
- Missing any layer from the prompt is a prompt-defect that routes back from QC.

**OBJECTS, CARDS, PANELS, INSETS, AND CALLOUT DEVICES (vocabulary and usage rules):** Premium deck slides use intentional design objects to create structure, frame information, and add visual interest beyond a photo with text. These are not decorations -- each device has a purpose and placement rule:
- **Gold-rule divider**: a 2-3px horizontal gold line that separates the kicker label from the headline, or the headline from the sub-headline. Always horizontal. Placed between rung changes in the hierarchy stack. Required in the canonical stack (see element 5).
- **Callout chip / kicker label**: a gold all-caps letter-spaced 13pt label that sits above the headline and identifies the slide's category or moment ("THE PROMISE", "YOUR TRANSFORMATION", "THE PROOF"). Carries the gold rule beneath it.
- **Vignette / scrim gradient**: a soft white-to-transparent or dark-to-transparent gradient that separates the typography zone from the photo zone (A1 archetype). Required whenever text sits over a photo band. State the direction and coverage percentage in the prompt.
- **Hang-tag / price-tag motif**: the visual device for price-drop slides -- a stylized price tag shape with the ANCHOR price in a large weight, used to set the value reference before the drops. Required on the ANCHOR slide. Specify the shape, color (white on brand color background, or brand-color stroke on white), and the text it carries.
- **Inset / callout panel**: a floating card or semi-transparent panel that holds a supporting proof point, stat, or testimonial fragment while the main image runs behind it. Used when a second information element must appear without a full split-layout. Specify exact position (e.g., "lower-left inset, 28% width, semi-transparent white, 2px gold border, anchored to the lower-left third intersection").
- **Placement rule**: all objects must be placed in named thirds zones. "Bottom-right corner" is insufficient; "logo chip at the lower-right third intersection" is correct.

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
- Giant numbers as the hero: dollar figures and stats rendered 110-150pt in the heaviest weight (Black), 1.5x to 3x the size of surrounding text, the hero of the data zone; rendered in the "liquid gold" gradient or the accent with a glow.
- Kicker label: small all-caps letter-spaced label (~13pt, Bold) in gold or pink above the headline, with a short gold rule beneath it.
- Gold rules framing the message: thin gold rules above and below the core message (premium paired-rule framing); a 3px full-width gold rule as the divider between photo and type zones.
- Drawn strikes on superseded prices: old prices struck with a single clean DRAWN line in the brand accent (double-thickness, a drawn object, never a font strikethrough or a diagonal scribble), per SOP 9.5; the anchor price is NOT struck.
- Two-line tight dominating headlines: headlines set as two short, tightly-stacked lines that fill and dominate the zone.
- Single-word color swaps for emphasis: inside a charcoal headline, one or two words switch to raspberry or gold for emphasis.
- Color roles: gold = money, value, and dividers; pink/accent = action, emphasis words, and urgency; charcoal = headlines (never pure black backgrounds).
- Price tag motif: drops are rendered as a large white hang-tag shape with a gold border; old prices struck through with a DRAWN line in the brand accent (SOP 9.5); the new price glowing in accent at the bottom of the tag.
- Section progress labels on section-opener slides ("SECTION 3 OF 7", "SECRET #1" in a filled accent banner box).
- White scrim gradients over full-bleed photos: a soft white-to-transparent gradient (never a black box) so charcoal text reads over the imagery.
- Logo on a white chip (~9% of slide width, subtle 1px gold border) in the same corner on every slide, never recolored, never distorted, never clipped.
- Compliance line: any results/income claim slide carries a small italic disclaimer in the lower margin.
- Text baked INTO the image as designed typography: because the deck ships as rendered images, the typography is generated by the image model from the exact font weight, size, and color spec, then composed over the photography. Every prompt declares the weights and hexes explicitly; a slide theme font does nothing.

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
1. The three engines are the authority for every people-slide and are written in element 11 per SOP 9.1: the FACIAL EXPRESSION ENGINE (hair + clothing + explicit expression from the Expression Vocabulary Table, SOP 9.2 strengthening), the AUDIENCE ENGINE (representation group, age range, gender mix, niche dress per the STYLE BLOCK ratio), and the WORLD ENGINE (real-world setting + justification from the Lighting + World Library, SOP 9.3 strengthening, AND the GROUNDED_CONTENT variable so the setting/props depict a concrete moment from THIS client's method, not a generic stand-in). All three are mandatory; missing any one is an auto-fail. Ungrounded generic imagery that shows no concrete moment from the client's method is an auto-fail at the image-grounding gate.
2. Beneath the three engines, pick the SHOT framing layer for this slide:
   - Shot A (Single Subject): one person, full-body or three-quarter shot.
   - Shot B (Audience Group): a small group of 2 to 4 people representing the STYLE BLOCK ratio, natural energy, not a posed stock photo.
   - Shot C (Presenter / Speaker): one person presenting or teaching, confident posture, reads as a knowledgeable guide not a salesperson.
3. Match the shot to the slide section: Hook/Close use Shot A or C. Proof slides use Shot A (testimonial subject). Audience/problem slides use Shot B. Speaker slides use Shot C. The shot layer answers "how is the person framed"; the three engines answer "what they feel, who they are, where they are".
4. Write the people description with BOTH layers present: the three engines first (expression, representation, world), then the shot framing.
5. Verify: representation ratio is honored across the deck as a whole. The Brand Steward tracks deck-level ratios; at the slide level, use the per-engine spec.

**Steps (Logo -- Element 10):**
1. Read the logo_placement_rule from the STYLE BLOCK. Typical rule: "Logo in lower-right corner, approximately 3-5% of slide width, no less than 40px from any edge."
2. Write element 10 verbatim from the STYLE BLOCK's logo_placement_rule.

**Steps (Overlays -- Element 8):**
1. Check hook_variants.json. If this slide has a hook_overlay flag: write "A semi-transparent [SECONDARY_HEX] horizontal band at the bottom 15% of the slide. White text in [font from STYLE BLOCK]: '[HOOK VARIANT TEXT]' -- centered, size 36-42pt."
2. If no hook overlay for this slide: write "No text overlays on this slide beyond the headline."
3. No overlays may cover the logo placement zone.

**Outputs:**
- Elements 8, 10, and 11 written into the prompt

**Hand to:** SOP 9.1

**Failure mode:** If STYLE BLOCK has no representation_ratio, DO NOT invent a racial default. Inventing a demographic ratio for a client is a brand and trust risk. Set representation to NO PEOPLE (people element omitted from all slides) and flag: `representation_source: "default_no_people -- intake unanswered"`. Immediately notify the operator with a flag: "REPRESENTATION UNANSWERED: STYLE BLOCK has no representation_ratio. Deck will default to no people in images. Please confirm or supply the intended breakdown before Phase 2." Do not write a single people-inclusive prompt until the operator or client has answered. Document the no-people state in a comment in every prompt: `// REPRESENTATION: NO PEOPLE default -- no STYLE BLOCK ratio supplied, operator flag issued`. (This is the verbatim brand-steward rule; never invent percentages the client did not supply.)

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

### SOP 9.6 -- Designed-Typography and Standalone-Art Enforcement (every prompt)

**When to run:** Within SOP 9.1, on every prompt, as a final composition check before handoff to Phase 3 QC. This SOP carries the Brand Steward's TYPOGRAPHY LAW (brand-steward SOP 9.4) and the core design principle that each slide is a standalone piece of art into the prompt.

**Inputs:**
- The completed prompt for the slide
- The TYPOGRAPHY LAW from the STYLE BLOCK (the weight map, the size scale, the hierarchy stack, the palette, the zero-black-background rule)

**Part A -- DESIGNED TYPOGRAPHY (never basic, never default):**
1. Every text line in the prompt names its exact font WEIGHT and a large pt SIZE relative to slide height. "Montserrat Black, approximately 78-86pt" is correct; "Montserrat Bold" with no size is insufficient; "a clean sans-serif" or any unnamed/default font is a defect.
2. The one-family weight map is honored: headlines and giant numbers in the heaviest weight (Black); sub-headlines, body beats, and before/after stats in ExtraBold; gold all-caps letter-spaced kicker labels in Bold; section labels and subheads in SemiBold; tertiary breathing lines in Medium italic; footnotes in Regular. Hierarchy is created by weight, never by mixing typefaces.
3. The size scale is applied: giant numbers 110-150pt, hero 2-line headline 62-86pt, secondary headline 42-62pt, sub-headline 24-32pt, body beat 17-22pt, tertiary italic 16-19pt, kicker label ~13pt, footnote 11-13pt.
4. The canonical hierarchy stack is present in element 5 (gold caps label -> gold rule -> charcoal Black 2-line headline -> Secondary ExtraBold sub -> gold rule -> body beat -> italic tertiary -> logo chip).
5. The creative devices are specified where they apply: giant numbers as the hero, paired gold rules, drawn strikes on superseded prices, two-line tight dominating headlines, single-word color swaps, white scrim gradients over full-bleed photos.
6. The prompt states the typography is DESIGNED INTO the image (baked into the pixels as rendered designed type), and explicitly forbids basic or default fonts in the AVOID block.
7. BASIC OR DEFAULT FONTS = AUTO-FAIL: a prompt that names a basic or platform-default typeface (Calibri, Arial, Times, system default), or that names any font with no per-line weight and large pt size, is an AUTO-FAIL at prompt QC.

**Part B -- EACH SLIDE IS A STANDALONE PIECE OF ART:**
1. Standalone test: pull THIS slide out of the deck with no other slide for context. The prompt must direct an image that still reads as a deliberate, beautiful, finished piece of visual art on its own. A composition that only works as part of a sequence FAILS.
2. The prompt directs intentional art direction (focal hierarchy, negative space, depth of field), premium lifestyle-documentary photography (never stock, clipart, or cartoon), directional warm lighting, and a clear hero subject.
3. The large creative typography is composed INTO the image as part of the composition, not pasted on top.
4. The slide carries its OWN felt emotional beat (a Significant Emotional Experience), readable in 2 seconds without narration.
5. The image is gallery-grade: the photo + the large Montserrat-Black typography + the brand palette + the gold rules compose one image you could frame and hang.
6. "JUST A BACKGROUND WITH TEXT" = AUTO-FAIL. A prompt that produces a generic background with text dropped on it, with no art direction and no standalone composition, is an AUTO-FAIL at prompt and image QC.

**Steps:**
1. Run Part A on every prompt; fix any line that lacks an exact weight and large pt size before handoff.
2. Run Part B on every prompt; if the prompt would produce "just a background with text," rebuild the composition (art direction, hero subject, typography composed in, the felt beat) before handoff.
3. Record in the prompt's self-check (SOP 9.1 step 7 items f and g) that both parts pass.

**Outputs:**
- Every prompt carrying designed typography (exact weights + large pt sizes + hierarchy + creative devices + text-baked-in) and directing a standalone gallery-grade art piece

**Hand to:** QC Specialist -- Presentations (the typography AUTO-FAIL and the standalone-art AUTO-FAIL are scored at Phase 3 prompt QC and re-verified at Phase 5 image QC)

**Failure mode:** If a prompt cannot be made to carry designed typography (e.g., the STYLE BLOCK shipped without the TYPOGRAPHY LAW), halt and flag the Brand Steward and Director: "Phase 2 blocked -- STYLE BLOCK is missing the TYPOGRAPHY LAW; prompts will default to basic fonts and auto-fail." Never default to a basic font to keep moving.

---

### SOP 9.7 -- Color Theory, Color Relationships, and Color Grading (every prompt)

**When to run:** Within SOP 9.1, during elements 2, 9, and 15 (BACKGROUND, BRAND PALETTE, and AVOID BLOCK). Must complete before handoff to Phase 3 QC.

**Inputs:**
- The STYLE BLOCK from the Brand Steward (COLOR THEORY section and COLOR GRADING PROFILE -- generated by Brand Steward SOP 9.1 step 5a and SOP 9.2)
- The client brand hex codes and their roles

**Part A -- COLOR RELATIONSHIPS (complementary, contrasting, analogous):**
1. Read the COLOR THEORY section of the STYLE BLOCK: what is the primary-secondary relationship? (complementary = opposite on the wheel for maximum pop; analogous = adjacent hues for warmth and harmony; triadic = three equidistant hues for vibrant balance)
2. The BRAND PALETTE is the governing constraint -- brand hex codes do not change. Color theory governs HOW the colors RELATE and appear together, not which colors are used.
3. Complementary accent use: when the STYLE BLOCK names a complementary accent (e.g., raspberry-pink as the pop accent against a gold primary), that accent color is reserved for MAXIMUM CONTRAST moments -- CTAs, price reveals, the single most important number on a slide. Using it everywhere kills its power.
4. Contrast declaration (required in every prompt's BRAND PALETTE element): state the contrast relationship between the headline color and the background it sits on. The minimum threshold is WCAG AA: 4.5:1 for normal text, 3:1 for large text (large = 18pt+ regular or 14pt+ bold). "Charcoal (#231F20) on white (#FBF7F4): contrast ratio 16.5:1, PASS" is the correct form. A prompt that places light text on a light background without a contrast declaration is a defect.
5. Include a COLOR GRADING block at the end of every prompt per Part B.

**Part B -- COLOR GRADING (consistent warm/cool tone, saturation, and temperature across the deck):**
1. Read the COLOR GRADING PROFILE from the STYLE BLOCK: WARM, COOL, or NEUTRAL grade.
   - WARM grade: golden-hour light temperature, slightly lifted shadows, warm midtones, saturated sunset-direction tones. Charcoal and raspberry-pink on an off-white base reads as WARM.
   - COOL grade: silver-blue light temperature, neutral-to-cool midtones, clean shadows. A navy-primary palette typically grades COOL.
   - NEUTRAL grade: balanced daylight, no dominant temperature lean.
2. Every prompt must state the TEMPERATURE LOCK: "Image color temperature: WARM / COOL / NEUTRAL -- lock to [description] to match the deck's grade profile."
3. Saturation consistency: state the saturation level in the prompt (e.g., "slightly elevated saturation on the primary subject, desaturated background for separation -- consistent with the deck's warm-grade palette").
4. Tonal contrast: state whether the overall key is HIGH (strong shadow/highlight separation) or LOW (softer, more even tonal range). Keep this consistent across the deck.
5. Include the following COLOR GRADING block verbatim in every prompt (adapt values to client profile):
   ```
   // COLOR GRADING: TEMPERATURE=[WARM/COOL/NEUTRAL], SATURATION=[description],
   // TONAL CONTRAST=[HIGH/LOW], GRADE=[match deck profile from STYLE BLOCK].
   // Every image in this deck must feel like it was shot in the same light.
   ```
6. A deck where some images are warm-toned and others are cool-toned = an UNGRADED INCONSISTENT DECK, which is an AUTO-FAIL at QC (AF-DC5 in the Design-Craft battery).

**Steps:**
1. Read the COLOR THEORY and COLOR GRADING sections of the STYLE BLOCK before writing element 9 (BRAND PALETTE).
2. Write the contrast declaration into element 9 (headline color vs. background, WCAG ratio, PASS/FAIL).
3. Note the complementary accent and restrict its usage to maximum-impact moments only.
4. Write the TEMPERATURE LOCK into element 13 (MOOD) or element 14 (PROFESSIONALISM).
5. Append the COLOR GRADING block comment before the AVOID block.
6. Record in the prompt self-check (SOP 9.1 step 7 item h): "COLOR GRADING verified: TEMPERATURE=[value], GRADE=[value]."

**Outputs:**
- Contrast declaration in element 9
- TEMPERATURE LOCK in element 13 or 14
- COLOR GRADING block appended before the AVOID block

**Hand to:** QC Specialist -- Presentations (color-harmony and color-grading dimensions are scored at Phase 3 prompt QC and Phase 5 image QC)

**Failure mode:** If the STYLE BLOCK is missing the COLOR THEORY or COLOR GRADING sections, halt and notify the Brand Steward: "Phase 2 blocked -- STYLE BLOCK is missing color-theory sections. Cannot guarantee color harmony or grade consistency across the deck." Never write color elements without the STYLE BLOCK's grade profile.

---

