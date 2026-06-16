# SOPs Mirror -- Offer and Price Strategist

**Source:** presentations/offer-price-strategist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Spread Value-Ladder Choreography (ANCHOR -> DROP1/2/3 -> FINAL)

**When to run:** Concurrently with Phase 1 (copy writing). Must complete before the Slide Copywriter reaches the Price Ladder section.

**Inputs:**
- intake.json (FINAL_PRICE, payment_plan if any, stated_anchor if client provided one)
- arc_allocation.json (slide count and price ladder section slide range)

**Steps:**
1. Read FINAL_PRICE from intake.json. If no FINAL_PRICE is present, stop immediately and notify the Director. Do NOT invent a price.
2. Set the ANCHOR. The ANCHOR is a VALUE anchor, not a price, and it is NOT a drop. It is a value plant placed mid-teach inside Secret #1 or #2 (around the 32% mark of the deck), establishing what a system like this is WORTH, and it carries the explicit memory hook in copy and presenter note: "Remember this number. Hold onto it. Keep watching." Rule: ANCHOR_VALUE must be >= 3x the FINAL real buy price and must sit above the highest value-ladder rung. If the client has stated an anchor in intake.json, use it IF it satisfies this rule. If the stated anchor is < 3x FINAL_PRICE, flag the discrepancy to the Director and propose a compliant anchor. Record the source: `anchor_source: "client_stated"` or `anchor_source: "strategist_proposed"`.
3. Build the SPREAD VALUE LADDER. The proven structure (the proven 75-slide reference run) walks a VALUE ladder down -- $[ANCHOR] -> $[DROP1] -> $[DROP2] -> $[DROP3] (illustrative round rungs -- substitute your DISCOVERY VARIABLES) -- spread across the deck, then SHATTERS it with the real price reveal. The rungs sit at approximately these percentages of the total deck slide count:
   - ANCHOR: ~32% mark (value plant with memory hook, mid-teach, NOT a drop)
   - DROP1: ~47% mark ("because you showed up live")
   - DROP2: ~68% mark ("because you believed")
   - DROP3: ~87% mark ("because you stayed")
   - FINAL: ~97% mark (the real buy price, below the entire ladder, before the CTA)
   Calculate the target slide numbers using the formula: target_slide = round(slide_count_final x percentage).
   **(Density-floor overhaul) The 8-slide MINIMUM-GAP FLOOR overrides the percentages.** After computing the percentage-based target slides, verify every ADJACENT pair (ANCHOR->DROP1, DROP1->DROP2, DROP2->DROP3, DROP3->FINAL) is at least 8 slides apart, computed against the FULL deck count. If any gap is under 8 (the reference failure case defect: $[ANCHOR] s32 -> $[DROP1] s34 -> an off-ladder rung s37, gaps of 2 and 3), the percentages have crammed the ladder; flag the Director to lengthen the offer window or the deck and re-space. The floor wins over the percentages. The proven reference run's gaps are 11/16/14/8 (the AF-DEN-1 reference). The ANCHOR must land in the 25-45% depth band (AF-DEN-2), never the back third.
   **(Density-floor overhaul) Use round doctrinal numbers; flag off-ladder rungs.** The doctrinal five-rung ladder is $[ANCHOR] / $[DROP1] / $[DROP2] / $[DROP3] / FINAL with ROUND numbers. An off-ladder, non-round number (the exact defect carried over in the reference failure case; it should snap to the nearest round rung) is flagged to the Director, not silently shipped. Scale the rungs to the client's real anchor, keeping them round and strictly decreasing. Never fabricate the client's prices; if the client has not set them, mark `[CLIENT TO SUPPLY]` and re-sequence the doctrine onto their real numbers when supplied.
4. Assign a value to each rung and the real price at FINAL. Rules:
   - ANCHOR value > DROP1 value (the anchor is the ceiling the ladder descends from)
   - DROP1 value > DROP2 value > DROP3 value (the VALUE ladder is strictly decreasing)
   - DROP3 value > FINAL real buy price (the real price sits BELOW the lowest ladder rung for maximum contrast)
   - No two rung values may be equal.
   - Each rung carries a stated EARNED REASON (showed up live / believed / stayed). A drop with no reason is a discount, not a reward.
   - Drops should feel meaningful (not $1 reductions). Use the drop-percentage bands as guidance for the VALUE rungs: DROP1 = 60-70% of the anchor, DROP2 = 45-55%, DROP3 = 35-45%, then the FINAL real price lands far below (the proven deck used the 20-30% band region as the contrast floor before revealing $47 / $97).
