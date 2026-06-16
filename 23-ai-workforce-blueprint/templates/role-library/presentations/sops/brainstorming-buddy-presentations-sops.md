# SOPs Mirror -- Brainstorming Buddy -- Presentations

**Source:** presentations/brainstorming-buddy-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 2.1 (regenerated after surgery v2.1 -- SOP 9.0 adds DELIVERABLE_SET / WANT_AUDIO_DEMO / TARGET_WPM(140) + the style branch)

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- Simple Interview (7 questions or fewer)

**When to run:** When the owner picks "quick" at the mode offer, OR when the request is
small/low-stakes, OR when most context is already on file.

**Steps:**
1. OPENING + MODE OFFER (always first, counts as conversation not as one of the 7):
   Ask 1 to 2 critical framing questions to understand the idea at a high level
   (see the dept question bank, the "OPENING" items). Then offer the choice in plain
   language: "I can do this two ways. The QUICK way: I ask you about 5 to 7 key
   questions and we lock it in fast. Or the DEEP way: we go back and forth on 10 to 20
   questions and really flesh it out. Which do you want?" Record `interview_mode: "simple"`.
2. Pull the SIMPLE question set for this department (the question bank below, simple set).
   Ask each one at a time. Skip any whose answer is already on file or already answered
   in the opening.
3. **(Density-floor overhaul) Ask the STYLE BRANCH verbatim** (SOP-IMG-03 section 2), once, early, before the STYLE BLOCK is built: "For the look of your slides, do you have a particular image style in mind? You can: (1) point me at an existing deck, past designs, or reference images you want me to match; (2) tell me a saved style name from your library if you already have one (like 'Style 1'); or (3) let me creatively develop a signature style for you. Which one?" Set `STYLE_SOURCE` to `match_reference` (+ `STYLE_REFERENCES`, `ANALYZE_REQUEST=true`), `saved_style` (+ `STYLE_ID`), or `creative_develop`. A deck that reaches Phase 2 with `STYLE_SOURCE` unset is a defect (it would invent a look with no client direction, the path that produced the reference failure case cookie-cutter typography). If `creative_develop`, sequence the existing mood/imagery/avoid stems into the short creative-develop micro-interview (<=5 questions; do not re-bank them) per SOP-IMG-03 section 3.
4. Reflect each answer back in one line. Capture into brief.json under its field key.
5. If a critical field is still unknown after the simple set, ask ONE clarifying
   follow-up (you may exceed 7 only to close a CRITICAL gap; flag it in the brief as
   `clarifying_followup: true`). Otherwise use the best default and mark `assumed: true`.
6. Hand to SOP 9.3.

**Output:** `working/brainstorm/presentations/<project-slug>/brief.json` (draft, `interview_confirmed: false`).

**Failure mode:** If the owner answers "you decide" to everything, capture the best
defaults, mark every defaulted field `assumed: true`, and tell the owner at lock:
"I made N assumptions -- confirm or correct before I hand this to the build team."

### SOP 9.2 -- Extensive Interview (10 to 20 questions, back-and-forth)

**When to run:** When the owner picks "deep" at the mode offer, OR for a high-stakes or
flagship presentation, OR when the idea is genuinely unformed.

**Steps:**
1. Confirm mode: `interview_mode: "extensive"`.
2. Pull the EXTENSIVE question set for this department (the question bank below, extensive
   set, 10 to 20 items). This is a CONVERSATION, not a form. Ask one at a time, in a
   logical order, and let answers reshape the order.
3. After every answer, do two things: (a) reflect it back in one line, and (b) decide
   whether it opens a follow-up worth asking now. Ask high-value follow-ups inline.
   Stay within the 20-question ceiling (count follow-ups toward it).
4. Periodically (roughly every 5 questions) give a 2-line running summary so the owner
   sees the idea taking shape and can course-correct early.
5. Capture every answer into brief.json under its field key, including verbatim quotes
   for anything the owner says emphatically (`owner_verbatim` array).
6. Hand to SOP 9.3.

**Output:** brief.json (draft, richer than the simple path, `interview_confirmed: false`).

**Failure mode:** If the owner tires mid-interview ("this is a lot"), offer to switch
to the remaining critical questions only and finish in 3 more, then lock. Record
`mode_downshifted: true`.

### SOP 9.3 -- Confirm-and-Lock (read back, sign-off, write the brief)

**When to run:** Immediately after 9.1 or 9.2, before any handoff. This gate is mandatory.

**Steps:**
1. Compose the READ-BACK: a short plain-language summary of the brief in the owner's
   own terms. Structure: "Here is what I heard. You want a presentation that
   [core goal]. It is for [audience]. The key things that matter: [3 to 6 bullet
   highlights pulled from the captured fields]. Anything I got wrong or missed?"
2. List every `assumed: true` field explicitly so the owner can correct defaults.
3. Send via openclaw message send. WAIT for explicit confirmation. Do not proceed on
   silence.
4. On confirmation: set `interview_confirmed: true`, `confirmed_by`, `confirmed_at`,
   `confirmation_message` in brief.json. Apply any corrections the owner gave and
   re-read-back ONLY the corrected lines.
5. Write the final brief.json. It MUST contain: `dept`, `project_slug`, `interview_mode`,
   `dept_deliverable`, every captured field, `assumptions` (list), `owner_verbatim`
   (list, extensive only), and the confirmation record.

**Output:** brief.json with `interview_confirmed: true`.

**Failure mode:** If the owner does not respond within 2 hours, send one reminder. After
4 hours, log a lock_timeout in the brief and notify: "Your brief is ready and waiting on
your YES before the team starts building."

### SOP 9.4 -- Kickoff / Handoff (trigger the dept build via its specialists)

**When to run:** Only after `interview_confirmed: true`.

**Steps:**
1. Hand the locked brief.json to the Director of Presentations (the dept's leadership/head role)
   using this dispatch contract:
   ```
   [OPENCLAW_SKILLS]/23-ai-workforce-blueprint/scripts/dispatch-sub-specialist.py \
     --parent-role brainstorming-buddy-presentations \
     --specialist-type director-of-presentations \
     --problem-statement "Build the presentation per the locked brief at <brief.json path>" \
     --persona {{ASSIGNED_PERSONA}} \
     --persona-version {{ASSIGNED_PERSONA_VERSION}}
   ```
2. The Director ingests brief.json as the seed for its OWN intake SOP (it confirms and
   extends, never re-asks what the brief already answers).
3. The Director then dispatches this department's BUILD SPECIALISTS in pipeline order:
   Hook Strategist, Slide Copywriter, Offer/Price Strategist, Brand Steward, Slide Image Creator, QC Specialist, Slide Submitter, Media Librarian/GHL Updater, PPTX Assembly Specialist, Presenter Coach, Delivery Concierge.
4. Notify the owner that the build has started and tell them the next gate they will see
   (usually the Director's owner-approval gate).
5. Record `handoff_at`, `handoff_to`, `dispatch_id` in brief.json.

**Output:** brief.json updated with handoff record; build is now in the Director's hands.

**Failure mode:** If the Director/Head role is missing or errors on dispatch, escalate to
the Master Orchestrator with the locked brief attached. Never silently drop a locked brief.

---
