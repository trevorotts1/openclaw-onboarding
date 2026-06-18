# SOP: Creative Typography Guide

**Cluster:** Design System
**Owner role:** Typography Architect (SOP 9.1). Enforced by: QC Specialist (Phase 3 prompt QC, Phase 5 image QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7.2, 7.4, 7.5)
**Version:** 1.0

> Grounds the deck's typography in real type practice so it is a DESIGNED system, not a default one. The forensic reference deck used one device (a black headline with a single teal accent word) on about 40 of 45 slides: no weight ladder, no expressive display type, no per-slide treatment. This guide encodes the weight ladder, expressive display rules, and hierarchy that the Typography Architect locks and the prompt writer renders.

---

## 1. Purpose

Give the Typography Architect and the Slide Image Creator a concrete, checkable typographic system so every slide looks art-directed. Typography is decided BEFORE any image prompt is written (the Typography Architect runs in Phase 1.5). The guide turns "use creative typography" (the soft guidance that already failed) into named weights, named roles, named display treatments, and a per-word emphasis rule that a QC gate can pass or fail.

---

## 2. The Hard Rule

Every deck obeys ONE locked weight ladder with at least FOUR distinct weights and named roles, and a per-word emphasis rule. The single repeated device (one black headline plus one accent word on every slide) is banned. Display type is used expressively where the master SOP archetypes call for type to be the hero (A4 type-punch, A3 data hero, hook slides).

### 2.1 The locked weight ladder (the gold-standard reference deck, adapt sizes to slide height)

| Weight | Role | Typical size (relative to 1440px slide height) |
|--------|------|-------------------------------------------------|
| BLACK | Hero headlines, hero numbers, the live price numeral, the climbing running value total | 60 to 86pt |
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

Each headline names AT MOST one or two emphasis words. Emphasis is rendered in the secondary accent hex (or the gold gradient for money words). The emphasis must CHANGE meaningfully slide to slide: which word carries the accent is chosen for the slide's one idea (the contrast word, the money word, the promise word). Using the same single word style on every slide (the forensic failure) is banned.

### 2.4 Hierarchy (one reading order per slide)

Every slide has exactly one clear reading order: the eye lands on the hero element first (the BLACK line or the photo subject), then the sub-head, then the body, then the kicker/label, then the logo. The Typography Architect states this order implicitly through the weight ladder; the prompt writer renders it. Two elements competing for "first" on the same slide is a hierarchy failure.

### 2.5 The price ladder AND the rising-value curve (the inverse, drawn)

On every DROP slide (or its immediate successor) the price-typography system renders TWO opposing movements so the audience SEES them, never just reads them in copy:

- The PRICE FALLING: the cumulative struck ladder. Every prior (dead) price is double-struck in the gold treatment and the new (live) price glows in the live-price accent; the audience watches the ladder die rung by rung.
- The VALUE RISING: the cumulative RUNNING VALUE TOTAL, climbing. The Offer Price Strategist supplies a `running_value_total` at each rung (offer_stack.json `value_additions_by_drop`, SOP 9.2 step 5b) that begins at the proven tally and strictly increases at every drop. The renderer draws this climbing total as a hero number (BLACK weight, gold gradient, the same money treatment) and shows it INCREASING from the prior rung's total to this rung's.

The two are visually PAIRED on the same slide so the widening gap is seen: the falling struck price and the rising value total set against each other (side by side, stacked as a two-line ledger, or as an up-arrow value beside the struck price), so the audience literally watches the price line move down while the value line moves up. Rendering only the struck price, with no climbing value total beside it, leaves the inverse implied rather than seen and fails this rule. The numbers are the Strategist's (consistent with offer_stack.json, AF-C4 clean); the renderer draws the two lines and the gap. The rendered VALUE numbers are pitch-stack figures, NOT a presenter-narration line: the telegraphing phrases ("the lower the price, the greater the value", "the value is still climbing") remain banned as on-slide copy (AF-C9). What is rendered is the climbing TOTAL itself, shown rising, not a sentence describing it.

### 2.6 TYPOGRAPHY INTELLIGENCE -- the 8th-row test, the salesy-font ban, and "typography = funnel"

This is the named TYPOGRAPHY INTELLIGENCE engine (SOP-ENGINE-00 Engine 3): type is engineered for the room and the goal, not decorated.

**(a) The 8th-row readability test.** Headlines are sized so they read FROM THE 8TH ROW of a room. The test is mechanical and relative to slide HEIGHT, never to a guessed room distance: shrink the rendered slide to about 25% (or stand back from it) and the headline must STILL read clearly. The weight ladder in 2.1 sets the sizes (hero headlines BLACK at 60-86pt relative to a 1440px slide height); the 8th-row test is the verification that those sizes actually carry. A headline that disappears or becomes illegible at 25% shrink fails the 8th-row test.

