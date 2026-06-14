# SOPs Mirror -- Hook Strategist

**Source:** presentations/hook-strategist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Hook Generation and Scoring (the Hook Lab, part 1)

**When to run:** Phase 1, before the Slide Copywriter writes slide 1. The hook must exist and be owner-selected before the copy is written around it.

**Inputs:**
- working/copy/intake.json (BIG_PROMISE, TRANSFORMATION, audience language, HOOK SEED, offer stack, primary objection)
- working/copy/mission_prd.json
- working/copy/arc_allocation.json

**Steps:**

1. Inputs intake: read intake.json (BIG_PROMISE, TRANSFORMATION, audience language, HOOK SEED), the offer stack, and the primary objection.

2. Mine the client's OWN language first. The HOOK is derived from the strongest promise in the offer -- the most concrete, most credible outcome the client can deliver. Pull from BIG_PROMISE, HOOK SEED, and verbatim client notes before inventing anything new. A hook not rooted in the strongest promise is a tagline, not a hook.

3. Generate exactly 10 candidates, with at least 1 from each of the 7 formulas. THE THREE required qualities (a hook must score on all three):
   - **MEMORABLE:** number symmetry ("30 Kids. 30 Days."), triple alliteration ("Confident. Consistent. Clear."), contrast pairs, rhythm of 2 to 8 words with hard stops.
   - **PROVOCATIVE:** challenges a held belief or dares. ("It's not your heart. It's your system." / "Stay. I dare you.")
   - **PUNCHY:** 8 words or fewer per line, max two lines, short hard words, one breath, a STATEMENT never a question.

   THE SEVEN proven hook formulas (generate candidates from these):
   - **F1 Number Symmetry:** [N] [thing]. [N] [timeframe]. ("30 Kids. 30 Days.")
   - **F2 False Cause Kill:** "It's not your [assumed]. It's your [real]." ("It's not your heart. It's your system.")
   - **F3 Contrast Pair:** "There's a difference between [X] and [Y]."
   - **F4 The Dare:** "[Command]. I dare you." / "[Promise] or [stake]." ("Fill 3 seats. Or I pay.")
   - **F5 Identity Claim:** "I [did it]. I [do it]. I'm [you]." ("I built it. I run it. I'm you.")
   - **F6 Belief Flip:** "[What they believe] is wrong. [Truth]." ("They're not ignoring you. Your message is wrong.")
   - **F7 Time Collapse:** "[Outcome] in [short]. Not [long]." ("Fill seats in 7 days. Not 7 months.")

4. Score each candidate 1 to 10 on Memorable, Provocative, and Punchy, plus SPECIFIC and SINGABLE. DQ anything that hits an anti-pattern (see Section 14 below). The ANTI-PATTERN list (instant DQ): is a question; generic transformation verbs (unlock / elevate / empower / transform / level up / journey / thrive) with no concrete noun; interchangeable across any niche; needs the offer explained first; more than 8 words per line; kitchen-table jargon; contains an em dash.

5. Field-test the top 3:
   - **SAY-IT-ALOUD:** can it be said in one breath?
   - **3-SECOND RECALL:** cover it, recall it verbatim.
   - **T-SHIRT:** would the client wear it on a shirt?
   - **COOKOUT:** is THIS the sentence that comes back, the one people quote later?

6. Present the top 3 to the owner with scores. The owner picks. Record the pick as HOOK in mission_prd.json with its hook_score.

7. Hand to the Copywriter variant system (this is SOP 9.2): 7 to 10 variants, placement map, first occurrence inside the first 10 to 15%, dedicated A4 hook slide, refrains after proof slides, reprise as the FINAL substantive slide.

8. Post-deck Hook Audit (this is SOP 9.2): count occurrences mechanically, verify distribution (no section without a refrain candidate, never more than 2 consecutive ladder/close slides without the hook nearby), verify the closing slide carries it, verify total is approaching the ~10x target (7 is the floor; push toward 10 with placement additions if under 9).

