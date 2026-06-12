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

**Steps:**
1. Extract brand colors from intake.json. If the client provided hex codes, use them verbatim. If the client described colors without hex codes (e.g., "gold and navy"), find the closest brand-standard hex codes and record them as `color_source: "derived_from_description"` in the STYLE BLOCK. If no color information exists, use a professional neutral default (#1A2B4C navy, #C4A44D gold, #FFFFFF white) and flag as `color_source: "default_pending_client_confirmation"`.
2. Assign roles to the 3 hex codes. Exactly 3 hex codes are required:
   - PRIMARY: accent-1 -- used for money/value displays, dividers, and key visual highlights (gold or brand equivalent)
   - SECONDARY: accent-2 -- used for action/urgency/emphasis words and CTA elements
   - ACCENT: the third client color
   - WHITE BASE: #FFFFFF (or a faint warm off-white per style references such as #FBF7F4) is ALWAYS the base layer beneath all three. It is not one of the three named hex slots. Do NOT label any client hex as "tertiary almost always white." The base layer is white and is listed separately in the STYLE BLOCK.
3. Extract typography from intake.json. If no fonts are specified, default to: headline font = "Montserrat Bold" (or similar geometric sans-serif), body font = "Open Sans Regular". Record as `font_source: "default_pending_client_confirmation"`.
4. Extract logo placement. Default rule: "Logo on a white chip at approximately 9% of slide width with a subtle 1px brand-accent border, placed in the same corner on every slide, minimum 40px from any edge, full color version." If client has provided a logo file, note the file path.
5. Extract representation preferences from intake.json field `REPRESENTATION_MIX`. This field is collected WITH PERCENTAGES during discovery (e.g., "70% African American women, 20% African American men, 10% mixed" or "100% women, diverse" or "no people at all"). The percentage breakdown drives the deck-level ratio in SOP 9.2.
   - If `REPRESENTATION_MIX` is present and answered: use the client's stated breakdown verbatim. Record as `representation_source: "client_intake"`.
   - If `REPRESENTATION_MIX` is unanswered or blank: DO NOT invent a racial default. Set representation to NO PEOPLE (people element omitted from all slides) and flag: `representation_source: "default_no_people -- intake unanswered"`. Immediately notify the operator with a flag: "REPRESENTATION UNANSWERED: intake.json has no REPRESENTATION_MIX value. Deck will default to no people in images. Please confirm or supply the intended breakdown before Phase 2." Do not proceed to people-inclusive prompts until the operator or client has answered.
6. Build the STYLE BLOCK text. Format (800-1,500 characters):
   ```
   STYLE BLOCK -- [client_slug] -- [deck_slug]
   Generated: [ISO_DATE]

   COLORS:
   White base: #FFFFFF (or [warm off-white hex if style refs specify]) -- slide background, dominant layer (80%+ of visual area)
   Primary (accent-1): [HEX1] -- money/value displays, dividers, kicker rules, price tag borders
   Secondary (accent-2): [HEX2] -- action/urgency/emphasis words, CTA elements, section banner fills
   Accent: [HEX3] -- [role description from intake]
   White base rule: ALL slides use the white base as the background. Brand colors are ACCENTS only (max 20% of visual area each). Dark backgrounds are PROHIBITED unless DARK_OK=true.

   TYPOGRAPHY:
   Headline font: [Font Name], Bold weight, [suggested size range]
   Body font: [Font Name], Regular weight, [suggested size range]
   Type is always legible on white backgrounds. No reversed-out text on dark backgrounds (unless DARK_OK).

   LOGO:
   [Logo placement rule: white chip at ~9% slide width, subtle 1px brand-accent border, consistent corner, full color version]

   BRAND GRAMMAR (embed in every prompt):
   - Kicker label: small all-caps letter-spaced label in Primary above the headline, with a short Primary gold rule beneath it
   - Divider: 3px full-width Primary rule between photo band and type zone on all split-layout slides
   - Color roles: Primary = money/value and dividers; Secondary = action/urgency/emphasis; charcoal = headlines (never pure black backgrounds)
   - Price tag motif: large white hang-tag shape with Primary border; old prices struck through with DRAWN Primary diagonal lines; new price in Secondary at the bottom of the tag
   - Section progress banners: "SECTION 3 OF 7" or "SECRET #1" rendered in a filled Secondary banner box on section-opener slides
   - Compliance line: small italic disclaimer in the lower margin on every slide containing a results or income claim

   REPRESENTATION RATIO (deck-level target):
   [If client answered: list each group and percentage verbatim from intake]
   [If unanswered: "NO PEOPLE -- operator flag issued, awaiting confirmation"]
   Age range: [range from intake or NONE if no people default]

   ARCHETYPES: A1-A5 per master SOP Section 7.2 (delivered separately via SOP 9.3)

   16:9 ALWAYS. 2K resolution (2560x1440). Never 4:3 or square.
   ```
7. Write the completed STYLE BLOCK to working/brand/style_block.md.
8. Register the STYLE BLOCK in working/brand/brand_registry.json: `{ "client_slug": "...", "deck_slug": "...", "style_block_path": "working/brand/style_block.md", "generated_at": "...", "color_source": "...", "font_source": "...", "representation_source": "..." }`.
9. Notify the Director and the Slide Image Creator that the STYLE BLOCK is ready.

**Outputs:**
- working/brand/style_block.md (complete STYLE BLOCK, 800-1,500 characters)
- working/brand/brand_registry.json (entry added)

**Hand to:** Slide Image Creator (for use in all 15-element prompts); also triggers SOP 9.3 delivery

**Failure mode:** If intake.json has no brand information at all (no colors, no fonts, no logo), write the STYLE BLOCK with all default values and flag: "STYLE BLOCK uses all defaults -- please confirm brand colors, fonts, and logo before final image generation. Images generated with defaults will need re-generation if brand is different." Notify the Director. If representation is unanswered, follow the no-people default rule in Step 5 above.

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