5. Place a mandatory BUILDUP before every DROP. Each of DROP1, DROP2, DROP3 is immediately preceded by one emotional A1-archetype buildup slide (future-pacing or recognition, e.g. "Imagine this running tonight," "You didn't leave. That tells me everything."). Record each buildup slide number in price_ladder.json. A DROP with no preceding BUILDUP is invalid; flag it.
6. Place the CALLBACK in the offer section. When the full stack total is revealed, one slide explicitly closes the loop opened by the ANCHOR memory hook: "I told you to remember that number. Here it is." Record the callback slide number.
7. If the client has a payment plan, add a PAYMENT_PLAN entry after FINAL: the monthly payment equivalent of FINAL_PRICE, expressed as "N payments of $X."
8. Write the full ladder to working/copy/price_ladder.json. Structure:
   ```json
   {
     "deck_slug": "...",
     "final_price": 0,
     "anchor_value": 0,
     "anchor_source": "client_stated|strategist_proposed",
     "anchor_min_ratio_satisfied": true,
     "anchor_memory_hook": "Remember this number. Hold onto it. Keep watching.",
     "callback_slide": N,
     "callback_line": "I told you to remember that number. Here it is.",
     "payment_plan": null,
     "rungs": [
       {"rung": "ANCHOR", "target_slide": N, "value": 0, "is_drop": false, "buildup_slide": null, "memory_hook": true, "label": "What a system like this is worth"},
       {"rung": "DROP1", "target_slide": N, "value": 0, "is_drop": true, "buildup_slide": N, "reason": "because you showed up live"},
       {"rung": "DROP2", "target_slide": N, "value": 0, "is_drop": true, "buildup_slide": N, "reason": "because you believed"},
       {"rung": "DROP3", "target_slide": N, "value": 0, "is_drop": true, "buildup_slide": N, "reason": "because you stayed"},
       {"rung": "FINAL", "target_slide": N, "price": 0, "is_drop": false, "below_ladder": true, "window_minutes": 15, "label": "Your investment today"}
     ]
   }
   ```
9. Verify the VALUE ladder is strictly decreasing: assert ANCHOR > DROP1 > DROP2 > DROP3, and assert DROP3 > FINAL real price (FINAL sits below the ladder). If any violation exists, fix it before proceeding.
10. Verify anchor_value >= 3 x final_price. If not, flag and fix.
11. Verify every DROP has a buildup_slide and an earned reason, and that the callback_slide is set inside the offer section. If any is missing, fix or flag.

**Outputs:**
- working/copy/price_ladder.json (complete, verified)

**Hand to:** Director (who notifies the Slide Copywriter that price_ladder.json is ready)

**Failure mode:** If FINAL_PRICE is 0 or null in intake.json, halt. Send this message to the Director: "Price ladder cannot be built without FINAL_PRICE. Awaiting client confirmation." Log the halt in run_ledger.json.

---

### SOP 9.2 -- Offer Stack and Value-Anchor Construction

**When to run:** Concurrently with SOP 9.1 -- after ANCHOR_PRICE is set, immediately build the offer stack narrative.

**Inputs:**
- intake.json (offer_components: list of what is included in the offer)
- price_ladder.json (DROP prices for each drop point)
- master SOP Section 4.2 (value anchoring)

**Steps:**
1. Extract offer_components from intake.json. If the client did not list components, flag to the Director and use a single-component entry: `[OFFER COMPONENTS PENDING -- client must supply]`.
2. For each offer component, estimate a standalone VALUE. This value must come from ONE of: (a) client-stated value in intake.json, (b) a reasonable market rate the Director has approved, or (c) `[VALUE PENDING]`. Never invent a value.
3. Calculate the TOTAL STACK VALUE: sum of all component values. This is the number used in the ANCHOR+BUILDUP narrative (the cumulative value buildup before the first DROP).
4. Write the stack buildup sequence. This is a series of slides (typically 3-8 slides in the Offer Stack section) that:
   a. Introduces each component one at a time.
   b. Shows the standalone value of each component.
   c. Runs a running total: "So far that's $X in value..."
   d. Builds to the TOTAL STACK VALUE.
   e. Frames: "You could pay [TOTAL_STACK_VALUE] for this... but today it's not [TOTAL_STACK_VALUE]."
