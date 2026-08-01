# SOPs Mirror -- Signature Presentation Architect ("The Storymaker")

**Source:** departments/Presentations/roles/signature-presentation-architect.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Source classification:** custom (Trevor BlackCEO; the floor presentations library has no signature-presentation pitch-doctrine SOPs).
**Department:** Presentations -- BlackCEO
**Version:** 1.0
**Last updated:** 2026-06-14

---

## 9. Standard Operating Procedures (Numbered)

Master authority: `51-signature-presentation/MASTERDOC.md` (Prime Directives 1-14). Lockstep authority: `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (phases P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE) + `universal-sops/presentation-slide-craft/SOP-SLIDE-06-EXTENSION-AND-SYNC.md`.

> Engine cross-reference: this role OWNS the Signature Presentation methodology (the Trevor Otts 4-phase arc). Every SOP below is machine-enforced by a fail-closed prover: `51-signature-presentation/scripts/prove_sp_intake.py`, `prove_sp_structure.py`, `prove_sp_no_pitch.py`, wired into `scripts/build_deck.py` as the `_chk_sp_intake` / `_chk_sp_structure` / `_chk_sp_no_pitch` preflight wrappers (which DEFER for every non-signature deck).

---

### SOP 9.1 -- Signature Deck Arc Design (Start With The End In Mind)
> Gating enforcer: `P-SP-INTAKE-TRACE` / `build_deck._chk_sp_intake_trace` (fail-closed preflight, phase order 0.16); the QC/Healer scan enforces the same check out-of-band.

**SOP ID:** SOP-PRES-CUSTOM-01 (BlackCEO)
**Library pointer:** SOP-STORY-01-VILLAIN-HERO-ARC + SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE + director-of-presentations SOP 9.3 (PRESENTATION-MASTER-DOCTRINE.md §4) (17-row allocation), SOP-STORY-01-VILLAIN-HERO-ARC + SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE (PRESENTATION-MASTER-DOCTRINE.md §4) (seven-section proven flow), SOP-PITCH-* + SOP-PROCLAMATION-01 (Pitch Doctrine points 1-18 reproduced in devils-advocate-presentations SOP 9.1) (PRESENTATION-MASTER-DOCTRINE.md §4) (pitch doctrine)
**When to run:** When a deck arrives from the Director with complete intake and requires a narrative architecture before copy begins.
**Frequency:** On-demand, per deck.
**Inputs:** Complete intake.json (strongest-promise candidates, proof assets, offer details, PRICE_MODE, audience composition, hook seed), the slide-math ceiling from the Director, the proven exemplar deck.

**Steps:**
1. Confirm intake completeness: strongest-promise candidates, proof assets, offer and PRICE_MODE, audience composition, hook seed. If any field is missing, return to the Director with the specific missing fields before designing. Never invent a promise, proof, or offer.
2. Design backward from the finished signature deck (DR-20): state the end-state the client will reproduce on demand, then work backward to the opening.
3. Extract the PROMISE spine (DR-2): identify what the product is promising, not what it is. Every persuasive beat will pitch the promise.
4. Select the strongest promise as the HOOK SEED (DR-3) and hand it to the Hook Strategist; place the hook from the first content slide and mark it to recur about ten times through the deck (sing the chorus from the first verse).
5. Map the seven-section proven flow against the slide-math ceiling using the SOP-STORY-01-VILLAIN-HERO-ARC + SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE + director-of-presentations SOP 9.3 (PRESENTATION-MASTER-DOCTRINE.md §4) 17-row allocation. Place the cost-of-inaction beat AND the value-of-action beat (DR-7, cost versus value); place third-party proof beats answering "who says so other than you?" (DR-6); place the light-pitch lines on teaching slides from the front (DR-10).
6. Mark the value-anchor placements that feed the slow-drop ladder (DR-4, DR-5) and hand them to the Offer Price Strategist: ANCHOR is a gradual value plant, not a drop; every drop adds value.
7. Apply the appetizer-not-dinner guardrail (DR-9): mark any beat that over-teaches and trim it so the deck proves value and creates desire without fully solving the problem for free.

**Outputs:** A finalized narrative architecture: the promise spine, the hook seed, the seven-section flow mapped to slides, the value-anchor placements, the cost-versus-value beats, the proof beats, and the light-pitch map.
**Hand to:** Slide Copywriter (writes verbatim copy against the arc), Hook Strategist (develops the hook from the seed), Offer Price Strategist (builds the ladder against the value-anchor placements).
**Failure mode:** If the offer has no clear promise or the intake has no proof assets, do not fabricate them to complete the arc. Halt and return to the Director: the promise and proof come from the client, never invented.

---


### SOP 9.2 -- Pitch-Arc Review (The Pitch Is Where Decks Die)


**SOP ID:** SOP-PRES-CUSTOM-02 (BlackCEO)
**Library pointer:** SOP-PITCH-* + SOP-PROCLAMATION-01 (Pitch Doctrine points 1-18 reproduced in devils-advocate-presentations SOP 9.1) (PRESENTATION-MASTER-DOCTRINE.md §4) (pitch doctrine), SOP-PITCH-01-SLOW-DROP-PROCESS + offer-price-strategist SOP 9.x (PRESENTATION-MASTER-DOCTRINE.md §4) (spread ladder)
**When to run:** After the Copywriter and Offer Price Strategist execute, before the deck advances to image prompts.
**Frequency:** Per deck, at least once; re-run after any pitch revision.
**Inputs:** The drafted slide copy, the price_ladder.json, the hook package, the narrative architecture from SOP 9.1.

**Steps:**
1. Confirm the PROMISE is pitched, not the product, on every persuasive beat (DR-2). Flag any beat that lists features instead of the promise.
2. Confirm the hook is present from the first content slide and recurs throughout, not back-loaded (DR-3, DR-10). Flag any deck that waits until the end to pitch.
3. Confirm every price drop ADDS value and never subtracts (DR-4). Flag any drop that removes a bonus.
4. Confirm value is anchored gradually before any price reveal, with the frame matched to the offer type: money-math when the outcome is financial, the priceless frame when it is not (DR-5).
5. Confirm both the cost-of-inaction beat and the value-of-action beat are present (DR-7). This was the number-one substantive gap on a prior client deck; its absence is a structural fail.
6. Confirm third-party proof answers "who says so other than you?" (DR-6): case studies, white-paper studies, or a wall of wins. A deck with zero third-party proof fails.
7. Confirm every key beat serves both the emotional buyer and the logical justifier (DR-8): you are usually pitching a couple, so emotional appeals are paired with logical justification.
8. Confirm the deck did not over-teach (DR-9): appetizer, not dinner.

**Outputs:** A pitch-arc review record: pass, or a flagged list of missing or off-doctrine beats with the specific corrective instruction routed to the responsible role.
**Hand to:** Slide Copywriter or Offer Price Strategist or Hook Strategist for any flagged beat; Director of Presentations for the gate record once all beats pass.
**Failure mode:** If a deck is missing a mandatory beat and the responsible role cannot supply it from client material, escalate to the Director; do not pass the arc with a fabricated beat to clear the review.

---


### SOP 9.3 -- SEE Journey Design (Significant Emotional Experience)


**SOP ID:** SOP-PRES-CUSTOM-03 (BlackCEO)
**Library pointer:** Signature Presentation Theory (governing intelligence); SOP-STORY-01-VILLAIN-HERO-ARC + SOP-PRIORITY-02-EIGHT-MOVE-BUILD-SEQUENCE (PRESENTATION-MASTER-DOCTRINE.md §4)
**When to run:** During arc design, for every deck (the SEE journey is the spine the seven-section flow hangs on).
**Frequency:** Per deck.
**Inputs:** The narrative architecture, the client's audience composition, the client's methodology and story material.

**Steps:**
1. Design the deck as a JOURNEY, not a deck of facts. Map the emotional arc the viewer travels from open to close.
2. Build the see-yourself moment: through a story, the audience must find themselves in the deck. Mark the slide(s) where the viewer recognizes their own situation.
3. Design the see-plus-feel experience: each key idea is wrapped in something the viewer sees and feels, so it etches in memory (the Significant Emotional Experience mechanism).
4. Place old-to-new bridges: anchor every new idea to something the audience already understands, using their previous understanding to raise their current understanding.
5. Apply Point-Story-Demo on teaching slides: state the point, tell the story that lands it, then demonstrate it.
6. Open by caring about the audience before establishing the client's credentials: people do not care about who you are until you show them that you care about who they are.
7. Where the deck is interactive, design it so the audience teaches itself (the conversational learning environment); the audience arrives at the insight rather than being told.

**Outputs:** A SEE-journey map layered onto the narrative architecture: the see-yourself moment, the see-plus-feel beats, the old-to-new bridges, and the Point-Story-Demo teaching slides.
**Hand to:** Slide Copywriter (writes the story and bridge copy), Image-Grounding Steward (ensures the imagery makes the journey's pain and promise visible).
**Failure mode:** If the client supplies no story material to build the see-yourself moment, request it through the Director; do not fabricate a client story.

---


### SOP 9.4 -- Enhance-Don't-Replace Audit (The Improvement Boundary)


**SOP ID:** SOP-PRES-CUSTOM-04 (BlackCEO)
**Library pointer:** Governing intelligence GP-20; master intake rules
**When to run:** Whenever a deck is built from a client's existing presentation rather than from scratch.
**Frequency:** Per existing-deck job, before delivery.
**Inputs:** The client's original deck, the enhanced deck, the narrative architecture.

**Steps:**
1. Compare the enhanced deck against the client's original intent, words, and methodology, slide by slide.
2. Confirm the engine only ADDED slides and IMPROVED design and structure; confirm it did not change the client's intent, words, or methodology.
3. For any wording change the engine proposes, require per-substitution owner approval before it ships; never rewrite the client's words silently.
4. Confirm any added slide strengthens the arc (promise, hook, cost-versus-value, proof, light pitch) without contradicting the client's method.
5. Log every addition and every approved substitution in the enhance-don't-replace audit record.

**Outputs:** An enhance-don't-replace audit record: confirmed additions, approved substitutions, and a clean pass or a flagged list of unauthorized changes to revert.
**Hand to:** Director of Presentations for the gate record; Slide Copywriter to revert any unauthorized change.
**Failure mode:** If an unauthorized change to the client's methodology is found after assembly, halt delivery and revert before the deck ships; an unauthorized change is a trust violation.

---



---

### SOP 9.5 -- The 8 Questions (asked ONE at a time via the REQUIRED driver turn-gate, recorded as ONE atomic block)


**When to run:** first, before any authoring. Routed from the Brainstorming Buddy "signature presentation" trigger.

**Inputs:** the client conversation; `51-signature-presentation/intake/sp-8-questions.json` (the spec); the REQUIRED turn-gate `deck-intake-driver.py --signature --next` / `--answer <ID> "<TEXT>"`.

**Steps:** interview the owner choice-first (QUICK vs IN-DEPTH), then ask q1..q8 + the frame-selection question ONE AT A TIME through the turn-gate — never free-form and never a wall of questions (dumping two or more questions in one turn, or opening with no quick-vs-in-depth choice, is the `AF-INTAKE-BATCH` conversation autofail, gated by the required preflight `P-SP-INTAKE-TRACE`, `build_deck._chk_sp_intake_trace`, phase order 0.16, fail-closed; the QC/Healer scan runs the same scanner out-of-band as an additional post-hoc pass); the driver auto-assembles the answers into ONE atomic RECORD at `working/copy/sp_intake.json` on the final validated answer (that assembled record is what `prove_sp_intake.py` validates as `AF-SP-8Q-SPLIT` — a record-layer gate only, it says nothing about conversation pacing); set `deck_type: signature_presentation` in `working/copy/intake.json`; seed `offer_token_ledger` from q7 (the offer question).

**Outputs:** `working/copy/sp_intake.json` (clears `prove_sp_intake.py`).

**Hand to:** SOP 9.2.

**Failure mode:** Conversation layer: AF-INTAKE-BATCH. Record layer: AF-SP-8Q-MISSING, AF-SP-8Q-SPLIT, AF-SP-OFFER-UNDECLARED, AF-SP-TYPE-MISMATCH.


### SOP 9.6 -- Frame Selection and Template Load


**When to run:** after SOP 9.1, in the same intake block.

**Inputs:** the frame-selection answer; `51-signature-presentation/frame-templates/{rulebook,vault,quest,original}.md`.

**Steps:** lock `signature_frame` to exactly one of rulebook|vault|quest|original; load that frame template (devices, refrain policy, tone ladder, close).

**Outputs:** the locked frame in `sp_intake.json`.

**Hand to:** SOP 9.3.

**Failure mode:** AF-SP-FRAME-UNSET.


### SOP 9.7 -- Four-Phase Arc and Labels


**When to run:** after the frame is locked.

**Inputs:** the frame template; the SACRED structure contract `51-signature-presentation/structure/sp_structure.json`.

**Steps:** build `working/copy/sp_structure.json` with the 4 phases contiguous-from-slide-1 in the order avatar->story->teaching->pitch, a label slide per phase, a non-empty `suggested_image` on every slide, at most 2 CASE_STUDY-tagged slides, 3 to 7 teaching steps, one central hook + four DISTINCT section hooks, and the N.E.E.I.T. + 4-Quadrant markers in the required phases.

**Outputs:** `working/copy/sp_structure.json` (clears `prove_sp_structure.py`).

**Hand to:** SOP 9.4.

**Failure mode:** AF-SP-PHASE-RANGE, AF-SP-PHASE-ORDER, AF-SP-PHASE-LABEL, AF-SP-IMG-SUGGESTION, AF-SP-CASESTUDY-CAP, AF-SP-TEACH-STEPS, AF-SP-HOOK, AF-SP-QUADRANT.


### SOP 9.8 -- Expansion-to-100 Math


**When to run:** during structure build.

**Inputs:** the phase floors (avatar 11 / story 13 / teaching 36 / pitch 40); any logged client-exact count.

**Steps:** expand to >=100 slides on the phase floors (the bands are floors, not fixed spans). The Mode-A 90-slide cap is N/A for `deck_type: signature_presentation` (see Director SOP 9.4 signature branch and Edge Case 17.3 carve-out). A `client_overrode_slide_floor` + `client_exact_slide_count` is honored EXACTLY and recorded on the certificate.

**Outputs:** the final slide count in `sp_structure.json`.

**Hand to:** SOP 9.5.

**Failure mode:** AF-SP-SLIDE-FLOOR.


### SOP 9.9 -- Handoff to Copywriter / Hook Lab / phase-authors


**When to run:** after the structure clears the prover.

**Inputs:** the locked `sp_structure.json` + frame contract.

**Steps:** hand off to the Slide Copywriter and Hook Lab; the Phase-3 no-pitch prover (P-SP-P3-HYGIENE) guards the teaching band before Copy QC.

**Outputs:** the deck flows into the existing pipeline through Delivery.

**Hand to:** Slide Copywriter, Hook Lab, then the existing pipeline; QC by the QC Specialist (Signature Presentations).

**Failure mode:** AF-SP-P3-PITCH (a q7 offer/product name, a price token, or an enroll/scarcity CTA in the teaching band, or a non-contiguous Phase-3->Phase-4 bridge).



---

*End of SOPs mirror for the Signature Presentation Architect. Custom Presentations SOPs SOP-PRES-CUSTOM-01 through 04 for BlackCEO plus the standard intake/structure SOPs (9.5-9.9). This file is regenerated from the role file and is never edited directly.*
