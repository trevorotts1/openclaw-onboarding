# SOP: Pure-Typography Hook Slides

**Cluster:** Design System (density-floor overhaul)
**Owner roles:** Typography Architect (assigns PURE_TYPE_HOOK in the treatment table, SOP 9.3) + Slide Image Creator (renders it). Enforced by: QC Specialist (Phase 3 prompt QC, Phase 5 image QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7.2 A4, 7.5 exemplar)
**Version:** 1.0

> The hook is a refrain sung at 3 to 4 natural anchors, each on its OWN dedicated pure-typography slide. The forensic reference deck did the opposite: the hook was footer-wallpaper on about 40 of 45 slides, printed twice on several, mutated on one, misspelled on another, with no clean dedicated hook slide at all. This SOP defines what a dedicated hook slide looks like so the hook lives on type, not on a footer.

---

## 1. Purpose

Define the visual design of the 3 to 4 dedicated hook slides: the hook line set large over a low-opacity image, with no competing imagery, no footer band, and no second idea. This is the design half of the hook doctrine (the count and placement of hook anchors is owned by the Hook Strategist and the master SOP hook rule; this SOP owns how a dedicated hook slide is rendered). The two halves together kill the footer-wallpaper failure.

---

## 2. The Hard Rule

A dedicated hook slide is PURE TYPOGRAPHY. The hook line is the entire slide. It is set large (BLACK weight, hero scale) over a single low-opacity image (8 to 15% opacity, or a soft single-color wash) that does not compete with the words. There is no second photographic subject, no chart, no body paragraph, no kicker stack, no footer band, and no second idea. The hook line is the canonical refrain, verbatim, never reworded, never extended, never duplicated on the slide.

### 2.1 What goes on a dedicated hook slide

- The hook line (verbatim from hook_package.json), set large, BLACK weight, centered or in a single chosen position.
- At most one or two emphasis words in the accent hex (e.g. "control" and "clarity").
- A single low-opacity background image OR a soft single-color wash. The image is barely there; the type carries the slide.
- The logo, placed image-to-image at the locked size/position (per the Logo Consistency SOP).
- Nothing else.

### 2.2 What is BANNED on a dedicated hook slide

- A competing photographic subject (a person, a scene, a product) at normal opacity. The image must be low-opacity background only.
- A footer band carrying the hook (the reference-case failure). The hook is the hero of the slide, never a bottom strip.
- The hook line printed twice (a bold copy plus a ghosted italic repeat is the reference failure case's slide-10/12/14 failure).
- A reworded or extended hook (the reference failure case's slide-28 "...and the results are significantly different" failure). The refrain is fixed and verbatim.
- A second idea, a body paragraph, a kicker stack, a chart, or a sub-head that introduces a new concept.
- The signature quote stacked on top of the control-vs-clarity hook (these are two distinct beats and must be two distinct slides).

### 2.3 The signature quote slide is its own beat

The signature quote (e.g. "Instead of solving problems, we walk them through how to think about it...") is a SEPARATE dedicated beat, on its own slide, attributed at the bottom, with NO control-vs-clarity hook stamped on it. It follows the same pure-type-over-low-opacity-image treatment, but it is not counted as one of the control-vs-clarity hook anchors and the two never share a slide.

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

| Trigger | Verdict |
|---------|---------|
| The hook line (or its refrain) is rendered in a footer band on ANY slide | AUTO-FAIL that slide (footer-stamped hook) |
| A slide marked PURE_TYPE_HOOK carries a competing photographic subject at normal opacity | AUTO-FAIL that slide |
| The background image on a hook slide is above ~15% opacity (it competes with the type) | FAIL that prompt/image |
| The hook line appears twice on the same slide | AUTO-FAIL that slide |
| The hook line is reworded or extended from the canonical refrain | AUTO-FAIL that slide (verbatim refrain only) |
| A second idea, body paragraph, or chart appears on a PURE_TYPE_HOOK slide | FAIL that slide (one big idea) |
| The signature quote shares a slide with the control-vs-clarity hook | AUTO-FAIL both (two beats conflated) |
| The deck has zero dedicated pure-typography hook slides | AUTO-FAIL (deck-level): the hook has no home |
| The hook line is misspelled in the rendered image (e.g. "hclarity") | AUTO-FAIL (also caught by the text-render auto-fail) |

The Slide Image Creator marks each PURE_TYPE_HOOK prompt with the treatment tag so QC can target these checks. QC at Phase 3 verifies the prompt carries no competing imagery and no footer band; QC at Phase 5 verifies the rendered slide is pure type, the hook is verbatim and spelled correctly, and it appears once.

---

## 4. PASS vs FAIL Examples (from the actual reference-case defects)

**FAIL (reference failure case):** the hook (a contrast line of the form "There is a difference between [OLD_WAY] and [NEW_WAY]") was footer-stamped on about 40 of 45 slides, printed twice on slides 10/12/14/22/28/44, printed three times on slide 4 (headline, body, footer), extended on slide 28, and misspelled (a key word rendered as "hclarity") on slide 23. There was no clean dedicated hook slide. Verdict: deck-level AUTO-FAIL plus per-slide AUTO-FAILs.

**FAIL (reference failure case slide 18):** the signature quote ("We Walk Them Through How To Think About It") was correctly isolated, but the main contrast hook footer was stamped on top of it, conflating two distinct hooks. Verdict: AUTO-FAIL (two beats conflated).

**PASS (the fix):** about four dedicated hook slides, each the hook line set large over a low-opacity image, the two emphasis words in the accent, the logo bottom-right, nothing else. The signature quote is its own separate slide with the attribution at the bottom and no main hook on it. The hook appears nowhere else on the deck. Verdict: PASS.

**PASS (gold-standard reference proof):** the hook ("[PROMISE]. [TIMEFRAME].") recurs as its own beat across the deck, never as a footer stamped on every slide; pivotal hook slides are pure typography with the image at low opacity and the text doing the heavy lifting. Verdict: PASS.

---

## 5. Escalation / Repair Path

1. Phase 5 image FAIL (footer hook detected, or competing imagery, or doubled/misspelled hook): QC loops the slide back to the Slide Image Creator with the exact trigger. The slide regenerates as pure type with the low-opacity image and the verbatim refrain.
2. If the deck has no dedicated hook slide at all (deck-level AUTO-FAIL): QC returns to the Typography Architect (treatment table) and the Hook Strategist (anchor list); the hook anchors are added as PURE_TYPE_HOOK rows and the affected prompts are written.
3. If the signature quote and the hook are conflated: split into two slides; regenerate both.
4. Misspelled hook in render: this is also a text-render auto-fail. Re-render; if it fails twice, the hook text is composited as a native layer per the native-text fallback (see the Logo Consistency SOP and master SOP 7.4) so spelling is guaranteed.
5. 3 loops on the same slide: escalate to the Director, then the human owner. File a bug ticket.

---

## 6. Research Base

- The transcript "song" doctrine: the hook is sung at natural anchors, on its own slide, never stamped on every slide.
- The gold-standard reference proof: pivotal/hook slides are pure typography with a low-opacity image; the text does the heavy lifting; the hook recurs as its own beat.
- Master SOP Section 7.2 A4 (type-dominant punch: type IS the slide) and 7.5 (the exemplar's per-line type discipline).