5. THE LOWER THE PRICE, THE GREATER THE VALUE (master doctrine, rule 3). Every DROP slide -- or the slide immediately after it -- stacks NEW named value onto the table. The ladder descends in price while the table GROWS in value. Map which named component(s) get added at or right after each DROP:
   - At/after DROP1: name a new value item added to the table.
   - At/after DROP2: name another new value item added.
   - At/after DROP3: name another new value item added.
   Record this in offer_stack.json under `value_additions_by_drop`.
6. Stripping value to justify a discount is a VIOLATION. A DROP slide must never REMOVE a component to "explain" the lower price. If the run ever shows a component disappearing from the table as the price falls, flag it to the Director as a doctrine violation and refuse to ship the ladder until it is corrected.
7. Verify: a BUILDUP slide must always precede every DROP slide (per SOP 9.1 step 5). If a DROP slide exists without a preceding BUILDUP, flag it so the Copywriter inserts one before it.
8. **(Density-floor overhaul) Reserve the three mandatory pacing beats and record their slots** so they cannot be omitted (the reference failure case had none of them):
   - **PROMISES beat BEFORE the anchor** (`promises_slide`): plant the promise set (the transformations the program delivers) before the first number. People buy promises, not products. (AF-DEN-5.)
   - **A dedicated itemized VALUE-STACK slide BEFORE Drop 1** (`value_stack_slide`): the full stack listed with each component value, summed to a TOTAL that EXCEEDS the anchor, shown before the cheapest prices appear (the proven reference run s57 -> s58 "add it all up"). For a non-monetary offer, the stack is the deliverables list and the frame is the PRICELESS pitch (SOP 9.6), never fabricated dollar values. (AF-DEN-4.)
   - **A 4-to-7-slide RE-PITCH block AFTER the FINAL price** (`re_pitch_slide_range`): recap the full stack, restate the promises, reset the urgency ("next 15 minutes, FINAL_PRICE"), before the send-off (the proven reference run s74-75). A deck that closes on a plain thank-you fails. (AF-DEN-7.)
9. Write the offer_stack.json to working/copy/offer_stack.json. Structure:
   ```json
   {
     "components": [
       {"name": "...", "value": 0, "value_source": "client_stated|market_estimate|pending"}
     ],
     "total_stack_value": 0,
     "buildup_slide_range": [start_slide, end_slide],
     "promises_slide": N,
     "value_stack_slide": N,
     "re_pitch_slide_range": [start_slide, end_slide],
     "value_additions_by_drop": [
       {"drop": "DROP1", "added_component": "...", "added_value": 0},
       {"drop": "DROP2", "added_component": "...", "added_value": 0},
       {"drop": "DROP3", "added_component": "...", "added_value": 0}
     ]
   }
   ```

**Outputs:**
- working/copy/offer_stack.json

**Hand to:** Director (who combines with price_ladder.json and passes both to the Slide Copywriter)

**Failure mode:** If intake.json has no offer components at all, write offer_stack.json with a single component `[FULL OFFER PACKAGE -- components pending]` and a single value `[PENDING]`. Flag to the Director. If a DROP would have to strip value to justify itself (no new value available to stack), HALT and escalate: the master doctrine forbids discounting by stripping.

---

### SOP 9.3 -- Cross-Slide Numeric Consistency and Price Validation Gate

**When to run:** After slides_copy.md is completed by the Slide Copywriter -- this is a BLOCKING QC gate. The Phase 1Q QC gate should not run until this validation passes. Also run again after any copy revision.

**Inputs:**
- working/copy/slides_copy.md (completed by Slide Copywriter)
- working/copy/price_ladder.json
- working/copy/offer_stack.json

**Steps:**
1. Extract every numeric value from slides_copy.md that appears to be a price, value, or count. Write the extraction list to working/copy/numeric_audit.txt. Include: slide number, field (HEADLINE / SUBHEAD / BODY), the numeric value, and the context sentence.
2. For every price in numeric_audit.txt, verify against price_ladder.json:
   a. Does this price match a drop price or the anchor price in price_ladder.json?
   b. Is this price on the correct slide (within +/- 1 slide of the target_slide in price_ladder.json)?
   c. If the same price appears on multiple slides: do all appearances show the same value?
