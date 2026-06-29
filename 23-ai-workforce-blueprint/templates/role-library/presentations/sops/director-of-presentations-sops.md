# SOPs Mirror -- Director of Presentations

**Source:** presentations/director-of-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Brief Ingest and Validation

**When to run:** As soon as the Brainstorming Buddy (ROLE-17) hands off working/copy/deck_brief.json with brief_locked: true.

**NET-NEW REQUEST WITHOUT A LOCKED BRIEF (intake-first guard):** If a net-new owner deck request arrives directly here WITHOUT a locked brief, do NOT improvise an inline question batch and do NOT start building. Dispatch ROLE-22 (first-time onboarding) then ROLE-17 (Brainstorming Buddy) to run the binding CLIENT-WEBINAR-DECK-SOP.md section 0.5 Client Intake Conversation Contract: the quick-vs-in-depth CHOICE is offered FIRST, then one question at a time, never a batch (AF-INTAKE-BATCH). The Director never interviews the owner itself and never dumps a question batch.

**Inputs:**
- working/copy/deck_brief.json (locked, owner-signed, delivered by ROLE-17)

**Steps:**
1. Read working/copy/deck_brief.json in full.
2. Verify: brief_locked = true AND owner_confirmed = true are both present. If either is false or missing, hand the brief BACK to the Brainstorming Buddy with the exact gap; the Director does NOT re-interview the owner.
3. Verify every mandatory variable is present (see deck_brief.json mandatory checklist: interview_depth, GOAL, CTA_ACTION, AUDIENCE, TRANSFORMATION_PROMISE, TARGET_FEELING, TONE, OFFER_NAME, PRICE_MODE, FINAL_PRICE, DURATION_MIN, REPRESENTATION_MIX, plus PRICE_ANCHOR when PRICE_MODE = drop). If any mandatory variable is missing, hand the brief BACK to the Brainstorming Buddy with the exact missing field list. The Director does NOT fill discovery gaps itself. **Two-prices guard:** `EVENT_PRICE`/`ACCESS_FREE` (free or paid to ATTEND) and `FINAL_PRICE`/`pitch_included` (the OFFER sold at the end) are INDEPENDENT fields. NEVER infer `FINAL_PRICE` from a free event; if `ACCESS_FREE: true` arrives with `pitch_included: true` but `FINAL_PRICE` is missing or 0, hand the brief BACK to the Brainstorming Buddy for the offer price (do NOT default it to 0). A `free_only_close: true` brief requires the owner's explicit sign-off recorded in the brief.
4. Copy all brief variables into working/copy/intake.json for backward compatibility with downstream specialists. The brief is authoritative; intake.json is the generated mirror.
4a. **Propagate the audience-mode, deliverable bundle, AND persuasion intelligence from a content-to-presentation source brief, when present.** If the run originated from the Content-to-Presentation Architect (ROLE-23) and a `source_brief.json` accompanies the deck brief, carry these into intake.json:
   - `presentation_mode` (one-person / general), `recipient_name` (one-person only)
   - `deliverable_bundle` (deck + Presenter guide in portable-document format + one-page infographic checklist), `checklist_items`
   - **Persuasion-intelligence propagation (MANDATORY -- satisfies the mandatory-variable check in step 3 FIRST):** map the `persuasion_intelligence` block from `source_brief.json` onto `intake.json` mandatory variables BEFORE routing any missing field to the Brainstorming Buddy: `transformation_promise` -> TRANSFORMATION_PROMISE; `primary_objection` -> PRIMARY_OBJECTION; `goal` -> GOAL; `cta_action` -> CTA_ACTION; `target_feeling` -> TARGET_FEELING; `tone_detected` -> TONE (owner-overridable at the Brainstorming Buddy SOP 9.0 -- mark as pre-seeded, not locked); `hook_candidate` -> HOOK seed for the Hook Strategist; `offer_intelligence.offer_name` -> OFFER_NAME; `offer_intelligence.price_mode` -> PRICE_MODE; `offer_intelligence.final_price` -> FINAL_PRICE; `offer_intelligence.price_anchor` -> PRICE_ANCHOR; `offer_intelligence.offer_stack` -> OFFER_STACK; `offer_intelligence.vip_tier` -> VIP_TIER; `proof_assets` -> PROOF_ASSETS (feed to ROLE-04 and Slide Copywriter).
   - **Critical reconciliation:** the mandatory-variable check in step 3 (GOAL, CTA_ACTION, TRANSFORMATION_PROMISE, etc.) HARD-RETURNS the brief to the Brainstorming Buddy for any field that is missing. When a converter `source_brief.json` is present, those mandatory variables are satisfied FIRST from `persuasion_intelligence` (using the mapping above). ONLY the fields listed in `source_brief.json.persuasion_intelligence.fields_absent_in_source` PLUS the always-Buddy audience/representation fields (REPRESENTATION_MIX, AUDIENCE_COMPOSITION_NOTE, VISUAL_MIX, DARK_OK, GROUNDED_CONTENT) are sent to the Brainstorming Buddy. Pre-seed the Buddy with the fields that ARE extracted so it CONFIRMS rather than re-interviews. This is the point of the fix: the source's own answers are not thrown away and re-asked.
   - The `presentation_mode` drives the mode-aware privacy treatment, the personalization, and the tone for the whole build; it is distinct from this Director's Mode A / Mode B (independent axes). In one-person mode, propagate the personalized-cover and personalized-closing requirements to the Slide Copywriter, Typography Architect, and Slide Image Creator; in general mode, the cover and closing are generic.
   - With no source brief, default `presentation_mode` to general and the bundle per the deck brief's DELIVERABLE_SET; add the one-page infographic checklist whenever a content-to-presentation source brief requested it.