**Outputs:**
- working/copy/hook_package.json (the candidates block, the scores block, and the owner selection block)
- mission_prd.json updated with the owner-selected HOOK and its hook_score

**Hand to:** Slide Copywriter (the variant system, SOP 9.2) and the owner (Phase 1A picks the hook)

**Failure mode:** If intake.json has no HOOK SEED and no usable client language to mine, do NOT invent a hook from generic transformation verbs (that is an instant anti-pattern DQ). Derive candidates from BIG_PROMISE + TRANSFORMATION + the primary objection using the 7 formulas, present the top 3 to the owner, and flag to the Director that the hook is derived (not seeded) so the owner reviews it with extra care at Phase 1A.

---

### SOP 9.2 -- Variant Ladder, Placement Map, and Post-Deck Hook Audit (the Hook Lab, part 2)

**When to run:** Phase 1, immediately after the owner selects the hook (SOP 9.1 step 6). The placement map is drawn before the Copywriter writes; the audit runs after the Copywriter completes slides_copy.md.

**Inputs:**
- mission_prd.json (the owner-selected HOOK + hook_score)
- working/copy/arc_allocation.json (sections and slide positions)
- working/copy/slides_copy.md (in progress, then complete, for the audit)

**Steps:**

1. Hand the owner-selected hook to the Copywriter variant system: build 7 to 10 variants of the hook. Each variant says the same thing reframed for the section it appears in. Variants may be shorter, punchier, or reframed, but each must still pass the three qualities and avoid every anti-pattern.

2. Draw the placement map. The hook is sung on a SCHEDULED CADENCE, not on every slide. First occurrence lands inside the first 10 to 15% of the deck (sing it early; nobody waits to the end of the song to sing Purple Rain), and it reprises on scheduled beats through the deck (after a proof BEAT, at a section turn, at the close), NOT as a fixed footer device on every slide. The scheduled placements are: a dedicated A4 hook slide (type-dominant) at the open verse; reprises placed AFTER a proof beat (the proof just earned the hook); a reprise as the FINAL substantive slide of the deck. A refrain is placed on a slide only WHERE IT EARNS IT (a scheduled beat), never as wallpaper on slides that did not call for it.

2a. DEDICATED-HOOK-SLIDE SCALE (FIX-1 / FIX-4). On a roughly 30-minute deck (about 35 to 60 slides), the hook stands on its OWN dedicated A4 type-dominant slide 3 to 4 times, and no more: (1) the OPEN verse, (2) one MID reprise after the first proof block, (3) one POST-PROOF reprise after the Wall of Wins / who-says-so block, and (4) the CLOSE reprise as the final substantive slide where the hook graduates into the signature line. On a compressed 10 to 15 minute deck, keep at minimum the OPEN dedicated slide and the CLOSE reprise (2 dedicated slides) and compress the mid reprises. These dedicated A4 hook slides are type-driven (the type IS the slide), not a footer overlay.

2b. CONSECUTIVE-SLIDE CEILING (FIX-1). The hook is NEVER carried on two consecutive slides. Between any two hook appearances there is at least one slide that does not carry the hook. Beyond the 3 to 4 dedicated slides, only light refrains placed where earned are allowed, and the hook appears on no more than roughly 1 slide per 6 across the deck (a HARD CEILING). The hook is not a refrain device stamped low on every composition; that over-stamping is the #1 defect this scale rule exists to kill. The flag `hook_variants.json` carries `hook: true` ONLY on the scheduled beats; every other slide carries no hook overlay.

3. Distribution rule: the hook reprises on its scheduled cadence (open, mid, post-proof, close, plus earned light refrains), never on 2 consecutive slides, and never as a footer on every slide. There must be at least one scheduled refrain candidate near the ladder and close sections, and never more than 2 consecutive ladder or close slides with NO hook nearby on the scheduled beats; this is a cadence-near rule, not a license to stamp the hook on every ladder slide. Record each placement as `{ "slide": N, "section": "...", "variant_used": "...", "after_proof": true|false, "dedicated_slide": true|false, "scheduled_beat": true }`.

