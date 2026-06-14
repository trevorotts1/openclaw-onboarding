# SOPs Mirror -- Deck Systems Specialist ("The Architect") -- DIU

**Source:** graphics/deck-systems-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** PPT-ANALYSIS-SOP v1.0, MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, PHOTO-SHOOT-SOP v1.0, CLIENT-WEBINAR-DECK-SOP v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- [SOP-DIU-201] Deck Style System Analysis

**Vendor SOP.** Library pointer: `_system/PPT-ANALYSIS-SOP.md` (full document).
**Library-version pin:** PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** When a deck brief is received that requires a new style system analysis (no existing PPT-category card covers this client's brand deck aesthetic).
**Frequency:** On-demand, typically 1-3 times per week.
**Inputs:** 2-3 client reference decks in the source format (PPTX, PDF, images), deck brief from CDO specifying purpose and target audience.

**Steps:**
1. Confirm the brief is complete: client name, reference materials provided, deck purpose stated, slide count target, resolution preference, and deadline. If incomplete, return to CDO with the specific missing fields before any analysis work begins.
2. Open `_system/PPT-ANALYSIS-SOP.md` and confirm the version pin at the top of this SOP matches the current library file version. If the pin is stale, halt and flag to CDO.
3. Execute the analysis per PPT-ANALYSIS-SOP §§2-4 on each reference deck: identify the deck's visual grammar (foundation prompt block, color system, typography treatment, layout rhythm, background behavior, accent usage).
4. Synthesize findings across all reference decks into a single style system: one foundation prompt block (~1,200-1,500 characters), rotation variants covering at minimum 3 layout types (title/hero, content/data, transition/divider), and the text strategy decision (a or b per `powerpoint-designs/_RULES.md`).
5. Write the draft PPT-category style card following STYLE-CARD-TEMPLATE.md conventions. Do NOT register the card in INDEX.md yourself -- hand the draft to the Style Analyst for registration, embedding index update, and deduplication check.
6. Notify CDO that analysis is complete and card is in the Style Analyst's registration queue. Confirm the card's expected production status timeline before scheduling manifest assembly.

**Outputs:** Draft PPT-category style card handed to Style Analyst for registration; CDO notified of analysis completion and card registration ETA.
**Hand to:** Style Analyst (card registration + INDEX entry + embedding index update). Manifest assembly (SOP 9.2) begins only after CDO confirms the card has reached production status.
**Failure mode:** If 2-3 reference decks have irreconcilably different visual styles, do not produce a hybrid analysis. Flag to CDO: "Two distinct style systems detected. Which should govern this engagement?" CDO makes the call.

---

### SOP 9.2 -- [SOP-DIU-202] Deck Generation & Rotation Engine Manifest Assembly

**Vendor SOP.** Library pointer: `_system/PPT-ANALYSIS-SOP.md` §3B (Slide Manifest); `powerpoint-designs/_RULES.md` (Rotation Engine parameters).
**Library-version pin:** PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** After CDO confirms the deck's PPT-category style card is at production status in INDEX.md.
**Frequency:** On-demand, per deck project.
**Inputs:** Production-status PPT-category style card (card ID@version confirmed in INDEX.md), complete deck brief (slide count, purpose, all verbatim text strings, brand variables, resolution, deadline), CDO approval to proceed.

**Steps:**
1. Open INDEX.md and confirm: (a) the style card ID exists, (b) its status is "production," (c) the version matches the brief's pinned version. If status is not production, halt and notify CDO.
2. Build the Slide Manifest as an ordered table: one row per slide containing -- slide number, slide type (from the Rotation Engine variant list in `powerpoint-designs/_RULES.md`), foundation block reference, active rotation variant, filled variable values, text strategy (a or b), destination resolution, and the generation tier.
3. Verify the Rotation Engine pattern across the manifest: no two consecutive slides may use the identical variant unless the deck's style system explicitly permits repetition. Flag any deviation to CDO before submitting.
4. For decks of 10 or more slides: submit the complete Slide Manifest to CDO for approval before any generation begins. CDO approval covers cost/timeline authorization, not just style sign-off. Record the CDO approval timestamp in the manifest header row.
5. Assemble the manifest file in the job directory (`_local/jobs/{job-id}/SLIDE-MANIFEST.md`) alongside an estimated total generation cost. Manifest file is the single interface artifact crossing into the Generation Operator's lane.
6. Hand the approved manifest to the Generation Operator with: card ID@version, manifest file path, budget ceiling, resolution, deadline, and identity involvement flag.

**Outputs:** Approved, complete Slide Manifest file in the job directory; Generation Operator briefed and ready to execute.
**Hand to:** Generation Operator for slide-by-slide batch execution. Manifest ownership transfers at this point.
**Failure mode:** If the brief's verbatim text strings contain unfilled placeholders, do not assemble the manifest. Return the incomplete brief to CDO with the specific unfilled fields listed. Never send a manifest with placeholder tokens to the Generation Operator.

---

### SOP 9.3 -- Client-in-Slide Mode (Mode E Co-Production)

**Operational SOP.** Wraps PHOTO-SHOOT-SOP Mode E references; PPT-ANALYSIS-SOP §3B.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** When a deck brief specifies that the client's likeness must appear within slide imagery.
**Frequency:** On-demand; less common than pure style-driven decks.
**Inputs:** Deck brief with likeness_present flag set, confirmed active consent record (from Photo Shoot Director), deck's PPT-category style card at production status.

**Steps:**
1. Verify the Photo Shoot Director has confirmed an active consent record covering Mode E usage for the client. Do not begin manifest assembly until this confirmation is in writing. A missing consent record is a hard stop.
2. In the Slide Manifest, flag every slide containing the client's likeness with an `identity_lock: true` column entry. These slides require the Identity Lock Block assembled by the Photo Shoot Director before the Generation Operator may submit them.
3. Sequence the manifest so identity-locked slides are NOT in the same batch as non-identity slides.
4. Co-run the identity-locked slide batch with the Photo Shoot Director: the Director assembles the Identity Lock Block per PHOTO-SHOOT-SOP §4, attaches it to the manifest row, and confirms the reference image URL is hosted and liveness-verified before the Generation Operator submits.
5. Cohesion review for identity slides (SOP 9.4) applies the standard Rotation Engine check PLUS a visual continuity check: the client's likeness should appear consistent in lighting, scale, and pose style across all identity-locked slides in the deck.

**Outputs:** Identity-locked slides in the manifest with Identity Lock Block confirmed by Photo Shoot Director; non-identity batch proceeds in parallel without delay.
**Hand to:** Photo Shoot Director (Identity Lock Block assembly for flagged slides) + Generation Operator (non-identity slides proceed immediately).
**Failure mode:** If the client's consent record covers specific modes but not Mode E, halt the identity-locked slides. Notify CDO and Photo Shoot Director to either obtain Mode E consent or redesign those slides to use stylized/non-likeness treatments.

---

### SOP 9.4 -- Deck Cohesion Review

**Operational SOP.** Wraps PPT-ANALYSIS-SOP §3B Step 5 cohesion check; `powerpoint-designs/_RULES.md` (Rotation Engine variant rules).
**Library-version pin:** PPT-ANALYSIS-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** After the Generation Operator delivers a completed slide batch (5 or more slides, or a full deck run).
**Frequency:** Per batch delivery, typically 1-3 times per deck project.
**Inputs:** All generated slide images from the batch, the Slide Manifest, the deck's PPT-category style card, generation receipts confirming each slide's card ID@version, model, and tier.

**Steps:**
1. Confirm every slide in the batch has a corresponding receipt file with status = complete and a locally stored image file (never review from a Kie.ai resultUrl -- URLs expire).
2. Run the Rotation Engine compliance check: lay all slides side by side in the order specified in the manifest. Verify: (a) foundation block is consistent across all slides, (b) variant assignments match the manifest, (c) no two consecutive slides share the same variant unless the style system permits it, (d) transition/divider slides fall at the positions specified.
3. Visual coherence check beyond the Rotation Engine: assess the deck as a sequence. Check compositional energy, color proportions, and decorative element intensity for consistency.
4. Flag any slides failing cohesion review: record the slide number, the specific violation, and the corrective instruction for the Generation Operator. Log the flag in the manifest's status column.
5. Submit flagged slides back to the Generation Operator with the corrective instruction. Non-flagged slides are staged for Fidelity Tester review.
6. When all flagged slides have been regenerated and pass re-review, confirm the full deck batch to CDO as cohesion-cleared. Hand the complete batch to Fidelity Tester for the 12-dimension style-fidelity pass.

**Outputs:** Cohesion-cleared deck batch handed to Fidelity Tester; all cohesion flags and regenerations logged in the manifest receipt file.
**Hand to:** Fidelity Tester (12-dimension style fidelity review). Cohesion review and fidelity testing are sequential, not parallel.
**Failure mode:** If more than 20% of slides in a batch fail cohesion review, halt, diagnose the root cause, and address it before re-running. Escalate to CDO if root cause is unclear.

---

### SOP 9.5 -- [SOP-DIU-611] Graphics-Presentations Deck Boundary Contract

**ZHC SOP.** Wraps PPT-ANALYSIS-SOP §§3B-3C; `powerpoint-designs/_RULES.md`; `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`.
**Library-version pin:** PPT-ANALYSIS-SOP v1.0, CLIENT-WEBINAR-DECK-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Every time a deck request is received, before manifest assembly begins. Also run when a routing dispute arises between the DIU and the Presentations department.
**Frequency:** Every deck request (step 1 is a quick decision; full procedure only when ambiguous).
**Inputs:** Deck brief from CDO including deck purpose, audience, any existing style reference, and client context.

**Steps:**
1. Apply the deck type decision table:

   | Deck type | Routing verdict | Owner |
   |---|---|---|
   | Webinar / funnel / virtual event (5 contracted archetypes, white-base, brand accents) | Presentations dept -- CLIENT-WEBINAR-DECK-SOP | Director of Presentations |
   | Strategy deck, brand deck, or campaign deck whose style must match an analyzed client/brand visual system | DIU -- PPT-ANALYSIS-SOP + Rotation Engine | Deck Systems Specialist |
   | Sales proposal, capability presentation, or investor pitch with no specific visual style ID | Presentations dept (narrative + layout) with optional DIU style imagery (strategy b, background panels only) | Director of Presentations primary; CDO requests style imagery via SOP-DIU-612 |
   | Training / onboarding deck | Presentations dept unless the brief specifies a brand deck style system | Director of Presentations |
   | Ambiguous (does not cleanly fit a row above) | Escalate to Director of Presentations for arbiter decision -- log the decision in this deck's project record | Director of Presentations decides; logged |

2. For routing verdicts that land in the DIU, confirm that the text strategy is set: strategy (a) = text generated into slide imagery (required for audience/webinar decks - but those must not reach this step; see the routing interlock in step 1 above); strategy (b) = background-only with text-clear zones, editable text overlay added by Presentations - valid ONLY for confirmed non-audience DIU-routed decks. Do NOT default to strategy (b) for audience or webinar decks.
3. **Hard rules that override all other routing logic:**
   - **ROUTING INTERLOCK (coded hard stop):** Audience decks, webinar decks, funnel decks, and virtual event decks CANNOT proceed on the DIU strategy-(b) pipeline. Halt immediately and route to CDO for forwarding to the Presentations Director. Proceeding past this interlock will produce an AUTO-FAIL at final QC.
   - DIU-contracted PPT-category foundation blocks are NEVER overridden by Slide Image Creator prompts.
   - The only two legal crossings between DIU and Presentations pipelines are: (a) the Brand Steward consuming a PPT-category style card's foundation block as a STYLE BLOCK input within the CLIENT-WEBINAR-DECK-SOP, and (b) DIU strategy-(b) background-only imagery handed to Presentations for editable text overlay on confirmed non-audience decks only.
4. If the Director of Presentations is required as arbiter (ambiguous deck type), route through CDO -- do not contact the Presentations department directly without CDO awareness.
5. Log all non-trivial routing decisions in the deck's project record with: the decision, the deciding party, and the date.

**Outputs:** Deck routed to the correct pipeline with documented decision. For DIU-routed decks, Slide Manifest assembly (SOP 9.2) proceeds. For Presentations-routed decks, brief is handed to CDO for forwarding.
**Hand to:** CDO for forwarding to Presentations dept (if Presentations-routed) OR proceed to SOP 9.1/9.2 (if DIU-routed).
**Failure mode:** If the Director of Presentations disputes a DIU routing decision after manifest assembly has begun, halt generation immediately and escalate to CDO. Do not continue a disputed deck run. CDO is the final arbiter.

---

*SOPs owned: [SOP-DIU-201], [SOP-DIU-202], [SOP-DIU-611]. sop_count: 5 (including SOP 9.3 and SOP 9.4 as operational non-vendor numbered SOPs).*