4b. **Capture the definitive `audience_mode` and `target_talk_minutes` into intake.json (ADDITIVE -- both are non-defaultable build-stopping fields, enforced by `build_deck.py` `_chk_intake`).** These are in ADDITION to the existing `presentation_mode` axis (one-person / general), not a replacement for it.
   - **`audience_mode` (mandatory; one of `STANDARD` / `PERSONAL` / `GENERAL`):** the three definitive audience modes.
     - `STANDARD` -- the deck is NET-NEW, built from a brainstorm (no client-supplied source content).
     - `PERSONAL` -- the deck is built from the CLIENT'S OWN content for a NAMED recipient. PERSONAL is the only NAMED mode, so it REQUIRES `recipient_name`. Propagate the personalized cover and closing exactly as the existing one-person `presentation_mode` does.
     - `GENERAL` -- the deck is built from the CLIENT'S OWN content but DE-IDENTIFIED (no named recipient; names and identifying specifics are removed / generalized).
     Map a ROLE-23 converter origin to `PERSONAL` (when a recipient is named) or `GENERAL` (when de-identified); a pure brainstorm origin is `STANDARD`. If `audience_mode` is absent, the build HALTS at intake (the Director asks the owner which of the three it is). There is NO default audience_mode.
   - **`target_talk_minutes` (mandatory; positive number):** the speaking length the owner wants. It feeds the duration-sizing doctrine below and is read by the speech-length gate. If absent, the build HALTS at intake. (Where the existing `DURATION_MIN` variable is present it carries the same minutes; `target_talk_minutes` is the canonical field the renderer and the speech-length gate read.)
   - **DURATION-SIZING DOCTRINE (sizing follows the talk length, not the reverse):** the slide count, the on-slide copy density, AND the presenter speech are all sized to `target_talk_minutes`, paced at the verified **130 words per minute** standard (the Presenter Speech Writer's exposed, tunable rate). `slide_count_final = max(target-sized slide count, source_slide_count)` (the anti-compression coverage floor still applies, Mode B add-only). The presenter speech is budgeted at `target_talk_minutes x 130 wpm` minus the mandatory pause budget, exactly as the Presenter Speech Writer SOP 9.1 specifies.
   - **SPEECH-LENGTH GATE (AF-SPEECH-SHORT; fails SHORT):** once the presenter speech exists, its word count MUST be at least `target_talk_minutes x 120 wpm` (120 is the low end of the verified 120-140 absorption band; a script below it does not fill the requested duration). A speech under that floor is an AF-SPEECH-SHORT auto-fail and is routed back to the Presenter Speech Writer to lengthen. This is enforced by `build_deck.py` `_chk_speech_length` (conditional -- it fires once the speech is written, never blocking the pre-speech render) and is a DECK-level row in the MASTER QC auto-fail ruleset Section 5.
4c. **(Decisions 1C + 2A) Capture the three Goal-4 intake fields into intake.json (all build-stopping):**
   - **`asset_intake_question_asked` (mandatory boolean; true once the Brainstorming Buddy asked the ASSET BRANCH).** Persist it to intake.json. The gate **AF-ASSET-QUESTION-MISSING** (`build_deck.py` `_chk_asset_question`) fails any deck whose intake does not record `asset_intake_question_asked: true`. If the client provided materials, also set `assets_provided: true` (else `false`) and carry the captured items forward to the Media-Librarian asset-ingest step.
   - **`pitch_included` (mandatory boolean; NON-DEFAULTABLE).** Persist the explicit yes/no the client gave to the PITCH BRANCH. The gate **AF-PITCH-FLAG-UNSET** (`_chk_pitch_flag`) fails any deck with no boolean `pitch_included`. NEVER infer it; NEVER force a pitch.
     - If `pitch_included: false` (PITCHLESS, first-class): DO NOT dispatch the Offer Price Strategist; the arc walks the canonical sections MINUS the offer/ladder/guarantee/scarcity/close beats; no `price_ladder.json` is produced. The gate **AF-PITCH-LEAK** (`_chk_pitch_leak`) then fails the deck if ANY pitch/price/offer/ladder/re-pitch content leaks in.
     - If `pitch_included: true`: the offer arc is required and **AF-PITCH-MISSING** (`_chk_pitch`, now CONDITIONAL on `pitch_included:true`) enforces the value-stack -> anchor -> price-ladder -> re-pitch beats.
4d. **(Decision 1C) When `assets_provided:true`, dispatch the Media-Librarian asset-ingest step BEFORE Phase 2.** It classifies each provided asset, uploads it to a stable public URL, and writes `working/copy/assets_manifest.json` with a per-asset `public_url` + `consumed_by` (brand-steward and/or slide-image-creator). If the client uploaded a rough/old deck, the Media-Librarian's scratch-deck parser extracts its content/structure into `working/copy/scratch_seed.json`. Gates: **AF-MANIFEST-UNREFERENCED** (provided assets must be provably consumed) and **AF-SCRATCH-PARSE-SKIPPED** (an uploaded deck must be parsed + seed the PRD). The interview still runs in full — the scratch deck only SEEDS the PRD, it never replaces the client's answers.
5. Proceed to SOP 9.2 (Echo Protocol and Mission PRD Gate).
5a. **Dispatch ROLE-04 Deep Research Specialist as Phase -0.5 (MANDATORY).** After the brief lock (step 5) and after SOP 9.2 PRD approval, dispatch ROLE-04 as Phase -0.5. Supply the locked `working/copy/deck_brief.json` (or `source_brief.json` when originating from ROLE-23). BLOCK: do not dispatch Phase B+ (Hook Strategist) until `working/research/brief-[DECK_SLUG].md` exists on disk and its header records `research_complete: true`. On receipt of the completed Research Brief, route ALL twelve categories (A-L) as follows:
   - Category A (Niche Deck Structures) -> Director (informs arc allocation, SOP 9.4)
   - Category B (Pricing & Value Benchmarking) -> Offer Price Strategist (Phase 1)
   - Categories C and D (Statistics + External Corroboration) -> Slide Copywriter (Phase 1)
   - Category E (`grounded-content-[DECK_SLUG].json`) -> Slide Image Creator (Phase 2)
   - Category F (`design-brief-[DECK_SLUG].md`) -> Typography Architect (Phase 1.5) AND Slide Image Creator (Phase 2)
   - Category G (Credible Attributable Quotes) -> Slide Copywriter (Phase 1; feeds "who says so" beats and the Wall of Wins)
   - Category H (Fact-Validation Ledger) -> QC Specialist AND Slide Copywriter (Phase 1; every number on a slide must be VERIFIED in the Category H ledger before the prompt is written)
   - Category I (Objection Research) -> Slide Copywriter AND Devil's Advocate (Phase 1; pre-load objection-handling beats with sourced rebuttals)
   - Category J (Social-Proof Patterns) -> Slide Copywriter (Phase 1; shapes how proof is framed in Wall-of-Wins and testimonial slides)
   - Category K (Persuasion-Framework Validation) -> Director AND Slide Copywriter (Director uses it to validate the arc; Copywriter uses it for the teaching and close sections)
   - Category L (Compliance Flags) -> Director AND Devil's Advocate (Director flags any compliance-sensitive claim before Phase 1; Devil's Advocate monitors throughout)
   If the brief carries `external_proof_count: 0` (GP-8 ALERT), surface to the operator before Phase 1 for a supply-or-approve decision. Categories G, H, I, K, and L are MANDATORY for the research brief to be considered complete (AF-RESEARCH-GATE); a brief that omits any of these categories routes back to ROLE-04 for completion before Phase 1 proceeds.

