# SOPs Mirror -- Presenter Coach -- Talk-Track Specialist

**Source:** presentations/presenter-coach.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Talk Track

**When to run:** After the PPTX assembly final QC has passed (>= 8.5 per master SOP Section 11.3). The approved slides_copy.md and presenter_notes.json must both exist before this SOP begins.

**Inputs:**
- working/copy/slides_copy.md (QC-passed, owner-approved, complete with PRESENTER NOTE on every slide)
- working/copy/intake.json (DURATION_MIN, TONE, HOOK, GOAL, CTA_ACTION, TARGET_FEELING, primary objection, OFFER_STACK, FINAL_PRICE, VIP_TIER, PRICE_MODE)
- working/copy/arc_allocation.json (section names, slide ranges, ladder positions: ANCHOR, BUILDUP, DROP1, DROP2, DROP3, FINAL)

**Steps:**

1. **Compute the time budget.** Divide DURATION_MIN by SLIDE_COUNT to get the average seconds-per-slide across the deck. Then apply the pacing model:
   - Hook section (Section 1 of 7): 1.5x the average (these slides carry more weight per minute; the audience is deciding whether to stay).
   - Authority and story section (Section 2 of 7): 1.3x average.
   - Each Secret section (Sections 3, 4, 5 of 7): 1.0x average (teach at pace; do not over-teach).
   - The Offer section (Section 6 of 7): 1.2x average (the price sequence needs breath; rushed drops lose conviction).
   - The Close section (Section 7 of 7): 0.9x average (momentum builds; the audience is either in or out).
   - Transitions between sections: budget 15 to 20 seconds each (6 transitions for a 7-section deck).
   - Record the per-slide time budget in working/presenter-coach/timing_model.json.

2. **Expand each PRESENTER NOTE into a timed talk-track entry.** For every slide, write a talk-track entry in this exact format:

   ```
   ## SLIDE NN -- [HEADLINE from slides_copy.md]
   SECTION: [section name]
   LADDER: [ANCHOR | BUILDUP | DROP1 | DROP2 | DROP3 | FINAL | none]
   TIME BUDGET: [N seconds]
   CUMULATIVE TIME: [MM:SS]
   TALK TRACK:
   [Full spoken narration -- 2 to 6 sentences. Written in the owner's TONE. This is what they SAY, not what the slide shows. Begin with an ACTION CUE if needed: "PAUSE here." / "Advance the slide." / "Hold this slide."]
   DELIVERY NOTE:
   [One sentence of coaching: pace, eye contact, gesture, emphasis, or silence. Examples: "Land the number then go quiet for 3 seconds." / "Say this directly to camera, not to the slides." / "Slow down on 'remember this number' -- make them write it down."]
   ```

   Hard rules for talk-track entries:
   - The talk track says what the presenter SAYS. The slide carries the one big idea; the talk track carries the narration. These must not duplicate each other (master SOP Section 4.3, rule 15).
   - The HOOK must appear at every slide tagged HOOK_REFRAIN: yes in slides_copy.md. On those slides, the talk track entry includes the hook line verbatim -- exactly as recorded in intake.json -- as its closing sentence.
   - On ANCHOR slides: the talk track includes the memory hook line verbatim and the explicit coaching note "say 'remember this number' slowly and let them write it down before advancing."
   - On BUILDUP slides: the talk track uses future-pacing language and ends on an open loop that the next slide (the DROP) closes. The owner does not advance the slide until they have landed the buildup.
   - On every DROP slide: the talk track states the earned-reason line verbatim (e.g., "because you showed up live"), then the new price, then goes silent for 2 to 3 seconds before advancing.
   - On FINAL slides: the talk track walks the owner through the full strikethrough sequence by name ("point to each struck price as you say it") before landing the real buy price.
   - On CTA slides: the talk track includes the complete CTA script -- the join URL stated aloud, the exact action ("go to [URL] right now, while we are still here"), and the urgency close.
   - Any [CLIENT TO SUPPLY] placeholder in the PRESENTER NOTE stays flagged in the talk track as "[OWNER: fill this in with your specific [result/testimonial/number] before going live]". Never fabricate.
   - No em dashes in any talk-track entry.

