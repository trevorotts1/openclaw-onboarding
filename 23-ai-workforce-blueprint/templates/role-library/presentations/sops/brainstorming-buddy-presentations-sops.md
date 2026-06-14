# SOPs Mirror -- Brainstorming Buddy (Presentations)

**Source:** presentations/brainstorming-buddy-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 2.1 (regenerated after surgery v2.1 -- SOP 9.0 adds DELIVERABLE_SET / WANT_AUDIO_DEMO / TARGET_WPM(140) + the style branch)

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.0 -- PRE-PRESENTATION HARD-REQUIRED CAPTURE (runs FIRST, before mode offer)

**When to run:** The instant a new deck request arrives, before the mode offer and before
any other question is asked. This SOP is MANDATORY and NON-SKIPPABLE. It cannot be
deferred to the main interview. No brief may be locked without the six hard-required fields
resolved (REPRESENTATION_MIX, AUDIENCE-COMPOSITION NOTE, GROUNDED-CONTENT, VISUAL_MIX,
DARK_OK, HOOK SEED) plus the three scope fields and the style branch captured or defaulted
(DELIVERABLE_SET, WANT_AUDIO_DEMO, TARGET_WPM, STYLE_SOURCE).

**Inputs:** the incoming request (however thin); workspace SOUL.md / USER.md pre-read.

**Steps:**
1. Check SOUL.md / USER.md / any prior brief for the required fields. Credit any
   already on file and confirm them rather than re-asking.
2. For each field NOT already on file, ask the question below (one at a time,
   in the order listed). The six audience/content/hook fields are MANDATORY -- there is no
   skip and no assumed default except where explicitly stated; the scope fields
   (DELIVERABLE_SET, WANT_AUDIO_DEMO, TARGET_WPM) and the STYLE BRANCH have sensible defaults
   (deck-only / false / 140 / create-new) and never block the gate:

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

   **Field 7 -- DELIVERABLE_SET (what ships beyond the deck)**
   Ask: "Beyond the slide deck itself, what else do you want? I can also produce a
   presenter's GUIDE (a beautiful branded at-a-glance run-of-show), a full word-for-word
   SPEECH script, and even an AUDIO demo of the talk in a chosen voice. Pick one:
   deck only / +guide / +guide+speech / +audio."
   Capture as: `DELIVERABLE_SET` (one of: deck-only / +guide / +guide+speech / +audio).
   Default if owner says "just the deck" or "no preference": `deck-only`. The Director uses
   this to decide whether to dispatch the Presenters Guide Specialist (ROLE-19), the
   Presenters Speech Writer (ROLE-20), and the Audio Demonstration Specialist (ROLE-21)
   after the Presenter Coach.

   **Field 8 -- WANT_AUDIO_DEMO (audio demo + voice/persona)**
   Ask only if DELIVERABLE_SET is "+audio" (otherwise default false): "For the audio demo,
   what voice or persona should it use -- your own cloned voice, a warm female narrator, a
   high-energy male host, or something else?"
   Capture as: `WANT_AUDIO_DEMO` (true / false) and `AUDIO_VOICE_PERSONA` (free text).
   If "+audio" with no voice named: set `WANT_AUDIO_DEMO: true`, `audio_voice_unset: true`
   (the Audio Demonstration Specialist asks the owner via the Director before synthesizing;
   a voice is never defaulted silently). Default when not "+audio": `WANT_AUDIO_DEMO: false`.

   **Field 9 -- TARGET_WPM (speech pace; default 140)**
   Ask only if DELIVERABLE_SET includes a speech ("+guide+speech" or "+audio"): "How fast
   should the spoken pace feel -- standard (about 140 words a minute, the most credible
   pace), a slower teach pace (about 130), or a high-energy pace (about 150 to 160)?"
   Capture as: `TARGET_WPM` (integer). Default if owner says "you decide" or not asked:
   `140` (the presentation-speech constant; never silently 150). Mark `target_wpm_defaulted:
   true` when defaulted.

   **STYLE BRANCH -- "do you have a style or want me to create one?"**
   Ask: "Do you have an existing deck or visual style you want matched, a reference deck I
   should analyze, or should we CREATE a fresh signature style for you?"
   Capture as: `STYLE_SOURCE` (one of: match-existing / analyze-reference / create-new) plus
   `STYLE_REFERENCE` (a deck/file/URL when match-existing or analyze-reference).
   - On match-existing or analyze-reference: note that the Brand Steward (the only permitted
     crossing) submits the reference to the Graphics DIU Style Analyst for a PPT-tier style
     card whose ID flows to the Slide Image Creator.
   - On create-new (or no preference): note that the Brand Steward builds the STYLE BLOCK
     fresh. Default when unanswered: `create-new` with `style_source_defaulted: true`.