5b. **Dispatch ROLE-04 again for Phase 3.5 Research-to-Slide Mapping (AFTER the arc, BEFORE copy).** Once the Signature Presentation Architect has locked `working/copy/arc_allocation.json`, dispatch ROLE-04's SOP 9.5 to produce `working/research/research_map.json` — the per-slide assignment of the already-gathered facts/quotes/stats. This is a short second pass (the heavy discovery already ran at Phase -0.5); its job is to map research to SPECIFIC slides so the Slide Copywriter writes copy ON TOP of mapped research instead of funnelling everything to the proof beat. BLOCK Phase 4 (copy) until research_map.json exists. The gate **AF-RESEARCH-WEAVE** (`_chk_research_map`) then fails any deck that weaves a mapped item into fewer than 60% of non-exempt content slides, whose copy does not actually carry the assigned anchors, or that draws on fewer than 8 distinct items — research woven ACROSS the deck, the #1 fidelity requirement.

**Outputs:**
- working/copy/intake.json (populated from deck_brief.json plus, when originating from ROLE-23: `source_brief_origin: "content-to-presentation-architect"`, `presentation_mode`, `recipient_name`, `deliverable_bundle`, `checklist_items`, AND all propagated persuasion-intelligence variables -- TRANSFORMATION_PROMISE, PRIMARY_OBJECTION, GOAL, CTA_ACTION, TARGET_FEELING, TONE, HOOK seed, OFFER_NAME, PRICE_MODE, FINAL_PRICE, PRICE_ANCHOR, OFFER_STACK, VIP_TIER, PROOF_ASSETS -- mapped from `source_brief.json.persuasion_intelligence`; interview_confirmed: true)

**Hand to:** SOP 9.2 (Echo Protocol and Mission PRD Gate)

**Failure mode:** If the Brainstorming Buddy does not acknowledge the returned brief within 1 hour, escalate to the Master Orchestrator. The Director never re-interviews the owner under any circumstance; gap-filling is the Brainstorming Buddy's job.

---

### SOP 9.2 -- Echo Protocol and Mission PRD Gate

**When to run:** Immediately after intake.json is complete and interview_confirmed = true.

**Inputs:**
- working/copy/intake.json (complete)
- workspace SOUL.md and USER.md (for mission alignment check)

**Steps:**
1. Write the ECHO: a 3-5 sentence paragraph in plain language that restates the deck's mission. Format: "This deck is for [AUDIENCE]. It presents [OFFER] at [FINAL_PRICE]. It will [TRANSFORMATION_PROMISE]. The owner's primary goal is [GOAL]. The audience's biggest objection is [OBJECTION]."
2. **Declare the MODEL MANIFEST** in the echo (per master SOP Section 9.0). Include it as a named block in the echo message and in the PRD:
   ```json
   {
     "image_platform": "kie.ai",
     "image_model_t2i": "gpt-image-2-text-to-image",
     "image_model_i2i": "gpt-image-2-image-to-image",
     "resolution": "2K",
     "aspect_ratio": "16:9",
     "authorized_by": "<operator>",
     "date": "<run date>"
   }
   ```
   Save this to `working/checkpoints/model_manifest.json`. The operator's confirmation of the echo IS their authorization of this manifest. Any model change the operator wants must be declared here at echo time; agents never improvise a model change mid-run.