3. For every component value in numeric_audit.txt, verify against offer_stack.json:
   a. Does this value match the component's value in offer_stack.json?
   b. Is the running total on each buildup slide arithmetically correct?
4. For the total stack value: verify that TOTAL_STACK_VALUE matches the sum of all component values in offer_stack.json (to the dollar -- no rounding discrepancy).
5. For the anchor price: verify ANCHOR_PRICE appears correctly on the "anchoring" slide before Drop 1 and matches price_ladder.json exactly.
6. Record every discrepancy in numeric_audit.txt as `DISCREPANCY: slide N shows $X but price_ladder.json says $Y`.
7. If ANY discrepancy exists: return numeric_audit.txt to the Director with a flag: "Numeric consistency gate FAILED -- [N] discrepancies found. See numeric_audit.txt. Copywriter must fix before Phase 1Q."
8. If ZERO discrepancies: write `NUMERIC CONSISTENCY GATE: PASSED` to numeric_audit.txt. Notify the Director.

**Outputs:**
- working/copy/numeric_audit.txt (pass or fail with discrepancy list)

**Hand to:** Director (gate result determines whether Phase 1Q can proceed)

**Failure mode:** If slides_copy.md contains no numeric values at all (e.g., all prices are `[PRICE PENDING]` placeholders), the gate result is `INCONCLUSIVE -- all prices are pending`. Notify the Director. Phase 1Q can proceed with a note that numeric consistency must be re-validated after prices are confirmed.

---

### SOP 9.4 -- PRICE_MODE straight (one-reveal sequence)

**When to run:** Concurrently with Phase 1, when intake.json has `PRICE_MODE: "straight"` (one price, stated once). Replaces the SPREAD VALUE LADDER of SOP 9.1; the cross-slide consistency gate (SOP 9.3) and the no-strip rule (SOP 9.2) still apply.

**Inputs:**
- intake.json (FINAL_PRICE, offer_components, VIP_TIER if any, payment_plan if any)
- arc_allocation.json (offer section slide range)
- master SOP Section 5.5 ("Mode straight")

**Steps:**
1. Read FINAL_PRICE from intake.json. If absent, halt and notify the Director (do NOT invent a price).
2. Build the sequence in this exact order (master Section 5.5 straight mode):
   a. **STACK:** present the value stack one named component per slide, each `Name + $X value` (SOP 9.2 rules).
   b. **ANCHOR with memory hook:** land the TOTAL STACK VALUE as the value reality check, carrying the explicit memory hook: "Remember this number. Hold onto it. Keep watching." The anchor value must be >= 3x FINAL_PRICE.
   c. **ONE reveal:** a single price reveal slide, "all of that, for FINAL_PRICE." There is no ladder; the price is stated once.
   d. **CTA:** the call to action immediately after the reveal.
   e. **Bonuses stacked AFTER the price:** bonuses are revealed AFTER the price reveal to widen the value gap, never before (each named, each with a standalone value).
   f. **VIP side-by-side:** if VIP_TIER exists, present it WITH the final price as a two-option close (GA | VIP side by side), per SOP 9.5 -- never after the close.
3. The straight mode still answers cost-vs-value explicitly in the offer section (SOP 9.6).
4. Write the sequence into price_ladder.json with `price_mode: "straight"`, the single `final_price`, the `anchor_value` and its memory hook, the `reveal_slide`, the `cta_slide`, the bonus slide list (all after the reveal), and the VIP block if present.
5. Verify: exactly ONE price reveal slide exists; no DROP rungs are present in straight mode; bonuses are all positioned AFTER the reveal slide; anchor_value >= 3x final_price; no component is stripped to justify anything.

**Outputs:**
- working/copy/price_ladder.json (with `price_mode: "straight"`)

**Hand to:** Director (who notifies the Slide Copywriter)

**Failure mode:** If FINAL_PRICE is missing, halt and notify the Director ("Straight-mode reveal cannot be built without FINAL_PRICE"). If any bonus is positioned before the reveal slide, flag it as a sequence violation and correct before shipping.

---

### SOP 9.5 -- VIP Tier (two-option close)

**When to run:** Concurrently with SOP 9.1 or 9.4, whenever intake.json has `VIP_TIER: true`.