**(b) The salesy / cheap-font ban (fonts to avoid for trust).** Typeface choice signals INTENT. Certain display faces telegraph "salesy / cheap / $9.97-big-price-tag carnival" and are BANNED whenever the deck's goal is TRUST or credibility. The banned-for-trust taxonomy: loud condensed "big price tag" display faces, infomercial / late-night-sale carnival fonts, novelty or "free download" display fonts, distressed grunge faces, over-rounded bubble fonts, and any font whose primary association is a discount sticker or a hype sales page. These compete with the very credibility a webinar deck is built to establish. The default editorial sans (Montserrat) and the client's locked brand typeface are trust-appropriate; a banned salesy display face on a credibility deck is a defect (AF-TYPE-SALESY-FONT). (This is a TASTE / INTENT rule layered on top of the weight ladder; the ladder says HOW MANY weights, this says WHICH faces are allowed.)

**(c) Typography and funnel are the same thing.** The type DOES the persuading, so the type is chosen like a funnel step, not like decoration. Every typographic decision (which word carries the accent, how big the hero line is, which face the deck wears) is a conversion decision: it moves the eye, sets the trust temperature, and times the reveal. "Typography = funnel" is the binding framing for this engine: a font choice that would weaken trust is a funnel leak, exactly like a weak headline or a cold price.

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

These gates are checked by QC. Each is a concrete PASS/FAIL.

| Trigger | Verdict |
|---------|---------|
| The deck uses only ONE weight across all headlines (no ladder) | AUTO-FAIL (deck-level) |
| A slide's prompt names no weight-ladder role for its text (just "bold text") | FAIL that prompt at Phase 3 |
| The same single-device look (black headline + one accent word) is used on more than 70% of slides | AUTO-FAIL (deck-level): the forensic cookie-cutter pattern |
| An A4 type-punch or A3 data slide does NOT set its hero element in BLACK weight at hero scale | FAIL that prompt |
| A money/price number is rendered in flat color when the locked price-type system specifies the gold gradient | FAIL that prompt/image |
| A DROP slide (or its successor) renders the struck/falling price but NOT the climbing running value total beside it (the rising-value curve of SOP 2.5 is absent, so the inverse is implied not seen) | FAIL that prompt/image |
| Two elements on one slide compete as the visual "first" (no single reading order) | FAIL that prompt |
| Emphasis word(s) absent on a headline that names a contrast or a money word | FAIL that prompt |
| A headline does not survive the 8th-row test (illegible when the rendered slide is shrunk to ~25%) | FAIL that image (AF-TYPE-8THROW) |
| A banned salesy / cheap / "big price tag" carnival display face is used on a trust or credibility deck (SOP 2.6b) | AUTO-FAIL (deck-level): AF-TYPE-SALESY-FONT |

QC checks the prompt at Phase 3 against the Typography Architect treatment table (the prompt must name the assigned weight roles and emphasis word) and checks the rendered image at Phase 5 (the hero element is visibly the heaviest; the emphasis word is visibly accented; the price uses the gradient). On DROP slides, QC additionally confirms the rising-value curve of SOP 2.5: the cumulative running value total is rendered, climbing, against the struck/falling price so the widening gap is visible (a struck price with no climbing value total beside it fails); this is the rendering half of the choreography the QC Specialist enforces under AF-C7 sub-condition (c).

---

## 4. PASS vs FAIL Examples (from the forensic defects)

**FAIL (the forensic reference deck, deck-wide):** essentially one device, a black headline with a single teal accent word, reused on about 40 of 45 slides. No weight ladder. No expressive display. The only good idea (gold $5,000 on slide 32) was not carried to slides 34, 37, 43, which landed flat. Verdict: deck-level AUTO-FAIL (single-device over 70%) plus per-slide FAIL on the flat price beats.

**PASS (the gold-standard reference deck):** a locked Montserrat weight ladder (BLACK headlines, ExtraBold sub-heads, Bold labels, Medium/Italic body), hero numbers in metallic gold gradient, the live price glowing in raspberry-pink, dead prices double-struck in gold, per-word color emphasis ("EVER" in gold, "RIGHT NOW" underlined), and giant faint watermark numerals on section reveals. Every price beat carried the gold treatment, not just one. Verdict: PASS.

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

- The gold-standard design proof (the locked Montserrat weight ladder, gold gradient, glow, strikethrough, watermark numerals, per-word emphasis) is the empirical model this guide encodes.
- Hierarchy and weight-contrast principles (one reading order, four-weight ladder) from established editorial and display-type practice.
- Master SOP Section 7.2 (archetypes, where type is the hero) and 7.4 (price typography as a drawn object, not a font style).
