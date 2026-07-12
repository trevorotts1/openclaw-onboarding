# SOP-PITCH-06: THE PITCH ENGINES (NET-NEW MECHANICAL AUTO-FAILS)

**Cluster:** Pitch-Craft Rules (the offer choreography)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (SOP-STORY-01-VILLAIN-HERO-ARC + SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE (PRESENTATION-MASTER-DOCTRINE.md §4) the proven flow, SOP-PITCH-01-SLOW-DROP-PROCESS + offer-price-strategist SOP 9.x (PRESENTATION-MASTER-DOCTRINE.md §4) the price sequence); SOP-ENGINE-00 (the engine framework)
**Owning roles at write time:** Offer Price Strategist (cadence loop, cost-of-inaction, guarantee felt-frame), Slide Copywriter (branded method, expectation, felt-stakes, villain ordering, method beat tags), Presenters Speech Writer (spoken hook count), Director of Presentations (reserves the per-rung beat block + villain/hero order in the arc), Brainstorming Buddy (proposes branded-method candidates)
**Enforced at the gate by:** QC Specialist - Presentations (Phase 1Q + Phase 6, via `scripts/pitch_engines_check.py`); QC Specialist - Speech (Phase Speech-QC, the hook count)
**Enforcement phase:** **WRITING (copy / offer).** Every pitch engine below is a SCRIPT/OFFER property, proven at COPY-QC (Phase 1Q + re-verified Phase 6), the EARLIEST phase the defect is detectable — before any image prompt is authored.
**Status:** Standalone pitch-craft SOP. Every engine below is a BINARY auto-fail with an EXACT mechanical detection method against a named data file / arc tag / regex / count / arithmetic, owned by a role, and run by a QC specialist at the 8.5 gate. The mechanical detection lives in `scripts/pitch_engines_check.py`. As of **v15.0.0** these checks ALSO fire un-bypassably inside the render preflight via `build_deck.check_pitch_engines` (running the copy/offer `--phase 1Q` against the run dir, registered in `PREFLIGHT_REQUIRED`, conditional on `intake.pitch_included`): a pitch deck missing cadence / cost-of-inaction / felt guarantee / branded method / time-to-result cannot reach kie.ai even if Phase-1Q copy-QC was skipped. A copy-QC failure routes back through the SEND-BACK loop (`run_copy_qc_loop`, SOP-SLIDE-00 §5.5) to the Offer Price Strategist / Slide Copywriter, re-authoring only the failing beat, bounded by `PROMPT_QC_MAX_ATTEMPTS`. Each code is registered in PIPELINE-MANIFEST.autofails (`enforced_by: "qc_check"`, `py_symbol: null`, exactly like the AF-DEN / AF-HOOK / AF-OBI copy-QC battery) and in SOP-SLIDE-00 Section 5 (the machine-checkable table) and Section 8 (the detail blocks). No client names.

---

## 0. DOCTRINE — A RULE THAT CANNOT BE MECHANICALLY CHECKED IS NOT A RULE

