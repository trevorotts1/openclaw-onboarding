# SOPs Mirror -- Offer and Price Strategist

**Source:** presentations/offer-price-strategist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.0 -- PITCHLESS SUPPRESSION GATE (Decision 2A — READ FIRST)

**Hard guard, evaluated before ANY work in this role.** Read `intake.json.pitch_included`:
- **If `pitch_included` is `false` (a PITCHLESS, teaching/content-only deck — first-class):** this role MUST NOT run. Produce NOTHING — no `price_ladder.json`, no `offer_stack.json`, no offer/ladder/anchor/re-pitch arc beats. The Director does not dispatch you, and if you are dispatched anyway you immediately return with `suppressed: true, reason: "pitch_included:false"` and write no artifact. A pitch is NEVER forced onto a pitchless deck. The gate **AF-PITCH-LEAK** (`build_deck.py` `_chk_pitch_leak`) fails the deck if any price/offer/ladder content — including the mere presence of `price_ladder.json` — appears when `pitch_included:false`.
- **If `pitch_included` is `true`:** run normally (SOP 9.1+). The gate **AF-PITCH-MISSING** (`_chk_pitch`, conditional on `pitch_included:true`) then requires the full offer arc (value-stack -> anchor -> price ladder -> re-pitch after FINAL).
- **If `pitch_included` is unset/non-boolean:** the deck has already failed **AF-PITCH-FLAG-UNSET** at intake; do not proceed — the Director must capture the explicit yes/no first.

---

### SOP 9.1 -- Spread Value-Ladder Choreography (ANCHOR -> DROP1/2/3 -> FINAL)

**When to run:** Concurrently with Phase 1 (copy writing), **ONLY when `intake.json.pitch_included:true`** (see SOP 9.0). Must complete before the Slide Copywriter reaches the Price Ladder section.

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
6a. Mark CASE STUDIES between the drops. The GRADUAL doctrine sits a case study ("who says so other than you") between the rungs so the proof rides down with the price. Record in price_ladder.json which slides between the drops carry a case study, and flag to the Director if a long stretch of the ladder has no proof beat between rungs. (The Copywriter writes the case-study copy; you mark where the doctrine requires one.)
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
4a. COMPONENT-CARD + $-CHIP MODEL (FIX-5a). Every offer component gets its OWN slide built as a COMPONENT CARD: the component name as the headline, a one-line benefit, and its OWN $ VALUE CHIP. The $ chip is a consistent reusable template (same shape, same corner, same gold treatment, same placement on every component card) so the cards read as one family across the offer arc. Component cards are SPREAD across the offer section (not crammed into one stack slide), each carrying its named $ value (each on its own card, spread across the offer arc, then callback-proved). Record each component card with `{ "component": "...", "value": 0, "chip": "$X", "own_slide": true }`. (The Slide Copywriter writes the card copy and the Slide Image Creator renders the chip per a consistent template; you specify the value, the chip text, and that each component owns a slide.)
4b. TALLY slide (FIX-5a). After the component cards, one TALLY slide ("Here's Everything You're Getting") sums every component + its $ chip in one grid; the SUM must equal the ANCHOR value (proving the anchor plant). Assert: TALLY total == sum of component chips == anchor_value (within the stated rounding). Record `tally_slide: N` and `tally_total: 0` in offer_stack.json.
5. THE LOWER THE PRICE, THE GREATER THE VALUE (master doctrine, rule 3). Every DROP slide -- or the slide immediately after it -- stacks NEW named value onto the table. The ladder descends in price while the table GROWS in value. Map which named component(s) get added at or right after each DROP:
   - At/after DROP1: name a new value item added to the table.
   - At/after DROP2: name another new value item added.
   - At/after DROP3: name another new value item added.
   Record this in offer_stack.json under `value_additions_by_drop`.
5a. THE ESCALATION RULE -- BIGGER AND BETTER AT EVERY DROP (master doctrine, the red rule made operational). Naming SOME new value at each drop is the floor; this step raises it. The value added at each successive drop must ESCALATE: each rung's addition is a bigger and better promise, bonus, or guarantee than the rung before it, never a token or restated add. Operationally, every entry in `value_additions_by_drop` must satisfy all three:
   - It is a SUBSTANTIVE named deliverable, bonus, or guarantee (a real component the audience can point to), not a vague "and more" or a restatement of value already on the table.
   - It is DISTINCT from every value already added at a prior rung (no re-adding the same component, no re-wording a prior add).
   - It carries a non-trivial `added_value`, so the RUNNING VALUE TOTAL strictly INCREASES at this rung by a non-trivial amount over the prior rung. A drop whose addition is trivial, restated, or merely cosmetic FAILS the escalation rule even though it technically "added" something. (For a non-monetary offer the added_value is a priceless-frame weight per SOP 9.6, not a fabricated dollar figure; the escalation is then judged on the substance and distinctness of the named bonus, never an invented number, per the AF-SRC discipline that bars un-cited external constants. The running total here is an internal pitch figure built from the client-stated stack, not an external-service value.)