**Inputs:**
- intake.json (VIP_TIER, VIP_PRICE, VIP_SPOTS, VIP contents)
- price_ladder.json (the FINAL real buy price)
- master SOP Sections 3.1 Q5 and 5.5 (VIP rules)

**Steps:**
1. Read VIP_TIER, VIP_PRICE, VIP_SPOTS, and the VIP contents from intake.json. If VIP_TIER is false or absent, this SOP does not run.
2. Present the VIP option WITH the final price as a two-option close: GA price and VIP price SIDE BY SIDE on the same moment of decision. The VIP is NEVER presented after the close, and never as a separate later pitch.
3. Spot counts are REAL scarcity only. Use VIP_SPOTS exactly as the client stated it. If VIP_SPOTS is missing or the client cannot state a real number, do NOT invent one -- present VIP without a spot count and flag to the Director. Fabricated scarcity is forbidden (master Section 5.4).
4. List the VIP contents as named items with values, the same way the GA stack is built (SOP 9.2). VIP value is GA value PLUS the named VIP additions; it never strips GA value.
5. Record the VIP block in price_ladder.json:
   ```json
   "vip": {
     "present": true,
     "vip_price": 0,
     "vip_spots": 0,
     "vip_spots_source": "client_stated",
     "side_by_side_with_final": true,
     "added_components": [{"name": "...", "value": 0}]
   }
   ```
6. Verify: the VIP slide shares the decision moment with the final price (side_by_side_with_final = true), spot count is client-stated (never invented), and VIP value >= GA value.

**Outputs:**
- working/copy/price_ladder.json (with the `vip` block)

**Hand to:** Director (who notifies the Slide Copywriter)

**Failure mode:** If VIP_SPOTS is fabricated or VIP is positioned after the close, that is a violation; flag it and correct before shipping. If VIP_PRICE is missing, halt the VIP block and notify the Director.

---

### SOP 9.6 -- Priceless Pitch / Cost-vs-Value

**When to run:** Concurrently with Phase 1, for EVERY deck. The cost-vs-value answer is mandatory in every offer section; the priceless elevation is used specifically when the offer outcome is non-monetary.

**Inputs:**
- intake.json (offer outcome, whether the offer produces measurable money, LTV inputs if monetary)
- master SOP Section 4.3 rule 6 (cost versus value, the priceless pitch)

**Steps:**
1. Determine whether the offer outcome is MONETARY (produces measurable money for the buyer, e.g. enrollments, revenue) or NON-MONETARY (a transformation, peace, confidence, a better relationship).
2. Every deck must explicitly answer BOTH questions in the offer section: what is the COST of NOT taking action (cost of inaction), and what is the VALUE of taking action.
3. **If MONETARY:** do the math on screen. Run cost-of-inaction vs value-of-action with real figures (illustrative -- substitute your DISCOVERY VARIABLES: LTV: 1 client = $[ANNUAL_VALUE]/yr; 3 = 3x that; payback period). These figures come from intake.json or client-supplied numbers, never invented.
4. **If NON-MONETARY:** NEVER fabricate dollar values for the outcome. Run the cost-of-inaction vs value-of-action contrast in real terms, then run the AmEx-style PRICELESS elevation (master rule 6): name the small real costs (the "hot dog $5, parking $20" frame) and then elevate the actual outcome ABOVE money -- "priceless." Elevate the outcome above money; do not slap a fake dollar figure on it.
5. Record the cost-vs-value treatment in price_ladder.json:
   ```json
   "cost_vs_value": {
     "outcome_type": "monetary|non_monetary",
     "cost_of_inaction_slide": N,
     "value_of_action_slide": N,
     "priceless_pitch_used": false,
     "monetary_math_source": "client_stated|null"
   }
   ```
6. Verify: both the cost-of-inaction and value-of-action are present in the offer section; for non-monetary outcomes no fabricated dollar value exists and the priceless elevation is used; for monetary outcomes the math traces to client-supplied figures.

**Outputs:**
- working/copy/price_ladder.json (with the `cost_vs_value` block)

**Hand to:** Director (who routes to the Slide Copywriter and the QC Specialist)

**Failure mode:** If a deck reaches the offer section without answering BOTH cost-of-inaction and value-of-action, flag it as a doctrine gap. If a non-monetary outcome has a fabricated dollar value attached, that is a fabrication violation -- strip the fake number, run the priceless pitch instead, and notify the Director.

---
