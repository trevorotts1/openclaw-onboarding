# SOP: Variable Layout / Anti-Template

**Cluster:** Design System (density-floor overhaul)
**Owner roles:** Typography Architect (builds the LAYOUT MAP, SOP 9.2) + Slide Image Creator (renders the assigned archetype + position). Enforced by: QC Specialist (Phase 3 prompt QC, Phase 5 image QC, Phase 6 final deck QC).
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 7.2 the five archetypes)
**Version:** 1.0

> A premium deck rotates image position (left, right, top, bottom, full-bleed) and varies word placement across the deck so it reads as one cohesive piece, not a cookie-cutter chassis. The reference failure case's later revision rotated image position (real improvement) but the word block stayed the identical five-part vertical stack (kicker caps, headline, subhead, footer hook, italic caption) on nearly every slide: a rigid recurring chassis. This SOP makes layout variety an enforceable gate, not a hope.

---

## 1. Purpose

Turn the master SOP's five-archetype system into an ENFORCED rotation. The five archetypes already exist (A1 full-bleed, A2 photo-one-side, A3 photo-top/data-bottom, A4 type-punch, A5 portrait); the problem was nothing forbade reusing one chassis on the whole deck or repeating the same word-block position slide after slide. This SOP adds the variation rules and the auto-fail that catches a deck whose layout never varies, so every image stands on its own while the deck stays cohesive.

---

## 2. The Hard Rule

1. The deck rotates image position across the five archetypes: image LEFT (A2), image RIGHT (A2 mirrored), image TOP (A3), image FULL-BLEED (A1), and TYPE-DOMINANT/portrait (A4/A5). At least THREE of the five archetypes appear in the deck.
2. No single archetype is used on the whole deck. No archetype exceeds ~50% of slides (a soft cap that triggers review; see the enforcement check for the hard auto-fail).
3. No two CONSECUTIVE slides share BOTH the same archetype AND the same word-block position. The eye must move between adjacent slides.
4. Word-block position rotates across the deck: lower-left, lower-right, centered, top-band, left-panel, right-panel. The identical five-part vertical stack on every slide (the reference-case rigid chassis) is banned.
5. The deck is cohesive: the brand grammar (palette, type ladder, logo placement, kicker/rule devices) is constant; it is the LAYOUT and word placement that vary. Variety is in position and archetype, not in inventing new colors or fonts per slide.

---

## 3. The Enforcement Check (what auto-fails the slide/deck)

The check runs on the LAYOUT MAP at Phase 1.5 (Typography Architect self-audit) and again on the rendered deck at Phase 6 final QC.

| Trigger | Verdict |
|---------|---------|
| The deck uses only ONE archetype across every slide | AUTO-FAIL (deck-level): layout never varies |
| Fewer than THREE distinct archetypes used across the deck | AUTO-FAIL (deck-level) |
| Any single archetype exceeds 60% of slides | AUTO-FAIL (deck-level): cookie-cutter chassis |
| Two CONSECUTIVE slides share the same archetype AND the same word-block position | FAIL the later slide; loop to fix |
| The same five-part word-block stack (kicker + headline + subhead + footer + caption) appears on more than 60% of slides | AUTO-FAIL (deck-level): the reference-case rigid chassis |
| A slide's prompt does not declare its archetype on line 1 | FAIL that prompt (also a master SOP prompt-QC auto-fail) |
| A slide's prompt does not state its word-block position in thirds language | FAIL that prompt |

**Mechanical computation (the QC agent runs this on layout_map.json and on the rendered deck):**
- Count distinct archetypes. If under 3, AUTO-FAIL.
- Compute the max share of any one archetype. If over 60%, AUTO-FAIL.
- Walk the slide order; for each adjacent pair, if archetype[i] == archetype[i+1] AND position[i] == position[i+1], FAIL slide i+1.
- Count slides whose word block is the full five-part vertical stack. If over 60%, AUTO-FAIL.

---

## 4. PASS vs FAIL Examples (from the actual reference-case defects)

**FAIL (reference failure case, original deck):** image position rotated, but the word block was the identical five-part vertical stack (kicker caps, headline, subhead, footer hook, italic caption) on nearly every slide. No five-archetype rotation of word placement. Verdict: deck-level AUTO-FAIL (rigid chassis over 60%).

**PARTIAL (reference failure case, later revision):** image position genuinely rotated now (full-bleed, photo-left, photo-right, pure-type, photo-top), which passes the archetype-variety check, BUT a rigid recurring chassis remained in the word block. Verdict: still AUTO-FAIL on the word-block-stack check until the word placement varies too.

**PASS (gold-standard reference proof):** a five-archetype system makes 75 independently generated images read as ONE deck; image position varies by archetype (full-bleed for emotion, photo-one-side for authority, photo-top/data-bottom for stats, type-dominant for prices, portrait for founder); word placement rotates (left-aligned panels, centered hero numbers, top-band labels, bottom-scrim overlays) so it never feels cookie-cutter. Verdict: PASS.

**PASS (consecutive slides):** slide 11 is A2 with the word block in the right panel; slide 12 is A4 with the word block centered. Different archetype, different position. Verdict: PASS. (If slide 12 were also A2 right-panel, slide 12 would FAIL.)

---

## 5. Escalation / Repair Path

1. Phase 1.5 self-audit FAIL (the LAYOUT MAP violates the rule): the Typography Architect reassigns archetypes/positions to satisfy the rule before any prompt is written. This is the cheapest place to fix it (no images burned).
2. Phase 3 prompt FAIL (a prompt does not declare its archetype or position): QC loops it back to the Slide Image Creator; the writer adds the archetype on line 1 and the thirds-position statement.
3. Phase 6 final-deck AUTO-FAIL (the rendered deck reads cookie-cutter): QC returns the affected slides to the Typography Architect for re-assignment and the Slide Image Creator for re-prompt and re-render of the minimum set of slides needed to break the repetition (do not re-render the whole deck if a few re-assignments fix it).
4. 3 loops on the same variation failure: escalate to the Director, then the human owner. File a bug ticket.

---

## 6. Research Base

- The gold-standard reference proof: the five-archetype system + rotated image position + rotated word placement is the empirical model for cohesive-but-varied.
- Master SOP Section 7.2 (the five proven archetypes and the rule that rotating five strong layouts beats inventing a new layout per slide).
- The reference-case forensic Dimension F (the rigid word-block chassis is the named defect this SOP prevents).