5b. THE RUNNING VALUE TOTAL (the on-screen rising line that mirrors the falling price). Maintain a cumulative `running_value_total` that begins at the TALLY total (the proven stack value at the anchor) and INCREASES at every drop by that drop's `added_value`. This climbing total is what the audience watches rise while the price falls; it is the inverse line of the price ladder. Record the running total at each rung in `value_additions_by_drop` as `running_value_total`, and assert it is strictly increasing (TALLY total < total after DROP1 < total after DROP2 < total after DROP3). Every running total is internally consistent with offer_stack.json (it equals the prior total plus that rung's added_value, to the dollar) so the cross-slide number-reconciliation gate (AF-C4) finds no mismatch. The design-system price-typography SOP renders this climbing total beside the struck price so the widening gap is SEEN, not just implied; you supply the numbers, the renderer draws the two opposing lines. The VALUE-GAP slide before FINAL (step 6b) uses the FINAL running total, which is the largest of all.
6. Stripping value to justify a discount is a VIOLATION. A DROP slide must never REMOVE a component to "explain" the lower price. If the run ever shows a component disappearing from the table as the price falls, flag it to the Director as a doctrine violation and refuse to ship the ladder until it is corrected.
6a. PROMISE SLIDE BETWEEN DROPS (FIX-5b; running promise inventory, master doctrine rule 2). Between each pair of drops, place a PROMISE slide that restates the promise just earned, so each drop is paid for by a promise just made (the concern this kills is "promises missing" between drops). Maintain a running PROMISE INVENTORY: each promise made in the teach/offer arc is logged, and at least one promise slide sits between DROP1 and DROP2 and another between DROP2 and FINAL, restating the next promise the audience is buying. Record `promise_slides: [N, ...]` and the `promise_inventory` list in offer_stack.json. (The Copywriter writes the promise copy from the inventory; you mark where the doctrine requires a promise beat.)
6b. VALUE-GAP slide before FINAL (FIX-5). Right before the FINAL price reveal, quantify the value gap on the slide: "Total value [TALLY total] vs your price today." The gap (total stack value minus FINAL price) must be stated on screen before the FINAL number lands. Record `value_gap_slide: N` and `value_gap: 0` (tally_total minus final_price) in offer_stack.json.
7. Verify: a BUILDUP slide must always precede every DROP slide (per SOP 9.1 step 5). If a DROP slide exists without a preceding BUILDUP, flag it so the Copywriter inserts one before it.
8. **(Density-floor overhaul) Reserve the three mandatory pacing beats and record their slots** so they cannot be omitted (the reference failure case had none of them):
   - **PROMISES beat BEFORE the anchor** (`promises_slide`): plant the promise set (the transformations the program delivers) before the first number. People buy promises, not products. (AF-DEN-5.)
   - **A dedicated itemized VALUE-STACK slide BEFORE Drop 1** (`value_stack_slide`): the full stack listed with each component value, summed to a TOTAL that EXCEEDS the anchor, shown before the cheapest prices appear (the proven reference run s57 -> s58 "add it all up"). For a non-monetary offer, the stack is the deliverables list and the frame is the PRICELESS pitch (SOP 9.6), never fabricated dollar values. (AF-DEN-4.)
   - **A 4-to-7-slide RE-PITCH block AFTER the FINAL price** (`re_pitch_slide_range`): recap the full stack, restate the promises, reset the urgency ("next 15 minutes, FINAL_PRICE"), before the send-off (the proven reference run s74-75). A deck that closes on a plain thank-you fails. (AF-DEN-7.)
