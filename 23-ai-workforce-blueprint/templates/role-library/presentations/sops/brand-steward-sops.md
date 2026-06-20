# SOPs Mirror -- Brand Steward

**Source:** presentations/brand-steward.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Shared STYLE BLOCK Authorship

**When to run:** At the start of every new deck run, dispatched by the Director concurrent with Phase 1 (copy writing). Must complete before Phase 2 begins.

**Inputs:**
- intake.json (brand_colors, brand_fonts, logo_description, representation_preferences, style_references)
- **(Decision 1C) `working/copy/assets_manifest.json`** when present — client-provided logo / brand-color / photo assets to CONSUME.

**Steps:**
0. **(Decision 1C) Consume client-provided brand assets FIRST.** If `working/copy/assets_manifest.json` exists with `assets_provided:true`, read it before authoring the STYLE BLOCK: for every asset whose `consumed_by` includes `brand-steward` (logo / brand_color / founder-proof photo), use the asset's `public_url` as the authoritative source — the locked `LOGO_URL` IS the provided logo's `public_url` (composited image-to-image, never redrawn); the brand palette is derived from the provided brand-color swatches; provided photos are carried to the Slide Image Creator as gpt-image-2 `input_urls`. Provided client material ALWAYS wins over an invented/default look. The gate **AF-MANIFEST-UNREFERENCED** fails the deck if a provided brand asset is recorded but not actually consumed.
1. Extract brand colors from intake.json. If the client provided hex codes, use them verbatim. If the client described colors without hex codes (e.g., "gold and navy"), find the closest brand-standard hex codes and record them as `color_source: "derived_from_description"` in the STYLE BLOCK. If no color information exists, use a professional neutral default (#1A2B4C navy, #C4A44D gold, #FFFFFF white) and flag as `color_source: "default_pending_client_confirmation"`.
2. Assign roles to the 3 hex codes. Exactly 3 hex codes are required:
   - PRIMARY: accent-1 -- used for money/value displays, dividers, and key visual highlights (gold or brand equivalent)
   - SECONDARY: accent-2 -- used for action/urgency/emphasis words and CTA elements
   - ACCENT: the third client color
   - WHITE BASE: #FFFFFF (or a faint warm off-white per style references such as #FBF7F4) is ALWAYS the base layer beneath all three. It is not one of the three named hex slots. Do NOT label any client hex as "tertiary almost always white." The base layer is white and is listed separately in the STYLE BLOCK.
3. Extract typography from intake.json. If no fonts are specified, default to: headline font = "Montserrat Bold" (or similar geometric sans-serif), body font = "Open Sans Regular". Record as `font_source: "default_pending_client_confirmation"`.
4. Extract logo placement. Default rule: "Logo on a white chip at approximately 9% of slide width with a subtle 1px brand-accent border, placed in the same corner (bottom-right) on every slide, minimum 40px from any edge, full color version, never recolored or distorted." If client has provided a logo file, note the file path.
   **(Density-floor overhaul) Lock ONE canonical logo asset.** Record a single `LOGO_URL` (a public https URL; re-host to the client GHL media library or Drive if needed). If the client supplied MULTIPLE lockups/monograms/icon/mountain/sprout/tagline variants, pick exactly ONE canonical mark and FORBID the rest in the STYLE BLOCK (`forbidden_logo_variants: [...]`). The logo is ALWAYS composited image-to-image from this locked LOGO_URL (never text-to-image), so the SAME mark renders on every slide. A drifting logo (a different mark per slide) was the reference failure case Dimension F defect (AF-I11). Source: universal-sops/presentation-design-system/05-SOP-logo-consistency.md and presentation-image-library/SOP-IMG-01 Mode B.
   **(Density-floor overhaul) Pin the price-typography + weight-ladder system in the STYLE BLOCK** so the Typography Architect and Slide Image Creator share one source: the metallic-gold gradient on hero price numerals, the accent glow on the LIVE price, the drawn-gold double-strike on DEAD prices (applied across the WHOLE ladder, not one beat), and the Montserrat (or client) weight ladder (BLACK headlines, ExtraBold sub-heads, Bold labels, Medium/Italic captions). The Typography Architect owns the per-slide treatment; you pin the system tokens.
   **(Density-floor overhaul) Style-source trigger (SOP-IMG-02 / SOP-IMG-03):** read `STYLE_SOURCE` from intake. If `match_reference` (a reference deck / `ANALYZE_REQUEST` / `STYLE_ID`), fire Crossing A via SOP-DIU-612 (write style_request.json to the Chief Design Officer), fold the returned Foundation Prompt Block into the STYLE BLOCK, and record `style_card_id@version` in brand_registry.json BEFORE delivering the STYLE BLOCK. If `saved_style`, run the SOP-IMG-04 recall path (resolve the alias in NAMED-STYLES.md to a production card, pin the version). If `creative_develop` or no style fields, build the STYLE BLOCK from intake brand fields plus the SOP-IMG-03 creative-develop probe. Never invent a look on a deck that requested a style match.
5. Extract representation preferences from intake.json field `REPRESENTATION_MIX`. This field is collected WITH PERCENTAGES during discovery (e.g., "70% African American women, 20% African American men, 10% mixed" or "100% women, diverse" or "no people at all"). The percentage breakdown drives the deck-level ratio in SOP 9.2.
   - If `REPRESENTATION_MIX` is present and answered: use the client's stated breakdown verbatim. Record as `representation_source: "client_intake"`.
   - If `REPRESENTATION_MIX` is unanswered or blank: DO NOT invent a racial default. Set representation to NO PEOPLE (people element omitted from all slides) and flag: `representation_source: "default_no_people -- intake unanswered"`. Immediately notify the operator with a flag: "REPRESENTATION UNANSWERED: intake.json has no REPRESENTATION_MIX value. Deck will default to no people in images. Please confirm or supply the intended breakdown before Phase 2." Do not proceed to people-inclusive prompts until the operator or client has answered.

5a. DERIVE THE COLOR RELATIONSHIPS AND GRADING PROFILE (required -- must complete before step 6):
   a. Identify the COLOR RELATIONSHIP from the brand palette: map the three client hex codes to the color wheel. Determine whether the relationship is COMPLEMENTARY (primaries on opposite sides of the wheel -- maximum contrast and pop), ANALOGOUS (adjacent hues -- warm harmony and cohesion), or TRIADIC (three equidistant hues -- vibrant balance).
   b. Identify the COMPLEMENTARY ACCENT: which color creates the strongest contrast pop against the others? This is the accent reserved for CTAs, price reveals, and the single most important number per slide. Do not spread it indiscriminately.
   c. Run the CONTRAST CHECK on the headline color against the white base: the charcoal headline (#231F20 default) on the white base (#FBF7F4 default) must pass WCAG AA (minimum 4.5:1 for normal text, 3:1 for large text at 18pt+ regular or 14pt+ bold). Record the ratio. If the client brand requires a lighter headline on white that fails WCAG AA, flag to the Director and suggest a darker shade.
   d. Derive the COLOR GRADING PROFILE: look at the warmth of the brand palette overall. A gold-primary, charcoal-secondary, off-white-base palette is WARM. A navy-primary, silver-secondary, cool-white-base palette is COOL. A balanced multi-hue palette with no dominant temperature lean is NEUTRAL. Record WARM, COOL, or NEUTRAL.
   e. Record these findings as the COLOR THEORY section and COLOR GRADING PROFILE in the STYLE BLOCK (step 6 template below).

6. Build the STYLE BLOCK text. Format (800-1,500 characters):
   ```
   STYLE BLOCK -- [client_slug] -- [deck_slug]
   Generated: [ISO_DATE]

   COLORS:
   White base: #FFFFFF (or [warm off-white hex if style refs specify]) -- slide background, dominant layer (80%+ of visual area)
   Primary (accent-1): [HEX1] -- money/value displays, dividers, kicker rules, price tag borders
   Secondary (accent-2): [HEX2] -- action/urgency/emphasis words, CTA elements, section banner fills
   Accent: [HEX3] -- [role description from intake]
   Headline color: charcoal [HEX or default #231F20], NEVER pure black (#000000). The warm charcoal is softer and more premium.
   Giant-number treatment: a two-stop gold gradient (dark stop -> light stop; default #B8860B -> #E6C66E, "liquid gold"), OR the Secondary accent with a subtle glow for the "winner" price.
   White base rule: ALL slides use the white base as the background. Brand colors are ACCENTS only (max 20% of visual area each). ZERO black backgrounds anywhere in the frame -- not in corners, not behind text, not as a vignette. Dark backgrounds are PROHIBITED unless DARK_OK=true.

   HIERARCHY STACK (the canonical top-to-bottom vertical rhythm on every text-bearing slide):
   gold caps kicker label -> thin gold breathing rule -> massive charcoal Black 2-line headline (dominates, first thing the eye reads) -> raspberry/Secondary ExtraBold sub-headline -> second thin gold rule (paired-rule framing around the core message) -> charcoal body beat -> italic tertiary breathing line -> logo chip bottom-right.

   TYPOGRAPHY LAW (one typeface, hierarchy by WEIGHT; carry into every prompt -- SOP 9.4):
   Typeface: [Font family -- default Montserrat]. ONE family only; hierarchy is created by weight, never by mixing typefaces.
   Weight map by role:
   - Headlines + giant numbers: [family] Black (the hero weight)
   - Sub-headlines + body beats + before/after stats: [family] ExtraBold
   - Gold all-caps letter-spaced kicker labels, pills, badges: [family] Bold
   - Section labels + subheads on photo slides: [family] SemiBold
   - Tertiary / breathing lines: [family] Medium, often italic
   - Footnotes / fine print / disclaimers: [family] Regular, ~11-13pt, often italic
   Size scale (relative to slide height): giant numbers 110-150pt (Black); hero 2-line headline 62-86pt (Black); secondary headline 42-62pt; raspberry sub-headline 24-32pt (ExtraBold); body beat 17-22pt; tertiary italic 16-19pt; gold kicker label ~13pt (Bold); footnote 11-13pt.
   Type is always legible on the white base. No reversed-out text on dark backgrounds (unless DARK_OK).
   BASIC OR DEFAULT FONTS ARE FORBIDDEN: Calibri, Arial, Times, or any system/platform default is an AUTO-FAIL at QC. Every prompt must name the exact weight and a large pt size per line.

   LOGO:
   [Logo placement rule: white chip at ~9% slide width, subtle 1px brand-accent border, consistent corner, full color version]

   BRAND GRAMMAR (embed in every prompt):
   - Kicker label: small all-caps letter-spaced label in Primary above the headline, with a short Primary gold rule beneath it
   - Divider: 3px full-width Primary rule between photo band and type zone on all split-layout slides
   - Color roles: Primary = money/value and dividers; Secondary = action/urgency/emphasis; charcoal = headlines (never pure black backgrounds)
   - Price tag motif: large white hang-tag shape with Primary border; old prices struck through with DRAWN Primary diagonal lines; new price in Secondary at the bottom of the tag
   - Section progress banners: "SECTION 3 OF 7" or "SECRET #1" rendered in a filled Secondary banner box on section-opener slides
   - Compliance line: small italic disclaimer in the lower margin on every slide containing a results or income claim
   - Subtle brand cue (in-world, optional per slide): one hidden, believable in-scene reminder of the brand's core value (the brand's tagline on a mug, a wall, a notebook in the corner), never competing with the headline (see the Subtle Brand Cue doctrine below SOP 9.1)

   REPRESENTATION RATIO (deck-level target):
   [If client answered: list each group and percentage verbatim from intake]
   [If unanswered: "NO PEOPLE -- operator flag issued, awaiting confirmation"]
   Age range: [range from intake or NONE if no people default]

   COLOR THEORY (derived from brand palette in step 5a -- governs how colors relate, not which colors are used):
   color_relationship: [COMPLEMENTARY / ANALOGOUS / TRIADIC]
   complementary_accent: [HEX and role -- the accent reserved for maximum-contrast moments: CTAs, price reveals, the single most important number per slide]
   contrast_check: [e.g., "Charcoal #231F20 on white #FBF7F4: ratio 16.5:1, WCAG AA PASS" OR "flag: ratio X:1, below 4.5:1 threshold for normal text"]
   contrast_rule: complementary accent is used ONCE per slide maximum for maximum-impact moments; spreading it across the deck dilutes its power.

   COLOR GRADING PROFILE (consistency across the deck -- every image must feel shot in the same light):
   color_grade_profile: [WARM / COOL / NEUTRAL]
   temperature: [description, e.g., "warm golden-hour light temperature, slightly lifted shadows, warm midtones"]
   saturation: [description, e.g., "slightly elevated saturation on primary subjects, desaturated backgrounds for separation"]
   tonal_contrast: [HIGH / LOW -- high = strong shadow/highlight separation; low = softer, more even tonal range]
   lock: "Every prompt in this deck states TEMPERATURE=[value], SATURATION=[value], TONAL CONTRAST=[value] in a COLOR GRADING comment block. A deck where some images are warm-toned and others are cool-toned is an AUTO-FAIL at QC."

   ARCHETYPES: A1-A5 per master SOP Section 7.2 (delivered separately via SOP 9.3)

   16:9 ALWAYS. 2K resolution (2560x1440). Never 4:3 or square.
   ```
7. Write the completed STYLE BLOCK to working/brand/style_block.md.
8. Register the STYLE BLOCK in working/brand/brand_registry.json: `{ "client_slug": "...", "deck_slug": "...", "style_block_path": "working/brand/style_block.md", "generated_at": "...", "color_source": "...", "font_source": "...", "representation_source": "...", "color_relationship": "COMPLEMENTARY/ANALOGOUS/TRIADIC", "color_grade_profile": "WARM/COOL/NEUTRAL" }`.
9. Notify the Director and the Slide Image Creator that the STYLE BLOCK is ready.

**Outputs:**
- working/brand/style_block.md (complete STYLE BLOCK, 800-1,500 characters)
- working/brand/brand_registry.json (entry added)

**Hand to:** Slide Image Creator (for use in all 15-element prompts); also triggers SOP 9.3 delivery

**Failure mode:** If intake.json has no brand information at all (no colors, no fonts, no logo), write the STYLE BLOCK with all default values and flag: "STYLE BLOCK uses all defaults -- please confirm brand colors, fonts, and logo before final image generation. Images generated with defaults will need re-generation if brand is different." Notify the Director. If representation is unanswered, follow the no-people default rule in Step 5 above.

**SUBTLE BRAND CUE (the in-world hidden cue doctrine; pairs with PRODUCT INTELLIGENCE, SOP-ENGINE-00 Engine 9).** Beyond the formal brand grammar (the logo chip, kicker, divider, palette, price-tag motif), the deck may plant ONE hidden, in-scene reminder of the brand's core VALUE on designated slides: the brand's tagline or core phrase appearing in-world (on a mug, a wall, a notebook, a poster in the corner) -- the way a sponsor's product or message sits naturally inside a TV-show scene, noticed without being announced. Rules: it is BELIEVABLE in the world (it must still pass World Intelligence, slide-image-creator-sops.md SOP 9.3), it NEVER competes with the headline, and it is distinct from the formal logo chip (which is the explicit brand chrome). The cue carries the brand's VALUE; the logo carries the brand's MARK. This pairs with Product Intelligence (the real product in-scene): both are subtle in-world placements composited believably, never floating overlays. The cue text, like all brand assets, comes from the client (their real tagline / core value), never invented.

---

### SOP 9.2 -- Cross-Slide Consistency and Representation-Ratio Audit

**When to run:** After Phase 2 (prompts) is complete -- before Phase 3 QC gate. The audit catches systematic representation imbalances before images are generated. If the STYLE BLOCK was built with the no-people default (representation unanswered), this audit is inconclusive by design -- log it and notify the Director.

**Inputs:**
- working/prompts/slide-NN-prompt.txt (all prompt files)
- working/brand/style_block.md (representation ratio target)
- arc_allocation.json (total slide count, section breakdown)

**Steps:**
1. Scan all prompt files. For each prompt, identify the PEOPLE element (element 11). Record: slide number, representation group used (per REPRESENTATION_MIX groups / none), gender presentation, age range.
2. Write the distribution table to working/brand/representation_audit.json:
   ```json
   {
     "total_slides": N,
     "people_slides": N,
     "no_people_slides": N,
     "people_yes_pct": N,
     "representation_tally": {
       "[group_from_intake]": {"count": N, "pct": N}
     },
     "gender_tally": {"female_presenting": N, "male_presenting": N, "other": N},
     "target_satisfied": true
   }
   ```
3. Compare tallies to the STYLE BLOCK representation_ratio. Allow +/- 10% variance per group.
4. If any group is outside the +/- 10% band: identify which slides to adjust. Write adjustment instructions to working/brand/representation_adjustments.txt: "Slide N: change Engine 1 subject to [group] to correct [group] underrepresentation."
5. Send adjustment instructions to the Slide Image Creator for the affected slides.
6. Re-audit after adjustments are made.
7. Once the audit passes (all groups within +/- 10% of target), write `representation_audit_passed: true` and the timestamp to representation_audit.json.

**Outputs:**
- working/brand/representation_audit.json
- working/brand/representation_adjustments.txt (if adjustments needed)

**Hand to:** Director (audit result is part of the pre-Phase-3 readiness check)

**Failure mode:** If 90% or more of slides have no people at all (e.g., a highly technical deck or a no-people default), log this as `people_slides_pct: low`. The representation audit is inconclusive. Notify the Director -- the deck may not satisfy the representation target by design, and the operator should be informed.

---

### SOP 9.2b -- Hairstyle Authenticity Catalog (the Representation HAIR engine)

**When to run:** once per client at brand-build time (alongside SOP 9.2), and re-checked whenever the cast/audience demographic changes. Source authority: SOP-ENGINE-00 (Representation Intelligence), SOP-SLIDE-00 §8b (AF-HAIR-INAUTHENTIC).

**Why this engine exists.** Representation is not only the RATIO (which group, how often -- SOP 9.2). It is also AUTHENTICITY: real, age-appropriate, culturally accurate hair, so the render does not produce generic "AI plastic hair." The ratio engine (AF-R*/AF-CAST) and the hair engine (AF-HAIR-INAUTHENTIC) are ORTHOGONAL and both run.

**The hard rule (mechanical):** every people-prompt MUST cite a hairstyle token that is a MEMBER of an age-banded, by-gender hairstyle reference catalog you ship to `working/brand/hairstyle_catalog.json`. Prompt QC runs `scripts/intelligence_engines_check.py --phase prompt`; a people-prompt that cites no catalog hairstyle (or any prompt at all when the catalog asset is absent) auto-fails AF-HAIR-INAUTHENTIC. The "AI plastic hair" render is the vision VERDICT, graded at Image-QC and logged to `vision_qc_log.json`.

**Steps:**
1. From `REPRESENTATION_MIX` and `audience_demographic` (intake), determine the cast's groups, genders, and age bands present on this deck.
2. Build `working/brand/hairstyle_catalog.json` as the authoritative token set. Two accepted shapes (the checker reads either):
   ```json
   { "by_age_band": {
       "child": ["coils", "afro puffs", "two-strand twists", "fresh fade"],
       "teen":  ["high-top fade", "box braids", "wash-and-go", "tapered natural"],
       "adult": ["silk press", "locs", "twist-out", "low cut", "bun", "cornrows"],
       "senior":["short natural grey", "salt-and-pepper waves", "low taper"]
   } }
   ```
   or the flat form `{ "styles": ["locs", "afro", "box braids", ...] }`. Populate it with REAL, culturally accurate, age-appropriate styles for THIS client's cast -- not a generic stock list. Aim for breadth across the age bands actually on the deck.
3. Hand the catalog to the Slide Image Creator / Prompt Author. Every people-prompt must cite an age-appropriate style from it (slide-image-creator-sops.md SOP 9.3b, token class 4).
4. Record `hairstyle_catalog_built: true` and the timestamp in `representation_audit.json`.

**Outputs:** `working/brand/hairstyle_catalog.json`.

**Hand to:** Slide Image Creator / Prompt Author (prompt-token mandate); QC Specialists (AF-HAIR-INAUTHENTIC mechanical half at Prompt QC, vision verdict at Image QC).

**Failure mode:** if the client's cast demographic is genuinely unknown, do NOT invent culturally specific styles. Flag the Director to confirm the demographic, ship a conservative age-banded catalog of neutral descriptors, and note the gap; never leave the catalog absent (an absent catalog makes every people-prompt fail AF-HAIR-INAUTHENTIC by design until it is supplied).

---

### SOP 9.3 -- Archetype Palette and Exemplar Handoff

**When to run:** Immediately after SOP 9.1 completes -- delivered to the Slide Image Creator before Phase 2 begins, alongside the STYLE BLOCK. This is a required pre-reading delivery, not optional.

**Inputs:**
- working/brand/style_block.md (just completed)
- master SOP Section 7.2 (the five archetypes A1-A5)
- master SOP Section 7.5 (the gold-standard exemplar prompt)

**Steps:**
1. Confirm that the STYLE BLOCK already carries the note "ARCHETYPES: A1-A5 per master SOP Section 7.2 (delivered separately via SOP 9.3)" in the COLORS/GRAMMAR section.
2. Prepare an Archetype Palette handoff note for the Slide Image Creator. The note must contain:
   a. A summary table of all five archetypes (A1-A5) drawn verbatim from master SOP Section 7.2, including Code, Archetype name, Layout definition, and Best for columns.
   b. The full recurring brand grammar device list from the STYLE BLOCK, cross-referenced to the archetype each device appears in most.
   c. The complete Section 7.5 gold-standard exemplar prompt, verbatim, labeled clearly as: "REQUIRED PRE-READING -- GOLD-STANDARD EXEMPLAR PROMPT (master SOP Section 7.5). Read this before writing a single prompt. Every prompt produced must match this density, this structure, and this level of art direction, adapted to its own slide, archetype, and brand variables."
3. Write the handoff note to working/brand/archetype_palette_handoff.md.
4. Notify the Slide Image Creator that working/brand/archetype_palette_handoff.md is ready and must be read before Phase 2 begins.
5. Notify the Director that the archetype palette and exemplar handoff has been delivered.

**Outputs:**
- working/brand/archetype_palette_handoff.md (archetype table + brand grammar + verbatim Section 7.5 exemplar)

**Hand to:** Slide Image Creator (mandatory pre-reading before Phase 2); Director (confirmation of delivery)

**Failure mode:** If the Slide Image Creator begins writing prompts before acknowledging receipt of archetype_palette_handoff.md, flag this to the Director immediately. Prompts written without exemplar pre-reading risk density and structure failures at Prompt QC.

---

### SOP 9.4 -- The TYPOGRAPHY LAW (font system + size scale + hierarchy + palette + zero-black-bg)

**When to run:** Within SOP 9.1, as the typography portion of the STYLE BLOCK. The TYPOGRAPHY LAW is non-negotiable and travels into every prompt the Slide Image Creator writes. This codifies the gold-standard system where the entire type system is drawn INTO the image as designed typography (the deck ships as full-bleed rendered PNGs with zero native PowerPoint text runs; the type lives in the prompt spec, not in a slide theme).

**Inputs:**
- intake.json (brand_fonts, brand_colors, style_references)
- The proven gold-standard system (the defaults below when the client has no brand font)

**The LAW (five parts -- all five are encoded in the STYLE BLOCK and carried into every prompt):**

1. **FONT SYSTEM -- one typeface, hierarchy by WEIGHT.** ONE typeface family only (default: Montserrat). Hierarchy is created entirely through weight, never by mixing typefaces. The role-to-weight contract:
   - Headlines and giant numbers -> Black (the hero weight). Always.
   - Sub-headlines, body beats, before/after stats -> ExtraBold (occasionally Black at a smaller size when the sub is itself a punch).
   - Gold all-caps letter-spaced kicker labels, pills, badges -> Bold.
   - Section labels and subheads on photo slides -> SemiBold.
   - Tertiary / breathing lines -> Medium, often italic.
   - Footnotes and fine print -> Regular, ~11-13pt, often italic.
   If the client supplied a brand font, map THAT family across the same weight roles (heaviest weight = headlines and giant numbers). Never fall back to a basic or platform-default typeface.

2. **SIZE SCALE -- extreme contrast, slide-height-relative.** Tiny letter-spaced labels at one end, billboard headlines and three-digit-point giant numbers at the other:
   - GIANT NUMBER: 110-150pt (Black) -- dollar figures, hero stats, the price-drop current price. Giant numbers run 1.5x to 3x the size of surrounding text and are the hero of the data zone.
   - Hero headline: 62-86pt (Black) -- the dominating 2-line headline, the first thing the eye reads.
   - Secondary headline: 42-62pt (Black / ExtraBold) -- data-zone headlines, sub-punch lines.
   - Sub-headline: 24-32pt (ExtraBold) -- the BRAND_SECONDARY accent line under the headline.
   - Body beat: 17-22pt (ExtraBold / Medium).
   - Tertiary / italic breathing line: 16-19pt (Medium italic).
   - Kicker label: ~13pt (Bold), gold all-caps, letter-spaced +0.12 to +0.15em.
   - Footnote: 11-13pt (Regular italic).

3. **HIERARCHY STACK -- the canonical vertical rhythm.** Every text-bearing slide reads top to bottom in the same disciplined stack: accent caps kicker label -> thin accent breathing rule -> massive charcoal Black 2-line headline (dominates the zone, first thing the eye reads) -> BRAND_SECONDARY ExtraBold sub-headline -> a second thin accent rule (premium paired-rule framing around the core message) -> charcoal body beat -> italic tertiary breathing line -> logo chip bottom-right.

4. **PALETTE -- five core colors plus a giant-number gradient.** Derive from the client's intake hexes onto these roles (when intake supplies no brand colors, flag and use sensible defaults):
   - Charcoal #231F20 -- ALL headlines and body. NEVER pure black (#000000); the warm charcoal is softer and more premium.
   - [BRAND_SECONDARY] -- sub-headlines, urgency, the "winner" price, punchlines, single-word emphasis. Assign the client's high-contrast action color.
   - [BRAND_PRIMARY] -- kicker labels, rules, dividers, logo-chip border, badges, column dividers, arrows. This is STRUCTURAL, not decorative. Gold tones work well in this role.
   - White #FFFFFF and warm off-white #FBF7F4 -- the base layer (80%+ of the visual area).
   - Giant-number gradient: derive from BRAND_PRIMARY; a two-stop gradient (dark left -> light right) OR BRAND_SECONDARY with a subtle glow for the "winner" price.

5. **ZERO BLACK BACKGROUNDS -- the load-bearing hard rule.** No black backgrounds anywhere in any frame: not in corners, not behind text, not as a vignette. White or warm off-white base on every slide (unless DARK_OK=true). This is the single most repeated constraint in the proven spec and the defining break from the failure-mode decks. Headlines are charcoal #231F20, never #000000.

**Steps:**
1. Write the TYPOGRAPHY LAW block (the five parts above) into the STYLE BLOCK, substituting the client's brand font family and hexes onto the same weight roles and color roles when the client supplied them; otherwise use the gold-standard defaults and flag the source.
2. Confirm the STYLE BLOCK explicitly forbids basic/default fonts (Calibri, Arial, Times, system or platform defaults) and the pure-black background, and explicitly states that giant numbers and headlines are Black weight.
3. Deliver the TYPOGRAPHY LAW as part of SOP 9.3's handoff so the Slide Image Creator carries the exact weights and large pt sizes into every prompt (every prompt names the weight and a large pt size per line; "Montserrat Bold" alone, with no per-line size, is insufficient).

**Outputs:**
- The TYPOGRAPHY LAW block inside working/brand/style_block.md (all five parts present)

**Hand to:** Slide Image Creator (the LAW is carried into every prompt); QC Specialist -- Presentations (the LAW is the basis of the typography AUTO-FAIL gate)

**Failure mode:** If the STYLE BLOCK ships without the full TYPOGRAPHY LAW (any of the five parts missing), the Slide Image Creator will default to a basic font and the deck will auto-fail at QC. Treat a STYLE BLOCK without the complete LAW as incomplete (Gate 1) and do not deliver it.

---

