# SOPs Mirror -- Director of Presentations

**Source:** presentations/director-of-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Brief Ingest and Validation

**When to run:** As soon as the Brainstorming Buddy (ROLE-17) hands off working/copy/deck_brief.json with brief_locked: true.

**Inputs:**
- working/copy/deck_brief.json (locked, owner-signed, delivered by ROLE-17)

**Steps:**
1. Read working/copy/deck_brief.json in full.
2. Verify: brief_locked = true AND owner_confirmed = true are both present. If either is false or missing, hand the brief BACK to the Brainstorming Buddy with the exact gap; the Director does NOT re-interview the owner.
3. Verify every mandatory variable is present (see deck_brief.json mandatory checklist: interview_depth, GOAL, CTA_ACTION, AUDIENCE, TRANSFORMATION_PROMISE, TARGET_FEELING, TONE, OFFER_NAME, PRICE_MODE, FINAL_PRICE, DURATION_MIN, REPRESENTATION_MIX, plus PRICE_ANCHOR when PRICE_MODE = drop). If any mandatory variable is missing, hand the brief BACK to the Brainstorming Buddy with the exact missing field list. The Director does NOT fill discovery gaps itself.
4. Copy all brief variables into working/copy/intake.json for backward compatibility with downstream specialists. The brief is authoritative; intake.json is the generated mirror.
5. Proceed to SOP 9.2 (Echo Protocol and Mission PRD Gate).

**Outputs:**
- working/copy/intake.json (populated from deck_brief.json, interview_confirmed: true)

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
5. Write both the ECHO and the PRD to working/copy/mission_prd.json.
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

4. Apply the master SOP Section 4.2 proven flow. The proven deck runs SEVEN sections with on-screen progress labels ("SECTION 3 OF 7"). This is the narrative the allocation table serves:

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

**Hand to:** Typography Architect (ROLE-18, Phase 1.5) and Brand Steward (LOGO_URL lock); THEN Slide Image Creator (Phase 2 prompt authoring, after the treatment table exists). Post-Phase-6: Presenter's Guide Specialist (ROLE-19), Presenter's Speech Writer (ROLE-20) + Fish Audio / Expression Specialist (ROLE-21), and Presenter Coach (ROLE-14) for the speaker-facing deliverables and audio demo.

**Failure mode:** If the operator requests changes to the copy, send the copy back to the Slide Copywriter with the exact change instructions. Re-run Phase 1Q QC after changes. Present the revised copy to the owner again. Do not skip the re-QC step even for minor changes.

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
4. For Phase 4 (image generation): submission runs in waves of 20 slides with 15-second sleeps between waves (= 2 RPS cap per master SOP). Dispatch the Slide Submitter as a single detached agent. NEVER split submission across multiple agents (creates rate-cap violations).
5. For Phase 5 (image QC): dispatch up to 5 QC agents in parallel. Each scores a non-overlapping batch of images.
6. Log every dispatch event in working/checkpoints/dispatch_log.json with: agent_type, assigned_slides, dispatched_at, status.

**Outputs:**
- working/checkpoints/phase2_dispatch.json
- working/checkpoints/dispatch_log.json

**Hand to:** Next phase as appropriate (each phase's specialist receives its dispatch record)

**Failure mode:** If a dispatched agent does not produce its checkpoint within 30 minutes, the Director checks the agent's working directory for partial output, then either resumes from the checkpoint or re-dispatches the failed slice. Never re-dispatch a slice that already has a complete checkpoint (idempotency rule).

---