3. **Verify total timing.** Sum all TIME BUDGET fields. If the total deviates from DURATION_MIN by more than 10%, identify which sections are over or under and adjust the entry lengths proportionally. Do not cut the CTA section. Do not cut drop entries. If cuts are needed, tighten the Secrets teach narration first.

4. **Write the talk track** to working/presenter-coach/talk_track.md with a header block showing: DECK_SLUG, DURATION_MIN, SLIDE_COUNT, TONE, HOOK, FINAL_PRICE, VIP_PRICE (if applicable), and TOTAL_TIMED_MINUTES.

**Outputs:**
- working/presenter-coach/talk_track.md (one entry per slide, full timed narration)
- working/presenter-coach/timing_model.json (per-section time budgets)

**Hand to:** SOP 9.3 (Rehearsal Pack) -- the talk track is the source for the hook lines and transition cues in the run sheet.

**Failure mode:** If the PRESENTER NOTE field on any slide is blank or too vague to expand (fewer than 10 words), do not fabricate a talk track. Flag that slide with [INCOMPLETE PRESENTER NOTE: requires Slide Copywriter revision] in the talk_track.md entry and log the gap in working/presenter-coach/gaps.md. Notify the Director immediately. The Director routes the gap back to the Slide Copywriter. Do not deliver a talk track with unflagged blanks.

---

### SOP 9.2 -- Q&A Objection Prep

**When to run:** Concurrently with SOP 9.1 (after prerequisites are confirmed). The Q&A prep does not depend on the talk track being finished, only on the source documents being available.

**Inputs:**
- working/copy/intake.json (primary_objection field, OFFER_STACK, FINAL_PRICE, TONE, AUDIENCE, TARGET_FEELING)
- working/qc/devils_advocate_kill_list.md (the Devil's Advocate specialist's hardest challenges to the deck -- use these as the raw material for the hardest questions; if this file does not exist, proceed without it and note the absence)
- working/copy/slides_copy.md (proof assets actually on the deck, the guarantee language, the objection-handling slides)

**Steps:**

1. **Compile the objection universe.** Combine:
   - The primary objection from intake.json (this is always question 1).
   - Every objection the Devil's Advocate kill list raised (each becomes a candidate question).
   - Universal objections for the client's niche (derive from AUDIENCE and OFFER_STACK -- e.g., for a childcare business coach: "I'm too busy to add another program"; "I'm not tech-savvy enough"; "Will this work in my market?").
   - Price objections: one question per price tier that exists in the offer (base, VIP if applicable).
   - "What makes you different from X" (the competitive comparison question; every presenter faces this).

2. **Select the 10 hardest questions.** Prioritize: the questions the owner is most likely to dread, not the softballs. A question is "hard" if it could genuinely stall a sale or shake the owner's confidence if they are unprepared. Include at least one question that challenges the owner's credentials or authority, one that challenges the price, one about results ("can you prove it?"), one about fit ("is this for me?"), and one about timing ("why now?").

3. **Write a strong answer for each question.** Format:

   ```
   ### Q[N]: [The question, written exactly as the audience would ask it]

   **Why this question is hard:** [One sentence: the fear it triggers in the owner.]

   **Strong answer:**
   [2 to 4 sentences in the owner's TONE. Use the proof the deck already contains. Reference named testimonials, specific numbers, or the guarantee language where applicable. Do not invent proof that is not in the deck. If no proof exists for this specific objection, the answer pivots to the guarantee or the risk-reversal frame.]

   **Anchor line** (one memorable sentence to close the answer):
   "[The line the owner lands on and then goes quiet -- the version that sticks in the audience's mind]"

   **Coaching note:**
   [One sentence: eye contact, pace, posture, or framing advice for delivering this answer live.]
   ```

