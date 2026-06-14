# SOP: Creative Typography Guide

**Cluster:** Design System (Corey overhaul)
**Owner role:** Typography Architect (SOP 9.1). Enforced by: QC Specialist (Phase 3 prompt QC, Phase 5 image QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7.2, 7.4, 7.5)
**Version:** 1.0

> Grounds the deck's typography in real type practice so it is a DESIGNED system, not a default one. Corey's deck used one device (a black headline with a single teal accent word) on about 40 of 45 slides: no weight ladder, no expressive display type, no per-slide treatment. This guide encodes the weight ladder, expressive display rules, and hierarchy that the Typography Architect locks and the prompt writer renders.

---

## 1. Purpose

Give the Typography Architect and the Slide Image Creator a concrete, checkable typographic system so every slide looks art-directed. Typography is decided BEFORE any image prompt is written (the Typography Architect runs in Phase 1.5). The guide turns "use creative typography" (the soft guidance that already failed) into named weights, named roles, named display treatments, and a per-word emphasis rule that a QC gate can pass or fail.

---

## 2. The Hard Rule

Every deck obeys ONE locked weight ladder with at least FOUR distinct weights and named roles, and a per-word emphasis rule. The single repeated device (one black headline plus one accent word on every slide) is banned. Display type is used expressively where the master SOP archetypes call for type to be the hero (A4 type-punch, A3 data hero, hook slides).

### 2.1 The locked weight ladder (the Lyric proof, adapt sizes to slide height)

| Weight | Role | Typical size (relative to 1440px slide height) |
|--------|------|-------------------------------------------------|
| BLACK | Hero headlines, hero numbers, the live price numeral | 60 to 86pt |
| ExtraBold | Sub-heads, the second line of a two-line headline, the struck price | 26 to 34pt |
| Bold | Kicker labels, section banners, tag-price labels, bullet labels | 16 to 22pt |
| Medium / SemiBold + Italic | Body lines, tertiary lines, captions, the compliance disclaimer | 17 to 24pt |

Default family: Montserrat (geometric editorial sans). If the client has a locked brand typeface, use it and map its available weights to these four roles. A family with fewer than four weights maps its heaviest weight to BLACK and notes the substitution.

### 2.2 Expressive display type (where type is the hero)

- A4 (type-dominant punch): the headline or number is enormous and dominates the frame; negative space around it is a designed feature, not emptiness. Set the hero line in BLACK weight at the top of the size range.
- A3 (data-bottom): the hero number is set roughly 3x the size of any supporting line, in BLACK weight, in the gold gradient when it is a money number.
- Hook slides: the hook line is the whole slide, set large in BLACK weight over a low-opacity image (see the Pure-Typography Hook Slides SOP).
- Watermark numerals: section-opener slides may carry a giant faint background numeral (the section number) as a display device, set well below the headline in opacity.

### 2.3 The per-word emphasis rule

Each headline names AT MOST one or two emphasis words. Emphasis is rendered in the secondary accent hex (or the gold gradient for money words). The emphasis must CHANGE meaningfully slide to slide: which word carries the accent is chosen for the slide's one idea (the contrast word, the money word, the promise word). Using the same single word style on every slide (Corey's failure) is banned.

### 2.4 Hierarchy (one reading order per slide)

Every slide has exactly one clear reading order: the eye lands on the hero element first (the BLACK line or the photo subject), then the sub-head, then the body, then the kicker/label, then the logo. The Typography Architect states this order implicitly through the weight ladder; the prompt writer renders it. Two elements competing for "first" on the same slide is a hierarchy failure.

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

These gates are checked by QC. Each is a concrete PASS/FAIL.

| Trigger | Verdict |
|---------|---------|
| The deck uses only ONE weight across all headlines (no ladder) | AUTO-FAIL (deck-level) |
| A slide's prompt names no weight-ladder role for its text (just "bold text") | FAIL that prompt at Phase 3 |
| The same single-device look (black headline + one accent word) is used on more than 70% of slides | AUTO-FAIL (deck-level): the Corey cookie-cutter pattern |
| An A4 type-punch or A3 data slide does NOT set its hero element in BLACK weight at hero scale | FAIL that prompt |
| A money/price number is rendered in flat color when the locked price-type system specifies the gold gradient | FAIL that prompt/image |
| Two elements on one slide compete as the visual "first" (no single reading order) | FAIL that prompt |
| Emphasis word(s) absent on a headline that names a contrast or a money word | FAIL that prompt |

QC checks the prompt at Phase 3 against the Typography Architect treatment table (the prompt must name the assigned weight roles and emphasis word) and checks the rendered image at Phase 5 (the hero element is visibly the heaviest; the emphasis word is visibly accented; the price uses the gradient).

---

## 4. PASS vs FAIL Examples (from the actual Corey defects)

**FAIL (Corey, deck-wide):** essentially one device, a black headline with a single teal accent word, reused on about 40 of 45 slides. No weight ladder. No expressive display. The only good idea (gold $5,000 on slide 32) was not carried to slides 34, 37, 43, which landed flat. Verdict: deck-level AUTO-FAIL (single-device over 70%) plus per-slide FAIL on the flat price beats.

**PASS (Lyric proof):** a locked Montserrat weight ladder (BLACK headlines, ExtraBold sub-heads, Bold labels, Medium/Italic body), hero numbers in metallic gold gradient, the live price glowing in raspberry-pink, dead prices double-struck in gold, per-word color emphasis ("EVER" in gold, "RIGHT NOW" underlined), and giant faint watermark numerals on section reveals. Every price beat carried the gold treatment, not just one. Verdict: PASS.

**PASS (single slide):** a treatment-table row sets the headline in BLACK, the sub-head in ExtraBold, the kicker in Bold, and emphasizes "control" and "clarity" in the accent hex; the prompt names each weight and the emphasis words; the rendered image shows a clear single reading order. Verdict: PASS.

**FAIL (single slide):** the prompt says "professional bold headline with a teal accent word" with no weight role, no specific emphasis word, and no hierarchy statement. Verdict: FAIL at Phase 3 (no weight-ladder role; generic emphasis).

---

## 5. Escalation / Repair Path

1. Phase 3 prompt FAIL on a typography criterion: QC loops the prompt back to the Slide Image Creator with the exact failing trigger and the assigned treatment-table row. The writer rewrites the prompt to name the weight roles and the emphasis word.
2. Phase 5 image FAIL (the rendered hero is not the heaviest, or the price is flat): QC classifies it, and the slide regenerates with a stronger weight contrast or the gold gradient explicitly described.
3. Deck-level AUTO-FAIL (single-device over 70%, or no ladder): the deck does not pass; QC returns it to the Typography Architect to revise the type system and treatment table, then the affected prompts are rewritten.
4. If a typography criterion fails 3 loops on the same slide, escalate to the Director, then the human owner. File a bug ticket (the unfiled bug is a future repeat).

---

## 6. Research Base (where the rules come from)

- The Lyric gold-standard design proof (the locked Montserrat weight ladder, gold gradient, glow, strikethrough, watermark numerals, per-word emphasis) is the empirical model this guide encodes.
- Hierarchy and weight-contrast principles (one reading order, four-weight ladder) from established editorial and display-type practice.
- Master SOP Section 7.2 (archetypes, where type is the hero) and 7.4 (price typography as a drawn object, not a font style).
