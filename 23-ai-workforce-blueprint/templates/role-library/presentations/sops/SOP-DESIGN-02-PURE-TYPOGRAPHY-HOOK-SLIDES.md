# SOP: Pure-Typography Hook Slides

**Cluster:** Design System
**Owner roles:** Typography Architect (assigns PURE_TYPE_HOOK in the treatment table, SOP 9.3) + Slide Image Creator (renders it). Enforced by: QC Specialist (Phase 3 prompt QC, Phase 5 image QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md; the full-density A4 type-dominant exemplar in slide-image-creator.md Appendix A (Exemplar 1)
**Version:** 1.0

> The hook is a refrain sung at 3 to 4 natural anchors, each on its OWN dedicated pure-typography slide. The forensic reference deck did the opposite: the hook was footer-wallpaper on about 40 of 45 slides, printed twice on several, mutated on one, misspelled on another, with no clean dedicated hook slide at all. This SOP defines what a dedicated hook slide looks like so the hook lives on type, not on a footer.

---

## 1. Purpose

Define the visual design of the 3 to 4 dedicated hook slides: the hook line set large over a low-opacity image, with no competing imagery, no footer band, and no second idea. This is the design half of the hook doctrine (the count and placement of hook anchors is owned by the Hook Strategist and the master SOP hook rule; this SOP owns how a dedicated hook slide is rendered). The two halves together kill the footer-wallpaper failure.

---

## 2. The Hard Rule

A dedicated hook slide is PURE TYPOGRAPHY. The hook line is the entire slide. It is set large (BLACK weight, hero scale) over a single low-opacity image (8 to 15% opacity, or a soft single-color wash) that does not compete with the words. There is no second photographic subject, no chart, no body paragraph, no kicker stack, no footer band, and no second idea. The hook line is the canonical refrain, verbatim, never reworded, never extended, never duplicated on the slide.

### 2.0 "Pure typography" means kie.ai RENDERS THE TYPE AS THE IMAGE — it does NOT mean "render this slide locally"

This is the single most important sentence in this SOP, stated first so it cannot be misread: a PURE_TYPE_HOOK slide is a **kie.ai gpt-image-2 render** exactly like every other slide in the deck. kie.ai bakes the cream surface (or the low-opacity wash/image) AND the verbatim hook display type into ONE composed image. "Pure typography" describes the *visual content* (type carries the slide, no competing photographic subject), NOT the *render path*. The render path is identical to every other slide: text-to-image (Mode A) when no logo is composited, image-to-image (Mode B) when the locked logo is composited — both kie.ai, per SOP-IMG-01.

**FORBIDDEN — the exact defect this kills:** generating a hook slide locally with Pillow/PIL (`Image.new('RGB',(W,H),'#FFFBF1')` to fabricate a flat cream card), with ImageDraw text, with a PowerPoint-rendered card, with any built-in `image_generate` tool, or with any model other than kie.ai gpt-image-2. A hook slide that never reaches kie.ai — i.e. one that carries **no real kie.ai `taskId`** — is an AUTO-FAIL (`AF-LOCAL-CANVAS` / `AF-CANONICAL-RENDER-BYPASS`), not an acceptable shortcut. The phrase "skip kie.ai for this slide" is doctrine-illegal and appears nowhere in this department. Pillow/PIL is permitted on a slide for the LOCKED LOGO image composite ONLY (SOP-IMG-05) — never to draw the slide, the cream surface, or any hook text.

**Every PURE_TYPE_HOOK slide therefore carries, like every other slide:** a real kie.ai `taskId` in `working/checkpoints/kie_task_ids.json`, a downloaded PNG above the kie-bake byte floor (>= 51,200 bytes; a ~26–30 KB flat cream card is below the floor by construction and hard-fails), and the verbatim hook words baked into that PNG by the model. Hook slides are NEVER excluded from image-QC scope.

### 2.1 What goes on a dedicated hook slide

- The hook line (verbatim from hook_package.json), set large, BLACK weight, centered or in a single chosen position.
- At most one or two emphasis words in the accent hex (e.g. "control" and "clarity").
- A single low-opacity background image OR a soft single-color wash. The image is barely there; the type carries the slide.
- The logo, placed image-to-image at the locked size/position (per the Logo Consistency SOP).
- Nothing else.

### 2.2 What is BANNED on a dedicated hook slide

- A competing photographic subject (a person, a scene, a product) at normal opacity. The image must be low-opacity background only.
- A footer band carrying the hook (the forensic failure). The hook is the hero of the slide, never a bottom strip.
- The hook line printed twice (a bold copy plus a ghosted italic repeat is the forensic-deck slide-10/12/14 failure).
- A reworded or extended hook (the forensic-deck slide-28 "...and the results are significantly different" failure). The refrain is fixed and verbatim.
- A second idea, a body paragraph, a kicker stack, a chart, or a sub-head that introduces a new concept.
- The signature quote stacked on top of the control-vs-clarity hook (these are two distinct beats and must be two distinct slides).

### 2.3 The signature quote slide is its own beat

The signature quote (e.g. "Instead of solving problems, we walk them through how to think about it...") is a SEPARATE dedicated beat, on its own slide, attributed at the bottom, with NO primary hook stamped on it. It follows the same pure-type-over-low-opacity-image treatment, but it is not counted as one of the primary hook anchors and the two never share a slide.

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

| Trigger | Verdict |
|---------|---------|
| A PURE_TYPE_HOOK slide was rendered locally (Pillow/PIL `Image.new`/ImageDraw, PowerPoint card, native image tool, or any non-kie.ai model) instead of by kie.ai gpt-image-2 | AUTO-FAIL that slide (`AF-LOCAL-CANVAS` / `AF-CANONICAL-RENDER-BYPASS`) |
| A PURE_TYPE_HOOK slide has NO real kie.ai `taskId` in `kie_task_ids.json`, or its PNG is below the 51,200-byte kie-bake floor (the flat-cream-card signature) | AUTO-FAIL that slide (`AF-LOCAL-CANVAS`) |
| A PURE_TYPE_HOOK slide is excluded from image-QC scope ("slides 1/24/49 out of scope") | AUTO-FAIL the gate (no slide is exempt from pixel QC) |
| The hook line (or its refrain) is rendered in a footer band on ANY slide | AUTO-FAIL that slide (footer-stamped hook) |
| A slide marked PURE_TYPE_HOOK carries a competing photographic subject at normal opacity | AUTO-FAIL that slide |
| The background image on a hook slide is above ~15% opacity (it competes with the type) | FAIL that prompt/image |
| The hook line appears twice on the same slide | AUTO-FAIL that slide |
| The hook line is reworded or extended from the canonical refrain | AUTO-FAIL that slide (verbatim refrain only) |
| A second idea, body paragraph, or chart appears on a PURE_TYPE_HOOK slide | FAIL that slide (one big idea) |
| The signature quote shares a slide with the primary hook | AUTO-FAIL both (two beats conflated) |
| The deck has zero dedicated pure-typography hook slides | AUTO-FAIL (deck-level): the hook has no home |
| The hook line is misspelled in the rendered image (e.g. "hclarity") | AUTO-FAIL (also caught by the text-render auto-fail) |

The Slide Image Creator marks each PURE_TYPE_HOOK prompt with the treatment tag so QC can target these checks. QC at Phase 3 verifies the prompt carries no competing imagery and no footer band; QC at Phase 5 verifies the rendered slide is pure type, the hook is verbatim and spelled correctly, and it appears once.

---

## 4. PASS vs FAIL Examples (from the forensic defects)

**FAIL (the forensic reference deck):** the example signature hook was footer-stamped on about 40 of 45 slides, printed twice on slides 10/12/14/22/28/44, printed three times on slide 4 (headline, body, footer), extended on slide 28, and misspelled on slide 23. There was no clean dedicated hook slide. Verdict: deck-level AUTO-FAIL plus per-slide AUTO-FAILs.

**FAIL (forensic-deck slide 18):** the signature quote was correctly isolated, but the primary hook footer was stamped on top of it, conflating two distinct hooks. Verdict: AUTO-FAIL (two beats conflated).

**PASS (the fix):** about four dedicated hook slides, each the hook line set large over a low-opacity thematic image, with one or two emphasis words in the accent, the logo bottom-right, nothing else. The signature quote is its own separate slide with the attribution at the bottom and no primary hook on it. The hook appears nowhere else on the deck. Verdict: PASS.

**PASS (the gold-standard reference deck):** the example signature hook recurs as its own beat across the deck, never as a footer stamped on every slide; pivotal hook slides are pure typography with the image at low opacity and the text doing the heavy lifting. Verdict: PASS.

---

## 5. Escalation / Repair Path

1. Phase 5 image FAIL (footer hook detected, or competing imagery, or doubled/misspelled hook): QC loops the slide back to the Slide Image Creator with the exact trigger. The slide regenerates as pure type with the low-opacity image and the verbatim refrain.
2. If the deck has no dedicated hook slide at all (deck-level AUTO-FAIL): QC returns to the Typography Architect (treatment table) and the Hook Strategist (anchor list); the hook anchors are added as PURE_TYPE_HOOK rows and the affected prompts are written.
3. If the signature quote and the hook are conflated: split into two slides; regenerate both.
4. Misspelled hook in render: this is also a text-render auto-fail. Re-render via RE-PROMPT + RE-SEED; on persistent garble ESCALATE TO A HUMAN. The hook text is ALWAYS baked into the image, NEVER composited as a native layer — the native-text overlay path is eliminated (Decision 5C, AF-OVERLAY-DELIVERED). The only post-generation image-composite exception is the real LOGO image via the PIL path (SOP-IMG-05).
5. 3 loops on the same slide: escalate to the Director, then the human owner. File a bug ticket.

---

## 6. Research Base

- The transcript "song" doctrine: the hook is sung at natural anchors, on its own slide, never stamped on every slide.
- The gold-standard proof: pivotal/hook slides are pure typography with a low-opacity image; the text does the heavy lifting; the hook recurs as its own beat.
- slide-image-creator.md Appendix A Exemplar 1 (A4 type-dominant punch: type IS the slide; the exemplar's per-line type discipline).
