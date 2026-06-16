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
- working/research/grounded-content-[DECK_SLUG].json (Category E from ROLE-04 Phase -0.5 -- REQUIRED; load before writing any prompt)
- working/research/design-brief-[DECK_SLUG].md (Category F from ROLE-04 Phase -0.5 -- REQUIRED; informs composition and grading direction)

**Real-image-present requirement (AF-I11):** Every non-pure-typography slide must specify a real generated raster (Kie / GPT-Image-2) at >=1920px on the long edge, full-bleed or designed-zone, sourced from the Category E grounded anchor. Decorative icon-font glyphs, single-color clip-art PNGs <=256px, and emoji-as-iconography are FORBIDDEN as slide content art. Concept slides (process, architecture, comparison) must specify a generated diagram-as-image, never text in boxes.

**Steps:**
0. **Read the master SOP Section 7.5 gold-standard exemplar in full before writing your first prompt.** This is the actual prompt that produced the title slide of the QC-9.42 gold-standard reference deck. Study its anatomy: the header block (title, ARCHETYPE / SECTION / LADDER tags, ONE BIG IDEA line), zone percentages, emotionally precise photo direction, exact verbatim copy with per-line font/size/color, the gold rule devices, the logo chip spec, MOOD + LIGHTING, and the closing COLOR VERIFICATION and AVOID blocks. Also read the SECOND exemplar in the appendix of this file (Section 9.5 strengthening, the A2 people-slide exemplar). Your prompts must match their density and structure, adapted to each slide's own archetype and brand variables. Do not write a single prompt before you have read both.
1. For each slide N, create working/prompts/slide-NN-prompt.txt (zero-padded number, e.g., slide-01-prompt.txt). **Line 1 of every prompt declares its archetype**, in the form `[ARCHETYPE A1] [SECTION: ...] [LADDER: ...]` followed by a ONE BIG IDEA line, exactly as the master 7.5 exemplar does. The archetype is taken from the slide's ARCHETYPE field in slides_copy.md (A1-A5 per SOP 9.2).
2. Write the 15-element prompt in this exact order. Each element must be present:
   1. **FORMAT**: "Create a 16:9 presentation slide image at 2K resolution (2560x1440 pixels)."
   2. **BACKGROUND**: "White base background. [Brand accent color] used only as accent elements (no more than 20% of the visual area)."
   3. **HEADLINE VERBATIM (with the SPELLING-LOCK rule, FIX-2; and the NEVER-BAKE-A-SCENE-DESCRIPTION rule; FIX-3):** "The slide headline reads exactly: '[HEADLINE from slides_copy.md]'. This text is the primary typographic element. Place it in [position per thirds grid]." The ONLY text baked onto the slide is the verbatim copy from slides_copy.md (HEADLINE / SUBHEAD / SUPPORTING). **SPELLING-LOCK (mandatory on EVERY verbatim text string -- the garbled-text defect fix, "hclarity" / "GRABLED BRANDCO").** Every headline, sub-headline, supporting line, kicker label, price, struck price, and any other verbatim string in the prompt is wrapped in an explicit spelling-lock instruction, in this exact form: "Render this exact string, letter-for-letter, correctly spelled, with no added, dropped, doubled, or substituted characters: '[STRING]'. Do not alter, misspell, duplicate, abbreviate, translate, or garble any character of it." Write the spelling-lock sentence immediately after each verbatim string so the model cannot drift. A prompt that carries a verbatim text string without its spelling-lock instruction is an AUTO-FAIL at QC (AF-P14). NEVER bake a SCENE or IMAGE DESCRIPTION as the headline or sub. A scene description (for example 'Same parent, same child, two completely different rooms to grow up in' or 'The senior engineer who hit every goal and still feels lost') is photo-brief direction for YOU to depict in the imagery, NOT audience-facing copy. It belongs in the PEOPLE / WORLD ENGINE photo brief (element 11) and the MOOD (element 13), never in element 3 or as a sub line. If slides_copy.md ever carries a scene description in a HEADLINE or SUBHEAD field, do NOT bake it; flag it back to the Copywriter and the Director as a scene-description-as-copy defect (it is an audience-facing AUTO-FAIL at QC). Likewise never bake presenter narration, the AI's own meta-commentary, a telegraphing / stage-direction kicker ('one last proof before you decide', 'before you decide', 'this is not just a webinar'), or the literal word 'webinar' as on-slide text. **NO PLACEHOLDER / BRACKET TOKEN as rendered copy (the baked-placeholder defect fix, "[CLIENT WIN - owner to confirm]").** Never put a bracketed build token or a build note into element 3 (or any element) as text the model is told to render: no "[...]", no "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", or "pending". If slides_copy.md still carries an unresolved placeholder for this slide, do NOT write the prompt: halt and flag the Copywriter and Director to resolve it with the client's real interview-sourced content or pull the slide (a bracket token in the prompt is an AUTO-FAIL at QC, AF-P16, so it can never reach the render). The image depicts the scene; the slide never narrates it.
   4. **TYPOGRAPHY (carry the full TYPOGRAPHY LAW from the STYLE BLOCK, SOP 9.4 of the Brand Steward; designed type, never basic):** "One typeface family ([family from STYLE BLOCK -- default Montserrat]); hierarchy by WEIGHT, never by mixing typefaces. Headlines and giant numbers in [family] Black; sub-headlines and body beats in [family] ExtraBold; gold all-caps letter-spaced kicker labels in [family] Bold; section labels and subheads in [family] SemiBold; tertiary breathing lines in [family] Medium italic; footnotes in [family] Regular. Every text line in this prompt declares its exact weight AND a large pt size relative to slide height: giant numbers 110-150pt, hero 2-line headline 62-86pt, secondary headline 42-62pt, sub-headline 24-32pt, body beat 17-22pt, tertiary italic 16-19pt, kicker label ~13pt, footnote 11-13pt. The typography is DESIGNED INTO the image as part of the composition (text baked into the pixels as rendered designed type), not a basic font dropped on top. Basic or default fonts (Calibri, Arial, Times, system default) are forbidden." Never write a font name without an accompanying weight and large pt size; "Montserrat Bold" with no size is insufficient.
   5. **FONT PLACEMENT (consume the Typography Architect's per-slide-TYPE layout card; FIX-9):** "Pull this slide's TYPE-LAYOUT TEMPLATE for its ARCHETYPE from the Typography Architect's working/typography/type_layout_system.md (the Phase-0.7/1.5 gate that runs BEFORE this prompt is written). That card specifies, per slide type, the word-placement zone, the type treatment, and which rungs this slide type actually carries. Apply THAT card; do not stamp one hard-coded stack onto every slide. The canonical stack below is the FALLBACK ordering only (used when no type card exists for this slide type): gold all-caps letter-spaced kicker label -> thin gold breathing rule -> massive charcoal Black 2-line headline (dominates the zone, the first thing the eye reads) -> raspberry/Secondary ExtraBold sub-headline -> a second thin gold rule -> charcoal body beat -> logo chip bottom-right. CRITICAL (FIX-2): the HOOK REFRAIN and the italic tertiary breathing line are NOT default stack elements; they appear ONLY when this slide's type card (or hook_variants.json for the hook) explicitly calls for them. Do not add a hook refrain to a slide whose hook_variants.json entry is false, and do not add an italic tertiary line just to fill the stack. A slide that piles kicker + 2-line headline + sub + hook refrain + tertiary italic all at once is OVER-STUFFED and fails copy QC. Headline text is anchored per the type card and the thirds grid. No text appears within 5% of any edge. When the type card is present, the giant charcoal Black headline still dominates, but the rung set comes from the card, not from a fixed every-slide template."
   6. **THIRDS GRID**: "Using the rule of thirds: primary visual element in [upper-right / lower-left / center-right] region. Text occupies [upper-left / center-left] region. This creates clear visual tension and hierarchy."
   7. **OBJECT PLACEMENT**: "[Specific objects: product images, icons, diagrams, charts] placed in [specific region]. Objects must not overlap the headline text."
   8. **OVERLAYS**: "**(Density-floor overhaul) There is NO hook footer band. DELETED.** The hook is NEVER rendered as a bottom strip/band on any slide. The hook renders ONLY as the type-dominant content of its 3 to 4 DEDICATED pure-typography slides (treatment_table PURE_TYPE_HOOK: the hook line large over a low-opacity image, nothing else). On every non-hook slide write: 'No text overlays on this slide beyond the headline. No hook footer band.' The old bottom-15%-strip hook rendering produced the reference failure case 40-slide footer-stamping and is banned (AF-I8 / AF-HOOK-2)."
   9. **BRAND PALETTE**: "Primary accent: [HEX1, role from STYLE BLOCK]. Secondary accent: [HEX2, role]. Tertiary: [HEX3, role]. All backgrounds remain white. No dark backgrounds. No navy, black, or charcoal backgrounds unless DARK_OK=true."
   10. **LOGO (image-to-image, density-floor overhaul)**: when LOGO_ON_SLIDES = true, the locked LOGO_URL is passed as the first reference in `input.input_urls` and the prompt names it: 'The first reference image is the company logo: place it [per STYLE BLOCK placement], do not redraw, recolor, or restyle it.' NEVER describe the logo in words for text-to-image generation (that reinvents the mark per slide, the reference failure case logo-mutation defect). One locked mark, composited identically on every slide. See universal-sops/presentation-image-library/SOP-IMG-01 Mode B and presentation-design-system/05-SOP-logo-consistency.md. AF-P9/P10/P11 fail a logo drawn text-to-image or a missing 'do not redraw' instruction; AF-I4/AF-I11 fail a rendered mark that differs from the locked asset."
   11. **PEOPLE (driven by the THREE ENGINES, transplanted from master SOP Section 7.3 element 11; all three required on every people-slide, missing any one is an auto-fail):**
      - **FACIAL EXPRESSION ENGINE:** the face must match what the slide is SAYING. Every person spec includes hair (color, style, length), clothing (color, style, formality), and a facial expression described in terms of the emotion the slide communicates (a pain slide gets a worried, overwhelmed face; a vision slide gets the arrived, relieved smile). The expression is stated in explicit emotion terms, never just "smiling." Use the Expression Vocabulary Table (SOP 9.2 strengthening pack) to pick the exact expression for the slide's emotion. Missing hair, clothing, OR the expression = auto-fail.
      - **AUDIENCE ENGINE:** people match the slide's REPRESENTATION_MIX assignment and AUDIENCE from intake (the representation group, age range, gender mix, and the style of dress for the niche). The diversity spec comes from the STYLE BLOCK representation_ratio (e.g., 70% African American women, 20% African American men, 10% mixed) and the deck-wide ratio is honored across slides, not forced onto every single slide.
      - **WORLD ENGINE (real-world knowledge):** the SETTING matches the industry and the moment. Where would this person actually be: their office, the kitchen table at dinner, the empty classroom at 6am? Every people-slide prompt STATES the real-world setting AND justifies why it fits the slide's one idea. Pull the setting from the Lighting + World Library (SOP 9.3 strengthening pack). A generic studio backdrop where a real-world scene belongs is a defect and an auto-fail. The World Engine is also where GROUNDING lives: the scene, props, and moment must depict a concrete moment from THIS client's method (the GROUNDED_CONTENT variable: their book, message, offer, or methodology), not a generic stand-in. Stock-generic imagery that depicts no concrete moment from the client's actual method is an auto-fail at the image-grounding gate (QC final-deck grounding criterion). Carry GROUNDED_CONTENT into both the photo brief and the object placement so the slide shows the client's real thing, not an interchangeable stock scene.
      - **SHOT layer (taxonomy beneath the engines, not a replacement for them):** under the three engines, also pick the shot framing for the person. Engine A (Single Subject): one person, full-body or three-quarter shot. Engine B (Audience Group): a small group of 2 to 4 people, natural energy, not a posed stock photo. Engine C (Presenter / Speaker): one person presenting or teaching, confident posture, reads as a knowledgeable guide not a salesperson. The shot layer answers "how is the person framed"; the three engines above answer "what does the person feel, who are they, and where are they". Both layers must be present on a people-slide."
   12. **BULLETS** (if slide has bullet points): "Body text bullets are short, no full sentences. Each bullet is max 5 words. Bullets appear as [dot / dash / icon] markers."
   13. **MOOD (one felt beat per slide -- SEE):** "[Emotional tone for this slide: e.g., aspirational, urgent, celebratory, authoritative]. This slide carries its OWN felt emotional moment (a Significant Emotional Experience), readable in 2 seconds without narration. The visual energy should feel [descriptor] to [target audience descriptor from intake.json]."
   14. **PROFESSIONALISM (the standalone-art gate, SOP 9.6):** "Production quality: this slide must read as a finished, gallery-grade STANDALONE PIECE OF ART, complete on its own with no other slide for context. Intentional art direction (focal hierarchy, negative space, depth of field), premium lifestyle-documentary photography (never stock, clipart, or cartoon), directional warm lighting, a clear hero subject, and the large creative typography composed INTO the image as part of the composition (not pasted on top). Magazine-grade. No amateur stock photo aesthetic. No watermarks. No blur. Sharp focus on the human subject if people are present. This image is one you could frame and hang. A slide that is 'just a background with text' is a defect." A composition that only works as part of the sequence fails the standalone test.
   15. **CLOSING CONSTRAINTS (the MANDATORY PAIRED NEGATIVE-PROMPT BLOCK, SOP 9.8).** Element 15 is no longer a single thin AVOID line; it is the dedicated final-paragraph negative block authored per SOP 9.8 and placed as the LAST paragraph of the prompt (image models weight endings heavily). Because GPT-Image 2 has no negative-prompt field (MODEL-SPECS, "No (inline only)"), every negative is an inline imperative "Do not ..." sentence, and EACH critical negative is paired with a positive twin stated earlier in the prompt. The block covers, one imperative sentence each, all eight forensic defect classes (garbled text, logo mutation, placeholder / bracket tokens, image narration / presenter / meta / "webinar", anatomical artifacts, background competing with text, demographic / skin-tone fidelity, and the carried-forward universal baseline). Write it verbatim from the SOP 9.8 template, adapting only the bracketed client values. A prompt missing the negative block, missing any of the eight classes, or carrying a negative with no positive twin is an AUTO-FAIL at QC (AF-P13). See SOP 9.8 for the full template and the no-contradiction audit.
3. Verify character count of the completed prompt. Target: 9,000-14,000 characters. Soft minimum: 5,000. Hard maximum: 18,000 (the LONG-tier budget; GPT-Image 2 accepts up to 20,000 on both endpoints per MODEL-SPECS, and 18,000 keeps a 2,000-character safety margin). If under 5,000, the prompt is starved -- expand with genuine specificity (the per-line spelling-lock, the full paired negative block, exhaustive logo-placement language, complete people-anatomy direction, deeper world/scene detail), never with boilerplate. If over 18,000, the prompt is too long for the LONG tier -- tighten redundant phrasing, never by deleting the negative block or any spelling-lock. Spend the expanded budget ONLY on defect-preventing specificity (density-calibration rule, SOP 9.4-strengthening).
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
   h. NO SCENE-DESCRIPTION AS COPY (FIX-3): no prompt bakes a scene/image description, presenter narration, AI meta-commentary, a telegraphing/stage-direction kicker, or the literal word "webinar" as on-slide text (element 3 rule). The only baked text is the verbatim slides_copy.md copy. Any scene description in a HEADLINE/SUBHEAD field was flagged back to the Copywriter, not baked.
   i. TYPE CARD CONSUMED (FIX-9 / FIX-2): element 5 applied this slide type's Typography Architect type-layout card (not a hard-coded every-slide stack), and the hook refrain and italic tertiary line appear ONLY where the type card or hook_variants.json explicitly calls for them, never as default stack elements.
   j. NEGATIVE BLOCK PRESENT AND PAIRED (SOP 9.8): every prompt closes with the dedicated final-paragraph negative block covering all eight defect classes as imperative "Do not ..." sentences, each critical negative has a positive twin stated earlier in the prompt, and the no-contradiction audit passed (no negative contradicts the positive prompt). Missing the block, missing any class, or any negative without a positive twin = AUTO-FAIL (AF-P13).
   k. SPELLING-LOCK PRESENT (FIX-2): every verbatim text string (headline, sub, supporting line, kicker, price, struck price) carries its letter-for-letter spelling-lock instruction immediately after the string. Missing on any string = AUTO-FAIL (AF-P14).
   l. LOGO IMAGE-TO-IMAGE DECLARED (SOP-IMG-01 / SOP-DESIGN-04): on every LOGO_ON_SLIDES = true slide, the prompt declares Mode B (`gpt-image-2-image-to-image`) with LOGO_URL as the first reference and carries the verbatim "place, do not redraw" sentence plus the "do not invent any mark" negative twin. A logo-in-words-only or a text-to-image logo prompt = AUTO-FAIL (AF-P15).
   m. NO PLACEHOLDER / BRACKET TOKEN IN THE PROMPT (FIX-12): scan the whole prompt body for any bracket token "[...]" or the substrings "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending" intended as RENDERED copy. Any such token = AUTO-FAIL (AF-P16), so it can never reach the render. (A spelling-lock or negative sentence that merely names a banned token as forbidden, e.g. the negative block's own "Do not render any bracketed token ...", is permitted; the ban is on a token presented as text to render.)

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

**Failure mode:** If STYLE BLOCK has no representation_ratio, DO NOT invent a racial default. Inventing a demographic ratio for a client is a brand and trust risk. Set representation to NO PEOPLE (people element omitted from all slides) and flag: `representation_source: "default_no_people -- intake unanswered"`. Immediately notify the operator with a flag: "REPRESENTATION UNANSWERED: STYLE BLOCK has no representation_ratio. Deck will default to no people in images. Please confirm or supply the intended breakdown before Phase 2." Do not write a single people-inclusive prompt until the operator or client has answered. Document the no-people state in a comment in every prompt: `// REPRESENTATION: NO PEOPLE default -- no STYLE BLOCK ratio supplied, operator flag issued`. (This is the verbatim brand-steward rule; never invent percentages the client did not supply.)

---

### SOP 9.4 strengthening -- Density Calibration

**When to run:** Within SOP 9.1 step 3, when verifying the character count of every completed prompt.

**Inputs:**
- The completed prompt
- The master SOP Section 7.5 gold-standard exemplar (the density reference)

**Steps:**
1. Every prompt TARGETS 9,000 to 14,000 characters, calibrated against the master 7.5 exemplar (and the second A2 exemplar in Section 9.5 strengthening) as the density reference, then enriched to the higher band with the defect-preventing specificity this SOP adds (the per-line spelling-lock on every text string, the full eight-class paired negative block, the exhaustive image-to-image logo-placement language, the complete people-anatomy direction, deeper world/scene and grade detail). GPT-Image 2 accepts up to 20,000 characters on both endpoints and is strongest on long structured prompts (MODEL-SPECS, the authoritative source); the old 5,000-to-7,500 band used only a quarter to a third of the available budget and STARVED the prompt of the specificity that prevents the forensic defects. The exemplars show the art-direction floor; the higher band is reached by garble-proofing and negative-prompting every line, not by padding.
2. If a prompt comes in UNDER 7,000 characters, trigger a self-check: is the BACKGROUND characterized beyond one word? Is the EXPRESSION written in explicit emotion terms? Is every OBJECT placed (box, banner, rule, chip, tag)? Is the MOOD + lighting stated? Does EVERY verbatim string carry its spelling-lock? Is the full eight-class negative block present and paired? Is the logo image-to-image directive complete? A thin prompt usually means the spelling-lock, the negative block, or the logo/anatomy direction was skimped.
3. Pad with SPECIFICITY, never filler. Add real art direction (a precise scene detail, a per-line font/size/hex, the exact setting and its justification, the strike rendered as a drawn object, the per-string spelling-lock, the paired negative sentences). Never pad with repeated boilerplate or vague adjectives to hit a number. The expanded budget exists ONLY to carry specificity that prevents a forensic defect.
4. Hard limits still apply: under 5,000 characters is a starvation flag (and under any documented floor, an auto-fail at prompt QC); over 18,000 is an auto-fail (AF-P2, the LONG-tier budget, a 2,000-char safety margin below the 20,000 API ceiling). Never trim below the limit by deleting the negative block or any spelling-lock; tighten redundant phrasing instead.

**Outputs:**
- Every prompt in the 9,000 to 14,000 target band (or a documented reason it sits outside, within the 5,000 to 18,000 working range)

**Hand to:** SOP 9.1 step 3 verification

**Failure mode:** If a prompt cannot reach the soft 5,000-character minimum with genuine specificity even after the spelling-lock, the full paired negative block, the image-to-image logo language, and the complete anatomy direction are present, the slide's spec is probably too thin (a near-empty transition slide). Confirm the slide truly needs that little; if so, document it. Never inflate with filler to pass the count, and never reach the count by padding boilerplate.

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
7. **Two-failed-attempts native-text fallback (generalized from PRICE text to ALL critical text -- the forensic Dimension-F fix, "native-text fallback only triggered for price text").** The native-text fallback is NOT scoped to price text only. It applies to EVERY critical verbatim string -- every headline, sub-headline, supporting line, kicker label, price, struck price, and any logo wordmark -- whenever that string garbles, misspells, or duplicates twice at image QC (the "hclarity" / "GRABLED BRANDCO" defect class). After TWO failed render attempts on any such text element, trigger the native PPTX text overlay fallback: regenerate the slide WITHOUT the failing text element (the spelling-lock from element 3 having failed twice on the model), and record the exact intended string in working/checkpoints/pptx_text_overlays.json so the PPTX Assembly Specialist composites it as a native text box at Phase 6, where spelling is guaranteed. For a struck price, set `"strike": true` on the entry. Example entries: `{ "slide": "slide-65", "text": "$1,000", "strike": true, "color": "[BRAND_ACCENT]", "note": "old price, strike line failed render x2" }` and `{ "slide": "slide-23", "text": "the example signature hook", "strike": false, "note": "headline garbled to 'hclarity' x2; native text overlay" }`. This is the documented fallback for ANY slide whose verbatim text fails twice on render (master SOP Section 7.4 and 10.1; SOP-DESIGN-04 step 2 extends the same fallback to the logo).

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
3. Complementary accent use: when the STYLE BLOCK names a complementary accent (e.g., the client's action/urgency color as the pop accent against a structural primary), that accent color is reserved for MAXIMUM CONTRAST moments -- CTAs, price reveals, the single most important number on a slide. Using it everywhere kills its power.
4. Contrast declaration (required in every prompt's BRAND PALETTE element): state the contrast relationship between the headline color and the background it sits on. The minimum threshold is WCAG AA: 4.5:1 for normal text, 3:1 for large text (large = 18pt+ regular or 14pt+ bold). "Charcoal (#231F20) on white (#FBF7F4): contrast ratio 16.5:1, PASS" is the correct form. A prompt that places light text on a light background without a contrast declaration is a defect.
5. Include a COLOR GRADING block at the end of every prompt per Part B.

**Part B -- COLOR GRADING (consistent warm/cool tone, saturation, and temperature across the deck):**
1. Read the COLOR GRADING PROFILE from the STYLE BLOCK: WARM, COOL, or NEUTRAL grade.
   - WARM grade: golden-hour light temperature, slightly lifted shadows, warm midtones, saturated sunset-direction tones. Charcoal and a warm action accent on an off-white base reads as WARM.
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

### SOP 9.8 -- The Mandatory Paired Negative-Prompt Block (every prompt; the defect-mapped close)

**When to run:** Within SOP 9.1, as element 15 of EVERY prompt, written last and placed as the FINAL paragraph of the prompt. This SOP wires the design-library negative-prompt system (45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md) into the presentation prompt-writer and maps it directly onto the forensic reference deck defects. The thin one-line AVOID block of the old element 15 is replaced by this defect-mapped, paired block.

**Why this SOP exists (the defect it kills):** the forensic (Dimension F) shipped garbled text ("hclarity", "GRABLED BRANDCO"), a logo that mutated into four-plus marks, six slides with baked "[owner to confirm]" placeholders, image narration and presenter lines rendered on the slide face, and competing backgrounds. The old AVOID block named none of these as negatives. A negative the model is never told to avoid is a negative it will render. This block states every defect class as an explicit "Do not ..." sentence, and pairs each with a positive twin so the model is steered both away from the wrong result and toward the right one.

**The GPT-Image 2 mechanism (determined, not guessed; MODEL-SPECS Section 1 and Section 4, NEGATIVE-PROMPTING-SOP Section 3):** GPT-Image 2 (both `gpt-image-2-text-to-image` and `gpt-image-2-image-to-image`) has NO negative-prompt field; its roster row reads "Negative prompt: No (inline only)". There is no separate field to populate (a true `negative_prompt` field exists only on Ideogram V3, which this pipeline does not use). Therefore every negative is INLINE imperative text, written as a "Do not ..." sentence, gathered into this dedicated final paragraph. The model manifest (CLIENT-WEBINAR-DECK-SOP Section 9.0) pins GPT-Image 2, so this inline mechanism is the one and only path; never attempt to pass a `negative_prompt` parameter.

**The long-budget cap lift (explicit):** NEGATIVE-PROMPTING-SOP Section 3b caps inline negatives at "the 10 strongest" to avoid prompt pollution on SHORT and MEDIUM prompts. That cap is LIFTED for this long-budget GPT-Image 2 path. With the 18,000-character LONG-tier budget, the full eight-class defect-mapped block fits comfortably and pollution is not a concern at this length; the complete block is mandatory, not a top-ten selection. The two NEGATIVE-PROMPTING-SOP rules that still apply with full force: every critical negative is PAIRED with a positive twin (Section 3b rule 4), and the merged block passes the no-contradiction audit (Section 4) -- no negative may contradict a positive instruction (for example, if the prompt directs dramatic side lighting, the block cannot say "no shadows"; phrase it "no muddy crushed shadows on skin" instead).

**Inputs:**
- The completed positive prompt (elements 1-14) for the slide
- The STYLE BLOCK (REPRESENTATION_MIX, brand hexes, LOGO_URL, TYPOGRAPHY LAW)
- The universal baseline avoid-list (NEGATIVE-PROMPTING-SOP Section 2)

**The eight mandatory defect classes (one imperative sentence each, each with a positive twin stated earlier; adapt the bracketed client values):**

1. **GARBLED / MISSPELLED TEXT.** Negative: "Do not misspell, garble, duplicate, drop, add, substitute, or invent any letter or word; render every quoted text string exactly as written, letter-for-letter." Positive twin (element 3 spelling-lock): each verbatim string already carries "Render this exact string, letter-for-letter, correctly spelled ...".
2. **LOGO MUTATION.** Negative: "Do not draw, invent, redesign, recolor, restyle, or substitute any logo, monogram, icon, leaf, sprout, tree, mountain, badge, roundel, or tagline lockup; reproduce only the supplied reference mark exactly as placed." Positive twin (element 10 / Mode B): "The first reference image is the company logo: place it exactly as specified ... do not redraw, recolor, restyle, reinterpret, or invent it."
3. **PLACEHOLDER / BRACKET TOKENS.** Negative: "Do not render any bracketed token, any square brackets, or any of the strings 'owner to confirm', 'insert', 'tbd', 'placeholder', 'client win', 'endorsement', 'real result', 'to supply', 'pending', or any build note; only the audience-facing verbatim copy quoted in this prompt appears on the slide." Positive twin (element 3): the only baked text is the quoted verbatim slides_copy.md copy. (This pre-empts the render-time placeholder ban AF-F10.)
4. **IMAGE NARRATION / PRESENTER / META / "WEBINAR".** Negative: "Do not render any description of the picture, any spoken-script or presenter line, any stage direction, any telegraphing kicker ('one last proof before you decide', 'before you decide', 'this is not just a webinar'), any internal build note or model self-talk, or the literal word 'webinar' as on-slide text; the slide never narrates the scene it shows." Positive twin (element 3 NEVER-BAKE rule): the image depicts the scene; the slide carries only the verbatim audience copy. (This pre-empts AF-C9 and AF-F9.)
5. **ANATOMICAL ARTIFACTS.** Negative: "Do not render extra or missing fingers, malformed or fused hands, warped or distorted facial features, mismatched or asymmetric eyes, distorted teeth, plastic over-smoothed skin, or unnatural body proportions; hands, faces, and limbs are anatomically correct and natural." Positive twin (element 11): the clear people spec with hair, clothing, explicit expression, framing, and a real-world setting.
6. **BACKGROUND COMPETING WITH TEXT.** Negative: "Do not place a busy, cluttered, or high-detail background directly behind any text zone; keep the text zone clean -- a scrim, a base-color panel, or negative space -- so the type stays legible at presentation distance." Positive twin (elements 5, 6, 8): the thirds-grid text zone and the white-to-transparent scrim gradient over any full-bleed photo.
7. **DEMOGRAPHIC / SKIN-TONE FIDELITY (representation correctness).** Negative: "Do not render a demographic other than the slide's REPRESENTATION_MIX assignment; do not lighten, ashen, grey, or desaturate deep skin tones; do not mono-cast the deck; render rich, warm, dimensional skin true to the captured audience." Positive twin (element 11 Audience Engine): the REPRESENTATION_MIX from the STYLE BLOCK (with NO PEOPLE + operator flag when the mix is uncaptured -- never an invented default).
8. **CARRIED-FORWARD UNIVERSAL BASELINE.** Negative: "Do not render any watermark, signature, user-interface artifact, emoji or clipart glyph, em dash, dark or pure-black background (unless DARK_OK is true), grainy or banded texture, basic or platform-default font (Calibri, Arial, Times, system default), any text rendered without a designed weight and large size, any text within 5% of any slide edge, any text overlapping a human face, or any 'background with text dropped on top' that fails the standalone-art test." Positive twins (elements 2, 4, 6, 9, 14): white base, the designed weight-mapped typography composed into the image, the safe-margin thirds zones, the brand palette, and the gallery-grade standalone-art direction.

**Steps:**
1. Write elements 1-14 first (the positive prompt). For every critical negative you intend to state, confirm its POSITIVE TWIN is already present earlier in the prompt; if a twin is missing, add the positive instruction first, then the negative.
2. Author the eight-class block as the final paragraph, one imperative "Do not ..." sentence per class, adapting the bracketed client values (REPRESENTATION_MIX, hexes, DARK_OK). Keep each sentence specific ("Do not add extra fingers" works; "no bad anatomy" does nothing). Never negate composition by direction ("don't center the subject" is unreliable -- the positive zone instruction in element 6 handles placement).
3. Run the no-contradiction audit (NEGATIVE-PROMPTING-SOP Section 4): read every negative against the positive prompt; rephrase any negative that contradicts a positive instruction so the two agree.
4. Confirm the block is the LAST paragraph of the prompt (models weight endings heavily).
5. Record in the SOP 9.1 step 7 self-check items j (block present + paired + audited) and k (spelling-lock present).

**Outputs:**
- Every prompt closing with the dedicated final-paragraph negative block: all eight defect classes, each an imperative sentence, each critical negative paired with a positive twin, the no-contradiction audit passed.

**Hand to:** QC Specialist -- Presentations (AF-P13 negative-block-present-and-paired auto-fail at Phase 3; the eight classes are re-verified against the rendered image at Phase 5/6 via AF-I1/AF-I2/AF-F7/AF-F9/AF-F10/AF-DC1/AF-R1).

**Failure mode:** If the STYLE BLOCK has no REPRESENTATION_MIX, do not invent one for class 7; set NO PEOPLE + operator flag (SOP 9.4 strengthening failure mode) and phrase class 7 as "Do not render any person (representation uncaptured)." Never drop the block to save characters; the 18,000-character budget always has room for all eight classes.

#### SOP 9.8 reference template -- the full negative block (copy verbatim, adapt the bracketed values)

```
DO-NOT BLOCK (final paragraph; inline, because GPT-Image 2 has no negative-prompt field):
Do not misspell, garble, duplicate, drop, add, substitute, or invent any letter or word; render every quoted text string exactly as written, letter-for-letter.
Do not draw, invent, redesign, recolor, restyle, or substitute any logo, monogram, icon, leaf, sprout, tree, mountain, badge, roundel, or tagline lockup; reproduce only the supplied reference mark exactly as placed.
Do not render any bracketed token, any square brackets, or any of "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending", or any build note; only the quoted audience-facing copy appears.
Do not render any description of the picture, any spoken-script or presenter line, any stage direction, any telegraphing kicker, any internal build note, or the literal word "webinar" as on-slide text.
Do not render extra or missing fingers, malformed or fused hands, warped or distorted facial features, mismatched eyes, distorted teeth, plastic over-smoothed skin, or unnatural body proportions.
Do not place a busy or high-detail background behind any text zone; keep the text zone clean (scrim, base-color panel, or negative space) so type stays legible.
Do not render a demographic other than [REPRESENTATION_MIX]; do not lighten, ashen, grey, or desaturate deep skin tones; do not mono-cast the deck.
Do not render any watermark, signature, UI artifact, emoji or clipart glyph, em dash, dark or pure-black background, grainy or banded texture, basic or default font (Calibri, Arial, Times, system default), text without a designed weight and large size, text within 5% of any edge, text overlapping a face, or a plain background with text dropped on top.
```

---

### SOP 9.9 -- The Concrete Full-Prompt Template (positive block + image-to-image logo directive + negative block)

**When to run:** As the structural reference for SOP 9.1 -- the anatomy of a complete, defect-proofed, long-budget prompt. Use it alongside the master Section 7.5 exemplar; this template adds the spelling-lock, the image-to-image logo directive, and the SOP 9.8 negative block that the bare 15-element order does not show. Adapt every bracketed value from slides_copy.md and the STYLE BLOCK; never ship the bracket tokens themselves (they are an AF-P16 / AF-F10 defect on render).

```
[ARCHETYPE A1] [SECTION: <section>] [LADDER: <rung or none>]
ONE BIG IDEA: <the single idea of this slide, stated plainly>.

// MODE: image-to-image (gpt-image-2-image-to-image). input_urls[0] = LOGO_URL <https URL>.
// (If this is an A5 founder slide, input_urls[1] = FOUNDER_PORTRAIT_URL.)

FORMAT: Create a 16:9 presentation slide image at 2K resolution (2560x1440 pixels).

BACKGROUND: [BASE_COLOR, e.g. warm off-white #FBF7F4] base background. [BRAND_ACCENT hex] used only as accent elements, no more than 20% of the visual area. No dark, navy, charcoal, or pure-black background.

HEADLINE VERBATIM + SPELLING-LOCK: The slide headline reads exactly: "<HEADLINE>". Render this exact string, letter-for-letter, correctly spelled, with no added, dropped, doubled, or substituted characters. Do not alter, misspell, duplicate, abbreviate, or garble any character of it. [Repeat a spelling-lock sentence for EACH additional verbatim string: SUBHEAD "<SUBHEAD>", KICKER "<KICKER>", any price "<PRICE>", any struck price "<STRUCK_PRICE>".]

TYPOGRAPHY: One typeface family ([FAMILY, default Montserrat]); hierarchy by weight. <HEADLINE> in [FAMILY] Black, approximately 62-86pt; <SUBHEAD> in [FAMILY] ExtraBold, 24-32pt; <KICKER> in [FAMILY] Bold, ~13pt, gold, letter-spaced, all-caps; any giant number 110-150pt. The typography is designed INTO the image as rendered designed type, not a basic font dropped on top.

FONT PLACEMENT: [per the Typography Architect type-layout card for this archetype; the canonical stack is the fallback only].

THIRDS GRID: primary visual subject in the [zone] region; text occupies the [zone] region; the face sits in a named thirds zone that does NOT intersect the text zone.

OBJECT PLACEMENT: [objects/diagram/price-tag] in [region]; objects do not overlap the headline text.

OVERLAYS: [hook overlay per hook_variants.json IF this is a scheduled hook beat, else "No text overlays other than the verbatim copy above."]

BRAND PALETTE: Primary accent [HEX1, role]; secondary [HEX2, role]; tertiary [HEX3, role]. All backgrounds remain white. Headline contrast declaration: [charcoal #231F20 on off-white #FBF7F4, ratio 16.5:1, PASS] (WCAG AA minimum 4.5:1 normal, 3:1 large).

LOGO (image-to-image): The first reference image is the company logo: place it exactly as specified (bottom-right white chip, approximately 9% slide width, 1px gold border, at least 5% from any edge); do not redraw, recolor, restyle, reinterpret, or invent it -- reproduce the supplied mark pixel-for-pixel.

PEOPLE (three engines, on people-slides): FACIAL EXPRESSION ENGINE: [hair + clothing + explicit emotion expression from the vocabulary table]. AUDIENCE ENGINE: [person/people matching REPRESENTATION_MIX from the STYLE BLOCK]. WORLD ENGINE: [the real-world setting + why it fits the one idea + the GROUNDED_CONTENT moment from this client's method]. SHOT: [Engine A single / B group / C presenter framing].

BULLETS: [short, max 5 words each, IF present].

MOOD: [emotional tone]; this slide carries its own felt beat readable in 2 seconds. TEMPERATURE LOCK: [WARM/COOL/NEUTRAL] to match the deck grade.

PROFESSIONALISM (standalone-art gate): finished gallery-grade standalone piece of art; intentional art direction (focal hierarchy, negative space, depth of field); premium lifestyle-documentary photography (never stock, clipart, or cartoon); directional warm lighting; clear hero subject; typography composed INTO the image. One image you could frame and hang.

// COLOR GRADING: TEMPERATURE=[WARM/COOL/NEUTRAL], SATURATION=[desc], TONAL CONTRAST=[HIGH/LOW], GRADE=[deck profile]. Every image in this deck must feel shot in the same light.

DO-NOT BLOCK (final paragraph, all eight SOP 9.8 classes):
Do not misspell, garble, duplicate, drop, add, substitute, or invent any letter or word; render every quoted text string exactly as written, letter-for-letter.
Do not draw, invent, redesign, recolor, restyle, or substitute any logo, monogram, icon, leaf, sprout, tree, mountain, badge, roundel, or tagline lockup; reproduce only the supplied reference mark exactly as placed.
Do not render any bracketed token, any square brackets, or "owner to confirm", "insert", "tbd", "placeholder", "client win", "endorsement", "real result", "to supply", "pending", or any build note; only the quoted audience-facing copy appears.
Do not render any description of the picture, any spoken-script or presenter line, any stage direction, any telegraphing kicker, any internal build note, or the literal word "webinar" as on-slide text.
Do not render extra or missing fingers, malformed or fused hands, warped or distorted facial features, mismatched eyes, distorted teeth, plastic over-smoothed skin, or unnatural body proportions.
Do not place a busy or high-detail background behind any text zone; keep the text zone clean (scrim, base-color panel, or negative space) so type stays legible.
Do not render a demographic other than [REPRESENTATION_MIX]; do not lighten, ashen, grey, or desaturate deep skin tones; do not mono-cast the deck.
Do not render any watermark, signature, UI artifact, emoji or clipart glyph, em dash, dark or pure-black background, grainy or banded texture, basic or default font, text without a designed weight and large size, text within 5% of any edge, text over a face, or a plain background with text dropped on top. Do not apply any gradient fill, radial glow, bloom, or metallic shimmer to any text element; all type uses flat solid brand color only.
```

**Note on the logo directive:** the `// MODE` comment and the LOGO sentence together are the image-to-image guard; the Slide Submitter reads the mode and passes LOGO_URL as `input_urls[0]` per SOP-IMG-01 Mode B. A prompt that omits the image-to-image mode declaration or the "place, do not redraw" sentence on a logo slide fails AF-P15 at Phase 3 prompt QC.

**Hand to:** QC Specialist -- Presentations (the template is the structure every AF-P check is run against).

---

### SOP 9.10 -- Producing-Rule Additions (Vision-Gate Doctrine, v12.9.0)

**When to run:** Alongside SOP 9.1, SOP 9.6, and SOP 9.7 on every prompt in every presentation deck. These rules are the PRODUCING-ROLE half of each auto-fail code introduced in the vision-gate overhaul. Each rule here has a corresponding hard auto-fail in qc-specialist-presentations-sops.md (the gate is the enforcement; this SOP is the authoring discipline).

**Inputs:**
- intake.json (audience_composition, FINAL_PRICE, fish_audio_voice_id if available)
- SOP-CAST-01-AUDIENCE-COMPOSITION-AND-CASTING-LEDGER.md (the casting ledger)
- SOP-IMG-05-PIL-LOGO-COMPOSITE.md (gradient ban and PIL composite)
- SOP-PITCH-05-DELIVERABLE-BUNDLE.md (audio deliverable)
- The brief (value stack, promises, re-pitch block, validator sources, Wall of Wins tiles)

---

**Part A -- GRADIENT BAN (producing side; QC enforcement: AF-GRAD)**

The following prompt language is PERMANENTLY BANNED from every prompt in every presentation deck:

- Any gradient fill on a typographic element: "liquid-gold gradient", "metallic warm gold", "gold-to-gold gradient", "gradient fill on the headline"
- Any glow on a text element: "soft warm radial glow", "metallic glowing", "raspberry glowing result line", "glow behind the price"
- Any bloom or shimmer on type: "luminous bloom on the numeral", "warm shimmer on the headline"

Replace ALL of the above with: flat solid brand-color type at full weight and contrast. The STYLE BLOCK gold hex is used as a flat solid color; it can be the fill of a kicker label or divider rule but never a gradient fill on any type glyph. The scrim gradient (on the image atmospheric layer, behind type) is not banned. Only gradients and glows applied TO TYPE are banned.

Write the gradient ban into the DO-NOT BLOCK (element 15) as: "Do not apply any gradient fill, radial glow, bloom, or metallic shimmer to any text element; all type uses flat solid brand color only."

---

**Part B -- OPACITY BACKGROUNDS ON FLAT SLIDES (producing side; QC enforcement: AF-OPACITY)**

Slides that would otherwise be pure flat color (transition slides, type-dominant A4 slides with no photo brief, data-only slides) must include a faded photographic atmospheric background layer at low opacity (approximately 10-15%) behind the type. The atmospheric layer is:

- On-brand and on-temperature (matches the deck's grade profile per SOP 9.7 Part B)
- Contextually appropriate (a soft bokeh interior, a blurred outdoor scene, a textured warm surface -- never a distracting photo at full opacity)
- Composed so the type reads cleanly above it (scrim as needed)

State the atmospheric layer in the prompt: "Faded atmospheric background at approximately 10-15% opacity behind the type zone. [Describe the background scene.] The type must read cleanly above it; apply a soft white scrim if needed."

**Exception:** slides explicitly flagged DARK_OK = true use their dark base with no overlay requirement. Hook A4 slides (type-dominant) may use a 10-15% opacity atmospheric OR a clean base color -- both are acceptable.

---

**Part C -- IMAGE-MODEL CONSISTENCY (producing side; QC enforcement: AF-MODEL)**

All slides in a single deck are generated from the SAME image model and the SAME locked color-grade and lighting recipe. The model is declared once in the brief and does not change mid-deck. The grade is declared in the STYLE BLOCK COLOR GRADING PROFILE and applied identically to every prompt via SOP 9.7 Part B.

A mid-deck model swap (switching from one generation model to another without Director sign-off and a full re-grade of prior slides) is a defect. If a slide must be re-generated on a different model because the original is unavailable, flag the Director and the QC Specialist. A mixed-model deck fails AF-MODEL at image QC.

---

**Part D -- LAYOUT VARIETY AND NO-CONSECUTIVE-ARCHETYPE RULE (producing side; QC enforcement: AF-SAME)**

Authoring rule: when assigning archetypes to slides in Phase 1 (the arc assignment step), the following variety constraints apply:

1. NO TWO CONSECUTIVE SLIDES may share the same archetype (A1-A5) AND the same image zone (left/right/top/bottom/full-bleed). A deck where every slide is A2 photo-right / type-left is the documented "swap the person, keep the frame" failure.
2. MINIMUM VARIETY FLOOR: across any 10-slide window in the deck, at least 3 distinct archetypes must appear.
3. These constraints are checked at Phase 1 arc assignment AND enforced by AF-SAME at Phase 5/6 image QC.

Vary composition, crop, camera angle, and subject placement across slides while holding the grade and model constant. Consistency is a color and light property, not a composition property.

---

**Part E -- CASTING LEDGER PROPAGATION (producing side; QC enforcement: AF-CAST)**

Before writing any people-prompt, confirm `audience_composition` is captured in intake.json. If absent, HALT (see SOP-CAST-01). When captured:

1. Read the Casting Ledger from the brief (built by the Brief Author per SOP-CAST-01 Section 2).
2. For each people-slide, write element 11 (Audience Engine) using the demographic assigned by the Casting Ledger for that slide.
3. Do NOT add a per-slide demographic LOCK ("do not render a demographic other than [X] on this slide"). Replace it with: "render the demographic assigned by the Casting Ledger for this slide ([demographic]); render with dignity, warmth, and accurate skin-tone fidelity."
4. Facial-intelligence rule: bright, warm, hopeful expression on positive beats (vision, future-pace, celebration, transformation). Brow tension, the "2am-spreadsheet face" on pain beats. Never dour or blank on a positive beat (AF-FACE-MOOD).

---

**Part F -- PROMISES-NOT-PRICES (producing side; QC enforcement: AF-PRICE-FACE)**

On offer-component slides, the slide face carries the PROMISE / OUTCOME of each component, not a per-component dollar value. Examples:

- FAIL: "Day 1 Strategy Session | Value: $997"
- PASS: "Day 1: The one conversation that changes how your family reads money forever"

The only authorized dollar figure on the deck face is the SINGLE big callout (the final price, e.g., "$97") on the main offer slide. Every other slide states promises, outcomes, and transformations. The value-stack math (total stack dollar value, running tally) lives in the presenter notes and the re-pitch, not on the audience-facing slide copy.

---

**Part G -- EXTERNAL VALIDATORS ONLY (producing side; QC enforcement: AF-VALIDATOR)**

The "who says so" slide cites approximately 4 distinct EXTERNAL third-party references:

- Named publications (Forbes, Harvard Business Review, peer-reviewed journals with the journal name)
- Named institutions (universities, research centers, named government agencies)
- Named peer-reviewed studies (author + publication + year)

Do NOT cite self-referential proof on the validator slide: "our families agree", "students who lived it", "our graduates say" -- that is social proof, not external validation. Social proof lives on the Wall of Wins. The validator slide is for external institutions saying the SAME THING independently.

Capture external proof at intake. If the client has not supplied real external proof, the Deep Research Specialist finds credible public research. Never fabricate citations.

---

**Outputs:**

- All prompts passing the gradient ban (no gradient/glow on type)
- All flat slides carrying an atmospheric background layer
- Deck-wide archetype variety verified before prompt writing begins
- Every people-prompt referencing the casting ledger (no per-slide demographic locks)
- All offer-component slides stating promises not per-item prices
- The validator slide citing external proof only

**Hand to:** QC Specialist -- Presentations (AF-GRAD, AF-OPACITY, AF-MODEL, AF-SAME, AF-CAST, AF-FACE-MOOD, AF-PRICE-FACE, AF-VALIDATOR)

**Failure mode:** If audience_composition is absent, HALT at Part E (do not proceed to people-prompts). If no external proof is available for the validator slide, flag to the Director before writing that slide's prompt.

---
