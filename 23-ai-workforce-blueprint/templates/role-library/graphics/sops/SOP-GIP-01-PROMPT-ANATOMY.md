# SOP-GIP-01 — Graphics Prompt Anatomy (BINDING)

**ID:** SOP-GIP-01
**Classification:** ZHC SOP — Graphics Image Protocol (GIP)
**Owner Role:** Prompt Author (authoring, per decision GK-D2) + Prompt QC Specialist (independent grading, judge != writer) + Generation Operator (mechanical preflight backstop, brand verification via Brand Systems Specialist)
**Version:** 2.0 | **Date:** 2026-10-10
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.4, prompt-bands.json v3 (§-refs verified 2026-07-15, GK-20 band<->routing reconciliation; prompt-bands pin updated v2 to v3 at the v2.0 landing, band file full-read at v3)
**BlackCEO Integration:** v2.0 merges the BlackCEO Signature Image Intelligence system (skill 71-blackceo-signature-page) into the prompt anatomy. Where this SOP and the BlackCEO system conflict, the BlackCEO way wins. This is non-negotiable.

**Universal scope:** This image intelligence applies to EVERY image the Graphics Department creates: landing pages, social media posts, ad creatives, product shots, thumbnails, email headers, profile images, video stills, and any other visual asset. It is not limited to landing pages. The anti-generic-AI standard, the representation intelligence, the camera direction, the color grading, and the style systems work identically whether the output is a 21:9 hero image or a square Instagram post. When a section references a specific format (e.g., "landing page"), treat it as one application of a universal principle. Presentation slides are covered as doctrine, not as pipeline routing: the Presentations Department adopts this image intelligence inside its own pipeline, and audience decks are NOT routed through the Graphics Image Protocol pipeline. The presentations boundary contract (Skill 45 SKILL.md SCOPE, SOP-DIU-611, CDO SOP 9.8, SOP-IMG-02) governs deck routing and is unchanged by this SOP.

---

## BlackCEO Image Philosophy (applies to every prompt)

The operating philosophy is simple: **attention is scarce, boring is a defect, generic AI aesthetics are a defect, and every visual choice must earn its place.** Refuse work that is merely clean, trendy, symmetrical, or technically competent when it still looks like a generic AI image. Make intentional decisions about composition, typography, color, lighting, subject, fashion, texture, scale, and emotional effect. A passing image should feel art-directed rather than auto-generated.

**On dark vs. light:** Dark cinematic treatments are the industry default because shadows hide AI flaws — bad anatomy, muddy skin, warped features. Lighter treatments expose every flaw, which is why most AI work avoids them. The BlackCEO aesthetic does not hide behind darkness. When the brief calls for brightness, the prompt must carry enough specificity (skin chromatic depth, hair strand detail, lighting precision) to survive it. Do not default to dark overlays as a crutch for weak prompts.

---

## Why this exists

The Graphics department had MAX-only prompt caps (`diu_validator.py prompt-caps`, SHORT ≤500 /
MEDIUM ≤2,800 / LONG ≤19,000) and **no minimum floor anywhere** — a one-line prompt could reach
the paid Kie.ai / GPT-Image-2.5 API unchallenged (diagnosis G1). This SOP is the graphics analogue
of the Presentations 9,000-character prompt floor + quality gate: every production image prompt is
authored to a TEN-ELEMENT anatomy and validated by `diu_validator.py prompt-band` **before**
submission. SOP-DIU-601 preflight step 2 now runs the **BAND** check (floor + cap + quality), not
just the cap check.

> Design principle (copied from Presentations): *"Enforcement, not description — a rule without a
> gate is a suggestion."* Clearing the floor is **NECESSARY, never SUFFICIENT**: the quality gate
> (elements 4, 5, 8, 10) fails independently of length (AF-GIP-PROMPT-QUALITY).

Band names, tiers, and quality teeth live in `45-design-intelligence-library/library/_system/prompt-bands.json` (bands: `text_bearing_long`, `visual_long`, `medium`, `short_draft`; `short_draft` is NEVER a client deliverable). The band file's qualitative contract: `text_bearing_long` is the LONG text-bearing band (150 distinct-word floor), `visual_long` is the LONG non-text band (120 distinct-word floor), `medium` is the MEDIUM non-text specialty band (60 distinct-word floor), and `short_draft` is the SHORT draft band (25 distinct-word floor, drafts only). For length, the numbers (target, floor, ceiling) are defined only by rule 12 of `07-kie-setup/references/kie-common-rules.md`, enforced by `shared-utils/kie_prompt_enforcer.py` over `kie_live_adapter.py prompt-budget --model <id>`; this SOP states no character floors or caps, and the thresholds inside `prompt-bands.json` and `diu_validator.py` are owned by the prompt-band code work.

**GK-20 (2026-07-15, band<->routing reconciliation; conformed to prompt-bands.json v3 at the
v2.0 landing):** `text_bearing_long` targets GPT-Image-2.5 T2I/I2I only — `nano-banana-2` was
removed from its endpoints (Nano Banana is refused for ANY text-overlay deliverable everywhere
else in the fleet). prompt-bands.json v3 carries NO `text_bearing_medium` band. Every
quote-card/text-led social post declares `text_bearing_long` on the prompt's first line and
routes to GPT Image 2.5 Sunburst, per the band file's own routing note. Ideogram V3 appears
only in the `medium` band's endpoints, and `medium` is a non-text-bearing, non-social
specialty band: Ideogram V3 work declares `medium`, and no text-bearing band names an
Ideogram endpoint.

---

## The TEN-ELEMENT anatomy (every production prompt)

1. **ASSET CLASS + BAND declaration (first line):** `ASSET: <class> | BAND: <band-id>`. The band id
   selects the floor/cap/quality contract the validator enforces.
2. **SUBJECT + SCENE:** who/what, action, environment — specific, never generic stock language.
3. **COMPOSITION GRID:** thirds + zone percentages; focal hierarchy; safe margins for the target surface.
4. **STYLE BLOCK:** the style-card DNA or BRAND.md tokens (`{BRAND_COLOR_1/2}`, `{FONT_NOTE}`,
   `{LOGO_NOTE}`), verified by the Brand Systems Specialist BEFORE submission (existing rule,
   brand-systems-specialist.md §Brand Systems Verification). Include at least one brand HEX and an
   explicit type size on any text-bearing surface.
5. **TYPOGRAPHY + VERBATIM COPY (text-bearing bands only):** every baked string verbatim, each
   wrapped in a spelling-lock: *"Render this exact string, letter-for-letter, correctly spelled, with
   no added, dropped, doubled, or substituted characters: '<STRING>'."* A verbatim string without its
   lock is an AUTO-FAIL (AF-GIP-PROMPT-QUALITY).
6. **LIGHTING + COLOR GRADE:** direction, mood, grading block with brand hexes.

   **BlackCEO Lighting Intelligence:** Lighting must feel deliberate and sculptural. Use: dimensional
   beauty lighting, controlled studio key light, sculpting facial light, strong but elegant tonal
   separation, cinematic edge light, subtle rim light, luminous highlights, directional softbox quality,
   controlled shadow shaping. The subject should feel carved out of the frame. Avoid flat illumination.

   **Subject/background separation:** Create clear visual layers (background, subject, face/focal detail)
   using tonal contrast, color contrast, rim light, edge light, depth of field, or selective sharpness.

   **Shadow rule:** Very deep blacks with preserved internal texture — NOT featureless black holes.
   Dark skin must remain dimensional and chromatically rich. Dark clothing must show seams and fabric
   texture. Do not crush all shadow information.

   **Specular highlights:** Faces are not flat matte. Include luminous controlled specular highlights
   on skin, lips, and jewelry. High microcontrast on lashes, hair, and lip texture.
