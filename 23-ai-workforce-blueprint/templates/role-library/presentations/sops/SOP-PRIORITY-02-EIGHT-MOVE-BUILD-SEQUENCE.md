# SOP-PRIORITY-02: THE EIGHT-MOVE BUILD SEQUENCE -- ENGINEERING THE PRIORITY SHIFT

**Cluster:** North Star / Build sequence. Child of SOP-NORTHSTAR-00 (the destination) and SOP-PRIORITY-01 (the diagnostic that prescribes this sequence as Position/Priority remediation). The conductor that orders the department's existing persuasion instruments into the shift.
**Owning role at write time:** Attention Content Strategist (authors the eight-move map at P0B-PRIORITY, order 0.2) + Director of Presentations (reserves the move SLOTS in `arc_allocation.json`, SOP 9.4) + offer-price-strategist (owns moves 4-6 cargo/value-drop slots) + presenters-speech-writer (delivers moves 7-8 aloud).
**Enforced at the gate by:** QC Specialist - Presentations. The sequence becomes law as the monotonic-ordering check behind **AF-NO-SHIFT** (COPY-QC 4.2) plus three new per-move beat gates -- **AF-NO-PRIORITY-STACK** (move 1), **AF-NO-RERANK** (move 7), **AF-NO-TRIGGER** (move 8) -- and the arc gate **AF-PEAK-END** (order 3). Moves 2-6 are already enforced by live machinery (see §2); do NOT rebuild them.
**Detection script:** `scripts/intelligence_engines_check.py check_copy` (PRIORITY_STACK_NAMED before first ladder beat; explicit re-rank beat after PRICE; time-bound CTA token in CTA slide) + `scripts/build_deck.py` (PEAK tag in `arc_allocation.json`; peak+closing in top creativity-budget quartile; non-flat ending). REGISTRATION PENDING -- Agent W3 (H->I->J lockstep).
**Registered:** PENDING Agent W3 lockstep. Until then this is the stated build doctrine the strategist and director run by hand; the eight-move map is recorded in `priority_shift_spec.json.eight_move_map[]`.
**Enforcement phase:** Authored at P0B-PRIORITY (0.2); slotted into the arc at P3-ARC (3, `AF-PEAK-END`); verified in copy at COPY-QC (4.2, the three beat gates + AF-NO-SHIFT ordering); verified whole at P-SHIFT-QC (7.5, composite AF-PRIORITY-SHIFT).
**Status:** **DOCTRINE.** The eight-move spine has no foothold today. This SOP installs it and WIRES it into the existing arc allocation and pitch machinery rather than duplicating it. New gates registered in lockstep by Agent W3.

---

## 1. THE SEQUENCE -- EIGHT MOVES, IN ORDER (P141-P150)

Every presentation, in every mode and for both outcomes (sale or training), runs these eight moves **in order**. Running them is how you carry out the two-part job (*sell the vision and position the product*): the vision powers moves 2-3; the positioning is what moves 6-8 convert into a decision. The order is monotonic in `slides_copy.md` -- a move that appears out of order fails `AF-NO-SHIFT`.

1. **Surface the current priority stack.** Name out loud what the audience already spends money, time, or attention on. People cannot re-rank a list they have not looked at. *(Gate: AF-NO-PRIORITY-STACK -- a PRIORITY_STACK_NAMED beat must appear before the first ladder/offer beat.)*
2. **Expose the cost of the current ranking, in present tense.** Show what staying the same costs them right now -- money, time, identity -- with loss framing.
3. **Reframe your thing as the lever for a higher priority they already hold.** Connect it to legacy, family, freedom, purpose, or the person they want to become. **This is where you sell the vision** (SOP-VISION-01): help them see what you see for them, the transformed future, with your offer as the vehicle to it.
4. **Anchor the true value high.** State the real, honest value before any price or any ask of effort.
5. **Make it urgent and scarce.** Add limited time and limited availability so "this matters" becomes "this matters and I must decide now." Honest limits only.
6. **Remove the ability blocker.** For a buyer, drop the price and stack value (the value drop). For a learner, lower perceived difficulty and give a first step small enough that beginning feels easy.
7. **Demand the re-rank out loud.** Ask the priority question directly and make the audience answer, even silently. *(Gate: AF-NO-RERANK -- an explicit re-rank/decision-demand beat must appear after the PRICE beat.)*
8. **Fire the trigger.** Give the clear, time-bound call to act now, while the priority is freshly at the top. *(Gate: AF-NO-TRIGGER -- a time-bound CTA token must appear in the CTA slide.)*

## 2. WIRING -- EACH MOVE PLUGS INTO EXISTING MACHINERY (do NOT rebuild)

The eight-move sequence is a **conductor**, not a new orchestra. Six of the eight moves already have a live, enforced home. This SOP's job is to guarantee the *ordering and completeness*; the per-move mechanics stay where they are.