3. After the fields are resolved (captured OR flagged), write the pre-presentation
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
       "DELIVERABLE_SET": "deck-only",
       "WANT_AUDIO_DEMO": false,
       "AUDIO_VOICE_PERSONA": null,
       "TARGET_WPM": 140,
       "STYLE_SOURCE": "create-new",
       "STYLE_REFERENCE": null,
       "pre_presentation_gate_passed": true
     }
   }
   ```
   Set `pre_presentation_gate_passed: true` only if REPRESENTATION_MIX and
   GROUNDED_CONTENT are captured (or their respective flags are set). VISUAL_MIX,
   DARK_OK, HOOK_SEED, DELIVERABLE_SET, WANT_AUDIO_DEMO, TARGET_WPM, and STYLE_SOURCE may
   use defaults/flags without blocking the gate.
4. Confirm the fields back to the owner in a single brief summary before proceeding:
   "Quick check before we dive in -- I have your audience as [AUDIENCE_COMPOSITION_NOTE],
   the content grounded in [GROUNDED_CONTENT], visual style [VISUAL_MIX], dark backgrounds
   [DARK_OK], the hook seed [HOOK_SEED or 'to be derived by our Hook Strategist'], you want
   [DELIVERABLE_SET][, audio in a [AUDIO_VOICE_PERSONA] voice at [TARGET_WPM] WPM], and the
   style is [STYLE_SOURCE]. Does that look right?"
5. On confirmation, proceed to SOP 9.1 (mode offer).

**Outputs:** `brief.json` with `pre_presentation_capture` block and `pre_presentation_gate_passed: true`.
**Hand to:** SOP 9.1 (Opening + Mode Offer).

**Failure mode:** If the owner refuses to answer REPRESENTATION_MIX and GROUNDED_CONTENT
and the flags are set, proceed to mode offer with the flags active. Brief may be locked and
handed to the Director only with those flags explicitly visible -- the Director will surface
them to the operator before any image generation begins. The build CANNOT proceed past the
generation gate with `representation_uncaptured: true` without operator written authorization.

### SOP 9.1 -- Simple Interview (7 questions or fewer)

**When to run:** When the owner picks "quick" at the mode offer, OR when the request is
small/low-stakes, OR when most context is already on file.
**Prerequisite:** SOP 9.0 pre-presentation capture is complete and `pre_presentation_gate_passed: true`.

**Steps:**
1. OPENING + MODE OFFER (always first, counts as conversation not as one of the 7):
   Ask 1 to 2 critical framing questions to understand the idea at a high level
   (see the dept question bank, the "OPENING" items). Then offer the choice in plain
   language: "I can do this two ways. The QUICK way: I ask you about 5 to 7 key
   questions and we lock it in fast. Or the DEEP way: we go back and forth on 10 to 20
   questions and really flesh it out. Which do you want?" Record `interview_mode: "simple"`.
2. Pull the SIMPLE question set for this department (the question bank below, simple set).
   Ask each one at a time. Skip any whose answer is already on file or already answered
   in the opening OR already captured in SOP 9.0 (REPRESENTATION_MIX, AUDIENCE-COMPOSITION
   NOTE, GROUNDED-CONTENT, VISUAL_MIX, DARK_OK, HOOK SEED are all pre-captured -- do not
   re-ask them unless an answer needs clarification).
3. Reflect each answer back in one line. Capture into brief.json under its field key.
4. If a critical field is still unknown after the simple set, ask ONE clarifying
   follow-up (you may exceed 7 only to close a CRITICAL gap; flag it in the brief as
   `clarifying_followup: true`). Otherwise use the best default and mark `assumed: true`.
5. Hand to SOP 9.3.

**Output:** `working/brainstorm/presentations/<project-slug>/brief.json` (draft, `interview_confirmed: false`).

**Failure mode:** If the owner answers "you decide" to everything, capture the best
defaults, mark every defaulted field `assumed: true`, and tell the owner at lock:
"I made N assumptions -- confirm or correct before I hand this to the build team."
Note: REPRESENTATION_MIX and GROUNDED_CONTENT do NOT have a fallback default -- if
uncaptured, the flag is set per SOP 9.0 and a racial/gender ratio is NEVER assumed.

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

2. Compose the READ-BACK: a short plain-language summary of the brief in the owner's
   own terms. Structure: "Here is what I heard. You want a presentation that
   [core goal]. It is for [AUDIENCE_COMPOSITION_NOTE]. The content is grounded in
   [GROUNDED_CONTENT]. The key things that matter: [3 to 6 bullet highlights pulled from
   the captured fields]. Anything I got wrong or missed?"
   Include in the read-back: REPRESENTATION_MIX breakdown (or flag if uncaptured),
   VISUAL_MIX, DARK_OK, HOOK_SEED (or flag if missing).
3. List every `assumed: true` field explicitly so the owner can correct defaults.
   Explicitly call out any representation or grounded-content flags.
4. Send via openclaw message send. WAIT for explicit confirmation. Do not proceed on
   silence.
5. On confirmation: set `interview_confirmed: true`, `confirmed_by`, `confirmed_at`,
   `confirmation_message` in brief.json. Apply any corrections the owner gave and
   re-read-back ONLY the corrected lines.
6. Write the final brief.json. It MUST contain: `dept`, `project_slug`, `interview_mode`,
   `dept_deliverable`, the full `pre_presentation_capture` block (from SOP 9.0), every
   captured field, `assumptions` (list), `owner_verbatim` (list, extensive only), and
   the confirmation record.

**Output:** brief.json with `interview_confirmed: true` and `pre_presentation_capture` block.

**Failure mode:** If the owner does not respond within 2 hours, send one reminder. After
4 hours, log a lock_timeout in the brief and notify: "Your brief is ready and waiting on
your YES before the team starts building."
If GROUNDED_CONTENT remains uncaptured at lock and the owner has not responded: set
`grounded_content_provisional: "[to be confirmed by operator before image generation]"`.
NEVER fabricate a grounded-content description.

### SOP 9.4 -- Kickoff / Handoff (trigger the dept build via its specialists)

**When to run:** Only after `interview_confirmed: true` AND `pre_presentation_gate_passed: true`.

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
