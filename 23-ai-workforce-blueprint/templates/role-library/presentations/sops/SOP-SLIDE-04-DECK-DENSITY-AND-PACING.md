# SOP-SLIDE-04: DECK DENSITY AND PACING

**Cluster:** Slide-Craft Rules
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 4 Slide Math, Section 4.2 the proven flow, Section 5.5 the price sequence)
**Owning role at write time:** Director of Presentations (arc_allocation.json minimum-count enforcement)
**Enforced at the gate by:** QC Specialist - Presentations (auto-fail AF-DENSITY, below)
**Gold-standard numbers:** Lyric 75-slide deck (lyric-principles.md): ladder at s24/35/51/65/73, gaps 11/16/14/8, Wall of Wins 5 slides before offer, re-pitch s74-75.
**Status:** Reference SOP, RECONCILED with the live gate. The density/pacing protection is ALREADY WIRED in qc-specialist-presentations.md as auto-fail AF-C7 (the gradual-drop choreography, four sub-conditions: SPREAD / EARNED+BUILT-UP / ADDS-value / FINAL-below-ladder) plus copy QC criteria c17 (ladder integrity), c19 (Wall-of-Wins framing), c23 (re-pitch presence), and c24 (close density and Wall spacing), backed by the Offer Price Strategist SOP 9.1/9.2/9.9 gates. The draft codes AF-DEN-1..8 map onto AF-C7 + c17 + c19 + c23 + c24. IMPORTANT reconciliation: this SOP proposes an absolute "8-slide minimum gap"; the LIVE AF-C7 enforces "no 2 drops within 2 slides" plus the percentage placement (~47/68/87%). The 8-slide figure is the Lyric DOCTRINAL TARGET (gaps 11/16/14/8); the 2-slide minimum is the hard auto-fail floor. See sops/SOP-PITCH-01-SLOW-DROP-PROCESS.md Section 2 rule 2 for the authoritative reconciliation. Do NOT add a contradictory hard 8-slide auto-fail without the Director adjusting AF-C7. Do NOT add a parallel AF-DEN namespace.

---

## 1. PURPOSE

A slow drop is a reward for staying, earned across minutes of narrative. The Corey deck crammed the entire offer into the back third: the price beats landed 2 and 3 slides apart ($5,000 to $2,500 to $1,200 with no value stack, no promises, no re-pitch), and the Wall of Wins sat 3 slides before the offer. Lyric's gold standard spreads the ladder across the back two-thirds with gaps of 11, 16, 14, and 8 slides, a build-up before every drop, and the Wall of Wins exactly 5 slides before the offer. The reason Corey's compressed: the offer-price-strategist built the ladder by PERCENTAGE of slide count with no absolute minimum-gap floor, so when the arc allocated the offer to a narrow window, the percentages produced a cliff. This SOP adds hard minimum counts and a hard minimum-gap floor, computed against the FULL deck, so density and pacing are checkable, not vibes.

---

## 2. THE HARD RULE

1. **Minimum gap between any two price beats: 8 slides.** Anchor to Drop 1, Drop 1 to Drop 2, Drop 2 to Drop 3, Drop 3 to Final, every adjacent pair, at least 8 slides apart. Computed against the FULL deck slide count, never against the offer window only. (Lyric: 11/16/14/8.)
2. **The value anchor lands near the one-third mark**, not the back third. Target 30 to 40% depth. (Lyric: s24 = 32%.) The anchor is a value-plant ("remember this number"), not a drop.
3. **A dedicated BUILDUP slide immediately precedes every DROP.** No price ever drops cold. (Lyric: s34, s50, s64, s72.)
4. **A mandatory itemized value-stack slide precedes Drop 1**, and the stack total is proven to exceed the anchor before the cheapest prices appear. (Lyric: s57 stack, s58 "add it all up".)
5. **A promises beat precedes the anchor.** Promises are planted before the first number (people buy promises, not products).
6. **The Wall of Wins sits about 5 slides before the final offer** (4 to 6 acceptable), with a build-up run between, never jammed 2 slides against it. (Lyric: s68 -> s73.) See the Wall of Wins SOP in the offer cluster for its content rules; this SOP enforces only its SPACING.
7. **A 4-to-7-slide re-pitch block follows the FINAL price** (recap the stack, restate the promises, reset the urgency), before the send-off. (Lyric: s74-75.) A deck that closes on a plain thank-you with no re-pitch fails.
8. **Minimum slide counts per section** (scaled to deck length; these are floors for a ~25-to-30-minute deck, roughly 60 to 80 slides):
   - Hook + open: >= 5
   - Authority / who-listens: >= 4
   - Teaching arc (the Secrets / methodology): >= 18, with each mandatory split honored (a value trio = 4 slides, four pains = 4 slides, a gap+reframe = 2 slides; see SOP-SLIDE-01)
   - Proof (incl. the single Wall of Wins): >= 4
   - Offer + ladder + stack + promises: >= 14, spread per the 8-slide-gap floor
   - Re-pitch + close: >= 5
   A deck materially below these floors is too thin to pace a slow drop and fails.
9. **Total length:** a deck that is more than ~10 slides below the section floors summed (a thin deck that cannot space its drops) is rejected; the Director adds slides until the gaps and floors are satisfiable.

---

## 3. THE ENFORCEMENT CHECK (what auto-fails the deck)

**Auto-fail code AF-DENSITY. Checked on arc_allocation.json and slides_copy.md at Phase 1Q, and on slide order at Phase 6. Triggers, any one of which fails the DECK:**

