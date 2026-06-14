# SOPs Mirror -- Typography Architect

**Source:** presentations/typography-architect.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 1.0

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Type-Layout System Authoring

**When to run:** Phase 0.7 / Phase 1.5, AFTER the Brand Steward emits the STYLE BLOCK and the Director emits arc_allocation.json, and BEFORE the Slide Image Creator writes a single image prompt. This is a hard gate: the Slide Image Creator's element 5 requires this file.

**Inputs:**
- working/style/style_block.md (palette, font family, weight map, logo placement rule)
- working/copy/arc_allocation.json (the slide-type manifest)

**Steps:**

1. Inherit the type scale and weight map from the STYLE BLOCK. Do NOT invent a font family. Carry the weight ladder verbatim (for example: hero headlines in Family Black, sub-headlines in ExtraBold, kicker labels in Bold, section labels in SemiBold, tertiary lines in Medium italic, footnotes in Regular) and the pt-size ranges relative to slide height.

2. Enumerate the archetypes present in arc_allocation.json. The standing archetype set is: hook, divider, teach-one-big-idea, jaw-drop standalone, data, wall-of-wins, offer-component-card, CTA. Add any archetype the manifest names that is not in this set.

3. For EACH archetype, author one distinct LAYOUT TEMPLATE specifying:
   - **IMAGE POSITION:** one of left / right / top / bottom / full-bleed / none / low-opacity-bg. No two adjacent archetypes default to the same position.
   - **WORD-PLACEMENT ZONE:** which thirds-grid region the text occupies (upper-left / center / bottom-left, etc.), distinct per archetype so the eye is led differently slide to slide.
   - **TYPE TREATMENT:** which rungs of the weight ladder this archetype uses, in what order, at what pt sizes. NOT every rung on every slide; the canonical stack is per-archetype, not universal.
   - **DO / NEVER LIST:** the 2 to 4 things this archetype must do and the 2 to 4 it must never do (for example, teach-one-big-idea NEVER carries a hook refrain footer; jaw-drop standalone NEVER carries sub-copy or a tertiary line).

4. Apply the layout-rotation discipline borrowed from Skill 45 PPT-ANALYSIS-SOP.md: never more than 3 consecutive slides share the same type family treatment. The deck rotates between type-dominant, image-dominant, and balanced layouts.

5. Explicitly mark which archetypes are type-driven (hook, jaw-drop standalone, divider) versus image-led (teach-one-big-idea, wall-of-wins, offer-component-card). The hook archetype routes to SOP 9.2 for its full spec.

6. Write working/typography/type_layout_system.md. Structure: one section per archetype, each with IMAGE POSITION, WORD-PLACEMENT ZONE, TYPE TREATMENT (weights + pt sizes), and the DO/NEVER list. Open the file with the inherited type scale and weight map so it is self-contained for the Slide Image Creator.

**Outputs:**
- working/typography/type_layout_system.md (one LAYOUT TEMPLATE per archetype)

