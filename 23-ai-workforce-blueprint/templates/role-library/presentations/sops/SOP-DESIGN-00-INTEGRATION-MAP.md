# Design-System Cluster: Integration Map

**Cluster:** Design System.
**Presentations dept:** 23-ai-workforce-blueprint/templates/role-library/presentations/
**Master SOP:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md

> These SOPs EXTEND the existing Presentations department; they do not duplicate it. This map states where each rule lands.

**Status note (RECONCILED with the live repo, v12.6.1+):** the design-system overhaul this map describes has ALREADY LANDED in the live repo. The Typography Architect is ROLE-18 (live); Phase 1.5 (type system / layout map / treatment table before Phase 2) is already in 00-START-HERE.md and the pipeline. The design-craft auto-fails this map proposes are already wired under the repo's existing code namespace:

| This map proposes (proposed code) | LIVE enforcement already in qc-specialist-presentations.md |
|---|---|
| AF-I8 footer-stamped hook on render | AF-C2 (banded hook gate) + AF-P12 (prompt hook-overlay over-stamping) |
| AF-I9 hook slide not pure-typography | AF-F6 (hook slides must be type-driven: no image or <=15% opacity bg with large designed type) |
| AF-I10 hook doubled/reworded on render | AF-P3 + AF-I1 + AF-F9 |
| AF-I11 logo differs from locked asset / drifts | AF-F7 (logo IDENTITY drift, with the mandated image-to-image LOGO_URL path) |
| AF-I12 bracket/placeholder token on render | AF-F10 (FIX-12, the net-new blanket placeholder-on-render ban this overhaul adds) |
| AF-D1 layout never varies / single chassis | AF-F6 (image-position sameness: >2 consecutive slides same position = auto-fail) + AF-DC design-craft dimensions |
| AF-D2 zero dedicated hook slides | AF-C2 floor side (under the 3-4 dedicated beats = auto-fail) |
| AF-D3 single-device typography deck-wide | AF-DC1..AF-DC7 design-craft auto-fails |

Do NOT re-add an AF-I8..I12 or AF-D1..D3 namespace to the QC role; those protections are done under AF-C2 / AF-P12 / AF-P3 / AF-I1 / AF-F6 / AF-F7 / AF-F9 / AF-F10 / AF-DC1..7. The Phase 1.5 pipeline insert in Section 4 below is ALREADY in 00-START-HERE.md. Treat this map as the reference doctrine and the historical wiring record, not as pending work.

---

## 1. Files in this cluster

| File | What it is | Lands as |
|------|-----------|----------|
| 01-typography-architect-ROLE.md | NEW role (the only new role in this cluster) | New role file `typography-architect.md` + SOP mirror `sops/typography-architect-sops.md`; register as ROLE-18 |
| 02-SOP-creative-typography-guide.md | Type-research guide: weight ladder, expressive display, hierarchy, per-word emphasis | New universal sub-SOP under the master SOP design section; referenced by the Typography Architect (SOP 9.1) and the QC gate |
| 03-SOP-pure-typography-hook-slides.md | Dedicated hook slide design: hook large over low-opacity image, no competing imagery, no footer band | New universal sub-SOP; enforced by Slide Image Creator + QC |
| 04-SOP-variable-layout-anti-template.md | Rotate image position + word placement; auto-fail a deck whose layout never varies | New universal sub-SOP; enforced by Typography Architect self-audit + QC final deck gate |
| 05-SOP-logo-consistency.md | ONE locked logo mark, image-to-image at fixed size/position; auto-fail drift/misspelled render. Also encodes the full gold-standard design proof | New universal sub-SOP; enforced by Brand Steward + Slide Image Creator + QC |

---

## 2. Existing files this cluster EXTENDS (do not duplicate)

| Existing file | Current state | The extension this cluster adds |
|---------------|---------------|----------------------------------|
| `brand-steward.md` (SOP 9.1, Gate, §13) | Locks colors, logo PLACEMENT (~9% chip), representation | Add: lock ONE canonical `LOGO_URL` and FORBID other lockups/monograms; pin the price-typography + weight-ladder system in the style block (per the Logo Consistency SOP §2 and the Creative Typography Guide). The Brand Steward already pins placement; this cluster adds "one mark, image-to-image, drift is a defect." |
| `slide-image-creator.md` (SOP 9.1 element 8/10/11, SOP 9.2 archetypes, SOP 9.5 strike) | Element 8 prescribes a "semi-transparent band at bottom 15%" for hook overlays; element 10 takes logo placement from STYLE BLOCK; A4 = "type IS the slide"; strike is a drawn object (baked into the image); the legacy native-text fallback is ELIMINATED (Decision 5C) | DELETE the bottom-15% footer-band rendering for the hook refrain (element 8): the hook renders ONLY on the dedicated pure-type slide. Require `LOGO_URL` passed via `input.input_urls` (image-to-image) on every slide; never text-to-image the mark. There is NO native-text fallback (eliminated, Decision 5C): ALL critical text — headlines, hook line, logo wordmark — is fixed by the RE-PROMPT + RE-SEED loop then human escalation and is ALWAYS baked into the image (a native on-slide text run is AF-OVERLAY-DELIVERED); the only image-composite exception is the real LOGO image via SOP-IMG-05. Render only the assigned treatment-table typography (weight roles + emphasis word); apply the price-type system across the WHOLE ladder, not one beat. Read the Typography Architect's three artifacts as required pre-reading before Phase 2. |
| `qc-specialist-presentations.md` (Image QC Auto-Fails AF-I1..AF-I7; Prompt QC AF-P1..AF-P8) | AF-I4 = logo absent/illegible/distorted/misplaced; no "logo differs from locked asset"; no design-craft auto-fails for footer hook, layout-never-varies, single-device typography, placeholder render | Add the new auto-fail codes in §3 below. Promote the design-craft checks from soft scoring to auto-fails. |
| `00-START-HERE.md` (roster of 17 roles; pipeline sequence) | Lists ROLE-01..ROLE-17; pipeline jumps Phase 1A -> Phase 2 | Add ROLE-18 Typography Architect; insert "Phase 1.5: Typography Architect locks type system + layout map + treatment table" between Phase 1A and Phase 2; add the SOP mirror row. |
| `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` (SOP-DESIGN-03-VARIABLE-LAYOUT-ANTI-TEMPLATE + brand-steward SOP (PRESENTATION-MASTER-DOCTRINE.md §4) archetypes, 7.4 price strike, 7.5 exemplar) | Five archetypes exist; price strike is a drawn object; logo chip device exists | Reference the four new design-system sub-SOPs from SOP-DESIGN-01-CREATIVE-TYPOGRAPHY-GUIDE (strikethrough/price-typography handling) + typography-architect SOP 9.3 (PRESENTATION-MASTER-DOCTRINE.md §4) design area; add the Phase 1.5 Typography Architect step to the pipeline map (Section 0); note that the native-text fallback is ELIMINATED (Decision 5C) — all critical text is baked into the image and guaranteed by the re-prompt/re-seed loop then human escalation (a native on-slide text run is AF-OVERLAY-DELIVERED). |