The June-2026 pitch breakdown named a set of persuasion "engines" — the price-drop/value-increase loop, pitch cadence, cost-of-inaction, a guarantee they can feel, scarcity, a branded methodology, expectation (time-to-result), the formula, audience, choice, testimonial, research/reinforcement, hook repetition. Several already had mechanical gates (price-drop↔value `AF-C7`; scarcity `AF-DEN`/Devil's-Advocate; research `AF-NO-EXPERT-PROOF`/`AF-RESEARCH-*`; formula `AF-NO-FORMULA`; choice `AF-NO-FORK`; testimonial `AF-WALL`; shift/comparison `AF-NO-BEFORE-AFTER`). This SOP closes the rest by turning each remaining engine into a binary auto-fail with an exact detection method.

**Honest mechanical / vision split.** Where a rule is irreducibly perceptual (does a guarantee FEEL felt?), the GATEABLE half is made mechanical (assert a required token/field is present) and the VERDICT half is left to the copy/vision QC specialist and LOGGED — never silently waved through.

**The data model the checks read** (produced by the owning roles, never fabricated):
- `working/copy/slides_copy.md` — arc-tagged copy. New beat tags this SOP introduces: `VALUE_ADD`, `PROMISE`, `REPITCH_MINI`, `COST_OF_INACTION`, `EXPECTATION`, `FELT_STAKES`, `VILLAIN`(/`ANTAGONIST`), `HERO`(/`SOLUTION`), `NAMED_METHOD`. (Tag syntax: `<!-- ARC: TAG1 TAG2 -->` or `[ARC: TAG]`.)
- `working/copy/price_ladder.json` — `rungs[]` (ordered, each with `target_slide` + `kind`), `cost_of_inaction_slide`, `guarantee.statement`, `guarantee.guarantee_felt_frame`.
- `working/copy/offer_stack.json` — `value_additions_by_drop[]`, `running_value_total`.
- `working/copy/intake.json` — `hook`, `named_methodology`, `time_to_result`.
- `working/copy/method_name_approval.json` — `proposed_name`, `owner_approved:true|false`.
- `working/delivery/PRESENTERS-SPEECH.md` — the spoken script (for the hook count).

---

## 1. THE ENGINES (each = a binary auto-fail)

### 1.1 PITCH CADENCE — the ordered repeating loop (`AF-CADENCE`)
**Doctrine.** For EACH price-drop rung, the slides between that rung and the next DROP must carry, IN ORDER, the four beats: `VALUE_ADD → PROMISE → REPITCH_MINI → COST_OF_INACTION`. This is the per-rung layer ON TOP of the global price-drop↔value floor `AF-C7` (which answers "does every drop have a buildup and does the total climb?"). `AF-CADENCE` answers "does each rung run the FULL loop, in sequence, before the next drop?" The two do not contradict.
**Detection (`pitch_engines_check.chk_cadence`).** Load `price_ladder.rungs` (ordered) + the arc markers in `slides_copy.md`. For each adjacent price-beat pair, walk the slide window and assert the four beats appear in monotonic slide order. A missing or out-of-sequence beat fails, naming the rung and the offending beat.
**Owner:** Director (reserves the four-beat block per rung in `arc_allocation.json`) + Offer Price Strategist (records per-rung beats) + Slide Copywriter (writes + tags the copy).
**Gate:** Phase 1Q + Phase 6.

### 1.2 COST-OF-INACTION (`AF-NO-COST-OF-INACTION`)
**Doctrine.** The deck must state the cost of NOT acting. This promotes offer SOP 9.6 from "flag it as a doctrine gap" to a hard gate.
**Detection (`chk_cost_of_inaction`).** Assert `price_ladder.cost_of_inaction_slide` is non-null AND a `COST_OF_INACTION` arc beat is tagged in `slides_copy.md`. (Per 1.1 it must ALSO appear per-rung.)
**Owner:** Offer Price Strategist (SOP 9.6). **Gate:** Phase 1Q + Phase 6.

### 1.3 GUARANTEE THEY CAN FEEL (`AF-GUARANTEE-GENERIC`)
**Doctrine.** Presence of a guarantee is already enforced (offer SOP 9.8 + copy c20). This adds the anti-generic half: a guarantee whose copy is ONLY a refund-template phrase ("30-day money back") with no client-specific felt frame fails.
**Detection (two-part).**
- *Mechanical (`chk_guarantee_generic`, the hard trigger):* strip the generic-template phrases (`money-back`, `30-day`, `refund`, `satisfaction guaranteed`, `no questions asked`) from `guarantee.statement`; if nothing substantive remains AND no `guarantee_felt_frame` is supplied, fail.
- *Subjective (logged):* Copy-QC rates whether the guarantee reads as a felt promise vs a generic money-back line; logged to `copy_qc_report.json`.
**Owner:** Offer Price Strategist + Slide Copywriter. **Gate:** Phase 1Q (copy) + Phase 6.

### 1.4 BRANDED METHODOLOGY (`AF-NO-BRANDED-METHOD` + `AF-METHOD-FABRICATED`)
**Doctrine (FIX of the inverted ban).** Generic content sells at generic prices, so a deck with generic intake content must STILL carry a named-method beat — but the name is PROPOSED for owner approval, never silently invented on a slide. This replaces the retired hard "never fabricate a methodology name" ban. Two distinct failures:
- `AF-METHOD-FABRICATED` — a `NAMED_METHOD` beat on a slide with neither a client-supplied `intake.named_methodology` nor an `owner_approved:true` record in `method_name_approval.json` (silent fabrication, still banned).
- `AF-NO-BRANDED-METHOD` — generic intake (no client method) AND zero method beat at all (the inverted ban — leaving the deck method-less is also a failure).
**Detection (`chk_branded_method`).** As above, against the arc tag + `intake.named_methodology` + `method_name_approval.owner_approved`.
**Owner:** Slide Copywriter (proposes + tags) + Director (routes to owner) + Brainstorming Buddy (candidates). **Gate:** Phase 1Q.
**Decision flagged to owner:** auto-naming-with-owner-approval replaces the prior hard ban (see DECISIONS).

### 1.5 EXPECTATION — time-to-result (`AF-NO-TIME-TO-RESULT`)
**Doctrine.** A slide must state how long the result takes ("8 weeks to final, a shift in 2"), sourced from intake, never fabricated.
**Detection (`chk_time_to_result`).** Assert an `EXPECTATION` arc beat exists whose surrounding copy carries a duration token (`\b\d+\s*(day|week|month|session|hour|minute)s?\b`) AND `intake.time_to_result` is non-null.
**Owner:** Slide Copywriter + Offer Price Strategist. **Gate:** Phase 1Q.

### 1.6 EMOTIONAL — felt stakes (`AF-NO-FELT-STAKES`)
**Doctrine.** At least one felt-stakes slide must quantify the cost in human terms (the "3,285 mornings left" device) BEFORE the offer.
**Detection (`chk_felt_stakes`).** Assert a `FELT_STAKES` arc beat exists BEFORE the first ladder/price beat, whose copy pairs a concrete number (`\b\d[\d,]*\b`) with a personal-loss frame token (mornings / left / never get back / running out / by the time …). Presence + structure is the hard trigger; "does it land" stays a logged copy-QC note.
**Owner:** Slide Copywriter (copy/beat) + Deep Research Specialist (the real number). **Gate:** Phase 1Q.

### 1.7 STORY — villain before hero (`AF-NO-VILLAIN`)
**Doctrine.** No one cares about the hero until they meet the villain. A `VILLAIN`/antagonist beat must exist AND precede the `HERO`/solution beat. (Orthogonal to `AF-STORY-CHARACTER-DRIFT`, which governs visual continuity.)
**Detection (`chk_villain`).** Scan arc tags in slide order; absence of a villain, or villain after hero, fails.
**Owner:** Director (reserves the beat order in `arc_allocation.json`) + Slide Copywriter (writes/tags). **Gate:** Phase 1Q + Phase 6.

### 1.8 HOOK REPETITION — sung 5-20x in the SPEECH (`AF-SPEECH-HOOK-COUNT`)
**Doctrine (the visual-ceiling vs spoken-floor reconciliation).** The slide-side ceiling (3-4 dedicated typography slides; `AF-HOOK-1`/`AF-C2`) is a VISUAL rule and stays. "Sing it 5-20x" is a SPOKEN/teleprompter rule and lives in the speech. The two never contradict (visual ceiling vs spoken floor); the split is documented in SOP-SLIDE-03.
**Detection (`chk_speech_hook_count`).** In `PRESENTERS-SPEECH.md`, count char-exact occurrences of `intake.hook`; assert `5 ≤ count ≤ 20`. The existing verbatim-integrity gate (`AF-HOOK-5`) already bars mutation.
**Owner:** Presenters Speech Writer. **Gate:** Phase Speech-QC.

---

## 2. ENGINES ALREADY MECHANICAL — KEPT UNCHANGED (the model, do not re-gate)

| Engine | Live enforcing code | Why no new code |
|---|---|---|
| Price-drop ↔ value-increase | `AF-C7` (escalation + strictly-rising running total, reconciled to `offer_stack.json`) + `AF-C4` | genuinely mechanical; `AF-CADENCE` only adds the per-rung ORDERING layer on top |
| Scarcity | offer SOP 9.8 + SOP-PITCH-01 rule 7 + copy c21; fabricated scarcity = Devil's-Advocate BLOCKING | presence + no-fabrication already gated |
| Formula | `AF-NO-FORMULA` (this+this+this=this shape) | shape gate exists; method-overlap is a logged scored note, not a new hard fail |
| Audience | representation `AF-R*`/`AF-CAST`/`AF-P-REP` + `representation_audit.json` ±10% band | ratio is mechanical; copy/tone demographic adaptation handled in hook-strategist SOP |
| Choice (DIY vs with-us) | `AF-NO-FORK` (two-branch tree + check-mark + cost-of-inaction on the unchosen path) | SOP-ENGINE-00 §5.2 merge-map: the Fork IS the choice |
| Testimonial (2 or 6) | `AF-WALL` (≥4 named clients w/ city+result; future-pace fails c19) | count floor mechanical; 2-vs-6 layout is a coaching note |
| Research / reinforcement | `AF-NO-EXPERT-PROOF` + `AF-RESEARCH-GATE` + `AF-RESEARCH-UNCITED` (≥8 cited URLs) | named-source presence + citation floor already mechanical |
| Promise + Problem | promise `AF-DEN-5`; problem/stakes is arc beat (2) of `AF-C11` | co-presence already gated by `AF-C11`; no `AF-NO-PROBLEM` needed |
| Shift (was/now), Comparison/Contrast | `AF-NO-BEFORE-AFTER` | SOP-ENGINE-00 §5.2 merge-map; one before/after pair satisfies both |

---

## 3. ESCALATION / REPAIR PATH

1. Any `AF-*` from this SOP routes the slide/deck back to the owning role named above with the exact failing code + message from `pitch_engines_check.py`.
2. `AF-CADENCE` / `AF-NO-VILLAIN` are arc-ordering fails → the Director re-reserves the beat order in `arc_allocation.json`, then the Slide Copywriter re-tags the copy.
3. `AF-NO-COST-OF-INACTION` / `AF-GUARANTEE-GENERIC` → the Offer Price Strategist sets `cost_of_inaction_slide` / `guarantee.guarantee_felt_frame`.
4. `AF-NO-BRANDED-METHOD` → propose a name (with the Brainstorming Buddy), route to the Director → owner, record `owner_approved` in `method_name_approval.json`. `AF-METHOD-FABRICATED` → remove the unapproved name from the slide.
5. `AF-SPEECH-HOOK-COUNT` → the Presenters Speech Writer adds/removes verbatim refrains until `5 ≤ count ≤ 20`.
6. Loop up to 3 times. On the 4th failure escalate to the Director and ROLE-16 Healer per QC SOP 9.4.

---

## 4. DECISIONS FLAGGED TO THE OWNER (not silently resolved)

1. **Branded-Methodology (1.4):** auto-naming-with-owner-approval replaces the prior hard "never fabricate a methodology name" ban. Silent fabrication stays banned; owner-approved naming is now required.
2. **Hook split (1.8):** the visual ceiling (3-4 slides, `AF-HOOK-1`) vs the spoken floor (5-20x, `AF-SPEECH-HOOK-COUNT`) is the intended reconciliation.

---

## 5. INTEGRATION NOTE

The mechanical detection lives in `scripts/pitch_engines_check.py` and is invoked by the QC specialists at Phase 1Q, Phase 6, and Phase Speech-QC. Each code is registered in PIPELINE-MANIFEST.autofails (`enforced_by: "qc_check"`), SOP-SLIDE-00 Section 5 (the machine-checkable table), and Section 8 (the detail blocks). The `build_deck.py` render path is untouched. Cross-reference: SOP-PITCH-01 (slow drop), SOP-PITCH-02 (value stack and promises — the content the cadence loop re-stacks), SOP-PITCH-03 (re-pitch), SOP-PITCH-04 (Wall of Wins + external proof), SOP-ENGINE-00 (the engine framework + §5.2 merge map), SOP-SLIDE-03 (hook visual ceiling vs spoken floor), offer-price-strategist-sops.md SOP 9.6 / 9.8, slide-copywriter-sops.md (branded method, felt-stakes, expectation, villain tagging), presenters-speech-writer-sops.md (spoken hook count).