4. **Rules for Q&A answers:**
   - Every answer uses proof that is actually in the deck (slides_copy.md proof assets or the guarantee slide). No invented proof. If a [CLIENT TO SUPPLY] placeholder is unfilled, the answer says "I have a client who [result] -- I will share their full story when you connect with me after the session" and moves on.
   - The anchor line must not be a question. It is a confident declarative statement.
   - The tone of every answer matches the TONE from intake (a Tough Love deck gets Tough Love Q&A answers; a Calm Premium deck gets understated, confident replies).
   - The price objection answer always references the cost-of-inaction math from the deck (master SOP Section 4.3, rule 6) and the guarantee.
   - No em dashes anywhere in any answer or coaching note.

5. **Write the Q&A prep** to working/presenter-coach/qa_objection_prep.md with a header block: DECK_SLUG, DATE, TONE, primary_objection, source_documents used.

**Outputs:**
- working/presenter-coach/qa_objection_prep.md (10 questions + strong answers + anchor lines + coaching notes)

**Hand to:** SOP 9.3 (Rehearsal Pack) -- the 10 questions are drilled in the rehearsal session and the most critical anchor lines are referenced in the run sheet.

**Failure mode:** If the Devil's Advocate kill list does not exist and the intake primary_objection field is blank, the Q&A prep cannot be fully sourced. Flag this: produce the best 7 questions derivable from the OFFER_STACK and AUDIENCE fields, note the 3 unfilled slots as [REQUIRES: owner to identify top objections before webinar], and notify the Director. Do not skip the SOP -- deliver what you have with clear flags.

---

### SOP 9.3 -- Rehearsal Pack

**When to run:** After talk_track.md exists (SOP 9.1 complete) and qa_objection_prep.md exists (SOP 9.2 complete). This SOP synthesizes both into a single one-page run sheet.

**Inputs:**
- working/presenter-coach/talk_track.md (hook lines, section transitions, CTA script, timing)
- working/presenter-coach/qa_objection_prep.md (anchor lines from the 10 hardest questions)
- working/copy/intake.json (HOOK, DURATION_MIN, FINAL_PRICE, VIP_PRICE, CTA_ACTION, the three Secrets section names from arc_allocation.json)
- working/copy/arc_allocation.json (ladder positions: which slides are ANCHOR, BUILDUP, DROP1, DROP2, DROP3, FINAL)

**Steps:**

1. **Extract the following elements from the source documents:**
   - The HOOK line (verbatim from intake.json).
   - The three Secrets, one sentence each. Each sentence is the one-line distillation of what that Secret shifts in the audience: not the framework name, but the belief being changed. Derive from the slide copy of the Secret's section banner and opening slide. Example: "Secret 1: Your message is the reason the seats are empty -- fix the message, fill the room."
   - The six section transition cues (the line the presenter says to close one section and open the next). Pull these from the talk-track entries for the last slide of each section and the first slide of the next section.
   - The ladder cues: one line per rung, in order (ANCHOR cue, BUILDUP cue for each drop, each DROP price and earned reason, FINAL reveal sequence). Pull verbatim from the relevant talk-track entries.
   - The CTA script: the full verbatim close from the talk track's CTA slide entry, condensed to 3 to 5 sentences maximum.