| Trigger | How it is detected | Failure message |
|---|---|---|
| DEN-1: Any two adjacent price beats fewer than 8 slides apart | Read the LADDER tags (ANCHOR/DROP1/DROP2/DROP3/FINAL) in slide order; compute the slide-number gap between each adjacent pair. Any gap < 8 = fail. | "AF-DENSITY (DEN-1): [beat A] at slide X and [beat B] at slide Y are [gap] slides apart (min 8). Spread the ladder; add build-up and value between them." |
| DEN-2: Anchor outside the 25-to-45% depth band | Anchor slide position / total slides. Outside 0.25-0.45 = fail. | "AF-DENSITY (DEN-2): the anchor is at [pct]% depth (target ~one-third, 25-45%). Move it earlier; do not cram value into the back third." |
| DEN-3: A DROP with no BUILDUP immediately before it | For each DROP slide, the immediately preceding slide must be tagged BUILDUP. | "AF-DENSITY (DEN-3): [drop] at slide X has no BUILDUP slide immediately before it. Add an emotional build-up slide; never drop a price cold." |
| DEN-4: No itemized value-stack slide before Drop 1 | A slide tagged as the value stack (itemized components, each with its value, summed to a total) must exist before the first DROP. | "AF-DENSITY (DEN-4): no itemized value-stack slide precedes Drop 1. Add a stack slide that sums to a total exceeding the anchor before the first drop." |
| DEN-5: No promises beat before the anchor | A promises slide must exist before the ANCHOR. | "AF-DENSITY (DEN-5): no promises slide precedes the anchor. Plant the promises before the first number." |
| DEN-6: Wall of Wins not ~5 slides before the offer | Wall-of-Wins slide position vs final-offer slide position. Outside 4 to 6 slides = fail. | "AF-DENSITY (DEN-6): the Wall of Wins is [gap] slides before the offer (target ~5, range 4-6). Space it with a build-up run between; do not jam it against the offer." |
| DEN-7: No re-pitch block after FINAL | After the FINAL price, 4 to 7 slides recapping stack + promises + urgency must exist before the send-off. | "AF-DENSITY (DEN-7): the deck closes on [N] post-FINAL slides with no re-pitch block (need 4-7). Add the recap-stack, restate-promises, reset-urgency block before the thank-you." |
| DEN-8: A section below its minimum slide count | Count slides per SECTION label against the Section-2 floors. Any section below its floor = fail. | "AF-DENSITY (DEN-8): the [section] section has [N] slides (floor [M]). Add slides; a thinner section cannot pace the arc or honor the mandatory splits." |

---

## 4. PASS vs FAIL EXAMPLES (drawn from the actual Corey defects)

**FAIL (Corey ladder):** anchor s32, Drop 1 s34 (gap 2), Drop 2 s37 (gap 3), final s43 (gap 6) -> DEN-1 fails all three gaps; DEN-2 fails (anchor at 71% depth).
**PASS (Lyric model):** anchor at ~one-third, then gaps of 11, 16, 14, 8 across the back two-thirds.

**FAIL (Corey):** no itemized value stack (slide 39 only re-asserts $5,000 without summing components) -> DEN-4. No promises slide before the anchor -> DEN-5. No re-pitch after the final price (closes on a moment slide + thank-you) -> DEN-7.
**PASS:** a promises slide before the anchor; an itemized stack summed past the anchor before Drop 1; a 4-to-7-slide re-pitch after the final price.

**FAIL (Corey):** Wall of Wins (s40) 3 slides before the offer (s43) -> DEN-6.
**PASS:** Wall of Wins ~5 slides before the offer with a build-up run between.

**FAIL (Corey overall):** deck too thin to space the beats (Trevor: "needs roughly 8-10 MORE slides") -> DEN-8 across teaching and offer sections.
**PASS:** sections meet their floors; the ladder gaps are satisfiable because the deck is long enough.

---

## 5. ESCALATION / REPAIR PATH

1. The Director owns arc_allocation.json and runs the density pre-check at arc time: it computes the planned ladder positions, the gaps, the anchor depth, the Wall-of-Wins spacing, the re-pitch block, and the section counts, and will not release the arc to the Copywriter until all AF-DENSITY triggers are clear in the PLAN.
2. The minimum-gap floor (8 slides) is computed against the FULL deck count and OVERRIDES any percentage-based ladder placement. If the percentages and the floor conflict, the floor wins and the Director lengthens the offer window or the deck.
3. On any AF-DENSITY trigger at Phase 1Q, the repair is an arc change (add slides, move the anchor earlier, insert buildups/stack/promises/re-pitch), so it routes to the **Director**, then back to the **Slide Copywriter** and **Offer Price Strategist**.
4. Coordinate with SOP-SLIDE-01: the mandatory splits (value trio = 4, four pains = 4) consume slots; the Director reserves these BEFORE checking the section floors so a split does not later violate a gap.
5. Loop up to 3 times. On the 4th failure escalate to the Director and ROLE-16 Healer per QC SOP 9.4. A persistently un-spaceable deck means the deck length itself is too short; the Director increases the total slide count.

---

## 6. INTEGRATION NOTE

The offer-price-strategist currently builds the ladder by percentage with no absolute minimum-gap floor. The integrator must add the 8-slide minimum-gap floor (computed against the full deck), the mandatory value-stack slide, the promises beat, and the post-price re-pitch block to that role's output schema, and add the five-rung doctrinal ladder with round numbers there (the offer cluster owns the ladder NUMBERS; this SOP owns the SPACING). The Director's arc allocator must forbid jamming the offer into the back third and must reserve slots for the value-stack slide, the promises slide, the re-pitch block, and the mandatory one-big-idea splits.