9. Write the offer_stack.json to working/copy/offer_stack.json. Structure:
   ```json
   {
     "components": [
       {"name": "...", "value": 0, "chip": "$X", "own_slide": true, "value_source": "client_stated|market_estimate|pending"}
     ],
     "total_stack_value": 0,
     "buildup_slide_range": [start_slide, end_slide],
     "promises_slide": N,
     "value_stack_slide": N,
     "re_pitch_slide_range": [start_slide, end_slide],
     "value_additions_by_drop": [
       {"drop": "DROP1", "added_component": "...", "added_value": 0, "running_value_total": 0},
       {"drop": "DROP2", "added_component": "...", "added_value": 0, "running_value_total": 0},
       {"drop": "DROP3", "added_component": "...", "added_value": 0, "running_value_total": 0}
     ]
   }
   ```
   The `running_value_total` at each rung equals the prior rung's running total plus that rung's `added_value`; the first rung's prior total is `tally_total`. Each must strictly exceed the one before it (the escalation rule, step 5a), and each must reconcile to the dollar with `tally_total` and the per-drop `added_value` figures so AF-C4 finds no cross-slide mismatch.

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

**Failure mode (gated AF-NO-COST-OF-INACTION; promoted from a doctrine-gap flag to a HARD GATE).** A deck that reaches the offer section without the cost-of-inaction beat is no longer merely "flagged" -- it AUTO-FAILS. The mechanical gate (`scripts/pitch_engines_check.py::chk_cost_of_inaction`, SOP-PITCH-06 1.2) asserts `price_ladder.json.cost_of_inaction_slide` is present and non-null AND a `COST_OF_INACTION` arc beat is tagged in `slides_copy.md`; either absent = `AF-NO-COST-OF-INACTION` at Phase 1Q + Phase 6. Per the cadence loop (AF-CADENCE, SOP-PITCH-06 1.1) the cost-of-inaction beat must ALSO recur per price-drop rung, not just once. If a non-monetary outcome has a fabricated dollar value attached, that is a fabrication violation -- strip the fake number, run the priceless pitch instead, and notify the Director.

---

### SOP 9.7 -- SP-EXPERT: Expertise Over Charisma and the Ascension Ladder

**When to run:** Concurrently with SOP 9.1 or 9.4, during the offer-design phase, before price_ladder.json is finalized.

**Governing principle (SP-EXPERT):** The offer is won by demonstrated capability, not by charm or enthusiasm. People buy expertise. The entry product (a low-price offer, a free resource, a challenge, a mini-course, or any first transaction) is the buy-in signal: the first rung of the ASCENSION LADDER, the moment the audience self-identifies as a buyer and signals readiness for deeper engagement. The pitch works because the presenter proved they know what they are doing -- through a framework, a result, a specific mechanism, a case study -- before any price was named.

**Inputs:**
- intake.json (ENTRY_PRODUCT if present; OFFER_STACK; FINAL_PRICE; any stated back-end or VIP offer)
- price_ladder.json (draft)
- working/copy/arc_allocation.json (where proof and teaching slides fall relative to the offer)

**Steps:**
1. Review the arc_allocation.json to confirm that at least one of the following appears BEFORE the ANCHOR slide (before the 32% mark): a framework or mechanism slide, a case study or result slide, a white-paper reference, or a "how this works" teaching moment. If none exist before the anchor, flag to the Director: the audience has not yet seen proof of expertise. The ANCHOR must land AFTER the audience has reason to believe the number is credible.
2. Identify the ENTRY_PRODUCT in intake.json. This may be: a free lead magnet, a low-price challenge, a mini-course, a strategy session, or a trial tier. If none exists and the offer is a single core-product sale, note that there is no entry product; skip steps 3 and 4 and proceed to step 5.
3. If an ENTRY_PRODUCT exists: encode it as ASCENSION_RUNG_1 in price_ladder.json. Record:
   - `entry_product_name`: the name of the entry product
   - `entry_product_price`: its price (may be 0 for a free offer)
   - `entry_product_role`: "buy-in signal -- first rung of the ascension ladder"
   - `ascension_path`: a brief description of the journey from entry product to core offer to VIP (e.g., "Challenge -> Enrollment System -> VIP Coaching Pod")
   The Slide Copywriter will use this to frame the entry product in copy as the doorway, not the destination.