2. **Assemble the one-page run sheet** in this exact structure. It must fit on a single printed page (letter or A4, 12pt font, standard margins). If it does not fit, tighten by cutting coaching asides -- never cut the hook line, the Secrets summaries, the ladder cues, or the CTA script:

   ```
   REHEARSAL RUN SHEET -- [DECK_SLUG]
   Duration: [DURATION_MIN] min | Slides: [SLIDE_COUNT] | Date: [ISO_DATE]

   --- THE HOOK (say this at least 7 times) ---
   "[HOOK verbatim]"

   --- THE THREE SECRETS (one sentence each) ---
   Secret 1: [belief shift in one sentence]
   Secret 2: [belief shift in one sentence]
   Secret 3: [belief shift in one sentence]

   --- SECTION TRANSITIONS ---
   Hook -> Authority: "[transition line]"
   Authority -> Secret 1: "[transition line]"
   Secret 1 -> Secret 2: "[transition line]"
   Secret 2 -> Secret 3: "[transition line]"
   Secret 3 -> Offer: "[transition line]"
   Offer -> Close: "[transition line]"

   --- LADDER CUES ---
   Slide [NN] ANCHOR: "[memory hook line -- say 'remember this number' then pause]"
   Slide [NN] BUILDUP: "[future-pacing line before DROP1]"
   Slide [NN] DROP1: "$[amount] -- because [earned reason] -- pause 3 seconds"
   Slide [NN] BUILDUP: "[future-pacing line before DROP2]"
   Slide [NN] DROP2: "$[amount] -- because [earned reason] -- pause 3 seconds"
   Slide [NN] BUILDUP: "[future-pacing line before DROP3]"
   Slide [NN] DROP3: "$[amount] -- because [earned reason] -- pause 3 seconds"
   Slide [NN] FINAL: "GA $[amount] | VIP $[amount if applicable] -- [urgency window] -- go quiet"

   --- CTA SCRIPT ---
   [Full verbatim CTA, 3 to 5 sentences, ending with the join URL stated aloud]

   --- TOP 3 OBJECTION ANCHORS (if the room goes quiet) ---
   Price: "[anchor line from Q&A prep price objection answer]"
   Results: "[anchor line from Q&A prep results-proof answer]"
   Time/fit: "[anchor line from Q&A prep timing or fit answer]"
   ```

3. **Verify one-page fit.** If the content overflows, cut in this priority order: (a) trim coaching asides in transition lines to the bare cue line only, (b) trim the CTA script to 3 sentences minimum, (c) cut the top 3 objection anchors to 2. Never cut the hook, the Secrets, the ladder cues, or the full CTA URL.

4. **Write the rehearsal pack** to working/presenter-coach/rehearsal_pack.md. Add a note at the top: "PRINT THIS. Keep it on the chair beside you during rehearsal and during the live webinar. It is your fallback if you lose your place."

**Outputs:**
- working/presenter-coach/rehearsal_pack.md (one-page run sheet)

**Hand to:** SOP 9.4 (Rehearsal Gate) -- the rehearsal pack is the reference document the owner uses during the gate session.

**Failure mode:** If the talk track or Q&A prep has unflagged [CLIENT TO SUPPLY] blanks that affect the run sheet content (e.g., the CTA URL is still a placeholder), the rehearsal pack inherits the flag. Mark the placeholder clearly in the run sheet as "[OWNER: INSERT BEFORE LIVE]" and notify the Director. Do not hold the rehearsal pack; deliver it with the flag visible.

---

### SOP 9.4 -- Rehearsal Gate

**When to run:** After all three prior SOPs (9.1, 9.2, 9.3) are complete and their output files exist. This is the final gate before the deck is declared webinar-ready. The deck is NOT webinar-ready until this gate is cleared.