3. Write the PRD (1 page max). Required fields: deck_slug, client_slug, target_audience, offer_name, final_price, anchor_price (must be >= 3x final_price), transformation_promise, primary_objection, hook (one sentence -- stands on 3-4 DEDICATED pure-typography A4 slides, ~4-5 appearances max, never 2 consecutive, never a footer on every slide; over-stamping is the #1 defect, STRIP excess rather than pad), `source_slide_count` (integer; in Mode B = the count of existing source slides the client provided; in Mode A = 0), slide_count_target, style_references, qc_threshold (always 8.5), model_manifest (reference to the confirmed manifest file), and assumptions_list (any items flagged assumed: true from intake).
4. Run the Improvement Pass: read the PRD back against intake.json. Identify any gap. Fix it. Repeat once.
3z. **(Decision 1C) Fold the scratch-deck seed into the PRD when present.** If `working/copy/scratch_seed.json` exists (the Media-Librarian scratch-deck parser ran on an uploaded rough/old deck), read it and fold its extracted titles/structure/claims into the Mission PRD as a STARTING POINT, then set `seeded_from_scratch_deck: true` (and a `scratch_seed_ref`) in mission_prd.json. The client's interview answers remain authoritative — the seed never overrides them. The gate **AF-SCRATCH-PARSE-SKIPPED** verifies a parsed scratch deck actually reached the PRD.
4a. **Build the CHECKLIST OF PROMISES (required component 10: "a checklist for an AI is a list of promises").** Before any agent says "done," it walks its OWN checklist; that checklist is a list of promises. Write `checklist_of_promises` into mission_prd.json: an explicit list of every promise this run must keep, with the operator's TEN required presentation components (master Section 4.4) as named line items -- (1) the Promise leads, (2) the Hook sung on EXACTLY 3 to 4 DEDICATED pure-typography slides and nowhere else, never a footer (the banded ceiling that replaced the retired >= 7x floor), (3) a "who says so" external-proof beat woven between the drops, (4) a Wall of Wins slide near the close, (5) one big idea per slide, (6) a Guarantee beat, (7) a real Scarcity beat in the close, (8) a short-term-fix-vs-long-term-identity Story Arc beat, (9) the gradual spread price ladder, (10) this checklist itself walked before delivery -- plus the run-specific promises from the PRD. Confirm this checklist is checked at every gate; the final-deck QC PASS artifact (qc-specialist SOP 9.5 structural-completeness block) is the proof the checklist was walked. No "done" is accepted while any promise on this list is unverified.
5. Write the ECHO, the PRD, and the `checklist_of_promises` to working/copy/mission_prd.json.
6. Send the ECHO + PRD (including the manifest block) to the operator as a Telegram message via openclaw message send. Ask: "Does this match your vision? Reply YES to proceed, or tell me what to change."
7. WAIT for explicit written confirmation. Do not proceed to Phase 1 until received. Record the confirmation as `prd_approved_by`, `prd_approved_at`, and `prd_approval_message` in mission_prd.json.

**Outputs:**
- working/copy/mission_prd.json (echo + PRD + confirmation record)

**Hand to:** SOP 9.3 (Mode Selection and Enhancement Gap Analysis), then SOP 9.4 (Slide-Count Math)

**Failure mode:** If the operator does not respond within 2 hours, send a follow-up reminder. If no response after 4 hours, log the timeout in run_ledger.json and notify the operator: "Run is paused at PRD gate. Awaiting your confirmation to proceed."

---

### SOP 9.3 -- Mode Selection and Enhancement Gap Analysis

**When to run:** After PRD is approved. Determines whether the run is Mode A (build from scratch) or Mode B (augment an existing deck).

**Inputs:**
- working/copy/mission_prd.json (approved)
- Any existing deck assets the client has provided (slides, outlines, partial copy)

**Steps:**
1. Evaluate the incoming assets. If the client provided no prior deck content -> Mode A. If they provided an existing deck or outline -> Mode B.
2. For Mode A: record `mode: "A"` AND `source_slide_count: 0` as a TOP-LEVEL field in mission_prd.json. Proceed to SOP 9.4.
3. For Mode B:
   a. Inventory the existing content: how many slides exist? What copy is present? What images (if any)? Record the integer count of existing source slides as the TOP-LEVEL field `source_slide_count` in BOTH mission_prd.json AND enhancement_gap.json. This is the anti-compression floor: the output deck must contain AT LEAST `source_slide_count` slides (Mode B is ADD-only; never reduce below it).
   b. Build the Enhancement Gap: a table with one row per existing slide. Columns: slide_number, existing_headline, existing_body, enhancement_needed (ADD / PROPOSE / image-only / none), notes.
      - **ADD**: new slides to insert (hook slides, pain slides, proof/white-paper slides, ladder slides, roadmap slides, quote slides, cost-vs-value slides). The client's original content slides are NOT in this category.
      - **PROPOSE**: a suggested change to an existing slide's copy or structure. These are proposals only -- they are reported to the owner in the gap analysis report and may NOT be applied without explicit per-substitution owner approval. The client's words are never rewritten without that approval on a per-slide, per-change basis.
      - **image-only**: the client's copy stays verbatim (typo fixes only, flagged); only the visual treatment is redesigned to the premium standard.
      - **none**: slide is already compliant; no change.
   c. Record the gap table in working/copy/enhancement_gap.json.
   d. The Mode B gap analysis report (sent before any change is made) must list: (i) every ADD slide and its purpose, (ii) every PROPOSE change and the exact wording being proposed vs. the client's original, and (iii) every image-only redesign. The owner approves the full list before any work begins.
   e. After owner approval, ADD new slides and execute approved PROPOSE substitutions. Never change a word on any existing slide beyond approved substitutions and flagged typo corrections.
   f. Record `mode: "B"`, `enhancement_gap_file: "working/copy/enhancement_gap.json"`, and the top-level `source_slide_count` integer in mission_prd.json (and confirm the same `source_slide_count` is written in enhancement_gap.json).
4. For both modes: confirm the STYLE BLOCK source. If the Brand Steward has already produced a STYLE BLOCK for this client, load it. If not, dispatch the Brand Steward now (do not proceed past this step without a STYLE BLOCK).

**Outputs:**
- mission_prd.json updated with mode, enhancement_gap_file (Mode B only)
- STYLE_BLOCK confirmed or Brand Steward dispatched

**Hand to:** SOP 9.4

**Failure mode:** If the client's existing deck is in a format that cannot be parsed (e.g., binary PPTX without text extraction), request the client provide a plain-text export. Log the blocker in run_ledger.json.

---

### SOP 9.4 -- Slide-Count Math and Arc Allocation

**When to run:** After mode is confirmed and PRD is approved.

**Inputs:**
- mission_prd.json (slide_count_target OR presentation_duration_minutes)
- master SOP slide-math table (see below)

**Steps:**
1. If the client provided a duration in minutes (not a slide count), convert using the master SOP table (Section 4). This table governs and cannot be overridden by agent judgment:

   | Duration | Target slide count | HARD MAX |
   |----------|--------------------|----------|
   | 10 min | 12 to 15 | 15 |
   | 15 min | 18 to 22 | 25 |
   | 30 min | 35 to 42 | 45 |
   | 45 min | 50 to 58 | 60 |
   | 60 min | 60 to 70 | 75 |
   | 90 min | 70 to 85 | 90 |
   | 120+ min | 80 to 90 | **90 (Mode A target/cap only)** |

   Rules from the master SOP:
   - The rate is roughly 1.3 to 1.5 slides per minute, tapering as duration grows. A three-hour presentation does NOT mean 300 slides. In Mode A (net-new), 90 is the target/cap for any deck; in Mode B this cap yields to `source_slide_count` (add-only -- see step 2).
   - Below 30 minutes, the Hormozi arc compresses: merge the origin story into 2 slides, run ONE secret instead of three, and keep the offer section proportionally intact (the pitch never gets cut). This compression NEVER deletes a client source slide in Mode B.
   - Propose the slide count from this table; the client confirms it during the intake echo. Record `SLIDE_COUNT`.

2. **Floor overrides ceiling (anti-compression).** Compute `SLIDE_COUNT_FINAL = max(duration_target, source_slide_count)`. The output deck MUST contain AT LEAST `source_slide_count` slides. This floor OVERRIDES the duration-based target/cap and the 90 Mode-A figure. Never delete a client slide to hit a duration cap. Mode B is ADD-ONLY: improve and expand, never reduce below `source_slide_count`. (Mode A has `source_slide_count == 0`, so the duration target/cap governs unchanged.) Record `slide_count_final` in mission_prd.json.

3. Allocate the arc using the master SOP Section 4.1 worked allocation table. Percentages from the arc produce fractions; use this pre-reconciled allocation for the common counts. For other counts, allocate proportionally, round, then add or remove slides from the Secrets sections (NEVER from the offer section) until the total matches `SLIDE_COUNT`:

   | Arc section | 45 slides | 60 slides | 75 slides |
   |---|---|---|---|
   | 1. Big Bold Promise | 1 | 1 | 2 |
   | 2. Painful Math | 2 | 2 | 3 |
   | 3. Real Problem reframe | 2 | 3 | 3 |
   | 4. Commitment slide | 1 | 1 | 1 |
   | 5. Origin story + authority | 3 | 5 | 6 |
   | 6. Social proof | 2 | 2 | 3 |
   | 7. For / NOT for | 2 | 2 | 3 |
   | 8. Secret #1 (teach, proof, action) | 5 | 7 | 9 |
   | 9. Secret #2 (teach, proof, action) | 5 | 7 | 9 |
   | 10. Secret #3 (teach, proof, action) | 5 | 7 | 9 |
   | 11. The Window / urgency logic | 1 | 2 | 2 |
   | 12. Recap | 1 | 2 | 2 |
   | 13. Transition to offer | 1 | 1 | 2 |
   | 14. Offer + price sequence | 9 | 12 | 15 |
   | 15. Guarantee + risk reversal | 1 | 2 | 2 |
   | 16. Bonuses | 2 | 2 | 2 |
   | 17. Final CTA + Q&A close | 2 | 2 | 2 |
   | **Total** | **45** | **60** | **75** |

   The offer section (rows 14 to 17) is never compressed below 10 slides on a 45+ slide deck. If `VIP_TIER` exists, it takes 1 to 2 slides inside row 14 (presented AFTER the core final price).

3a. **Walk the canonical arc (master SOP Section 4.2A, THE BLACKCEO SIGNATURE WEBINAR ARC).** The allocation table sizes the deck; the canonical arc is the named slide-by-slide JOURNEY you allocate INTO. It runs ten named sections in the operator's revealed order: A. Hook Open -> B. Care / See-Yourself -> C. The Promise -> D. Story -> E. Teaching (one big idea per slide, each carrying the hook and a light pitch) -> F. Proof: Who Says So + Wall of Wins -> G. The Offer (gradual spread ladder, value added at every drop) -> H. Guarantee -> I. Scarcity / Close -> J. Hook Callback. Each arc section maps to its components (the doctrine 4.3 plus the ten required components 4.4), the typography-and-standalone-art standard, and a QC gate (the full mapping is the Section 4.2A table). The ten named sections collapse onto the seven proven sections below; record the arc-section label on each slot in arc_allocation.json so the Copywriter and QC can trace every slide to its beat. Carry forward the connective-tissue rules (hook cadence ~10x from the first verse and woven the whole way through; proof woven between the drops; value ADDED at every drop; the light pitch distributed not back-loaded; a slide earns the next slide; section banner-in / emotional-punctuation-out; text-anchor variation; the slide is not the script; the designed emotional sequence that creates a Significant Emotional Experience; no em dashes; echo-then-build; enhance-don't-replace).