4. Verify the ascension logic is consistent with the value ladder. The entry product price must be below FINAL_PRICE. If VIP_TIER exists, the ascension path is: ENTRY_PRODUCT (if any) -> GA (FINAL_PRICE) -> VIP. Record this in price_ladder.json as `ascension_ladder_verified: true`.
5. Review the offer section slides in arc_allocation.json. Confirm that the proof of expertise (case studies, results, mechanism slides) is woven into the teach sections BEFORE the offer reveals, not dumped into the offer section alone. If all proof is back-loaded to the offer section, flag it to the Director: "Proof arrives after the audience needs to believe. Recommend redistributing at least one proof beat to the teach sections." (This flag is advisory to the Copywriter and Director; it does not block the ladder build.)
6. Write a one-line SP-EXPERT assertion to price_ladder.json:
   ```json
   "sp_expert": {
     "expertise_before_price": true,
     "entry_product_name": "...",
     "entry_product_price": 0,
     "entry_product_role": "buy-in signal -- first rung of the ascension ladder",
     "ascension_path": "...",
     "ascension_ladder_verified": true
   }
   ```
   If no entry product exists, set `entry_product_name: null` and `ascension_ladder_verified: false` with a note: "No entry product in intake. Single-offer close."
7. Pass the `sp_expert` block to the Director with the rest of price_ladder.json. The QC Specialist will check that proof appears before the offer section (copy QC criterion: light pitch woven, appetizer not dinner).

**Outputs:**
- working/copy/price_ladder.json (with the `sp_expert` block appended)

**Hand to:** Director (who routes to the Slide Copywriter alongside price_ladder.json)

**Failure mode:** If the arc has zero proof or teaching content before the offer section -- i.e., the deck goes straight from intro to pitch with no expertise demonstrated -- that is a doctrine violation (GP-12, the pitch is where decks die). Flag it to the Director as a HIGH-severity gap before the Copywriter begins. Do not invent proof; instruct the Director to obtain it from the client via PROOF_ASSETS in intake.json.

---

### SOP 9.8 -- The Guarantee (required component 6) and the Scarcity Factor (required component 7)

**When to run:** Concurrently with SOP 9.1 or 9.4, before price_ladder.json is finalized. Both are required components of every deck (master SOP Section 4.4, rule 21).

**Inputs:**
- intake.json (any client-stated guarantee, refund policy, results promise; `VIP_SPOTS`, real cohort dates, real enrollment caps, real expiry windows)
- master SOP Section 5.4 (the four guarantee types) and Section 4.3 rule 21

**Steps:**
1. **Select the GUARANTEE type with the client (the deck must carry one).** Choose one of the four (master Section 5.4): Unconditional (any-reason refund), Conditional (do-the-work clause, allows a bolder promise), Anti-guarantee (all sales final, framed as exclusivity), or Implied (performance-based). For a service business wary of refunds, the operator-preferred frame is the SERVICE GUARANTEE: "if you do not get the result, your next 30 days is on us" or "five more sessions until your breakthrough." It reverses risk without writing checks. If intake states no guarantee, propose the service-guarantee frame and flag to the Director for the client to confirm; never ship a deck with no guarantee beat.
2. Record the guarantee in price_ladder.json:
   ```json
   "guarantee": {
     "type": "unconditional|conditional|anti|implied|service",
     "statement": "one bold sentence the guarantee slide carries",
     "guarantee_felt_frame": "the named, felt, client-specific stake the guarantee promises (e.g. 'your next 30 days is on us', 'five more sessions until your breakthrough') -- REQUIRED so the guarantee is one they can FEEL, not a bare refund template",
     "conditional_logic": "the do-the-work or eligibility clause, or null",
     "positioned_after_final_price": true,
     "source": "client_stated|strategist_proposed"
   }
   ```
   The `guarantee_felt_frame` is gate-checked: a guarantee whose `statement` reduces to a generic refund-template phrase (money-back / 30-day / refund / satisfaction guaranteed / no-questions-asked) with no `guarantee_felt_frame` AUTO-FAILS `AF-GUARANTEE-GENERIC` (`scripts/pitch_engines_check.py::chk_guarantee_generic`, SOP-PITCH-06 1.3). The mechanical anti-generic half is the hard trigger; the felt-vs-generic quality VERDICT is scored by Copy-QC and logged to `copy_qc_report.json`. A guarantee they can feel is required, not a money-back line.
3. **Define the SCARCITY FACTOR for the close (real only).** Set the real constraint the close will use: a real spot cap (`VIP_SPOTS`), a real cohort start date, or a real expiry window (the proven deck used a true 15-minute action window). Record:
   ```json
   "scarcity": {
     "type": "spot_cap|cohort_date|expiry_window",
     "real_value": "the true number / date / window",
     "source": "client_stated|null"
   }
   ```
   If no real constraint exists, do NOT invent one. Set `scarcity.real_value: null`, flag to the Director that the client must supply a real constraint, and warn that fabricated scarcity is a Devil's-Advocate BLOCKING flag. A real scarcity beat is required in the close; a fabricated one is forbidden.