---

## 3. New QC auto-fail codes to add (qc-specialist-presentations.md)

Slot these into the existing Image QC Auto-Fail table (currently AF-I1 through AF-I7) and add a deck-level design-craft block. Each is a concrete PASS/FAIL trigger:

| Proposed code | Auto-fail condition | Source SOP |
|---------------|---------------------|------------|
| AF-I8 | The hook refrain is rendered in a footer band on ANY slide (footer-stamped hook) | Pure-Typography Hook Slides |
| AF-I9 | A dedicated hook slide carries a competing photographic subject at normal opacity, or is not pure-typography | Pure-Typography Hook Slides |
| AF-I10 | The hook line appears twice on the same slide, or is reworded/extended from the canonical refrain | Pure-Typography Hook Slides |
| AF-I11 | The rendered logo is a DIFFERENT mark than the locked `LOGO_URL` asset, or the mark drifts between slides | Logo Consistency |
| AF-I12 | Any bracket / "owner to confirm" / placeholder token rendered into the image face | (offer/content cluster; listed here because it is a render-time finishing defect that QC checks in the same pass) |
| AF-D1 (deck) | The deck uses fewer than 3 distinct archetypes, OR one archetype exceeds 60% of slides, OR the same five-part word-block stack appears on more than 60% of slides | Variable Layout / Anti-Template |
| AF-D2 (deck) | The deck has zero dedicated pure-typography hook slides | Pure-Typography Hook Slides |
| AF-D3 (deck) | No locked weight ladder (only one headline weight deck-wide), OR the single black-headline-plus-one-accent-word device on more than 70% of slides | Creative Typography Guide |

Also extend AF-I4's wording so it covers "differs from the locked asset," and promote the Phase 6 final-deck QC to run the cross-slide logo-drift comparison (AF-I11) and the deck-level AF-D1/AF-D2/AF-D3 checks over all rendered pages.

Note: the new prompt-QC auto-fails this cluster implies (logo drawn text-to-image instead of image-to-image; prompt missing its assigned weight-ladder role/emphasis; prompt missing archetype/position) attach to the Prompt QC table (AF-P series) and are described in the per-SOP enforcement sections.

---

## 4. Pipeline change (the one structural edit)

Insert Phase 1.5 between Phase 1A (owner copy approval) and Phase 2 (image prompts):

```
Phase 1A  -- Owner approval gate (copy locked)
Phase 1.5 -- ROLE-18 Typography Architect: lock type_system.md + layout_map.json + treatment_table.md; run self-audit; hand the three artifacts to Slide Image Creator + QC. (Brand Steward locks the single LOGO_URL in parallel.)
Phase 2   -- ROLE-11 Slide Image Creator writes prompts TO the treatment table (no inventing typography)
Phase 3   -- ROLE-09 QC Specialist prompt QC (now includes the design-craft prompt auto-fails)
...
Phase 6 QC -- final deck QC now runs the cross-slide logo-drift check + the deck-level layout/hook/typography auto-fails
```

This is the load-bearing sequencing change: typography and layout are DECIDED before prompts exist, which is the root fix for "typography was an afterthought."

---

## 5. Why each rule is enforceable (not soft guidance)

The principal reviewer's overriding requirement: description alone already failed (PR #212 added 77 auto-fails and the FINAL deck still shipped the footer hook on 40 slides, the word "webinar", and raw placeholders). So every rule in this cluster is phrased as a concrete trigger with a mechanical check:
- Footer hook -> AF-I8 (any hook in a footer band = auto-fail), not "avoid footers."
- Layout never varies -> AF-D1 (mechanical archetype-count + max-share + word-block-stack count), not "vary the layout."
- Single-device typography -> AF-D3 (over 70% single device = auto-fail), not "be creative."
- Logo drift -> AF-I11 (cross-slide mark comparison to the locked asset = auto-fail), not "keep the logo consistent."
- The image-to-image path is forced at prompt time (LOGO_URL in input_urls) so the mutation cannot happen, AND caught at render time if it does.

Each SOP carries: purpose, the hard rule, the enforcement check (the exact auto-fail trigger), PASS vs FAIL examples drawn from the forensic defects, and the escalation/repair path.