**Inputs:**
- working/presenter-coach/talk_track.md (complete)
- working/presenter-coach/qa_objection_prep.md (complete)
- working/presenter-coach/rehearsal_pack.md (complete, printed or on-screen)
- The assembled PPTX (in the client's Downloads folder or confirmed delivery location per master SOP Section 11.4)
- DURATION_MIN from intake.json

**Steps:**

1. **Schedule the rehearsal session.** Send the owner a scheduling message via openclaw message send (never direct Telegram API) with:
   - The three output files listed as ready.
   - A clear request: "Before we go live, I need you to run the deck aloud -- just once. No audience, no perfection required. Pick [3 times that work] and I will hold the space with you."
   - The expected duration: DURATION_MIN + 10 minutes for notes.
   - The specific files they need open: the PPTX (with speaker notes visible) and the printed or on-screen rehearsal pack.
   - Log the scheduling message timestamp to working/presenter-coach/rehearsal_gate.json as `gate_initiated_at`.

2. **Run the rehearsal session** (synchronously with the owner, or asynchronously if the owner records a walkthrough and sends the video/audio). During the session:
   a. Owner presents from slide 1 to the last slide, using the talk track and run sheet as guides.
   b. Coach role: track timing per section (note in real time which sections ran over/under), note stumble points, note where the HOOK was or was not sung, note the CTA delivery.
   c. Do not interrupt the run for corrections -- coach after the full pass.
   d. After the run: deliver verbal (or written, if async) feedback using this structure:
      - Timing: "Section [X] ran [N] seconds over/under -- here is how to adjust."
      - Hook: "You sang the hook [N] times. Target is >= 7. Here are the slides where it was missing: [list]."
      - Drops: "The [DROP1/DROP2/DROP3/FINAL] delivery -- [specific note on pause, conviction, pacing]."
      - CTA: "The CTA was [strong/needs work] -- [one specific coaching note]."
      - Overall confidence score: 1 to 10 (the owner's apparent comfort level). Anything below 7 triggers a second rehearsal.

3. **Determine gate outcome:**
   - PASS: the owner completes the full run aloud, the overall confidence score is >= 7, and no section had more than 25% timing deviation from the budget. Record `gate_status: "passed"`, `rehearsal_completed_at` (ISO timestamp), `confidence_score`, `timing_deviation_worst_section`, and any coaching notes in working/presenter-coach/rehearsal_gate.json.
   - CONDITIONAL PASS: the owner completes the run but confidence score is 6 or timing deviation on one section is 25 to 40%. Record `gate_status: "conditional_pass"`, deliver specific drills for the weak section(s), and mark the deck as "webinar-ready with coaching notes." The owner can proceed but the gate file documents the open items.
   - NO PASS: confidence score below 6 or timing deviation > 40% on more than one section. Record `gate_status: "needs_second_rehearsal"`. Schedule a second session. The deck is NOT declared webinar-ready. Notify the Director.

4. **On PASS or CONDITIONAL PASS:**
   - Write the final confirmation to working/presenter-coach/rehearsal_gate.json.
   - Update working/checkpoints/run_ledger.json: `presenter_coach_phase: "complete"`, `rehearsal_gate: "passed"`, `webinar_ready: true` (or `"conditional"` for conditional pass), `gate_cleared_at` ISO timestamp.
   - Notify the Director of Presentations via openclaw message send: "Presenter Coach phase complete. [DECK_SLUG] is webinar-ready. Gate status: [PASS/CONDITIONAL PASS]. Rehearsal confidence: [N]/10. Output files in working/presenter-coach/."
   - Confirm that the PPTX with speaker notes is in the confirmed delivery location (the same location Phase 6 delivered to). If it has moved or is missing, flag immediately -- do not close the gate without a verified PPTX.

5. **On NO PASS:**
   - Notify the Director immediately via openclaw message send: "Rehearsal gate FAILED for [DECK_SLUG]. Confidence score [N]/10. Scheduling second rehearsal. Deck is NOT webinar-ready yet."
   - Do not update run_ledger.json to `webinar_ready: true`. Log `gate_status: "needs_second_rehearsal"` and the specific issues.
   - Deliver a targeted drill document to the owner (working/presenter-coach/drill_notes.md) covering the specific sections that failed: exact lines to practice, exact timing targets, specific delivery notes.

**Outputs:**
- working/presenter-coach/rehearsal_gate.json (gate record: status, timestamps, confidence score, coaching notes)
- working/presenter-coach/rehearsal_notes.md (per-session coaching notes from the live run)
- working/checkpoints/run_ledger.json updated with presenter-coach phase status

**Hand to:** ROLE-13 (PPTX Assembly Specialist) -- a PASS or CONDITIONAL PASS on the rehearsal gate is the final confirmation that the presenter-coach phase is complete and the deck is cleared for the live room. The gate record is the delivery receipt. No further work returns to this role unless the owner schedules a second run or a post-webinar debrief.

**Failure mode:** If the owner does not respond to the scheduling message within 48 hours, send one follow-up. If still no response after 72 hours total, log `gate_status: "owner_unresponsive"` in rehearsal_gate.json and escalate to the Director with the timestamp trail. The gate cannot be waived by silence. The Director and operator decide whether to proceed at risk.

---