4. Apply the master SOP Section 4.2 proven flow. The proven deck runs SEVEN sections with on-screen progress labels ("SECTION 3 OF 7"). This is the narrative the allocation table serves, and it is how the ten canonical arc sections (step 3a) collapse onto the slide-count math:

   | Section | Slides (of 75) | What it does | Signature moves |
   |---|---|---|---|
   | 1. THE HOOK | 1 to 7 | Promise, future-pace, painful math, reframe, commitment | "[PROMISE]. [TIMEFRAME]." promise with objection-killer sub (illustrative -- substitute your DISCOVERY VARIABLES); "This is what [DESIRED_STATE] looks like" future-pace; "$[ANNUAL_LOSS] a year. Gone." empty-chairs math; "It's not your heart. It's your system." reframe; "Stay. I dare you." commitment dare |
   | 2. AUTHORITY & STORY | 8 to 15 | Origin, receipts, peer proof, identity | "I didn't wake up like this"; "I'm not a coach who read about it. I built it. I run it. I'm you."; then/now split; receipts row (press, revenue, centers); "Women who look like us" representation wall; "If they did it, so can you" closer |
   | 3. SECRET #1 | 16 to 24 | Belief shift on the MESSAGE | Section banner; "They're not ignoring you. Your message is wrong."; old-way/new-way split; the 4 Questions framework; verified result ("47 inquiries, one post, 7 days"); client win; 3-step action plan; vision slide; **slide 24: ANCHOR plant ("worth $[ANCHOR]+. Remember this number. Keep watching.")** |
   | 4. SECRET #2 | 25 to 35 | Belief shift on SPEED/system | "Fill seats in 7 days. Not 7 months."; silent-leak stat (95%); 72-Hour Rule; 5-step automated journey diagram; live-demo dashboard; sprint proof; doubter testimonial; 7-day roadmap; old/new contrast; **BUILDUP ("Imagine this running tonight") then slide 35: DROP 1 to $[DROP1] ("because you showed up live; this price does NOT leave this room")** |
   | 5. SECRET #3 | 36 to 43 | Belief shift on ECONOMICS/LTV | "One campaign. $[LOW_RANGE] to $[HIGH_RANGE] a month." (illustrative -- substitute your DISCOVERY VARIABLES); lifetime-value math ($[WEEKLY_VALUE]/wk x 52 x [YEARS] yrs = $[LTV_TOTAL] from ONE client); One Message/One Funnel/One Follow-up; live funnel proof; real revenue testimonial; the Window (12 to 18 months urgency logic); identity slide ("The CEO you're about to become"); recap ("You now know more than 95% of owners") |
   | 6. THE OFFER | 44 to 59 | Choice frame, offer, stack, ladder | "Two Choices" frame; "Go build it" takeaway close; "Stop building. Start owning."; offer reveal with MAGIC name ("[OFFER_NAME]"); one-promise slide; stack components one per slide, each named with a benefit and valued ($[ITEM_VALUE], $[ITEM_VALUE], $[ITEM_VALUE]...); VIP bonuses ($[ITEM_VALUE], $[ITEM_VALUE]); full stack recap with checkmarks; **callback slide ("I told you to remember that number. Here it is: $[STACK_TOTAL]")**; LTV justification ("1 client = $[ANNUAL_VALUE]/yr; pays for itself" -- illustrative, substitute your DISCOVERY VARIABLES); **BUILDUP ("This is the part that changes everything") then slide 51: DROP 2 to $[DROP2] ("because you believed")** |
   | 7. THE CLOSE + FINAL PUSH | 60 to 75 | Objections, drops, guarantee, proof, urgency, welcome | Objection kills ("I'm too busy" = you don't have the system; "Will it scale?"); Day 1 onboarding picture; student proof with compliance line; future-pace Day 31; **BUILDUP ("You didn't leave. That tells me everything.") then slide 65: DROP 3 to $[DROP3] on the price-tag motif**; conditional guarantee ("Fill 3 seats. Or I pay. AND I'll personally work with you until you do."); "1,000 times" receipts; Wall of Wins (6 named results); keep-guessing/build-the-system choice; final push ("This isn't just a webinar. This is your moment."); last call with door-closing urgency and join URL; fast-action bonuses that expire; **slide 73: FINAL, the full strikethrough tag ($[ANCHOR] / $[DROP1] / $[DROP2] / $[DROP3] all struck) revealing GA $[FINAL_PRICE] | VIP $[VIP_PRICE], 15-minute window**; full recap table with both prices; "You made it. Welcome to the family." celebration |

   Flow rules enforced in Phase 1:
   1. Every section opens with a banner/progress slide and closes with an emotional punctuation slide.
   2. Each Secret follows: claim -> problem/stat -> framework -> proof -> action plan -> vision.
   3. Proof appears within 2 slides of every claim. Named, located testimonials ("[NAME], [CITY]") with compliance disclaimers.
   4. The ladder spreads across sections (rungs near the 32/47/68/87/97% marks), every drop earns its reason, every drop follows a BUILDUP. **(Density-floor overhaul) The 8-slide MINIMUM-GAP FLOOR overrides the percentages:** every adjacent price beat is at least 8 slides apart (the proven 75-slide reference run: 11/16/14/8) and the ANCHOR lands near the one-third mark (25-45% depth), NEVER the back third. Do NOT jam the offer into the back third (the reference failure case 2/10 defect). If the percentages cram the ladder, lengthen the offer window or the deck so the floor is satisfiable. (AF-DEN-1/2.)
   5. Open loops plant early and close on screen with explicit callbacks.
   6. The deck talks TO one person in the client's voice, in second person, with the client's edge. TONE from intake governs every line.
   7. **(Density-floor overhaul) Reserve dedicated slots BEFORE checking section floors:** the 3 to 4 DEDICATED hook slides (at the named anchor beats); the PROMISES slide (before the anchor); the itemized VALUE-STACK slide (before Drop 1); the 4-to-7-slide RE-PITCH block (after FINAL); and the mandatory ONE-BIG-IDEA splits (a diagnosis+method+outcome = 3 slots, a value trio = 4 slots [one per value + a formula slide], a gap+reframe = 2 slots, four pains = 4 slots). Encode the hard splits so a value trio is never one slide and four pains are never a bulleted list.
   8. **(Density-floor overhaul) Exactly ONE Wall of Wins**, placed 4 to 6 slides before the offer (the gold-standard reference deck: 5) with a build-up run between, never jammed against it. It is real named past clients only, never a child future-pace, never a research footnote. (AF-DEN-6; definition in master SOP 5.5.1.)
   9. **(Density-floor overhaul) Section floors** (scaled to length; floors for a ~25-30 min, ~60-80 slide deck): hook+open >= 5, authority >= 4, teaching >= 18, proof >= 4, offer+ladder+stack+promises >= 14, re-pitch+close >= 5. A section below its floor fails (AF-DEN-8); add slides so the gaps and splits are satisfiable.

5. Write the arc_allocation.json to working/copy/arc_allocation.json with the reserved slots tagged: HOOK_SLIDE (x3-4), PROMISES, VALUE_STACK, RE_PITCH, WALL_OF_WINS, and the LADDER tags (ANCHOR/DROP1/DROP2/DROP3/FINAL with their BUILDUP slides), plus each one-big-idea split.
6. **(Density-floor overhaul) Run the density pre-check on the PLAN before releasing the arc:** verify all AF-DEN triggers are clear in the plan (8-slide gaps, anchor at one-third, BUILDUP before every DROP, value-stack before Drop 1, promises before anchor, Wall of Wins 4-6 before offer, re-pitch 4-7 after FINAL, section floors). Do NOT verify a hook count floor (the hook is a CEILING of 3-4 dedicated slides; more is an auto-fail, not a target). Do not release the arc to the Copywriter until the plan clears every AF-DEN trigger.

**Outputs:**
- mission_prd.json updated with slide_count_final and the canonical HOOK string
- working/copy/arc_allocation.json (with the reserved slots and split slots tagged)

**Hand to:** Slide Copywriter (Phase 1 copy write), Hook Strategist (anchor map), and Offer Price Strategist (price ladder choreography, concurrent)

**Failure mode:** If the client's stated slide count is impossible for the duration (e.g., 200 slides for a 30-minute presentation), push back with the master SOP math table above and recommend an achievable count. Record the negotiated count in mission_prd.json with a note. In Mode A (net-new), if the stated count exceeds 90 for any duration, push back: 90 is the Mode-A target/cap. In Mode B, the 90 figure is only a target/cap and YIELDS to `source_slide_count`: never reject or trim a client source deck that already exceeds 90 -- the floor (`max(duration_target, source_slide_count)`) governs, and the deck is add-only.

---

### SOP 9.5 -- Owner Approval Gate and Presenter-Notes Export

**When to run:** Phase 1A -- after Phase 1Q copy QC passes (>= 8.5 average). This gate is mandatory. No prompts are written until the owner approves the slide copy.

**Inputs:**
- working/copy/slides_copy.md (Phase 1 output, QC-passed)
- working/qc/copy_qc_report.json (showing >= 8.5 average)

**Steps:**
1. Compile the owner approval package. Contents: (a) the full slides_copy.md, (b) the QC score summary (average score + worst-scoring slide), (c) a note on what happens next ("Once you approve this copy, I will write one image prompt per slide and begin generation. No changes to copy will be accepted after approval without restarting the image phase.")
2. Send the package to the operator via openclaw message send. Use this exact question: "Here is the full slide copy for [DECK_SLUG], QC score [AVERAGE]/10. Do you approve this copy as-is? Reply YES to proceed, or list any changes you need."
3. WAIT. Do not begin Phase 2 until the operator replies YES (or equivalent affirmation).
4. Record the approval: `copy_approved_by`, `copy_approved_at`, `copy_approval_message` in working/copy/approval_record.json.
5. After approval, export presenter notes to working/copy/presenter_notes.json. One entry per slide: `{ "slide_number": N, "headline": "...", "presenter_note": "..." }`. The presenter note is drawn from the PRESENTER NOTE field in each slide's copy block.
6. **(Density-floor overhaul) Dispatch PHASE 1.5 before Phase 2:** dispatch the Typography Architect (ROLE-18) to lock the type system, the layout/archetype map, and the per-slide treatment table BEFORE any image prompt is written; the Brand Steward (ROLE-02) locks the single LOGO_URL in parallel. Phase 2 (Slide Image Creator) is BLOCKED until the three Typography Architect artifacts exist and the self-audit passes. This is the root fix for "typography was an afterthought": typography and layout are DECIDED before prompts exist.

**Outputs:**
- working/copy/approval_record.json
- working/copy/presenter_notes.json

**Hand to:** Typography Architect (ROLE-18, Phase 1.5) and Brand Steward (LOGO_URL lock); THEN Slide Image Creator (Phase 2 prompt authoring, after the treatment table exists). Post-Phase-6: Presenter's Guide Specialist (ROLE-19), Presenter's Speech Writer (ROLE-20) + Fish Audio / Expression Specialist (ROLE-21), and Presenter Coach (ROLE-14) for the speaker-facing deliverables and audio demo. **FINALLY (the last mile — see SOP 9.6B): dispatch the Delivery Concierge (ROLE-13).**

**Failure mode:** If the operator requests changes to the copy, send the copy back to the Slide Copywriter with the exact change instructions. Re-run Phase 1Q QC after changes. Present the revised copy to the owner again. Do not skip the re-QC step even for minor changes.

---

### SOP 9.6B -- Final-Hop Dispatch to the Delivery Concierge (the last mile)

**When to run:** ONCE, after final Phase-6 QC PASS and after ALL speaker-facing deliverables exist. This is the step that connects the assembled deck to the client. R9-F7: without it the orchestration graph completes at the speaker-facing deliverables and the delivery hop never fires.

**Inputs:**
- `final_deck_qc.json` (qc-specialist Phase-6 PASS, score >= 8.5)
- The OPERATOR build bundle dir (`~/Downloads/<client-slug>-<deck-slug>/`, the NINE `build_bundle_files` from build_deck.py) — guide + speech (`PRESENTERS-SPEECH.md/.pdf/-FISH-TAGGED.md`) + audio + infographic + teleprompter all present.

**Steps:**
1. **Verify the AF-DELIVER prerequisites** before dispatch: confirm the guide PDF, the speech (`PRESENTERS-SPEECH.pdf`), the audio MP3, the deck PDF, and the infographic all exist and are non-empty (these are the upstream inputs SOP 9.0 curates the five-file CLIENT package from). If any is missing, route back to its producing role — do NOT dispatch delivery on a partial bundle.
2. **Dispatch ROLE-13 Delivery Concierge** with `final_deck_qc.json` + the build bundle dir. The Concierge runs SOP 9.0 (curate the clean five-file client package + AF-DH1), SOP 9.1 (destination resolution), SOP 9.2 (multi-destination upload — the WHOLE five-file package, not just the pptx), SOP 9.4 (ground-truth verify), SOP 9.5 (teleprompter publish), SOP 9.3 (notify).
3. **Do NOT call the run "Done"** until ROLE-13 returns `delivery_complete: true` (Gates 1–5 in delivery-concierge.md all green; the mechanical `scripts/delivery_gate.py` enforcer passes). A run that stops at "deck assembled + QC passed" with no `delivery_complete` is an incomplete run (AF-DELIVER / AF-DELIVERY-COMPLETE).

**Outputs:**
- ROLE-13 `delivery_plan.json` + `delivery_complete: true` returned to the Director.

**Hand to:** Delivery Concierge (ROLE-13). The Director holds the run open until ROLE-13 confirms delivery.

**Failure mode:** If ROLE-13 reports the clean client package is missing/incomplete, or a destination cannot be verified, the run is NOT Done — block on the specific failing artifact/destination and re-dispatch only the failing hop. Never send a "done" notification before `delivery_complete: true`.

---

### SOP 9.6 -- Parallelization and Sequencing Strategy

**When to run:** At the start of Phase 2 (prompt authoring) and Phase 4 (image generation), and whenever dispatching multiple sub-agents.

**Inputs:**
- working/checkpoints/capacity_plan.json (from Step 0.5)
- Current phase and the list of specialist agents available

**Steps:**
1. Read capacity_plan.json. Identify: max_concurrent_agents, qc_agents_allowed, writer_agents_allowed.
2. For Phase 2 (prompt authoring): dispatch prompt writers in batches of min(writer_agents_allowed, 10). Each writer handles a slice of slides. Slices must not overlap. Record the assignment map in working/checkpoints/phase2_dispatch.json.
3. For Phase 3 (prompt QC): dispatch min(qc_agents_allowed, 10) QC agents. Each scores the same prompt independently. Average their scores. Scores < 8.5 trigger revision; revised prompts are re-scored before proceeding.
4. For Phase 4 (image generation): submission runs in waves of 20 slides with 10-second sleeps between waves (= the documented 20-requests-per-10-seconds cap per master SOP; source: https://docs.kie.ai/ Section 8, verified 2026-06-14). Dispatch the Slide Submitter as a single detached agent. NEVER split submission across multiple agents (creates rate-cap violations).
5. For Phase 5 (image QC): dispatch up to 5 QC agents in parallel. Each scores a non-overlapping batch of images.
6. Log every dispatch event in working/checkpoints/dispatch_log.json with: agent_type, assigned_slides, dispatched_at, status.

**Outputs:**
- working/checkpoints/phase2_dispatch.json
- working/checkpoints/dispatch_log.json

**Hand to:** Next phase as appropriate (each phase's specialist receives its dispatch record)

**Failure mode:** If a dispatched agent does not produce its checkpoint within 30 minutes, the Director checks the agent's working directory for partial output, then either resumes from the checkpoint or re-dispatches the failed slice. Never re-dispatch a slice that already has a complete checkpoint (idempotency rule).

---

## AF-DARK-SLIDE — No Dark Slides (AUTO-FAIL)

Slides MUST use LIGHT / bright backgrounds by DEFAULT. DARK or black-background slides are NOT ALLOWED unless the CLIENT EXPLICITLY requests a dark theme via the intake flag `client_dark_theme: true`. Light is the default; dark is opt-in by client request only.

- DEFAULT: Light / bright background slides
- ALLOWED dark: Only when `client_dark_theme: true` is set in working/copy/intake.json
- AUTO-FAIL: Any dark/black/near-black default background without `client_dark_theme: true`

**Director intake responsibility:** during the intake interview (SOP 9.1), explicitly ask whether the client wants a dark theme. Record `client_dark_theme: true` in intake.json ONLY when the client explicitly requests it. Default (no request = no flag = light backgrounds enforced). This gate is enforced mechanically by build_deck.py `_chk_no_dark_slides` at preflight.

**Failure message:** `AF-DARK-SLIDE: Dark/black background detected in prompts but client_dark_theme is not set. Light backgrounds are required by default.`

---