4. Pass both blocks to the Director with price_ladder.json. The Slide Copywriter writes the guarantee slide (after the final price) and the scarcity beat (in the close) from these blocks; the QC Specialist checks their presence (copy QC criteria 20 and 21).

**Outputs:**
- working/copy/price_ladder.json (with the `guarantee` and `scarcity` blocks)

**Hand to:** Director (routes to Slide Copywriter and QC Specialist)

**Failure mode:** If the client provides neither a guarantee nor a willingness to use the service-guarantee frame, flag to the Director and halt the offer finalization until resolved (the deck cannot ship without a guarantee). If no real scarcity constraint exists, the close ships without scarcity ONLY on explicit owner sign-off; never substitute a fabricated cap or countdown.

---

### SOP 9.9 -- Re-Pitch Choreography (4 to 7 slides AFTER the FINAL price)

**When to run:** Concurrently with SOP 9.1 or 9.4, after the FINAL price reveal is placed. This is the genuinely MISSING structural beat (FIX-7): a deck that reveals the FINAL price and then simply ends is incomplete. The re-pitch sits AFTER the FINAL price and BEFORE the hook-reprise close (master arc: after section I scarcity, before section J hook callback).

**Inputs:**
- price_ladder.json (FINAL price, anchor value, callback, drops with earned reasons)
- offer_stack.json (component cards + $ chips, tally total, value gap, promise inventory)
- price_ladder.json guarantee + scarcity blocks (SOP 9.8)
- arc_allocation.json (the post-FINAL slide range)

**Steps:**
1. Author a named RE-PITCH MOVEMENT of 4 to 7 slides that fires AFTER the FINAL price and BEFORE the hook reprise. The movement re-sells the whole offer one more time at the moment of decision; it does not introduce new value, it RECAPS and RESETS what was already earned. The seven beats (use 4 to 7; a ~30-min deck uses all seven):
   1. FULL RECAP TABLE -- "Here's Everything You Get": every component card + its $ value + checkmarks in one grid (reuse the component-card $ chips from offer_stack.json).
   2. VALUE GAP RESTATED -- the total stack value (tally_total) vs the FINAL price, restated as the gap (reuse value_gap from offer_stack.json).
   3. PROMISES RE-LISTED -- the promise inventory (offer_stack.json promise_inventory) re-listed, so the audience sees every promise they are buying.
   4. GUARANTEE RESTATED -- the guarantee from SOP 9.8 restated (the service-guarantee frame, e.g. "your next 30 days is on us").
   5. OBJECTION KILLS -- the top 2 to 3 objections answered (from intake objections; never fabricated).
   6. RESET URGENCY / SCARCITY -- the real scarcity from SOP 9.8 re-armed (the real 15-minute window, the real spot cap, the real cohort date); REAL constraints only, never fabricated.
   7. FINAL CTA + join URL -- the call to action with the real join URL, then the deck hands to the hook-reprise close (section J).
2. Record the re-pitch block in price_ladder.json:
   ```json
   "re_pitch": {
     "present": true,
     "slide_range": [start_slide, end_slide],
     "slide_count": 0,
     "beats": ["recap_table", "value_gap", "promises", "guarantee", "objection_kills", "reset_scarcity", "final_cta"],
     "after_final_price": true,
     "before_hook_reprise": true
   }
   ```
3. Verify: the re-pitch sits AFTER the FINAL price slide and BEFORE the hook-reprise close; slide_count is 4 to 7; the recap table reuses the component cards and $ chips (no new value invented); the value gap and promises trace to offer_stack.json; the guarantee and scarcity trace to SOP 9.8; objection kills trace to intake (zero fabrication). A deck whose FINAL price is revealed and then goes straight to the close FAILS this SOP.

**Outputs:**
- working/copy/price_ladder.json (with the `re_pitch` block)

**Hand to:** Director (who routes to the Slide Copywriter to write the re-pitch copy and to the QC Specialist, who checks re-pitch presence as copy QC criterion 23)

**Failure mode:** If there is no room in arc_allocation.json for a 4 to 7 slide re-pitch after the FINAL price, flag to the Director that the arc is too thin for the post-price re-pitch (FIX-8 close-density) and request the slides. Never skip the re-pitch to save slides; a price reveal with no re-pitch is an incomplete close. Never invent new value, new promises, or fabricated scarcity inside the re-pitch; it recaps what was already earned.

---

