# SOPs Mirror -- Brainstorming Buddy (Presentations)

**Source:** presentations/brainstorming-buddy-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 2.0 (regenerated after surgery v2.0 -- added SOP 9.0 PRE-PRESENTATION HARD-REQUIRED CAPTURE)

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.0 -- PRE-PRESENTATION HARD-REQUIRED CAPTURE (runs FIRST, before mode offer)

**When to run:** The instant a new deck request arrives, before the mode offer and before
any other question is asked. This SOP is MANDATORY and NON-SKIPPABLE. It cannot be
deferred to the main interview. No brief may be locked without all six fields resolved.

**Inputs:** the incoming request (however thin); workspace SOUL.md / USER.md pre-read.

**Steps:**
1. Check SOUL.md / USER.md / any prior brief for the six required fields. Credit any
   already on file and confirm them rather than re-asking.
2. For each of the six fields NOT already on file, ask the question below (one at a time,
   in the order listed). Each is MANDATORY -- there is no skip and no assumed default
   except where explicitly stated:

   **Field 1 -- REPRESENTATION_MIX (with percentages; the audience-composition core)**
   Ask: "Who will be in the seats watching this -- and how should the people in the images
   break down? Give me percentages. For example: 70% African-American women, 20% mixed
   race, 10% men. Or: 100% women, diverse. Or: no people at all."
   Capture as: `REPRESENTATION_MIX` (list of {group, percent}).
   If the owner cannot or will not answer: set `representation_uncaptured: true`, flag the
   operator ("REPRESENTATION_MIX not captured -- deck will generate with NO PEOPLE; confirm
   before build starts"), and proceed. A racial or gender default is NEVER invented.

   **Field 2 -- AUDIENCE-COMPOSITION NOTE (plain language; the audience-engine front door)**
   Ask: "In plain words, who is this audience -- for example: all women, or multicultural
   Black + white + Hispanic professionals, or mixed gender diverse?"
   Capture as: `AUDIENCE_COMPOSITION_NOTE` (a single plain-language sentence).
   Derive from REPRESENTATION_MIX if the owner just answered it; no need to re-ask if the
   answer is already clear from Field 1.

   **Field 3 -- GROUNDED-CONTENT (the concrete client content the imagery must depict)**
   Ask: "What is the specific book, program, method, or message this deck is built around?
   I need the name and a one-line description so every image is grounded in YOUR content,
   not generic inspiration."
   Capture as: `GROUNDED_CONTENT` (free text: name + one-line description).
   If the owner does not have a name yet: capture whatever they describe and mark
   `grounded_content_provisional: true`. The build cannot start with a blank GROUNDED_CONTENT;
   if still empty at lock, block handoff and ask once more.

   **Field 4 -- VISUAL_MIX (people balance)**
   Ask: "Should the slides be people-heavy, some people, typography-led, or a mix?"
   Capture as: `VISUAL_MIX` (people-heavy / some-people / typography-led / mix).
   Default if owner says "no preference": `mix`. Mark `visual_mix_defaulted: true`.

   **Field 5 -- DARK_OK (dark background permission; default: false)**
   Ask: "Default is a clean white base -- the standard that makes premium decks pop. Do
   you specifically want any dark-styled slides?"
   Capture as: `DARK_OK` (true / false). Default if owner does not answer: `false`.
   Note: the Lyric gold standard eliminated all black backgrounds -- recommend false.

   **Field 6 -- HOOK SEED (the strongest-promise line)**
   Ask: "Is there one line you already say all the time -- the phrase you want them
   humming when they leave? The hook the whole deck will be built around?"
   Capture as: `HOOK_SEED` (free text).
   If none: mark `hook_seed_missing: true`. The Hook Strategist will derive one from the
   offer; note this in brief.json so the Director knows to trigger the Hook Lab.

3. After all six fields are resolved (captured OR flagged), write the pre-presentation
   block to brief.json:
   ```json
   {
     "pre_presentation_capture": {
       "REPRESENTATION_MIX": [...],
       "representation_uncaptured": false,
       "AUDIENCE_COMPOSITION_NOTE": "...",
       "GROUNDED_CONTENT": "...",
       "grounded_content_provisional": false,
       "VISUAL_MIX": "...",
       "DARK_OK": false,
       "HOOK_SEED": "...",
       "hook_seed_missing": false,
       "pre_presentation_gate_passed": true
     }
   }
   ```
   Set `pre_presentation_gate_passed: true` only if REPRESENTATION_MIX and
   GROUNDED_CONTENT are captured (or their respective flags are set). VISUAL_MIX,
   DARK_OK, and HOOK_SEED may use defaults/flags without blocking the gate.
4. Confirm the six fields back to the owner in a single brief summary before proceeding:
   "Quick check before we dive in -- I have your audience as [AUDIENCE_COMPOSITION_NOTE],
   the content grounded in [GROUNDED_CONTENT], visual style [VISUAL_MIX], dark backgrounds
   [DARK_OK], and the hook seed [HOOK_SEED or 'to be derived by our Hook Strategist'].
   Does that look right?"
5. On confirmation, proceed to SOP 9.1 (mode offer).

**Outputs:** `brief.json` with `pre_presentation_capture` block and `pre_presentation_gate_passed: true`.
**Hand to:** SOP 9.1 (Opening + Mode Offer).

**Failure mode:** If the owner refuses to answer REPRESENTATION_MIX and GROUNDED_CONTENT
and the flags are set, proceed to mode offer with the flags active. Brief may be locked and
handed to the Director only with those flags explicitly visible -- the Director will surface
them to the operator before any image generation begins. The build CANNOT proceed past the
generation gate with `representation_uncaptured: true` without operator written authorization.

### SOP 9.1 -- Simple Interview (<= 7 questions)

**When to run:** When interview_depth = simple.
**Prerequisite:** SOP 9.0 pre-presentation capture is complete and `pre_presentation_gate_passed: true`.

**Hard rule:** Ask 7 questions MAXIMUM, total. Skip any question already answered by SOUL.md / USER.md / prior brief and confirm that fact instead of asking. At most ONE follow-up per question, then move on. Goal: a complete brief in under 30 minutes of owner time.

**The Simple Bank (ask in priority order; skip what is already known; stop at 7):**

- **S1. GOAL + ACTION (always).** "What is this presentation for, and what do you want people to DO at the end? Buy, book a call, join, enroll, donate?" Vars: GOAL, CTA_ACTION.
- **S2. OFFER + PRICE (always).** "What are you offering, and what does it cost? Give me the name and the final price." Vars: OFFER_NAME, FINAL_PRICE. Follow-up allowed: "One price stated once, or do you want us to walk the price down from a bigger anchor?" -> PRICE_MODE (straight | drop).
- **S3. AUDIENCE (always).** "Who is this for? Describe the person in the seat." Var: AUDIENCE. (REPRESENTATION_MIX was captured in SOP 9.0 -- do not re-ask the percentage question.)
- **S4. TRANSFORMATION (always).** "When they finish, what changes for them? What is the promise?" Var: TRANSFORMATION_PROMISE.
- **S5. FEELING + TONE (always).** "How do you want them to FEEL walking away, and which voice fits you best: Inspirational, Tough Love, Challenger, Teacher, Storyteller, High-Energy Hype, or Calm Premium?" Vars: TARGET_FEELING, TONE (one of the seven named styles; blend of two allowed).
- **S6. DURATION (always).** "How long is the presentation? 10, 15, 30, 45, 60, or 90 minutes?" Var: DURATION_MIN.
- **S7. SIGNATURE LINE + LOOK (always; the catch-all).** "Two quick things: is there a line you already say all the time that you want them humming when they leave? And do you have brand colors and a logo you want on the slides?" Vars: HOOK_SEED (skip if already captured in SOP 9.0), BRAND_COLORS (hex if known), LOGO_ON_SLIDES, LOGO_URL.

**If a critical unknown is still open after S1-S7** (offer name, final price, transformation, audience, tone, or duration), ask ONE targeted clarifier even if it pushes to 8; flag it as simple_overflow: true with the reason. Anything still missing is recorded with assumed: true and surfaced to the owner at Confirm-and-Lock.

**Outputs:** deck_brief.json populated.
**Hand to:** SOP 9.3.

**Failure mode:** If the owner answers everything with "you decide," capture best-available defaults from SOUL.md / USER.md, mark each assumed: true, and tell the owner at lock: "I made N best guesses; confirm or correct these before I start the build."
Note: REPRESENTATION_MIX and GROUNDED_CONTENT do NOT have a fallback default -- if
uncaptured, the flag is set per SOP 9.0 and a racial/gender ratio is NEVER assumed.

### SOP 9.2 -- Extensive Interview (10 to 20 questions, back-and-forth)

**When to run:** When interview_depth = extensive. This is a conversation, not a form. Aim for 10 to 20 questions including follow-ups; NEVER exceed 20.

**Steps:** Run the Extensive Bank in priority order, skipping anything already on file. After each answer, decide if it raises a follow-up worth asking (this is where the back-and-forth happens). Help the owner sharpen fuzzy answers: reflect what you heard, offer a sharper version, let them confirm or adjust. Stop the moment all critical unknowns are resolved or you hit 20 questions, whichever comes first.

**The Extensive Bank (covers the simple bank plus depth; asterisked items are the same critical fields):**

- **E1. GOAL + ACTION*.** Same as S1, then follow up: "If only one thing happens at the end, what is the single most important action?" Vars: GOAL, CTA_ACTION.
- **E2. AUDIENCE DEEP.** "Who is this for? Walk me through the exact person: their job, their day, what is keeping them stuck right now." Vars: AUDIENCE, AUDIENCE_PAIN.
- **E3. PRIMARY OBJECTION.** "When this person hears your offer, what is the first reason they tell themselves NO?" Var: PRIMARY_OBJECTION.
- **E4. TRANSFORMATION*.** "Paint the after. Who are they once this works? Be specific." Var: TRANSFORMATION_PROMISE.
- **E5. THE FEELING.** "How do you want them to FEEL when they walk away? Capable and fired up, safe and understood, urgently behind, hopeful, seen for the first time?" Var: TARGET_FEELING.
- **E6. TONE*.** Offer the seven named styles (Inspirational / Tough Love / Challenger / Teacher / Storyteller / High-Energy Hype / Calm Premium); pick one or blend two. Var: TONE.
- **E7. THE OFFER*.** "What exactly are you selling? Give me the name and everything that is included." Vars: OFFER_NAME, OFFER_STACK (list each component the owner names).
- **E8. PRICE STRUCTURE*.** "Do you want a gradual price drop, where we walk it down from a big anchor (the proven Lyric method), or one straight price stated once?" If DROP: collect each component's standalone value, the anchor, the final price, the payment plan. If STRAIGHT: collect the price and the value stack that justifies it. Vars: PRICE_MODE, OFFER_STACK (values), PRICE_ANCHOR, FINAL_PRICE, PAYMENT_PLAN.
- **E9. VIP / PREMIUM TIER.** "Do you want a VIP or premium tier in the pitch? If yes, what is in it, what does it cost, and how many real spots?" (Real scarcity only; no fabricated limits.) Vars: VIP_TIER, VIP_PRICE, VIP_SPOTS.
- **E10. PROOF.** "What proof can we show? Testimonials, screenshots, press, revenue numbers, before-and-after results? Send me what you have now so the deck is not full of placeholders." Var: PROOF_ASSETS (list).
- **E11. THE HOOK SEED.** "Is there one line you already say all the time, the thing you want them humming when they leave?" Var: HOOK_SEED. (Skip if already captured in SOP 9.0. If none, note it; the Hook Strategist will derive one and the owner confirms it at the copy gate.)
- **E12. ORIGIN / AUTHORITY.** "Why you? Short version of your story and your receipts: what have you built, run, or proven?" Var: AUTHORITY_STORY.
- **E13. DURATION*.** "How many minutes? 10, 15, 30, 45, 60, 90?" Var: DURATION_MIN.
- **E14. AUDIENCE REPRESENTATION.** "How should the people in the images break down, in percentages? For example 70% African American women, 20% men, 10% mixed, or 100% women diverse, or no people at all." Var: REPRESENTATION_MIX (list of {group, percent}). (Skip if already captured in SOP 9.0.)
- **E15. VISUAL MIX.** "Should the slides be people-heavy, some people, typography-led, or a mix?" Var: VISUAL_MIX (people-heavy / some-people / typography-led / mix). (Skip if already captured in SOP 9.0.)
- **E16. BRAND COLORS.** "Exact hex codes for primary, secondary, accent? Or send your brand guide." Vars: BRAND_PRIMARY, BRAND_SECONDARY, BRAND_ACCENT.
- **E17. LOGO.** "Logo on the slides? If yes, send the highest-res transparent PNG and a public URL." Vars: LOGO_ON_SLIDES, LOGO_FILE, LOGO_URL.
- **E18. STYLE REFERENCES.** "Any decks, brands, or looks you admire and want this to feel like?" Var: STYLE_PREFS.
- **E19. DARK STYLING.** "Default is a clean white base. Do you specifically want any dark-styled slides?" Var: DARK_OK (default false). (Skip if already captured in SOP 9.0.)
- **E20. ANYTHING ELSE.** "What else matters to you about this deck that I have not asked?" Capture verbatim in CLIENT_NOTES.

**Outputs:** deck_brief.json fully populated (extensive).
**Hand to:** SOP 9.3.

**Failure mode:** If the owner stalls or the offer is genuinely undefined, do not force 20 questions; capture what exists, mark gaps assumed: true or [OWNER TO SUPPLY], and recommend at lock that the offer be firmed up before the build. Never invent proof, prices, or VIP spots to fill a gap.

### SOP 9.3 -- Confirm-and-Lock (read back, sign-off, write the brief)

**When to run:** Immediately after the chosen interview completes, before any handoff.

**Steps:**
1. Validate the MANDATORY PRE-PRESENTATION VARIABLE CHECKLIST before composing the read-back.
   Every field below must be resolved (captured or flagged) before lock is permitted:

   | Field | Status required | Fallback if uncaptured |
   |---|---|---|
   | REPRESENTATION_MIX (with percentages) | Captured OR `representation_uncaptured: true` set | NO PEOPLE + operator flag (NEVER a default ratio) |
   | AUDIENCE_COMPOSITION_NOTE (plain language) | Captured | Derived from REPRESENTATION_MIX if available |
   | GROUNDED_CONTENT | Captured OR `grounded_content_provisional: true` set | Block handoff; ask once more |
   | VISUAL_MIX | Captured OR defaulted to `mix` with `visual_mix_defaulted: true` | Default: mix |
   | DARK_OK | Captured OR defaulted to `false` | Default: false |
   | HOOK_SEED | Captured OR `hook_seed_missing: true` set | Hook Strategist derives at build |

   If GROUNDED_CONTENT is still blank after the interview AND the owner has not been
   asked yet, ask ONE more time now. If still unanswered: set `grounded_content_provisional`
   to the best available description and surface it at read-back.

2. Compose the READ-BACK: a short plain-language paragraph that restates the deck. Format:
   "Here is what I have. This deck is for [AUDIENCE_COMPOSITION_NOTE]. It presents
   [OFFER_NAME] at [FINAL_PRICE] ([PRICE_MODE]). The promise is [TRANSFORMATION_PROMISE].
   The voice is [TONE] and you want them feeling [TARGET_FEELING]. It runs [DURATION_MIN]
   minutes, and the action at the end is [CTA_ACTION]. The content is grounded in
   [GROUNDED_CONTENT]. The imagery will show [REPRESENTATION_MIX or 'NO PEOPLE -- audience
   not captured']. Visual style: [VISUAL_MIX]. Dark slides: [DARK_OK]."
   Add the hook seed, VIP, proof, and look if present.
3. List every assumed: true value explicitly: "I had to make a best guess on these: [list].
   Correct any of them now." Explicitly call out any representation or grounded-content flags.
4. Ask, verbatim: "Did I get this right? Reply YES to start the build, or tell me what to fix."
   WAIT for an explicit answer. Loop the read-back if the owner corrects anything (re-read
   the corrected line, re-confirm).
5. On YES: set owner_confirmed: true, owner_confirmed_at (ISO), owner_confirm_message (their
   exact words), and brief_locked: true.
6. Validate the brief against the mandatory-variable checklist. If any mandatory variable is
   still missing, do NOT lock; ask the one missing question, then re-confirm.
7. Write the complete working/copy/deck_brief.json. It MUST contain: `dept`, `project_slug`,
   `interview_mode`, `dept_deliverable`, the full `pre_presentation_capture` block (from
   SOP 9.0), every captured field, `assumptions` (list), `owner_verbatim` (list, extensive
   only), and the confirmation record.

**Outputs:** working/copy/deck_brief.json with brief_locked: true, owner_confirmed: true,
and the pre_presentation_capture block.
**Hand to:** SOP 9.4.

**Failure mode:** If the owner goes silent after the read-back, send one follow-up reminder.
After 4 hours, record lock_timeout: true and notify the operator: "Brainstorm is paused at
the confirm gate for [AUDIENCE]'s deck, awaiting the owner's YES."
If GROUNDED_CONTENT remains uncaptured at lock and the owner has not responded: set
`grounded_content_provisional: "[to be confirmed by operator before image generation]"`.
NEVER fabricate a grounded-content description.

### SOP 9.4 -- Kickoff and Handoff (trigger the build)

**When to run:** Immediately after brief_locked: true AND pre_presentation_gate_passed: true.

**Steps:**
1. Hand working/copy/deck_brief.json to the Director of Presentations. Trigger via:
   ```
   [OPENCLAW_SKILLS]/23-ai-workforce-blueprint/scripts/dispatch-sub-specialist.py \
     --parent-role director-of-presentations \
     --specialist-type director-of-presentations \
     --problem-statement "New deck request: brief locked at working/copy/deck_brief.json. Run Step 0, Step 0.5, then SOP 9.1 ingest-and-validate, then proceed." \
     --persona {{ASSIGNED_PERSONA}} \
     --persona-version {{ASSIGNED_PERSONA_VERSION}}
   ```
   (Implementation note: the Director is normally initiated by the Master Orchestrator; use
   whichever trigger the deployment uses to start the Director. The load-bearing contract:
   the Director receives the locked brief path and runs its SOP 9.1 ingest, not a fresh
   interview.)
2. Wait for the Director's acknowledgment. Record director_ack: true and director_ack_at.
   Any active flags (representation_uncaptured, grounded_content_provisional, hook_seed_missing)
   are included in the handoff so the Director surfaces them to the operator before image
   generation begins.
3. If the Director bounces the brief for a missing mandatory variable, re-open the relevant
   question with the owner (one question), re-confirm, re-lock, re-hand. Never let the
   Director re-interview the owner; gap-filling is YOUR job.
4. Notify the owner via openclaw message send: "Locked it. My team is building your deck
   now. You will hear from us next when the full slide copy is ready for your one approval.
   Nothing ships without your YES."
5. Update the run ledger: write working/checkpoints/run_ledger.json discovery entry with
   the brief_locked timestamp and interview_depth.

**Outputs:** Director acknowledged; owner notified; run_ledger discovery entry written.
**Hand to:** Director of Presentations (ROLE-01), which owns everything from Step 0 onward.

**Failure mode:** If the Director does not acknowledge within 1 hour, escalate to the Master
Orchestrator and notify the operator. Never start the build yourself; you do not own the build.
