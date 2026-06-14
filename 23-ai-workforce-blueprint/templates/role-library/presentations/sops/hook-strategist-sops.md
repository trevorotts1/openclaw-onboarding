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

2. Draw the placement map. The refrain is sung approximately 10x, WOVEN slide to slide through every section, sung the WHOLE WAY THROUGH (not only at the start and the close). First occurrence lands inside the first 10 to 15% of the deck (sing it early; nobody waits to the end of the song to sing Purple Rain). Include: a dedicated A4 hook slide (type-dominant); refrains placed AFTER proof slides (the proof just earned the hook); a reprise as the FINAL substantive slide of the deck. No section without a refrain candidate.

3. Distribution rule: no section without a refrain candidate, and never more than 2 consecutive ladder or close slides without the hook nearby. Record each placement as `{ "slide": N, "section": "...", "variant_used": "...", "after_proof": true|false }`.

4. Write the variants and the placement map into hook_package.json. The Copywriter reads this and places the variants; you own the map, the Copywriter owns the surrounding slide copy.

5. Post-deck Hook Audit (run on the completed slides_copy.md): count occurrences MECHANICALLY (do not estimate; count). Verify the total is >= 7 (minimum floor). Target is ~10x. If count is 7 or 8, identify which sections have no refrain and add standalone refrain slides at those section boundaries before closing the audit as complete.

6. Verify distribution mechanically: no section is missing a refrain candidate; there are never more than 2 consecutive ladder or close slides without the hook nearby; the first occurrence is inside the first 10 to 15%; a dedicated A4 hook slide exists.

7. Verify the closing slide carries the hook (the reprise as the final substantive slide).

8. Write the audit result into hook_package.json: `{ "occurrence_count": N, "first_occurrence_pct": ..., "dedicated_slide": true|false, "closing_carries_hook": true|false, "sections_without_refrain": [...], "max_consecutive_gap": N, "verdict": "PASS|FAIL" }`. If the audit fails, return the specific gap to the Copywriter for a refrain insertion and re-audit.

**Outputs:**
- working/copy/hook_package.json (the variants block, the placement map block, and the audit result block: candidates, scores, owner selection, variants, placement map, audit result, all in one file)

**Hand to:** Slide Copywriter (places the variants per the map) and the QC Specialist -- Presentations (the audit result feeds Phase 1Q criterion 11, the mechanical hook count)

**Failure mode:** If fewer than 7 natural placements exist in the arc, do NOT pad with wallpaper repetitions. Add standalone refrain slides (a single large headline carrying the hook variant, no other body copy) at the section boundaries that lack a refrain candidate, and hand those positions to the Copywriter. Re-run the audit. If the audit still cannot reach 7 occurrences AND a dedicated slide AND a closing reprise, escalate to the Director: the arc may be too short for the doctrine and the Director adjusts arc_allocation.json.

---
