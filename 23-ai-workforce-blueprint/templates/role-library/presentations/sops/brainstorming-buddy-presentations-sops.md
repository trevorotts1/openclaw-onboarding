# SOPs Mirror -- Brainstorming Buddy -- Presentations

**Source:** presentations/brainstorming-buddy-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 2.2 (regenerated after surgery v2.2 -- SOP 9.1 adds the PRICE-SEPARATION BRANCH: EVENT/ACCESS price vs OFFER price are two independent fields, free event != free offer, never deny an assumption)

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
3a. **(Decision 1C) Ask the ASSET BRANCH verbatim, once, early — every signature run:** *"Is there anything you already have that could help me build this — photos, a logo, brand colors, a rough/old deck, slides, or concepts? Drop them here."* Record `asset_intake_question_asked: true` in brief.json the moment it is asked (the gate **AF-ASSET-QUESTION-MISSING** fails any deck whose intake does not carry this flag). If the client provides anything, set `assets_provided: true` and capture each item (kind + where it is) so the Media-Librarian step can ingest it into `assets_manifest.json`; if they upload a rough/old deck, note it as a `scratch_deck` so the scratch-deck parser seeds the PRD. If they have nothing, set `assets_provided: false` — the question was still asked, which is what the gate requires.
3b. **(Decision 2A) Ask the PITCH BRANCH verbatim, once, early:** *"Does this presentation end with an offer or pitch — a price, package, or call to buy — or is it a teaching and content-only presentation?"* Record an explicit boolean `pitch_included` (true = ends with an offer/pitch; false = teaching/content-only). NEVER default it and NEVER force a pitch: a pitchless deck is first-class. The gate **AF-PITCH-FLAG-UNSET** fails any deck whose intake has no boolean `pitch_included`; downstream, `pitch_included:false` SUPPRESSES the Offer Price Strategist + price ladder and arms **AF-PITCH-LEAK** (no pitch/price content may appear), while `pitch_included:true` requires the offer arc (**AF-PITCH-MISSING**).
3c. **PRICE-SEPARATION BRANCH (TWO PRICES — never conflate).** Capture the EVENT/ACCESS price (`EVENT_PRICE` / `ACCESS_FREE` — free or paid to ATTEND, question-bank O3) and the OFFER price (`FINAL_PRICE` — the product SOLD at the end, question-bank #4) as TWO INDEPENDENT fields. A FREE event is the front of a funnel that almost always sells a PAID offer at the end; "free to attend" NEVER implies "free offer." When the event is free, DEFAULT to EXPECTING a paid offer and ASK what it is — do NOT conclude "no pitch / no price needed" and do NOT default the offer to free. `FINAL_PRICE` is NEVER inferred from `EVENT_PRICE`/`ACCESS_FREE`. A free-only close (`pitch_included: false`, `FINAL_PRICE: 0`) is permitted ONLY on the owner's EXPLICIT confirmation and is flagged `free_only_close: true` for sign-off (downstream Devil's Advocate doctrine point 14, ALWAYS PITCH SOMETHING).
4. Reflect each answer back in one line. Capture into brief.json under its field key.
5. If a critical field is still unknown after the simple set, ask ONE clarifying
   follow-up (you may exceed 7 only to close a CRITICAL gap; flag it in the brief as
   `clarifying_followup: true`). Otherwise use the best default and mark `assumed: true`.
   Any price you infer or default (`EVENT_PRICE`, `FINAL_PRICE`, `pitch_included`) MUST be marked
   `assumed: true`, read back at lock, and NEVER denied — if the owner challenges an assumption
   you made, own it and correct it; do not claim you did not make it.
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
2a. **(Decision 1C) ASSET BRANCH (verbatim, once, early):** *"Is there anything you already have that could help me build this — photos, a logo, brand colors, a rough/old deck, slides, or concepts? Drop them here."* Set `asset_intake_question_asked: true` immediately (gate **AF-ASSET-QUESTION-MISSING**). Capture any provided items (set `assets_provided: true`, record kind + location; note an uploaded old deck as a `scratch_deck`); else `assets_provided: false`.
2b. **(Decision 2A) PITCH BRANCH (verbatim, once, early):** *"Does this presentation end with an offer or pitch — a price, package, or call to buy — or is it a teaching and content-only presentation?"* Record the explicit boolean `pitch_included` (never default; never force a pitch — a pitchless deck is first-class). Gate **AF-PITCH-FLAG-UNSET**.
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
2. List every `assumed: true` field explicitly so the owner can correct defaults. Read back every
   inferred or defaulted PRICE in plain words ("I assumed the offer price is $X — confirm or
   correct") and surface any `free_only_close: true` flag for explicit sign-off. The agent must
   NEVER deny an assumption it made; if challenged, own it and correct it on the spot.
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