4. Write the variants and the placement map into hook_package.json. The Copywriter reads this and places the variants; you own the map, the Copywriter owns the surrounding slide copy.

5. Post-deck Hook Audit (run on the completed slides_copy.md): count occurrences MECHANICALLY (do not estimate; count). The audit is a BANDED check with both a floor and a CEILING, not a floor-only count. On a ~30-minute deck: there must be 3 to 4 DEDICATED A4 hook slides (open + mid + post-proof + close); total hook appearances (dedicated slides plus earned light refrains) should land roughly in the 4 to 8 range and MUST NOT exceed the ceiling. AUTO-FAIL the audit if the hook appears on more than roughly 5 slides as a refrain device beyond the dedicated slides, OR on 2 or more consecutive slides, OR as a footer on every slide (the over-stamping failure). The minimum is the OPEN dedicated slide and the CLOSE reprise; if the deck has fewer than the scheduled dedicated slides, add a dedicated A4 hook slide at the missing scheduled beat (do not pad with footers on already-busy slides).

6. Verify distribution mechanically: the hook lands on its scheduled beats (open, mid, post-proof, close); there are NEVER 2 consecutive slides carrying the hook (hard ceiling); the hook is NOT a footer on every slide; the first occurrence is inside the first 10 to 15%; 3 to 4 dedicated A4 hook slides exist (2 minimum on a compressed deck); and the appearance rate does not exceed roughly 1 per 6 slides across the deck.

7. Verify the closing slide carries the hook (the reprise as the final substantive slide, done as a dedicated A4 slide, not a footer).

8. Write the audit result into hook_package.json: `{ "occurrence_count": N, "dedicated_slide_count": N, "first_occurrence_pct": ..., "closing_carries_hook": true|false, "max_consecutive_hook_slides": N, "over_stamp_fail": true|false, "appearance_rate_per_slide": ..., "verdict": "PASS|FAIL" }`. The verdict is PASS only when the count is within the band (floor met AND ceiling not exceeded), `dedicated_slide_count` is 3 to 4 (2 minimum on a compressed deck), `max_consecutive_hook_slides` is 1 (never 2+), and `over_stamp_fail` is false. If the audit fails on the FLOOR, add a dedicated slide at a missing scheduled beat; if it fails on the CEILING (over-stamping, consecutive slides, or footer-on-every-slide), return the over-stamped slides to the Copywriter to STRIP the hook off them and re-audit.

**Outputs:**
- working/copy/hook_package.json (the variants block, the placement map block, and the audit result block: candidates, scores, owner selection, variants, placement map, audit result, all in one file)

**Hand to:** Slide Copywriter (places the variants per the map) and the QC Specialist -- Presentations (the audit result feeds Phase 1Q criterion 11, the mechanical hook count)

**Failure mode:** If fewer than the scheduled dedicated beats exist in the arc, do NOT pad with wallpaper footers on every slide (that is the over-stamping defect). Add DEDICATED standalone A4 hook slides (a single large headline carrying the hook variant, type-driven, no other body copy) at the missing scheduled beats (open, mid, post-proof, close), and hand those positions to the Copywriter. Re-run the audit. If the audit cannot fit 3 to 4 dedicated slides plus a closing reprise WITHOUT putting the hook on consecutive slides, escalate to the Director: the arc may be too short for the doctrine and the Director adjusts arc_allocation.json. Conversely, if the audit fails on the CEILING (the hook is stamped as a footer on every slide or on consecutive slides), return the over-stamped slides to the Copywriter to STRIP the hook down to the scheduled cadence and re-audit. Reaching a high count by stamping the hook everywhere is a FAIL, not a pass.

---