| Move | Already enforced by (reference -- do not duplicate) | New gate this SOP adds |
|---|---|---|
| 1 -- surface the stack | (none today) | **AF-NO-PRIORITY-STACK** |
| 2 -- present-tense cost | **SOP-ENGINE-00** Engine 10 felt-stakes (`AF-NO-FELT-STAKES`) + Pricing `AF-NO-COST-OF-INACTION` | -- |
| 3 -- reframe as higher-priority lever | **SOP-STORY-01** villain->hero (`AF-NO-VILLAIN`) + belief-shift (slide-copywriter SOP 9.7) + **SOP-VISION-01** | -- |
| 4 -- anchor value high | **SOP-PITCH-02** value-stack / promise-before-price (Pricing cadence) | -- |
| 5 -- urgent + scarce | **SOP-PITCH-01** + offer-price-strategist scarcity/urgency | -- |
| 6 -- remove ability blocker | **SOP-PITCH-01** slow-drop / value drop + offer-price-strategist | -- |
| 7 -- demand the re-rank | (none today) | **AF-NO-RERANK** |
| 8 -- fire the trigger | offer-price-strategist time-bound close (partial) | **AF-NO-TRIGGER** (time-bound CTA token) |

The three new gates close exactly the three moves with no current home (1, 7, 8). The composite **AF-NO-SHIFT** (SOP-PRIORITY-01) asserts the eight move-tags are present and **monotonic**.

## 3. THE PEAK-END OVERLAY (P49) -- AF-PEAK-END

The peak-end rule sits across the sequence: the audience judges the deck by its most intense moment and its ending, not its average. The Director, when reserving move slots in `arc_allocation.json`, must tag a **PEAK** slot (the wow/demonstration high point, usually landing on or just after move 3-4) and guarantee a **non-flat ENDING** (the trigger, move 8, must be the engineered close, never a "thank you" deflate). The Attention Designer gives the PEAK and ENDING slots the top creativity budget quartile (the most-vivid-by-the-end mandate, `AF-NO-SALIENCE-APEX`). **AF-PEAK-END** fires (build_deck, order 3) if no PEAK tag exists, if peak/closing are not in the top creativity quartile, or if the ending is flat.

## 4. APPLYING THE SEQUENCE BY MODE (P150)

- **From Scratch (Mode One):** build the eight moves in from the first draft. The brainstorm exists to gather the inputs each move needs (the one destination, the one promise, the priority stack, the higher priority, proof + demonstration, the wow, the value/price tiers).
- **Personal (Mode Two, one-to-one):** execute every move against the **one client's** actual priority stack, situation, and objections. Maximum personalization.
- **General Audience (Mode Three, one-to-many):** execute every move against the **common priority of the room**, and lean on moves 5 and 8 (scarcity, urgency, the trigger) plus social proof and unity to move many at once.

The Fogg behavior model (B = M·A·T, P51) maps to the spine's back half: moves 2-5 spike **Motivation**, move 6 confirms **Ability** (removes the blocker), move 8 fires the **Trigger**. Miss any one and nothing happens.

## 5. THE STRATEGIST'S OUTPUT (P0B-PRIORITY)

The Attention Content Strategist records the eight-move map into `working/copy/priority_shift_spec.json.eight_move_map[]` -- one entry per move with: the beat tag, the slide(s) it lands on, the existing-machinery hook it reuses (per §2), and the evidence the move is present. The Director consumes this to reserve the slots in `arc_allocation.json`; the Slide Copywriter writes the beats to those slots; QC verifies ordering at COPY-QC and completeness at P-SHIFT-QC.

## 6. FOR AGENT W3 -- ENFORCEMENT CODES THIS SOP DECLARES

Register all four in lockstep (manifest v17->18 + ruleset Section 5 + SOP-SLIDE-00 mirror + qc-specialist wiring + test_preflight fixtures), per the §7.4 frozen spec:

- **AF-NO-PRIORITY-STACK** (qc_check, COPY-QC 4.2) -- `intelligence_engines_check.check_copy`: PRIORITY_STACK_NAMED beat before first ladder beat. (Move 1.)
- **AF-NO-RERANK** (qc_check, COPY-QC 4.2) -- `intelligence_engines_check.check_copy`: explicit re-rank/decision-demand beat after PRICE. (Move 7.)
- **AF-NO-TRIGGER** (qc_check, COPY-QC 4.2) -- `intelligence_engines_check.check_copy`: time-bound CTA token in CTA slide. (Move 8.)
- **AF-PEAK-END** (build_deck, order 3; re-checked prompt-QC 4.8) -- PEAK tag in `arc_allocation.json`; peak+closing in top creativity-budget quartile; non-flat ending. (Acceptance test (a) of SOP-NORTHSTAR-00.)

Moves 2-6 reuse existing codes (`AF-NO-FELT-STAKES`, `AF-NO-COST-OF-INACTION`, `AF-NO-VILLAIN`, Pricing cadence) -- do not add duplicates. The eight-tag monotonic ordering is asserted by **AF-NO-SHIFT** (declared in SOP-PRIORITY-01).