7. **PEOPLE / REPRESENTATION:** explicit casting; likeness work routes to the Photo Shoot Director via
   the Likeness Rights Officer (existing DIU law); **no demographic default** (a hardcoded split such
   as "60/30/10" is a hard AF-R3 fail — representation comes from the client's captured audience).

   **BlackCEO Representation Intelligence (MANDATORY for Black/African-descended subjects):**
   Do not stop at "Black woman" or "Black man." Use the mandatory prompt order:
   - **Black woman:** role -> skin tone -> hairstyle -> attire -> expression/posture
   - **Black man:** role -> skin tone -> hairstyle -> facial hair -> attire -> expression/posture

   **Skin tone:** Select from the 25-entry BlackCEO skin-tone library (butter cream, light caramel,
   honey wheat, cafe au lait, golden pecan, cinnamon sugar, butterscotch, caramel bronze, toffee brown,
   copper penny, milk chocolate, chestnut brown, cocoa powder, burnt sienna, coffee bean, dark amber,
   mahogany wood, espresso brown, dark chocolate, ebony wood, midnight brown, charcoal velvet,
   obsidian black, onyx stone, jet black). Each label is a depth/undertone cue. Preserve natural
   gradients across face, neck, and hands. Do not lighten deep skin in aspirational scenes or darken
   it for pain. Lighting changes; identity does not.

   **Melanated skin chromatic depth (NON-NEGOTIABLE):** Rich melanated skin tones with full chromatic
   depth, warm brown, golden, and subtle red undertones; never gray, ashy, muddy, dull, or desaturated.
   Preserve fine skin microtexture (pores, subtle variation) while maintaining polished macro-level
   complexion. No plastic skin, no wax, no CGI smoothing.

   **Hair — Black Women's 40-Style Library (use exact names):**
   *Professional/corporate:* (1) Classic relaxed straight — waist-length, jet-black, pressed pin-straight, crisp middle part. (2) Soft body waves — mid-back rich chocolate-brown hair with loose even S-waves. (3) Sleek side-part ponytail — long ponytail anchored high with a deep side part. (4) Blunt-cut bob — jaw-length inky bob, sharp center part, ruler-straight hem. (5) Layered shoulder cut — shoulder-skimming hair with subtle face-framing layers. (6) Feathered pixie — short tapered sides with longer crown layers in wispy feathers. (7) Finger-wave pixie — very short crop with tight glossy finger waves. (8) Tapered curly crop — low-faded natural cut with defined coils on top. (9) Defined spiral wash-and-go — shoulder-length corkscrew curls, clumped and shiny with natural texture. (10) Flat-twist crown and low bun — two neat flat twists resolving into a compact sleek bun.
   *Lifestyle/creative:* (11) Goddess faux locs — soft wavy-ended locs, mid-back or longer, natural movement. (12) Waist-length honey-blonde waves — long center-parted extensions in warm blonde. (13) Iconic cropped pixie — close-cropped sides with feathered crown texture. (14) Side-shaved undercut with curls — one side buzzed, remaining hair in defined coils. (15) Boho jumbo box braids — tailbone-skimming braids with loose bohemian ends. (16) Knotless waist-length braids — lightweight tension-free braids, clean parting. (17) Teeny Weeny Afro (TWA) — carefully shaped short coils. (18) High Afro puff — curls gathered into a cloud-like crown puff. (19) Sleek high ponytail — glass-smooth roots and a high snatched ponytail. (20) Vibrant colored bob — chin-length blunt cut in a deliberate bold hue. (21) Platinum-blonde buzz cut — one-length clipper cut in icy blonde. (22) Crochet spiral curls — large bouncy pre-curled spirals. (23) Beaded Fulani braids — feed-in cornrows with selected wooden/cowrie accents. (24) Halo crown braid — single braid wrapped elegantly around the head. (25) Half-up half-down curls — top section gathered, remaining curls flowing. (26) Pastel mermaid waves — long layered waves in a deliberate fantasy palette. (27) Voluminous twist-out — two-strand twists unraveled into fluffy defined curls. (28) Braided Bantu knots — small braided sections wrapped into mini-knots. (29) Bubble ponytail — sleek pony segmented into intentional rounded bubbles. (30) Free-form natural afro/twist-out — large airy coils picked for volume.
   *Protective/cultural:* (31) Micro braids — very fine braids creating a dense curtain of delicate strands. (32) Passion twists — chunky bohemian twists with curled ends. (33) Marley twists — textured twists with natural loc-like surface. (34) Senegalese twists — sleek rope-like twists in selected length. (35) Triangle-part box braids — box braids with geometric triangle parting. (36) Feed-in cornrows with design — deliberate curved/zigzag patterns. (37) Stitch braids — cornrows with visible stitch-like parting technique. (38) Crochet locs — installed locs with believable texture and density. (39) Butterfly locs — distressed faux locs with wrapped/looped texture. (40) Spring twists — springy pre-twisted coils with visible bounce.

   **Hair — Black Men's Library:**
   *Professional:* (1) Low Caesar with taper. (2) Short textured crop, 1-1.5 inch natural texture with low fade. (3) Executive contour cut, low skin fade at temples. (4) Maintained short locs, 3-4 inch palm-rolled with clean temple fade. (5) Business buzz cut. (6) Conservative crew cut.
   *Lifestyle:* (7) High-top freeform locs with blonde tips. (8) Two-strand twist-out with taper fade. (9) 360 wave pattern with mid fade. (10) Burst-fade frohawk. (11) Box braids with undercut. (12) Bleached mini afro with skin fade. (13) Cornrow design with man bun. (14) Sponge curls with drop fade.
   *Facial hair:* (1) Pristine clean-shaven. (2) Five-o'clock shadow, 1-2mm. (3) Defined goatee circle. (4) Modern Van-Dyke. (5) Crisp chin strap. (6) Short boxed beard, 0.5-0.75 inch. (7) Tapered beard fade. (8) Groomed full beard, 1.5-2 inches. Clean-shaven counts as a deliberate selection.

   Describe construction, length, volume, parting, texture, color, hairline, and motion.
   Black hair must show individual strands and shape — never crushed to featureless black. Do not fuse
   braids into shoulders. Do not turn coils into a smooth helmet. Do not replace a specified style
   with a generic one. Do not crop away the hairstyle if it is part of the asset's distinctness.

   **Facial expression:** Replace generic emotion labels with visible physical cues: gaze, eyelids,
   brow tension, mouth/jaw, shoulder position, hand behavior, head angle. Do not default to a broad
   camera smile.

   **Set diversity:** Across a multi-image set, do not repeat the same skin-tone + hairstyle
   combination unless deliberate recurring-character continuity is recorded. Never randomize a real
   person's complexion, hair, or facial hair away from their supplied reference.
8. **LOGO / REFERENCE DIRECTIVE:** image-to-image `input_urls` handling; the STYLE-REFERENCE-ONLY
   sentence whenever refs are stylistic (MODEL-SPECS §4 — MANDATORY for GPT-Image-2.5 I2I and
   Nano Banana 2): *"Use the attached images only as style reference for color grading, lighting, and
   composition — do not copy their subjects, faces, or text."*
9. **TECHNICAL:** endpoint id, aspect ratio (REQUIRED on Seedream), resolution, `output_format`
   (`png` for text-bearing), `watermark:false` on Wan.
10. **NEGATIVE BLOCK (final paragraph):** imperative "Do not…" sentences covering the eight defect
    classes (garbled text, logo mutation, anatomy, contrast/legibility, placeholder tokens,
    demographic default, watermark, style-drift) PLUS the five BlackCEO-specific defect classes below.
    The validator requires the block to name **≥ 6 of the 8** base classes **AND all 5** BlackCEO classes
    when the prompt includes Black/African-descended subjects.

    **BlackCEO negative classes (mandatory when applicable):**
    - Do not render melanated skin as gray, ashy, muddy, dull, or desaturated.
    - Do not crush Black hair to featureless black; preserve individual strands and shape.
    - Do not smooth skin to plastic/wax/CGI; preserve fine microtexture.
    - Do not replace a specified hairstyle with a generic one or fuse braids into clothing.
    - Do not lighten deep skin in aspirational scenes or darken it for dramatic effect.

---

## BlackCEO Color Grading Intelligence

**Color correction** establishes believable exposure and color balance. **Color grading** establishes
the creative look and mood. The default BlackCEO grade: selective hyperchroma, deep black-point
architecture, controlled highlight energy, protected natural skin/material color, rich chromatic
depth, focal microcontrast, and sculptural separation.

**Three grade recipes:**
| Recipe | Role | Direction |
|---|---|---|
| Vivid editorial | Hero, purpose, desire | Bold selected colors, crisp separation, restrained neutral space, tactile materials, intact skin texture. |
| Cinematic pressure | Pain and inner conflict | Strong color relationships remain, tighter light, deeper surroundings; the person stays readable and dignified. |
| Warm, open possibility | Solution and human benefit | More open light, controlled warm accents, saturated brand details, relaxed posture; no automatic yellow/orange wash. |

**Selective saturation rule:** Saturate wardrobe, set, and architecture intentionally. Protect skin,
whites, paper, teeth, metallic reflections, and fine material detail. Do not apply a global orange
wash. Do not push all reds/oranges globally; the skin range must remain visibly different across
subjects.

**Avoid the generic AI finish:** Do not merely write "not a ChatGPT image." Specify replacements:
waxy skin → pores and natural tonal variation; identical models → cast register with distinct
individuals; default orange light → specified key light direction and temperature; arbitrary bokeh →
coherent depth of field; over-polished props → named materials; featureless beige room → meaningful
environment; generic stock smile → section-specific expression from the expression intelligence table.

---

## BlackCEO Camera, Lens, Aperture, Framing and Positioning Intelligence

A BlackCEO image prompt never stops at "cinematic portrait." It defines how the viewer experiences
the subject. Keep these four layers separate:

- **Shot distance** decides intimacy versus environmental information.
- **Camera angle/viewpoint** decides power, equality, observation, tension, or motion.
- **Frame position** decides where the subject lives in the composition (3x3 grid).
- **Lens/aperture** decides perspective feel, compression, depth, and subject separation.

Do not call "lower third" a camera angle. Do not call "85mm" a shot type. Name each applicable layer.

**Shot distance table:**
| Shot | Best use |
|---|---|
| Extreme close-up | Eyes, lips, hand detail; intensity, decisive emotional beat |
| Close-up | Face and upper shoulders; intimacy, micro-expression |
| Medium close-up | Head to chest; expression plus gesture, editorial portrait |
| Medium shot | Waist-up; gesture, conversation, work/action |
| Three-quarter portrait | Knees/thighs up; fashion, posture, editorial presence |
| Full-length | Entire body; fashion, movement, power stance |
| Wide/environmental | Full figure in meaningful setting; story, context, aspiration |

**Camera angle table:**
| Angle | Emotional purpose | Use |
|---|---|---|
| Eye-level | Equality, connection, direct conversation | Founder presence, conversational portraits |
| Slight low angle | Elevated confidence without caricature | Hero, authority, leadership |
| Low-angle power | Monumental presence | Select hero/climax moments; use sparingly |
| Slight high angle | Reflection, quiet observation | Desk moments, intimate pain |
| Dutch angle | Controlled tension | Bold/creative moments only; never default |
| Side profile | Contemplation, focus beyond frame | Pain, anticipation, thought |
| Over-the-shoulder | Participation, process | Writing, coaching, designing |
| Back view / entering frame | Forward movement, destination | Transformation, journey |

**Lens intelligence (full-frame-equivalent look):**
| Focal length | Character | Use |
|---|---|---|
| 35mm | Immersive environmental, energetic | Founder-in-environment, lifestyle, groups |
| 50mm | Natural, balanced | General editorial, two-person interaction |
| 70-85mm | Flattering compression, polished | Close portraits, hero, fashion beauty |
| 105-135mm | Stronger compression, luxurious | High-end editorial, controlled outdoor |

**Aperture intent:**
| Aperture | Result | Use |
|---|---|---|
| f/1.2-f/1.8 | Very shallow, strong bokeh | Single-face close-up, luxury beauty |
| f/2-f/2.8 | Shallow but usable | Medium close portraits, fashion |
| f/4 | Balanced separation and context | Waist-up, two people, editorial |
| f/5.6-f/8 | More environment clarity | Groups, rooms, full-body, lifestyle |

Never demand f/1.2 blur while requiring four people at different depths to be sharp.

**3x3 positioning:** Use a mental nine-zone grid. Record the subject anchor and text-safe area separately.
Example: Subject anchored in middle-right, eyes near upper-right intersection, generous left-third
negative space for copy or headline.

**Set variation rule:** Before writing prompts for a multi-image set, compare neighboring assets. Vary
shot distance, angle, 3x3 position, lens behavior, posture, lighting mood, and color emphasis. Do not
repeat the same 85mm eye-level portrait twelve times.

---

## BlackCEO Style System Libraries (149 styles across 3 libraries)

The BlackCEO system includes three canonical style libraries. Each contains complete visual grammars
with research synthesis, AI construction rules, style compilers, and fidelity gates. The full documents
live in this repository, in the Skill 71 reference library, at the paths below. **Do not inline all 149 styles into every prompt.** Select ONE
style per asset, load its complete style block, and translate it into Element 4 (Style Block).

**CRITICAL RULE: Never pass a source photographer, artist, or director name to an image generator.**
The source names exist only for internal research traceability. Translate the selected style into its
concrete visual grammar: composition, camera, lens, light, color, texture, environment, gesture,
wardrobe, emotional register, and finish. Never write "in the style of [name]" or "shot by [name]."

### Library 1: 50 Cinematic Image Style Systems
Path: `71-blackceo-signature-page/references/BlackCEO-Cinematic-Image-Style-Systems-v2.0.md`

01. Sovereign Human Light | 02. Physical Paradox Cinema | 03. Urban Voltage Framing | 04. Precision Storybook Geometry | 05. Social Dread Realism | 06. Pulp Deep-Frame Cinema | 07. Radiant Interiorism | 08. Chromatic Gothic Humanism | 09. Intimate Epic Realism | 10. Luminous Isolation | 11. Tactile Severity | 12. Living Memory Naturalism | 13. Embodied Light Realism | 14. Domestic Uncanny Noir | 15. Street Pulse Cinema | 16. Somatic Spiral | 17. Composed Heritage Radiance | 18. Neon Memory Drift | 19. Pressure-Point Realism | 20. Elastic Absurdist Optics | 21. Neighborhood Witness Realism | 22. Social Geometry Engine | 23. Gulf Gothic Reverie | 24. Monolithic Atmosphere | 25. Griot Social Clarity | 26. Pop Chiaroscuro Melodrama | 27. Liberation Collage | 28. Wandering Cinecriture | 29. Archive-Truth Remix | 30. Raw Sublime Friction | 31. Sovereign Angle Cinema | 32. Forensic Noir Precision | 33. Everyday Poetic Witness | 34. Operational Immersion | 35. Invitational Distance | 36. Suburban Dream Breach | 37. Tidal Haunt Realism | 38. Ornate Gaze Mechanics | 39. Ancestral Tide Lyrism | 40. Storybook Expressionist Gothic | 41. Sahel Surreal Montage | 42. Elastic Real-Time Immersion | 43. Dignified Human Focus | 44. Atmospheric Worldforge | 45. Chadian Luminous Minimalism | 46. Sensual Landscape Interiorism | 47. Historic Counter-Montage | 48. Fragmented Sensory Memory | 49. Equatorial Civic Witness | 50. Psychological Face Chamber

Each system includes: research synthesis, persistent visual invariants, AI image-construction rules
(composition/camera, lighting, color, texture/environment, character direction, avoid list), AI
deployment block, style compiler (5 non-negotiable anchors, compilation sequence, output checklist),
and style fidelity gate (signature test, scoring, correction rule).

### Library 2: 49 Photographer DNA Styles
Path: `71-blackceo-signature-page/references/BlackCEO-Famous-Photographers-DNA-Style-Library-v1.1.md`

VDL-001 Witnessed Dignity | VDL-002 Table of Memory | VDL-003 Power After Dark | VDL-004 Fragmented Evidence | VDL-005 White Field Intensity | VDL-006 Electric Social | VDL-007 Unvarnished Encounter | VDL-008 Ceremonial Grandeur | VDL-009 Fictional Identity | VDL-010 Shadow Poetics | VDL-011 Essential Studio | VDL-012 Patterned Prestige | VDL-013 Intimate Diary | VDL-014 Collaborative Presence | VDL-015 Sun-Sculpted Form | VDL-016 Confronting Presence | VDL-017 Classical Precision | VDL-018 Ritual Desire | VDL-019 Monumental Tonality | VDL-020 Chromatic Inversion | VDL-021 Epic Human Terrain | VDL-022 Iconic Defiance | VDL-023 Intimate Glamour | VDL-024 Primary Symbolism | VDL-025 Human Color | VDL-026 Ornate Sovereignty | VDL-027 Midnight Flash | VDL-028 Constructed Kinship | VDL-029 Haunted Collodion | VDL-030 Pastoral Freedom | VDL-031 Human Evidence | VDL-032 Beautiful Pride | VDL-033 Pop Revelation | VDL-034 Street Ceremony | VDL-035 Raw Elegance | VDL-036 Archive of Self | VDL-037 Geometric Instinct | VDL-038 Site of Memory | VDL-039 System Panorama | VDL-040 Dreamed Identity | VDL-041 Playful Provocation | VDL-042 Regal Pattern Sovereignty | VDL-043 Hyperreal Satire | VDL-044 Pop Icon Recode | VDL-045 Editorial Metamorphosis | VDL-046 Intimate Industry | VDL-047 Crafted Wonder | VDL-048 Cosmic Body | VDL-049 Shadow Abstraction

Each entry includes: human-only research layer (source mapping, NEVER passed to generator),
research synthesis, and AI-facing execution layer (branded name + visual rules for the prompt).

### Library 3: 50 Visual Artist Styles
Path: `71-blackceo-signature-page/references/BlackCEO-Visual-Artists-AI-Style-Intelligence-Guide-v1.0.md`

1. Legacy Street Portrait | 2. Coded Crown Expression | 3. Regal Pattern Portraiture | 4. Shadow Archive Tableau | 5. Monumental Black Presence | 6. Chromatic Grisaille Portrait | 7. Rhinestone Retro Sovereignty | 8. Fluid Metal Textile | 9. Transcultural Costume Theatre | 10. Cartographic Velocity Field | 11. Hybrid Mythic Collage | 12. Urban Relic Conceptualism | 13. Protective Spectacle Assemblage | 14. Labyrinthine Skin Narrative | 15. Psychedelic Sacred Pattern | 16. Fictional Presence Painting | 17. Excavated Urban Mapping | 18. Diasporic Interior Transfer | 19. Monumental Street Elegance | 20. Story-Quilt Chronicle | 21. Rhythmic Narrative Modernism | 22. Dignified Social Cinema | 23. Jazz-Cut Memory Collage | 24. Suspended Color Drift | 25. Intimate Symbolic Realism | 26. Fractured Viewpoint Construction | 27. Precision Dream Logic | 28. Serial Pop Transfer | 29. Atmospheric Light Mosaic | 30. Impasto Emotional Current | 31. Urban Paradox Stencil | 32. Infinite Repetition Field | 33. Kinetic All-Over Trace | 34. Magnified Organic Essentialism | 35. Quiet Visual Paradox | 36. Gilded Ornamental Figure | 37. Flat Pop Mythos | 38. Mirror-Finish Monumental Pop | 39. Luminous Multi-Perspective Modernism | 40. Baroque Heroic Chiaroscuro | 41. Tenebrist Immediate Drama | 42. Cut-Color Arabesque | 43. Cinematic Solitude Realism | 44. Panoramic Moral Fantasia | 45. Angular Nervous Figuration | 46. Distorted Existential Chamber | 47. Gestural Figure-Field Collision | 48. Luminous Emotional Field | 49. Psychological Domestic Monument | 50. Conceptual Craft Disruption

Each entry includes: research synthesis, visual DNA, AI preflight, generation instructions, avoid list,
and internal quality gate (target 8+).

### How to invoke a style in Element 4 (Style Block)

1. Select ONE style from the libraries above based on the asset's emotional role and section.
2. Read the complete style entry from the source document.
3. Translate the style's visual grammar into concrete prompt language: composition, camera, lens,
   lighting architecture, color system, texture, environment, character direction, emotional register.
4. Write the translated grammar into Element 4. Never write the source name.
5. Record the selected style ID (e.g., "CIS-07", "VDL-015", "Artist-03") in the asset's build record.

**Style fidelity gate:** After generation, score the image against the selected style's signature test.
If the score is below the style's passing threshold, run the correction loop: identify which visual
anchors failed, write a repair delta specifying what to change, and regenerate. Do not accept a
style-drifted image.

---

## BlackCEO Secret Super Sauce - Adaptive Aesthetic Engine

The target aesthetic is **Hyperchromatic Luxury Editorial Realism**. It combines luxury beauty/fashion
campaign photography, cinematic contrast, selective hyper-saturation, deep inky blacks, polished but
textural skin, controlled specular highlights, extreme subject/background separation, high microcontrast,
and sculptural composition. The result should feel bold, expensive, commanding, polished, saturated,
dimensional, glamorous, modern, tactile, cinematic, and visually magnetic.

**The most important principle: Contrast is the engine. Color is the weapon.**

Do not simply oversaturate the entire image. Highly saturated colors are placed against deep blacks,
clean whites, charcoal, gray, rich skin tones, dark hair, and restrained neutral areas. The contrast
architecture is what makes the color feel powerful.

**How it works with style selection:**
- When no external Creative Direction is selected: Secret Sauce is the primary aesthetic engine at full strength.
- When one Photographic, Cinematic, or Visual-Artist system is selected: Secret Sauce becomes an adaptive house layer. Preserve every compatible quality, translate what can be translated, suppress only dimensions that would damage the chosen style.
- Never flatten 149 distinct visual systems into one generic house filter.

**Blend profile:** The Asset Visual Bible records which Sauce dimensions are FULL (apply at full strength),
ADAPT (translate to fit the style), or SUPPRESS (would damage the style) for the selected Creative Direction.

**Mood rule:** The BlackCEO aesthetic does not mean every image must feel cheerful or equally saturated.
A painful, reflective, or tense scene may reduce chroma and brightness, use darker jewel tones, heavier
black architecture, and cooler light. Mood may reduce chroma; it does not authorize accidental mud,
lifelessness, or unart-directed desaturation.

**Conflict rule:** If a Sauce dimension conflicts with the selected style, the style controls that dimension.
All compatible Sauce qualities stay active. Never disable the whole quality system over one conflict.

---

### BlackCEO Secret Sauce: Detailed Midjourney-Calibrated Aesthetic Breakdown

This is the granular visual intelligence behind the Secret Sauce, calibrated from Midjourney V5.1-V6.1
era outputs and now treated as vendor-neutral BlackCEO art direction.

**Color intelligence:**
- Use ONE dominant hero color per image. Examples: ruby red, crimson, cobalt blue, saturated cyan, deep teal, emerald, violet, royal purple, saffron, marigold, burnt orange, saturated gold.
- The hero color should feel unusually pure, dense, and authoritative.
- Avoid weak language: "colorful," "bright," "vibrant." Use stronger language: "exceptionally rich high-chroma color," "dense pigment-like saturation," "pure jewel-tone color," "deep chromatic intensity," "color with visual authority."
- Add ONE supporting color. Strong combinations: crimson + black, ruby + gold, teal + white, cobalt + mustard, violet + orange, emerald + gold, magenta + deep blue.
- Formula: one dominant color + one supporting color + strong neutrals. Do not make every image rainbow-colored.
- Preserve neutral zones: black, charcoal, white, ivory, gray, warm brown, natural skin, dark wood, restrained metallics. The eye needs somewhere to rest. If every object is saturated, the image loses hierarchy.

**Blacks and shadows:**
- Deep blacks are essential: inky blacks, velvet blacks, rich shadow density, strong black-point contrast, dimensional dark tones, preserved shadow detail.
- Do NOT crush all shadow information. Black hair must show strands and shape. Dark clothing must show seams and fabric texture. Dark skin must remain dimensional and chromatically rich.
- Target: very deep blacks with preserved internal texture. NOT featureless black holes.

**Skin intelligence:**
- Target: luxury beauty-editorial realism. Not raw documentary photography.
- Preserve microtexture: pores, fine texture, subtle facial surface variation. Use: "Preserve fine skin microtexture while maintaining polished, flawless macro-level complexion."
- Avoid plastic skin: no wax, doll skin, porcelain smoothing, CGI plastic, blurred pores, over-airbrushing. Skin may be perfected but must feel tactile.
- Melanated skin must retain chromatic depth: warm brown depth, golden undertones, subtle red undertones, rich tonal transitions, reflective luminosity, full color density. Never gray, ashy, muddy, dull, or desaturated.

**Specular highlights and luminosity:**
- Faces are not flat matte. Use controlled highlights on cheekbones, bridge of nose, forehead, lips, eyelids, jewelry, glasses, metallic accessories.
- Target: controlled luminous specular highlights. NOT oily skin, sweaty skin, or blown-out white patches.
- Glossy lips and reflective accessories give dimensionality.

**Sharpness (selective precision):**
- Do not sharpen the entire frame equally. Focal areas may be extremely crisp: eyes, lashes, lips, facial contours, hair, jewelry, fabric. Background may soften.
- Use: "razor-defined focal subject with controlled depth falloff and creamy background separation."
- Avoid: uniform digital crispness, crunchy sharpening halos, hyper-detailed background competing with the face.

**Microcontrast:**
- Extremely important. Gives small details separation without ruining smooth tonal areas.
- Increase local definition in: hair strands, brows, eyelashes, lip texture, jewelry, fabric fibers, eyeglass frames, reflective objects, skin texture.
- Use: "high local contrast and microcontrast with smooth broad tonal transitions."

**Facial and beauty rendering:**
- Faces should feel photoreal, glamorous, sculptural, commanding, slightly idealized, immaculately styled.
- Target sits between high-end beauty photography + fashion advertising + subtle fashion illustration.
- Use: "Hyperreal luxury beauty photography with subtle fashion-illustration perfection."

**Makeup intelligence:**
- Clean and intentional: precise lashes, strong brows, dimensional eye makeup, rich lip color, reflective gloss, controlled highlights, clean edges, sophisticated color coordination.
- Makeup should reinforce the hero palette. Example: orange background leads to warm metallic eye accents; purple wardrobe leads to plum lip; red fashion leads to crimson lip.

**Materials and surface quality:**
- Materials must feel tactile: velvet dense, leather with controlled sheen, metal reflecting sharply, crystals sparkling, glass refracting, satin glowing, wool retaining fibers, lips dimensional.
- Use: "tactile material rendering with realistic reflective behavior and premium editorial polish."

**Composition:**
- Simple and intentional: strong center weighting, clear focal subject, clean silhouette, bold negative space, strong graphic shapes, simple background architecture, limited clutter, direct visual hierarchy.
- The image should read immediately at thumbnail size.

**Depth:**
- Create depth through: foreground/background scale, controlled blur, tonal falloff, edge lighting, reflected light, dimensional facial shadows, specular highlights, atmospheric separation.
- The subject should feel physically present, not flat.

**What this style is NOT:**
Not pastel, faded, low contrast, vintage-washed, soft beige influencer photography, muted editorial minimalism, gray and lifeless, oversaturated rainbow, fluorescent neon, generic HDR, plastic CGI, waxy skin, heavy haze, or flat natural-light photography.

**Negative style control (use when engine supports negative instructions):**
Avoid pastel grading, washed-out colors, muted fashion palettes, gray shadows, muddy browns, dull skin, ashy skin, desaturated melanated skin, flat lighting, low-contrast photography, excessive haze, uniform saturation across every object, uncontrolled neon, rainbow color overload, plastic CGI skin, wax skin, porcelain skin smoothing, excessive airbrushing, HDR halos, crunchy oversharpening, clipped highlights, crushed featureless blacks, muddy shadow detail, weak subject separation, flat composition, and generic stock-photo styling.

---

## BlackCEO Art Direction Router - One Style, One Asset Set

**The non-negotiable One-Style Rule:** For a single asset set (a landing page, a social campaign, an ad series, a presentation deck, a product launch, or any grouped deliverable), activate ONE and ONLY ONE
external Creative Direction:

1. **Photographic Direction** - one style from the Photographer DNA Library (VDL); or
2. **Cinematic/Directorial Direction** - one style from the Cinematic Systems Library (CIS); or
3. **Visual-Artist Direction** - one style from the Visual Artists Guide; or
4. **No external direction** - Secret Super Sauce only.

Do NOT combine families. Do NOT stack two styles from the same library. The Secret Sauce is not
counted as a second style; it is the house quality layer.

**Selection order:**
1. Lock the asset facts (purpose, audience, offer or message, brand, required people/objects, identity references, typography needs, intended action, delivery surfaces).
2. Honor an explicit style choice from the client.
3. Honor an explicit family choice (photographic/cinematic/visual-artist).
4. If delegated, choose the family by the asset set's strongest organizing idea.
5. Choose one branded style by story fit, brand fit, audience fit, emotional-arc fit.
6. Lock the style for the asset set. Do not switch by asset simply because another style seems convenient.
7. Compile the Asset Visual Bible before authoring any prompt.

**Never use a second style to fill a missing dimension.** If a visual-artist system does not define
a photographic lens, use neutral BlackCEO framing logic. Do not import another style.

**Asset Visual Bible contents:** The selected style's non-negotiable visual anchors, the Secret Sauce
blend profile (FULL/ADAPT/SUPPRESS per dimension), continuity rules, allowed variation, and anti-drift rules.

---

## BlackCEO Fashion and Wardrobe Intelligence

Select one primary fashion language per asset set, then vary silhouettes and details within it.

**Fashion languages:** Minimalist, Techwear, Urban, Haute Couture, High Fashion, Hip-Hop Luxury,
Streetwear, Afrofuturism, Business Power, Creative Professional, Athleisure Luxe, Steampunk (only
when the concept genuinely calls for it).

Describe **silhouette, fabric, tailoring, color, texture, accessories, footwear, and status cues**
rather than relying on a brand name. Designer references may be used as shorthand but the prompt must
still explain the visible design language. Do not reproduce protected logos unless supplied and authorized.

Weave the brand's primary color into every prompt's palette plan. It may become dominant wardrobe,
background plane, architectural accent, accessory, practical light, typography, or a tiny counterpoint.
Brand continuity must not destroy the selected Creative Direction.

---

## BlackCEO Image Purpose Intelligence - Write for the Actual Job

Do not generate a generic image and hope it fits. Every image has a specific job based on its purpose,
regardless of whether it appears on a landing page, in a social post, in an ad, in a presentation, or
anywhere else.

| Image purpose | Image job | Direction |
|---|---|---|
| Opening/Hook | Make the opening possibility or core message visually arresting | One confident editorial focal point. Scale through framing, wardrobe, environment, color. Preserve negative space for copy or headline. |
| Pain/Problem | Make the specific problem recognizable at the moment it is felt. Preserve dignity. | Meaningful gesture, context, facial micro-expression. Close or medium scene. Do not equate pain with tears or collapse. Color can stay intense while light/framing convey pressure. |
| Solution/Response | Show the specific response to the problem. Relief must have a visible cause. | Change the person's relationship to the problem. One clear scene, not a before/after collage. Keep same-person continuity explicit if intended. |
| Benefit/Outcome | Show the human benefit as lived experience, not a trophy. | Satisfaction tied to the specific benefit: grounded confidence, relaxed joy, presence, human connection. Spacious composition. |
| Hero/Authority | Establish commanding presence. | Direct gaze, stable stance, deliberate head angle, controlled confidence. Monumental but human. |
| Product/Object | Make the object desirable through context, light, and material rendering. | Tactile surfaces, controlled reflections, meaningful environment. No floating product on white unless the brief demands it. |
| Social/Shareable | Stop the scroll with immediate visual impact. | Bold composition, high contrast, readable at thumbnail size. One clear focal point. |
| Testimonial/Social proof | Convey authenticity and trust. | Natural expression, real environment, unposed feel. Not a stock smile. |

**QC question for every image:** Does this scene serve its specific purpose, or is it a generic image
that could go anywhere?

---

## BlackCEO Pixel QC - Inspect the Generated Pixels, Not Just the Prompt

Prompt QC is not enough. After generation, inspect the actual pixels against these checks:

1. **Skin check:** Is melanated skin chromatically rich (warm brown, golden, red undertones) or has it drifted gray/ashy/muddy? Are pores and microtexture visible?
2. **Hair check:** Does the hair match the specified style with individual strand structure? Are braids fused into clothing? Are coils a smooth helmet?
3. **Style fidelity:** Does the image match the selected style's signature test? Score against the style's fidelity gate.
4. **Anatomy check:** Count fingers, check hand/arm attachment, verify facial symmetry is natural not cloned.
5. **Text check:** If text-bearing, verify every character against the spelling lock. No garbled, doubled, or substituted characters.
6. **Brand check:** Is the brand color present per the palette plan? Is the grade consistent with the Asset Visual Bible?
7. **Composition check:** Is the subject positioned per the 3x3 plan? Is text-safe area clear? Are critical features away from crop edges?

If any check fails, write a repair delta specifying exactly what to change and regenerate. Do not accept
a failed image.

---

## BlackCEO Typography-as-Image, Visual Rhythm and Anti-Template Intelligence

An asset set does not need a photographed person in every image. The image system builds an emotional
visual journey, not an "image, image, image" checklist.

**Treatment mix for a full asset set:**
- Human-centered imagery for emotionally important moments
- Environmental/object/conceptual imagery where setting or idea carries the story better
- One or two typography-as-image treatments when the message supports them
- Zero-image/typography-only sections when copy or layout is stronger without a generated asset

Never add a person just to satisfy a percentage. The wireframe decides which sections need assets.

**Typography-as-image definition:** The words themselves are the visual art. No photographed human
required. Use a solid field, gradient, abstract texture, atmospheric blur, dimensional geometry, or
other non-representational background.

Possible treatments: massive-scale type pushing against the frame, dimensional/extruded letters,
staggered or curved arrangement, mixed weights or serif/sans/script counterpoint, texture-filled
letters, knockout/reveal lettering, restrained shadow or embossed effects.

Use text effects to enhance readability, not to show off. If the effect is noticed before the words,
reduce it.

**Contrast commandments:** For every text-bearing image, explicitly state BOTH the text color AND the
exact background color behind it. Never leave contrast implicit. Use dark text over light surfaces or
light text over dark surfaces. On complex imagery, create a readable zone: semi-transparent color block,
subtle drop shadow, thin contrast stroke, localized blur/darken zone, or gradient fade. Never place
generated text over a face. Maintain 5-10% safe margins from frame edges. Every verbatim string uses
a spelling lock and is QC'd pixel-for-pixel.

**Two-font power dynamic:** Primary type personality for the main message, secondary accent only when
it improves hierarchy. Primary examples: heavy geometric sans for commanding scale; sophisticated
contrast serif for premium authority. Secondary: elegant script for warmth; condensed all-caps for edge.
Keep the secondary subordinate.

**Visual-rhythm rule:** Before authoring prompts, build a private visual-rhythm map with one row per
section: treatment type, aspect ratio, dominant color, shot distance, angle, subject zone, lighting mood,
emotional target. Use it to prevent monotony. Mix 21:9 cinematic breaks, 16:9/3:2/4:3 frames, portrait
3:4/2:3/9:16, detail crops, full-bleed fields, and typography-led blocks. Do not use the same 16:9
card everywhere.

**Distinctness requirement:** Every neighboring asset must differ in several dimensions: composition,
angle, shot distance, lighting mood, posture, expression, palette emphasis, treatment type. "Same layout,
different person" does not count. Harmony comes from brand, emotional arc, and color-grade family.
Distinctness comes from art direction.

---

## BlackCEO Set-Diversity Register Template

For each illustrative human asset, track the following. Use it to stop accidental cloning across a set.

| Field | Asset 1 | Asset 2 | Asset 3 | Asset 4 |
|---|---|---|---|---|
| Age band | | | | |
| Face shape | | | | |
| Skin-tone label | | | | |
| Undertone | | | | |
| Hairstyle | | | | |
| Facial hair | | | | |
| Body type | | | | |
| Wardrobe | | | | |
| Pose | | | | |
| Expression | | | | |
| Camera angle | | | | |
| Shot distance | | | | |
| Dominant color | | | | |

**Rules:**
- Across a multi-image set, do not repeat the same skin-tone + hairstyle + facial-hair combination unless deliberate recurring-character continuity is recorded.
- **Continuity exception:** When the asset set intentionally follows the same protagonist across pain to solution to outcome, preserve their identity, skin, hair, and core wardrobe. Distinctness then comes from posture, light, environment, camera, styling evolution, and emotion.
- Never randomize a real person's complexion, hair, or facial hair away from their supplied reference.

---

## Additional Teaching Examples

### EX-01: Pain Made Visible Without Degrading the Reader

**Section:** The Big Bold Pain 1. **Purpose:** Illustrate the cost of always making room for everybody else.

**Key direction:** A Black woman, approximately 44-49, with deep brown skin and neutral-red undertones,
short tapered natural cut with tight coils. She has just closed her personal sketchbook to make space
for household paperwork. Her expression is restrained frustration: inner brows drawn together slightly,
lips at rest, small pause in shoulders, gaze toward the closed book. No crying, no disheveled stereotype,
no suggestion of failure. She is thoughtful, tired of a pattern, still self-possessed.

**What makes it BlackCEO:** Specific skin tone with undertone. Named hairstyle with construction detail
("tight coils with more height at the crown, softly tapered sides, realistic hairline, not a smooth
helmet"). Expression built from visible physical cues, not "she looks sad." Dignity preserved in a pain
section. 50mm lens, eye-level, f/3.2 depth. Plum blouse with material specificity.

**Negative block excerpt:** "Do not lighten, grey, blur, or uniformly recolor the woman's skin; retain
her deep brown neutral-red undertone and natural texture. Do not turn quiet frustration into a smile,
tears, helplessness, or humiliation."

### EX-05: Typography-as-Image

**Purpose:** A typography-led asset as deliberate interruption in a long-form asset set (landing page, sales page, presentation deck). No human subject.

**Key direction:** The statement "YOUR NEXT LEVEL SHOULD NOT LOOK LIKE EVERYBODY ELSE'S" rendered as
designed typography on a 21:9 canvas. Two-font power dynamic: ultra-bold geometric sans for primary,
sophisticated serif accent. Electric cobalt dominant background, deep obsidian shadow, warm ivory text,
hot coral accent in one geometric interruption. Asymmetrical 3x3 grid, eye enters at "YOUR NEXT LEVEL,"
lands hard on "EVERYBODY ELSE'S."

**What makes it BlackCEO:** Hyper-saturated cobalt and coral with rich dark separation (Secret Sauce).
Deliberate art direction, not a centered template. Every text/background color pair explicitly stated.
Spelling lock on the verbatim string. Physical depth through believable light behavior on letterforms.

**Negative block excerpt:** "Do not create a generic centered SaaS hero. Do not use bland beige, dusty
pastel minimalism, default purple-blue gradient blobs. Do not misspell, garble, duplicate, omit, reorder,
or substitute any letter."

---

## Worked Example: Generic vs. BlackCEO Prompt (Element 7)

**GENERIC (AUTO-FAIL):**
> A professional Black woman smiling at the camera in an office.

**BLACKCEO (PASS):**
> Subject A is approximately 42, a business coach, with chestnut brown skin and warm-golden
> undertones, an oval face, and a curvy build. Her hair is waist-length knotless braids in
> deep espresso brown, gathered over one shoulder with clean parting and individual braid
> definition visible. She wears a tailored terracotta blazer over a cream silk blouse.
> Her expression is grounded confidence: direct gaze, relaxed jaw, shoulders open, one hand
> resting on a closed notebook. Rich melanated skin tones with full chromatic depth, warm
> brown, golden, and subtle red undertones; never gray, ashy, muddy, dull, or desaturated.
> Preserve fine skin microtexture. Sculptural beauty lighting from camera left with subtle
> rim light separating her braids from the warm neutral background.

---

## Mandatory gate (run before every `createTask`)

```
python3 45-design-intelligence-library/scripts/diu_validator.py prompt-band \
    --band <band-id> --prompt-file <assembled.txt> \
    [--copy "<verbatim string>" ...] [--style-ref] [--run-dir <job-dir>]
```

Exit codes: **0** pass; **3** = AF-GIP-PROMPT-FLOOR (under the band MIN) or AF-DIU-PROMPT-CAP (over the
band MAX) — the prompt is NOT submitted and NOT rendered; re-author (never truncate up to the floor);
**6** = AF-GIP-PROMPT-QUALITY (length cleared but a quality tooth failed). A standalone CI prover
(`scripts/prove_gip_prompt_floor.py --self-test`) exercises the same functions on fixtures so the
floor can never become a length-only rubber stamp.

Run `kie_live_adapter.py prompt-budget --model <id> --check --prompt-file <assembled.txt>` as well (exit 3 below the floor, exit 4 above the max); when its verdict and the band validator's differ, the stricter one blocks the submit.

**Handoff:** on a floor/cap/quality failure, return the itemized problem list to the prompt author
(the Generation Operator does not improvise fixes). On pass, proceed to SOP-DIU-601 preflight steps
3–10, then submit.

**Authoring + independent grading (GK-21, decision GK-D2 — Option A phased):** production prompts are
assembled by the dedicated Prompt Author (`prompt-author-graphics.md`), never self-authored by the 15
producing roles, and independently graded by the Prompt QC Specialist (`qc-specialist-prompt-graphics.md`,
judge != writer) BEFORE the Generation Operator's own preflight re-runs this same gate as a mechanical
backstop — dispatched per `chief-design-officer.md` SOP 9.9. The gate above is unchanged; only WHO runs
it first and WHO authors the prompt text has moved off the 15 self-authoring roles onto this dedicated pair.

---

## BlackCEO Fill-in-the-Blank Prompt Template

Copy this template for every image. Fill every [BRACKET]. Delete nothing. If a field does not apply
(e.g., no person in a typography image), write "N/A - [reason]" so the omission is deliberate, not drift.

```
ASSET: [asset class: e.g., editorial portrait, product still life, typography-as-image, social post] | BAND: [band-id]

1. IMAGE PURPOSE: [select one: Opening/Hook, Pain/Problem, Solution/Response, Benefit/Outcome, Hero/Authority, Product/Object, Social/Shareable, Testimonial]
   Job: [one sentence: what must this image accomplish?]

2. SUBJECT + SCENE:
   [Who/what is in the frame? What are they doing? Where are they? Write 3-5 sentences. No stock language.]

3. STYLE DIRECTION:
   Selected style: [one only: CIS-## name, VDL-### name, Artist-## name, or SECRET_SAUCE_ONLY]
   Style anchors: [list the 3-5 non-negotiable visual anchors from the selected style's entry]
   Secret Sauce blend: [for each dimension: FULL, ADAPT, or SUPPRESS, with one-line reason]
   Hero color: [one dominant color, e.g., "cobalt blue"]
   Supporting color: [one supporting color, e.g., "warm gold"]
   Neutral zones: [list: e.g., "deep black background, ivory wall, natural skin"]

4. CAMERA:
   Shot distance: [select: extreme close-up, close-up, medium close-up, medium shot, three-quarter portrait, full-length, wide/environmental]
   Camera angle: [select: eye-level, slight low angle, low-angle power, slight high angle, high-angle context, dutch angle, side profile, three-quarter profile, over-the-shoulder, back view]
   3x3 position: [e.g., "subject in middle-right, eyes near upper-right intersection, left third clear for copy"]
   Lens look: [select: 35mm environmental, 50mm natural, 70-85mm portrait compression, 105-135mm editorial]
   Aperture intent: [select: f/1.2-f/1.8 very shallow, f/2-f/2.8 shallow, f/4 balanced, f/5.6-f/8 deep]
   [If non-photographic style: replace with viewing scale, viewpoint, perspective, figure-ground logic]

5. LIGHTING:
   Key light: [direction + quality, e.g., "large softbox camera left, 45 degrees above eye line"]
   Fill: [e.g., "neutral bounce from tabletop, opens shadow side without flattening"]
   Rim/separation: [e.g., "subtle rim on hair from rear practical, separates from dark background"]
   Shadow quality: [e.g., "deep but open, preserve detail in darkest areas"]
   Skin priority: [e.g., "deep brown skin stays dimensional, warm highlights on cheekbones, no crushed shadows on face"]

6. PEOPLE / REPRESENTATION:
   [Repeat per person. For non-Black subjects, use equally specific language appropriate to the person.]
   Person [A/B/C]: [role], [skin tone from 25-entry library], [hairstyle from 40/14-entry library with construction detail], [facial hair if applicable], [attire with silhouette/fabric/color], [expression as physical cues: gaze, brows, mouth, shoulders, hands, posture]
   Skin rendering: Rich melanated skin tones with full chromatic depth, warm brown, golden, and subtle red undertones; never gray, ashy, muddy, dull, or desaturated. Preserve fine skin microtexture.
   Hair rendering: [strand structure, shape, density, hairline - never crushed, fused, or generic]
   Set diversity check: [confirm no repeated skin+hair combo unless intentional continuity]

7. COLOR GRADE:
   Correction: [e.g., "neutral white balance first, ivory surfaces clean, skin true to undertone"]
   Grade: [e.g., "selective hyperchroma on cobalt wardrobe and emerald background, protect skin/whites"]
   Saturation language: [use strong terms: "dense pigment-like saturation," "deep chromatic intensity" - never "vibrant" or "colorful"]
   Microcontrast: [e.g., "high local contrast on hair strands, lashes, fabric; smooth broad tonal transitions"]
   Specular highlights: [e.g., "controlled luminous highlights on cheekbones, lips, jewelry - not oily"]

8. TYPOGRAPHY (if text-bearing):
   Verbatim string: "[exact text]"
   Spelling lock: Render this exact string, letter-for-letter, correctly spelled, with no added, dropped, doubled, or substituted characters: '[STRING]'.
   Text color: [exact color]
   Background color: [exact color behind text]
   Font character: [e.g., "ultra-bold geometric sans, architectural, commanding"]
   [If no text: "No text, no letters, no words anywhere in the image."]

9. TECHNICAL:
   Endpoint: [model/endpoint ID]
   Aspect ratio: [e.g., 16:9, 1:1, 4:5, 21:9]
   Output format: [png for text-bearing, jpg otherwise]
   [Other engine-specific params]

10. NEGATIVE BLOCK:
    Do not [cover all applicable from the 13 classes]:
    [Base 8: garbled text, logo mutation, anatomy errors, contrast/legibility failure, placeholder tokens, demographic default, watermark, style drift]
    [BlackCEO 5: gray/ashy/muddy skin, crushed featureless hair, plastic/wax skin, substituted hairstyle, lightened/darkened skin for effect]
    [Style-specific negatives from the selected style's "Avoid" list]
```

**How to use this template:**
1. Fill every bracket before writing prose. The brackets force you to make each decision explicitly.
2. If you cannot fill a bracket, you are not ready to write the prompt. Go back to the Asset Visual Bible.
3. After filling, expand each section into flowing prompt prose using the specific language in your bracket answers.
4. The template IS the QC checklist. If a bracket is empty or vague, the prompt fails before generation.

**MANDATORY POST-GENERATION VERIFICATION - IMAGES THAT FAIL MUST BE REDONE:**

After generation, the image MUST be inspected against every requirement below. If ANY check fails,
the image is rejected and must be regenerated with a corrected prompt. There is no "close enough."
There is no "the client won't notice." A failed image is a failed image.

1. **Style verification:** Was ONE specific style selected from the three libraries (CIS-##, VDL-###, or Artist-##)? Was the style's actual entry loaded from the source document (not just the name)? Are the style's non-negotiable anchors visible in the image? Is the style's "Avoid" list respected?
2. **Character count:** Does the prompt satisfy rule 12 for the selected model (target 95 to 100 percent of the model's maxLength, never below the 80 percent floor), as reported by `kie_live_adapter.py prompt-budget --model <id> --check` and enforced by `shared-utils/kie_prompt_enforcer.py`? Count before submitting. This SOP states no fixed character minimum; rule 12 is the single length source.
3. **Prompt order:** For Black subjects, was the mandatory order followed (role → skin tone → hairstyle → facial hair → attire → expression/posture)? No deviations, no reordering.
4. **Skin check:** Is melanated skin chromatically rich with warm/golden/red undertones? Is microtexture visible? Not gray, ashy, muddy, or plastic.
5. **Hair check:** Does the hair match the named library style with individual strand structure? Not crushed, fused, or substituted.
6. **Color grade check:** Is selective hyperchroma visible? Are hero and supporting colors authoritative? Are neutrals preserved? Is the Midjourney-calibrated aesthetic (contrast architecture, microcontrast, specular highlights) present?
7. **Negative block check:** Were all 13 defect classes addressed? Were style-specific negatives included?
8. **Template completeness:** Was every bracket filled with a specific choice (not "good lighting" or "professional attire")?

**If any check fails: REJECT THE IMAGE. Fix the prompt. Regenerate. Do not deliver a failed image.**