**Hand to:** Slide Image Creator (element 5 of every Phase 2 prompt is sourced from the matching archetype's LAYOUT TEMPLATE, replacing the single hard-coded stack) and the QC Specialist (the layout-variety asserts in Phase 5 check against this file).

**Failure mode:** If the STYLE BLOCK is missing the weight map, do NOT invent fonts. Request the weight map from the Brand Steward and block until it arrives. If arc_allocation.json names an archetype with no template, author one rather than letting it fall back to a generic stack; flag the new archetype to the Director.

---

### SOP 9.2 -- Hook-Slide Typography Spec

**When to run:** During SOP 9.1, for the hook archetype and any dedicated A4 hook slide in arc_allocation.json. The Hook Strategist owns WHERE hooks land (the placement map); you own HOW the dedicated hook slides look.

**Inputs:**
- working/style/style_block.md (font family, weight map)
- working/copy/arc_allocation.json (the positions of the dedicated A4 hook slides)
- hook_package.json (read-only, for the placement map of dedicated hook slides)

**Steps:**

1. Specify the dedicated A4 hook slide as TYPOGRAPHY-DRIVEN: no image, OR a background image at 15% opacity or lower with oversized designed type over it. The hook line is the hero and dominates the frame.

2. Set the type treatment: the hook line in the heaviest weight (Family Black), oversized (the largest pt range on the deck for a text line), centered or anchored to a single strong thirds-grid region, with maximum breathing room. No kicker, no sub-copy, no tertiary line, no logo competing for the eye (logo chip remains small and consistent per the STYLE BLOCK).

3. Forbid the hook from appearing as a refrain footer device on non-hook slides (this is the FIX-1 over-stamping defect). The hook lives on its 3 to 4 dedicated slides only; everywhere else there is NO hook footer. Record this as a hard NEVER in the hook archetype's DO/NEVER list.

4. Specify layout variety across the 3 to 4 dedicated hook slides themselves: the open verse, the mid reprise, the post-proof reprise, and the close reprise should not be visually identical. Vary the type anchor and the bg treatment so even the hook slides rotate.

**Outputs:**
- The hook archetype section of working/typography/type_layout_system.md (type-driven spec, no-image-or-low-opacity rule, the no-footer NEVER rule)

**Hand to:** Slide Image Creator (the dedicated hook slides are rendered type-driven per this spec) and the Hook Strategist (confirms the placement map's dedicated A4 slides match this typography spec).

**Failure mode:** If the placement map asks for more than 4 dedicated hook slides or a hook footer on non-hook slides, flag the conflict to the Hook Strategist and the Director: the FIX-1 ceiling is roughly 1 hook occurrence per 6 slides and never 2 consecutive slides carrying the hook. Do not author a layout that violates the ceiling.

---

### SOP 9.3 -- Layout-Variety Audit (image-position rotation)

**When to run:** After SOP 9.1 produces the archetype templates and arc_allocation.json assigns archetypes to slide positions; re-run after the Slide Image Creator drafts prompts, to confirm the rendered plan honors the rotation.

**Inputs:**
- working/typography/type_layout_system.md (the archetype templates with their image positions)
- working/copy/arc_allocation.json (which archetype sits at each slide position)

**Steps:**

1. Walk the deck in slide order. For each slide, record its image position from its archetype's LAYOUT TEMPLATE (left / right / top / bottom / full-bleed / none / low-opacity-bg).

2. Flag any run of more than 2 consecutive slides sharing the same image position. This mirrors the existing TEXT_ANCHOR rule (the copy-QC layout-variety criterion). Where a run exceeds 2, assign an alternate position to the middle slide of the run (swap left/right, or insert a full-bleed or type-driven break) so the eye is moved.

3. Flag any run of more than 3 consecutive slides sharing the same type family treatment (the Skill 45 PPT-ANALYSIS rotation rule) and break it the same way.

4. Confirm the hook slides are type-driven (no image OR <=15% opacity bg) and are not visually identical to each other.

5. Write the audit result into type_layout_system.md: `{ "max_consecutive_same_image_position": N, "max_consecutive_same_type_family": N, "hook_slides_type_driven": true|false, "verdict": "PASS|FAIL" }`. PASS requires max image-position run <= 2, max type-family run <= 3, and all hook slides type-driven.

**Outputs:**
- The layout-variety audit block in working/typography/type_layout_system.md

**Hand to:** QC Specialist (the image-position-variety assert in Phase 5 reads this audit) and the Slide Image Creator (any re-assigned positions are reflected in the prompts).

**Failure mode:** If arc_allocation.json forces more than 2 consecutive slides of the same archetype with the same image position (for example a long offer-component-card run), introduce a position swap or a type-driven break slide between them and flag the arc density to the Director for a possible re-allocation. Never let the deck render photo-right / type-left on every slide.

---
