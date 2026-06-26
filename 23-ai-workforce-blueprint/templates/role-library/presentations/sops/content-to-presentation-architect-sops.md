# SOPs Mirror -- Content-to-Presentation Architect

**Source:** presentations/content-to-presentation-architect.md (v1.2)
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Audience-Mode Decision (Runs FIRST, Before Any Analysis)

**Purpose:** Decide the deciding fork for the whole build BEFORE ingestion: is this a ONE-PERSON presentation (a personalized deck for a single named recipient) or a GENERAL presentation (designed to be seen by many). This single choice drives privacy, personalization, and tone downstream.

**Hard rule:** ALWAYS ASK the owner the mode question before any analysis; never infer it. Record `presentation_mode` (one-person / general). In one-person mode, capture and confirm `recipient_name`. The owner's stated mode wins over any inference.

**Enforcement check:** `presentation_mode` is recorded before the ingestion step runs; in one-person mode `recipient_name` is present and confirmed; the mode was asked, not inferred. Pass when all hold (Gate 1).

**When to run:** FIRST, the instant a "turn this into a presentation" task arrives, before ingestion and before any analysis.

**Inputs:**
- The owner's request
- workspace SOUL.md / USER.md (context, never re-ask)

**Steps:**
1. Ask the owner via openclaw message send (never direct API), verbatim: "Is this a ONE-PERSON presentation (a personalized deck meant to be seen by a single named recipient) or a GENERAL presentation (designed to be seen by many)?" Ask even when the source seems to imply an answer.
2. Record `presentation_mode` = `"one-person"` or `"general"`.
3. One-person: capture `recipient_name` (the single person the deck is FOR -- the one identity the build keeps -- and the name on the personalized cover and closing). Confirm spelling.
4. General: record `recipient_name: null`; the build de-identifies everything.
5. State in one line what the mode means downstream so the owner can correct it: one-person keeps their named recipient and personalizes cover, close, and tone while stripping every other identity; general removes all personal references and is safe to show to many.

**Outputs:** `presentation_mode`, `recipient_name` in `source_brief.json`; archive records the mode.

**Hand to:** SOP 9.2 (Source Ingestion), which reads `presentation_mode` for the mode-aware privacy rule.

**Generic pass/fail examples:**
- PASS: owner is asked the mode question, replies "general," `presentation_mode: general` and `recipient_name: null` recorded before ingestion.
- PASS: owner replies "one-person, it is for the new regional lead," recipient name captured and spelling confirmed.
- FAIL: the role infers one-person from a personal-sounding source and never asks; Gate 1 fails.

**Escalation:** owner does not answer in the working window -> default to GENERAL (the safer mode; it removes all personal references), mark `mode_defaulted: true`, tell the Director the owner can switch to one-person on request. Never guess one-person.

---

### SOP 9.2 -- Source Ingestion per Modality (with the mandatory Mode-Aware Privacy Rule)

**Purpose:** Acquire any owner-supplied source and produce clean, faithful text the rest of the pipeline can work from, while applying the privacy treatment the chosen mode requires.

**Hard rule (reconciliation of the old blanket "zero names" rule):** the privacy treatment now depends on `presentation_mode` and SUPERSEDES the old blanket hard-zero-names rule. GENERAL mode = remove ALL personal references (full de-identification; identical to the old hard-zero behavior). ONE-PERSON mode = keep ONLY the named `recipient_name` (the deck is FOR them) and strip every OTHER identifiable person's personally identifiable information. In BOTH modes set `privacy_redaction_applied: true` and record `privacy_mode` = the mode. A raw un-redacted transcript is never written to the brief path and is never handed downstream.

**Enforcement check:** `transcript.txt` (for recordings) and `source_brief.json` are scanned against the mode. GENERAL: zero identities present. ONE-PERSON: only `recipient_name` present, zero other identities or third-party personally identifiable information. `privacy_redaction_applied: true` AND `privacy_mode` matches `presentation_mode` = pass. Any mode-disallowed identity = hard fail (Gate 3). For non-recordings, a complete, non-fabricated transcript or extract = pass.

**When to run:** Immediately after SOP 9.1, once `presentation_mode` is recorded, before any analysis.

**Inputs:**
- The source reference (a URL, a file path, or an uploaded file) and its declared or inferred modality
- `presentation_mode` and `recipient_name` from SOP 9.1
- workspace SOUL.md / USER.md (context, never re-ask)

**Steps:**
1. Classify the modality and choose the realistic ingestion path:
   - **YouTube video / Vimeo video / any video file:** acquire the audio track and TRANSCRIBE it to text (speech-to-text). Capture timestamps. An accurate published caption track may serve as the transcript.
   - **Audio training (any audio file):** TRANSCRIBE to text with timestamps.
   - **Website / blog post:** FETCH the page and EXTRACT the main article content (readability extraction). Strip navigation, ads, comments, boilerplate. Keep headings, body, author-stated lists or steps.
   - **PDF / report / white paper:** PARSE the text layer to plain text, preserving section headings and figure captions. If no text layer exists, run optical character recognition. Keep page references.
   - **Zoom recording / Google Meet recording (and any recording of identifiable people):** TRANSCRIBE to text, THEN apply the MODE-AWARE PRIVACY RULE below before anything else uses the transcript.
2. **MODE-AWARE PRIVACY RULE (HARD, NON-SKIPPABLE):**
   - **GENERAL mode:** remove ALL personal references -- every name, identity, piece of personally identifiable information, employer, client name, project code name, account number, identifying anecdote, and private figure. Full de-identification; the deck is safe to show to many. Replace every speaker name with a neutral role label or drop attribution; capture WHAT was taught, not WHO said it.
   - **ONE-PERSON mode:** KEEP the named `recipient_name` (the deck is FOR them; their name appears on the personalized cover and closing). It is the ONLY identity allowed to survive. STRIP every OTHER person's personally identifiable information exactly as in GENERAL mode (other speakers, third parties, other employers, other client names, project codes, account numbers, identifying anecdotes about anyone other than the recipient, private figures). The recipient's own private figures are kept only when they are the point of the lesson FOR the recipient and the owner cleared them; when in doubt, strip.
   - **Both modes:** if a lesson cannot be expressed without a mode-disallowed identity, exclude it with `identity_bound: true` and notify the Director (never invent a substitute). Set `privacy_redaction_applied: true` and `privacy_mode` = the mode.
3. Write cleaned text to `working/content-to-presentation/<source-slug>/transcript.txt` (recordings/video/audio, already redacted to the mode standard) or `extract.md` (web/PDF/report/white-paper).
4. Record the ingestion result in the archive (modality, presentation_mode, length, redaction flag).

**Outputs:** `transcript.txt` OR `extract.md` (redacted to the mode standard for recordings); archive entry.

**Hand to:** SOP 9.3 (Signal-vs-Fluff Extraction).

**Generic pass/fail examples:**
- PASS (GENERAL): a 30-minute meeting recording becomes a redacted transcript with all speaker names dropped, one client name and one project code stripped, `privacy_redaction_applied: true`, `privacy_mode: general`.
- PASS (ONE-PERSON): a recording where the named recipient's identity is kept (the deck is FOR them) and two third-party client names plus another speaker's name are stripped, `privacy_mode: one-person`.
- FAIL: a GENERAL brief states "the operations lead said to batch the work" -- the role label still ties the lesson to an identifiable person in a small named team; rewrite as "batch the work" with no attribution.
- FAIL: a ONE-PERSON brief leaks a third party's name in addition to the recipient; Gate 3 fails.
- FAIL: the source video is private and the transcript is invented from the title; report the failure instead.

**Escalation:** source cannot be acquired -> Director with exactly what failed and what is needed -> Operator via Telegram -> Human owner. Identity cannot be cleanly stripped from a load-bearing point -> exclude it, flag `identity_bound: true`, notify the Director -> Operator -> Human owner (clears the identity in writing).

---

### SOP 9.3 -- Signal-vs-Fluff Extraction (Both Modes)

**Purpose:** Separate the SIGNAL from the FLUFF so the deck functions as something useful, focused on the main points, not a transcript of a conversation.

**Hard rule:** Strip personal-conversation filler, chitchat, scheduling talk, tangents, and off-topic banter. KEEP the main theme, main points, decisions, lessons, key concepts, and action items. Capture `action_items` and `key_soundbites` where the source contains them. Apply the mode-aware privacy rule to every kept soundbite.

**Enforcement check:** no conversational fluff appears in the kept signal; `action_items` and `key_soundbites` are present when the source contains them; no real point was deleted as "filler." Pass when all hold (Gate 4).

**When to run:** Immediately after SOP 9.2, on the cleaned (mode-redacted, for recordings) source text, before analysis.

**Inputs:** `transcript.txt` or `extract.md` from SOP 9.2.

**Steps:**
1. **Strip the FLUFF.** Remove greetings and goodbyes, scheduling talk, small talk, technical-setup talk, tangents, repeated false starts, and off-topic banter (anything that does not advance a point, decision, lesson, key concept, or action item).
2. **KEEP the SIGNAL.** Preserve the main theme, main points, decisions, lessons, key concepts, and action items. When a useful point is buried inside chitchat, lift the point and drop the chitchat. Never delete a real point because it was phrased casually.
3. **Capture the ACTION ITEMS** into an `action_items` array (these feed the infographic checklist, SOP 9.7); kept in both modes.
4. **Capture the KEY SOUNDBITES** into a `key_soundbites` array (these feed the hook seeds in SOP 9.4, the checklist, and the memorable hooks in SOP 9.5); apply the mode-aware privacy rule to each before keeping.
5. Write the de-fluffed `signal_text` plus `action_items` and `key_soundbites` for SOP 9.4 onward.

**Outputs:** de-fluffed signal text; `action_items` (array); `key_soundbites` (array).

**Hand to:** SOP 9.4 (Analysis).

**Generic pass/fail examples:**
- PASS: a recording's opening small talk and a mid-call scheduling tangent are removed; 6 main points, 3 action items, and 2 soundbites are kept.
- FAIL: the brief carries "can everyone see my screen" and a weekend-plans tangent as if they were content.
- FAIL: a short, casually phrased but load-bearing point is dropped as "filler."

**Escalation:** source is all signal and no fluff -> record `fluff_removed: false` with a note and proceed; never invent fluff to remove. When unsure whether a passage is signal or fluff, keep it and let the analysis decide.

---

### SOP 9.4 -- Analysis, Main-Theme Hook Discovery, and Step-by-Step Teaching Arc

**Purpose:** Turn the de-fluffed signal text into the analytic spine of the deck: the major points, the one true main theme found by hook analysis, and a numbered teaching arc that ELABORATES the points.

**Hard rule:** The brief must carry a single one-sentence `main_theme` derived from the source's through-line and a numbered `teaching_arc` where every step teaches exactly ONE major idea, carries a short ELABORATION (what it means and why it matters), and states what it depends on. No multi-idea steps; not a bullet dump. This role does NOT search the open web for new facts -- claims needing proof are flagged for the Deep Research Specialist (ROLE-04), never asserted.

**Enforcement check:** `main_theme` is one sentence with at least one verbatim `hook_seed`; `teaching_arc` is an ordered array, each step has a point, a one-big-idea `headline_candidate`, an `elaboration`, and a `depends_on`; any external-fact claim carries `needs_proof: true` rather than a fetched statistic. All present = pass.

**When to run:** Immediately after SOP 9.3, on the de-fluffed signal text.

**Inputs:** de-fluffed signal text, `action_items`, and `key_soundbites` from SOP 9.3.

**Steps:**
1. **Extract the major points.** List every DISTINCT major point (the load-bearing ideas, not every sentence). Number them. Record `major_point_count` -- a direct input to SOP 9.6.
2. **Find the MAIN THEME via hook analysis.** Find the single idea the whole source is about -- the line it repeats, returns to, or opens and closes on; the promise it makes; the sentence that, if removed, makes the rest pointless. Write it as ONE sentence in the owner's plain language. Capture up to three verbatim `hook_seeds` (drawn from `key_soundbites` where possible).
3. **Build the STEP-BY-STEP teaching arc that ELABORATES.** Order the major points so each step earns the next. Number the arc. Each step records the point, the one-big-idea headline candidate, a short elaboration (what it means and why it matters), and its dependency. Map to the canonical teaching beats (open on the theme -> teach one idea per step -> close back on the theme).
4. **Flag claims needing proof.** For any point asserting a statistic, outcome, or external fact a slide would present as true, mark `needs_proof: true` with a one-line note. Do NOT verify it and do NOT search the web -- flag it for ROLE-04 via the Director.

**Outputs:** the `analysis` block of `source_brief.json` (major_point_count, main_theme, hook_seeds, teaching_arc with elaboration, proof_flags).

**Hand to:** SOP 9.4B (Source Persuasion-Intelligence Extraction).

**Generic pass/fail examples:**
- PASS: 6 major points; main theme = "Most teams lose deals in the follow-up, not the pitch"; 3 hook seeds; 6 numbered arc steps with elaboration and dependencies; 2 points flagged `needs_proof`.
- FAIL: a bullet list of every sentence with no main theme, no dependencies, and no elaboration -- a summary, not a teaching arc.
- FAIL: the brief states "studies show a 40% higher close rate" with a URL the role fetched itself -- that is ROLE-04's job; it should be a `needs_proof` flag.

**Escalation:** source has no discernible main theme -> Director with the strongest candidate marked `theme_provisional: true` -> Operator -> Human owner.

---

### SOP 9.4B -- Source Persuasion-Intelligence Extraction

**Purpose:** Extract from the source itself the persuasion fields the regular build brief carries, and write them into `source_brief.json` as a `persuasion_intelligence` block so the shared downstream roles receive parity-grade material regardless of pipeline entry point.

**Hard rule:** Extract ONLY what the source actually contains. Do NOT fill REPRESENTATION_MIX, AUDIENCE_COMPOSITION_NOTE, VISUAL_MIX, DARK_OK, GROUNDED_CONTENT, or DELIVERABLE_SET -- those route to the Brainstorming Buddy. Never guess a field not in the source. List every absent field in `fields_absent_in_source`. Do NOT run web searches. Do NOT produce image prompts, select models, or define a rendering path -- the Content-to-Presentation pipeline NEVER owns a renderer or image path; all image work routes through the shared Slide Image Creator and the canonical renderer `build_deck.py` (the retired `render_deck.py` is an orphan — see `docs/LEGACY-RETIREMENT.md`). A converter-specific image path is a hard doctrine violation.

**Privacy rule:** Runs AFTER SOP 9.2 mode-aware redaction. In GENERAL mode, extracted `proof_assets` and `offer_intelligence` carry zero third-party identities. In ONE-PERSON mode only `recipient_name` may appear. Re-state `privacy_mode` on the block.

**Enforcement check:** `persuasion_intelligence_complete: true` is present; `fields_absent_in_source` is explicit (never empty when fields are absent); `privacy_mode` on the block matches `presentation_mode`; no audience/representation field is filled; no web search was run; no image prompt or renderer is produced. Pass when all hold (Gates 15-18).

**When to run:** Immediately after SOP 9.4, before SOP 9.5. Runs on the de-fluffed `signal_text` from SOP 9.3.

**Inputs:** de-fluffed signal text from SOP 9.3; `analysis` block from SOP 9.4; `presentation_mode` and `privacy_mode` from SOP 9.1/9.2.

**Steps:**
1. **Transformation promise:** scan the opening 10-15% and any explicit "so that you can..." / "by the end of this you will..." framing. Record `transformation_promise` if found; list as absent if not.
2. **Primary objection:** look for "you might think... but actually...", "most people believe... the truth is..." reframe patterns. Record `primary_objection` if found.
3. **Goal and call to action:** identify what the source invites the audience to DO (purchase, book, apply, download). Extract verbatim. Record `goal` and `cta_action` if found.
4. **Target feeling:** infer the emotional arc (frustration to empowerment, confusion to clarity, fear to confidence). Record as `target_feeling` with `target_feeling_inferred: true`.
5. **Tone detected:** map the source register to one of seven named tones: Inspirational / Tough Love / Challenger / Teacher / Storyteller / High-Energy Hype / Calm Premium. Record as `tone_detected`. Not locked -- the owner overrides at Brainstorming Buddy SOP 9.0.
6. **Narrative arc type:** classify as Hormozi-arc / straight-teaching / case-study / how-to / conceptual-argument. Record as `narrative_arc_type`.
7. **Hook candidate:** compress the central promise into ONE singable line (distinct from the verbatim `hook_seeds` SOP 9.4 captured). The Hook Strategist refines this, not re-discovers it. Record as `hook_candidate`.
8. **Offer intelligence (when source contains an offer):** extract verbatim: `offer_name`, `offer_stack` (array), `price_mode` (drop/range/stated/not-present), `price_anchor`, `final_price`, `payment_plan`, `guarantee`, `scarcity_beats` (array), `vip_tier`. Do NOT fold offer beats into the teaching arc. Set `offer_intelligence: null` when no offer exists.
9. **Proof assets (source's own proof only):** extract the source's OWN stated results, testimonials, case outcomes, and revenue figures as an array of objects (`claim`, `source_context`, `confidence: high|medium`). Apply mode-aware privacy rule. These are distinct from `proof_flags` (which flag claims needing external proof from ROLE-04). The proof assets also pre-seed ROLE-04 Categories B and D -- ROLE-04 corroborates what the source asserts, not just what `proof_flags` tag.
10. **Assemble:** write `persuasion_intelligence` into `source_brief.json` alongside the `analysis` block. Set `persuasion_intelligence_complete: true`. List every absent field in `fields_absent_in_source`.

**Outputs:** `persuasion_intelligence` block in `source_brief.json` (transformation_promise, primary_objection, goal, cta_action, target_feeling, target_feeling_inferred, tone_detected, narrative_arc_type, hook_candidate, offer_intelligence, proof_assets, persuasion_intelligence_complete, fields_absent_in_source, privacy_mode).

**Hand to:** SOP 9.5 (Teaching Devices).

**Generic pass/fail examples:**
- PASS: a 45-minute training session yields `transformation_promise` from the opening segment, `primary_objection` from a "most people think..." reframe, `tone_detected: Teacher`, `narrative_arc_type: straight-teaching`, a synthesized `hook_candidate`, and `offer_intelligence` with a three-payment plan extracted verbatim; two proof assets extracted from the testimonial section; `fields_absent_in_source: ["goal", "cta_action"]` (the source was training-only, no explicit call to action).
- PASS: a technical white paper -- `persuasion_intelligence_complete: true`, all fields in `fields_absent_in_source`; note: "Source is informational/technical -- no persuasion structure found; Brainstorming Buddy must supply all persuasion fields."
- FAIL: `offer_intelligence` fields are folded into the `teaching_arc` steps instead of the dedicated sub-block -- Gate 16 fails.
- FAIL: `proof_assets` contains a claim with an external URL the role fetched itself (duplicating ROLE-04) -- Gate 14 and Gate 17 fail.
- FAIL: `persuasion_intelligence` block is absent from `source_brief.json` -- Gate 15 fails; AF-CONVERTER-PARITY triggers at QC.

**Escalation:** source is informational/technical with no persuasion structure -> record all fields as absent in `fields_absent_in_source`, set `persuasion_intelligence_complete: true`, and notify the Director to route all persuasion fields to the Brainstorming Buddy SOP 9.0.

---

### SOP 9.5 -- Teaching Devices (Analogy, Metaphor, Mnemonic, Memorable Hooks) and the Simplify-When Trigger

**Purpose:** Make each arc step land and stick by choosing the right teaching device, and make dense or jargon-heavy passages clear without losing meaning.

**Hard rule:** Each major point cluster records a device decision -- ANALOGY (compare a mechanism to a familiar one), METAPHOR (reframe what something IS to raise stakes), MNEMONIC (a memory device for a set or sequence), MEMORABLE HOOK (a sticky repeatable phrasing, often from a `key_soundbite`), or `none` -- each with a one-line rationale. Never force a device onto an already-plain point. Apply the SIMPLIFY-WHEN trigger and preserve the original in `source_excerpt`; never dumb down content that is already clear.

**Enforcement check:** every arc step has a `device_type` and `device_rationale`; where the simplify trigger fired, `simplified: true` with `source_excerpt` populated; where it did not fire, the source phrasing is kept. All present = pass.

**Device definitions and choosing rule:** mechanism the audience cannot picture -> ANALOGY; stakes or meaning they underrate -> METAPHOR; a list or sequence they must recall -> MNEMONIC; a point that deserves to leave the room as a repeatable phrase -> MEMORABLE HOOK.

**Worked examples (generic -- adapt, never copy verbatim):**
- ANALOGY: "compound interest grows slowly then explodes" -> "like a snowball rolling downhill -- tiny at the top, unstoppable at the bottom."
- METAPHOR: "untracked small expenses drain a budget" -> "those small charges are termites in the walls."
- MNEMONIC: "check accuracy, clarity, and tone before publishing" -> "the A-C-T check: Accuracy, Clarity, Tone."
- MEMORABLE HOOK: "follow-up is where deals are won" -> "the fortune is in the follow-up."

**When to run:** After the teaching arc exists (SOP 9.4), on each arc step.

**Inputs:** the `teaching_arc` from SOP 9.4.

**Steps:**
1. For each arc step, apply the choosing rule and record `device_type`, `device_text`, and `device_rationale` (a step with no device records `device_type: none` with a reason).
2. **SIMPLIFY-WHEN TRIGGER:** simplify when ANY holds -- (a) jargon the stated audience would not know without a definition; (b) one sentence carries more than one major idea (split it); (c) more than roughly a third of the source's length on a point that is one bullet for this audience (compress it); (d) a dense document (white paper, report, study) for a non-specialist audience. When fired, rewrite in plain language at the audience's level, preserve meaning, set `simplified: true`, keep the original in `source_excerpt`. When not fired, keep the source's phrasing.

**Outputs:** `teaching_arc` steps enriched with device fields and simplify flags.

**Hand to:** SOP 9.6 (Micro-vs-Full).

**Generic pass/fail examples:**
- PASS: a step explaining an unfamiliar process gets an analogy with the rationale "audience cannot picture the mechanism"; a plain step records `device_type: none, reason: already clear.`
- FAIL: a forced metaphor stacked on a point that was already plain, making it harder to follow.
- FAIL: a dense white-paper passage for a lay audience is copied verbatim with no simplification and no `source_excerpt`.

**Escalation:** no honest device fits a point -> use `none` and say so (a strained device is worse than a plain statement; no external escalation needed).

---

### SOP 9.6 -- Micro-vs-Full Decision

**Purpose:** Set the output scale so the deck pipeline builds the right size of presentation for the source and the owner's intended use. (Scale is independent of `presentation_mode`: a one-person deck can be micro or full.)

**Hard rule:** `output_scale` (micro / full) is recorded WITH `scale_deciding_criteria` naming the specific factors that decided it. On a borderline with no stated intended use, ask the owner one question; never guess. When criteria conflict, the owner's stated intended use wins.

**Enforcement check:** `output_scale` is set and `scale_deciding_criteria` names the deciding factors (point count / source length / intended use / owner override). Present = pass.

**Decision criteria:**
- **MICRO** when ALL hold: 1 to 3 distinct major points; short or single-topic source; intended use is a quick teach, a single-idea share, or a fast internal briefing. Targets roughly 3 to 10 slides around ONE theme.
- **FULL** when ANY holds: 4 or more distinct major points; long or multi-topic source (full video, multi-section report, white paper); intended use is a full teaching deck, webinar, or flagship talk. Targets the pipeline's normal full-length arc.
- Conflict -> the owner's stated intended use wins; record the conflict and the deciding factor.

**When to run:** After the arc and devices exist (SOP 9.5), before the bundle definition.

**Inputs:** `major_point_count`, source length, the owner's stated intended use.

**Steps:**
1. Compute the call from the criteria. Record `output_scale` and `scale_deciding_criteria`.
2. If intended use was never stated and the point count is borderline, ask the owner ONE question ("Is this a quick single-idea teach, or a full presentation?") and record the answer.

**Outputs:** `output_scale`, `scale_deciding_criteria` in `source_brief.json`.

**Hand to:** SOP 9.7 (Deliverable Bundle Definition).

**Generic pass/fail examples:**
- PASS: 6 points + 42-minute source + owner wants a webinar -> FULL, criteria = "point count + source length + intended use."
- PASS: 2 points + one short blog post + internal briefing -> MICRO, criteria = "point count + source length + intended use."
- FAIL: `output_scale: full` recorded with no `scale_deciding_criteria`, on a borderline source, without asking the owner.

**Escalation:** owner does not answer the borderline question in the working window -> default to MICRO, mark `scale_defaulted: true`, tell the Director the owner can upgrade on request.

---

### SOP 9.7 -- Deliverable Bundle Definition (Both Modes; Cover and Closing in One-Person Mode)

**Purpose:** Name the USABLE bundle a content-to-presentation source must produce (deck + Presenter guide + infographic checklist), supply the checklist raw material, and require the personalized cover and closing in one-person mode. This role NAMES the bundle and supplies raw material; the build roles produce the artifacts.

**Hard rule:** `deliverable_bundle` names the deck, the Presenter guide in portable-document format, and the one-page infographic checklist of the main points and action items, as required outputs. `checklist_items` is populated from the main points and `action_items`. In one-person mode, `personalized_cover` and `personalized_closing` are required and addressed to the named recipient; tone and examples are tailored only where the source supports it (never invented). `audience_appropriateness_checked: true` confirms the brief matches its mode.

**Enforcement check:** `deliverable_bundle` lists all three outputs; `checklist_items` is non-empty (from points and action items); one-person mode has `personalized_cover: true` and `personalized_closing: true` with the recipient named and grounded `tone_personalization_notes`; general mode has both false and no recipient; `audience_appropriateness_checked: true`. Pass when all hold (Gates 10, 11, 12).

**When to run:** After the scale is set (SOP 9.6), before handoff.

**Inputs:** every block produced by SOP 9.1 through 9.6, including `action_items` and `key_soundbites` from SOP 9.3.

**Steps:**
1. **Name the DELIVERABLE BUNDLE (both modes)** in `deliverable_bundle`: the deck (the PPTX Assembly Specialist also emits its portable-document export per the system-wide rule), the Presenter guide in portable-document format (built by the Presenters Guide Specialist; named required, not built here), and the one-page infographic checklist (built as an infographic-style slide by the Slide Image Creator and Typography Architect; named required here).
2. **Supply the checklist raw material** in `checklist_items`: a short, scannable, one-line-per-item list of the main points plus the action items, in teaching-arc order; attach the strongest `key_soundbites` for a memorable line.
3. **ONE-PERSON deliverables (only when mode is one-person):** record `personalized_cover` and `personalized_closing` (both true), each addressed to the `recipient_name`; record `tone_personalization_notes` describing how to tailor tone and examples, grounded only in what the source and owner stated. In general mode, set both false and name no recipient; cover and closing are generic.
4. **AUDIENCE-APPROPRIATENESS check:** confirm a general deck carries zero personal references and a one-person deck keeps only the named recipient; record `audience_appropriateness_checked: true` with a one-line confirmation; fix any leak before handoff.

**Outputs:** `deliverable_bundle`, `checklist_items`, `personalized_cover`, `personalized_closing`, `tone_personalization_notes`, `audience_appropriateness_checked` in `source_brief.json`.

**Hand to:** SOP 9.8 (Handoff).

**Generic pass/fail examples:**
- PASS: a general full deck names deck + Presenter guide + infographic checklist; `checklist_items` carries 5 points and 3 action items; cover and closing generic.
- PASS: a one-person deck names the bundle plus `personalized_cover: true` and `personalized_closing: true` addressed to the recipient, with source-grounded tone notes.
- FAIL: a deck-only brief with no Presenter guide and no infographic checklist named.
- FAIL: a one-person brief invents a personal fact about the recipient that the source never stated.

**Escalation:** source has no explicit action items -> build the checklist from main points alone, `action_items: []` with a note; never fabricate. One-person mode but no confirmed recipient name -> return to SOP 9.1 and confirm it first.

---

### SOP 9.8 -- Handoff (Produce the Source Brief, Hand to the Director)

**Purpose:** Package everything into one `source_brief.json` and route it to the Director so the deck pipeline can build, carrying the `presentation_mode` and the deliverable bundle, without inventing any audience or representation field.

**Hard rule:** `source_brief.json` PROVIDES the `presentation_mode` (which drives privacy, personalization, tone), the theme (a derived hook seed), the teaching arc (one big idea per slide, elaborated), the micro-vs-full call, the deliverable bundle and `checklist_items`, the one-person cover and closing requirements, and the proof flags. It NEVER fills REPRESENTATION_MIX, AUDIENCE_COMPOSITION_NOTE, VISUAL_MIX, DARK_OK, GROUNDED_CONTENT, or DELIVERABLE_SET -- those route to the Brainstorming Buddy's SOP 9.0. The `presentation_mode` is distinct from the Director's Mode A / Mode B (build-from-scratch vs augment-existing); they are independent axes.

**Enforcement check:** the brief validates against the schema below; the audience/representation/style fields are absent (not guessed); the `presentation_mode` and deliverable bundle are present; the handoff message names the Director and states the SOP 9.0 routing need. Pass when all hold.

**When to run:** After SOP 9.7, once the brief is complete.

**Inputs:** every block produced by SOP 9.1 through 9.7.

**Steps:**
1. Assemble `working/content-to-presentation/<source-slug>/source_brief.json` (source_slug, modality, source_reference, presentation_mode, recipient_name, mode_defaulted, privacy_redaction_applied, privacy_mode, fluff_removed, action_items, key_soundbites, analysis block with major_point_count/main_theme/theme_provisional/hook_seeds/teaching_arc-with-elaboration-and-device-fields/proof_flags, output_scale, scale_deciding_criteria, scale_defaulted, deliverable_bundle, checklist_items, personalized_cover, personalized_closing, tone_personalization_notes, audience_appropriateness_checked, handoff_to, handoff_at).
2. Map the source brief onto the Director's `deck_brief.json` intake (presentation_mode -> privacy/personalization/tone; theme -> derived HOOK SEED; teaching arc -> one-big-idea-per-slide outline; micro-vs-full -> deck size; deliverable_bundle + checklist_items -> required outputs; one-person cover/closing -> personalized slides; proof flags -> ROLE-04 routing). Do NOT add audience/representation/style fields.
3. Route the handoff to the Director. Because audience/representation fields are not captured, the Director either routes the owner through the Brainstorming Buddy's SOP 9.0 (with theme/arc/hook/mode pre-seeded so they are not re-asked) or, if those fields are on file, validates and proceeds. The mode and bundle travel with the brief so the Director propagates them to the build. **ROLE-04 Research Dispatch (MANDATORY):** The Director MUST dispatch ROLE-04 as Phase -0.5 for ALL content-to-presentation builds, regardless of `proof_flags`. `proof_flags` is copy-level ingest only; ROLE-04's full six-category mandate (A through F) runs unconditionally. `source_brief.json` pre-seeds ROLE-04's intake (main_theme, teaching_arc, any GROUNDED_CONTENT notes). The Director blocks Phase B+ until the Research Brief is complete and `research_complete: true`.
4. Notify the owner via openclaw message send (never direct API): "I have turned your [modality] into a presentation brief -- main theme captured, [N] teaching steps mapped, built as a [one-person/general] [micro/full] presentation. You will receive the deck, a presenter guide, and a one-page checklist of the key points. The Presentations team will confirm your audience and style, then build it."
5. Record the handoff in the archive.

**Outputs:** `source_brief.json`; archive entry; owner notified; Director holds the build.

**Hand to:** Director of Presentations (validates, propagates `presentation_mode` and the deliverable bundle, collects audience/style via the Brainstorming Buddy if needed, dispatches: Hook Strategist -> Slide Copywriter / Offer Price Strategist -> Brand Steward -> Typography Architect -> Slide Image Creator -> QC -> Slide Submitter -> Media Librarian -> PPTX Assembly (deck plus portable-document export) -> QC -> Presenters Guide Specialist -> Presenter Coach -> Delivery Concierge).

**Generic pass/fail examples:**
- PASS: a complete `source_brief.json` with mode, theme, elaborated arc, micro/full call, deliverable bundle, and proof flags, handed to the Director with the note "audience/representation not captured -- route through the Brainstorming Buddy SOP 9.0; theme/arc/hook/mode pre-seeded."
- FAIL: the brief sets REPRESENTATION_MIX to a guessed ratio because the source did not state the audience.
- FAIL: the completed brief is left in the working directory and never handed to the Director.

**Escalation:** Director / Head role missing or errors on dispatch -> Master Orchestrator with the source brief attached. Never silently drop a completed brief.

---

### SOP 9.9 -- Trigger Standard (the owner phrases that route work to this role)

**Purpose:** Define exactly which owner phrasing routes a source-conversion request to this role and how that request flows to a finished bundle.

**Hard rule:** A request routes here ONLY when a SOURCE is present (a link, a file, a recording). An idea-only request routes to the Brainstorming Buddy (ROLE-17). The trigger pattern is: "turn this <video | Vimeo | blog | PDF | report | white paper | audio | Zoom | Google Meet | recording | link> into a presentation (or deck / slides)."

**Enforcement check:** the Master Orchestrator / Director matches owner phrasing against the trigger list; a source-present request reaches this role; an idea-only request is redirected to the Buddy. Correct routing = pass.

**When to run:** This SOP is the routing contract; this role conforms to it rather than executing it.

**Trigger phrases:** "turn this video into a presentation," "turn this Vimeo into a presentation," "turn this blog post into a presentation," "turn this blog into a deck," "turn this PDF into a presentation," "turn this report into a presentation," "turn this white paper into a presentation," "turn this audio into a presentation," "turn this training into a deck," "turn this Zoom recording into a presentation," "turn this Google Meet recording into a presentation," "make a presentation from this [link/file]," "summarize this [video/article/document] as slides," "make a deck out of this."

**Disambiguation:** source present -> this role. Idea only, no source -> the Brainstorming Buddy. Both present -> ingest the source first, note the owner's additions in the handoff for the Buddy/Director.

**Flow from trigger to finished deck:**
1. Owner says a trigger phrase with a source -> Master Orchestrator / Director routes here.
2. This role: SOP 9.1 audience-mode (one-person / general, asked first) -> SOP 9.2 ingest (mode-aware privacy rule on recordings) -> SOP 9.3 signal-vs-fluff -> SOP 9.4 analysis + theme + arc -> SOP 9.4B source persuasion-intelligence extraction -> SOP 9.5 devices + simplify -> SOP 9.6 micro-vs-full -> SOP 9.7 deliverable bundle (deck + Presenter guide + infographic checklist; cover/closing in one-person mode) -> SOP 9.8 hand `source_brief.json` to the Director.
3. Director: validates, propagates mode, bundle, AND `persuasion_intelligence` block into `intake.json`; satisfies mandatory-variable check from `persuasion_intelligence` FIRST; routes genuinely source-absent fields and audience/representation fields to the Brainstorming Buddy's SOP 9.0 (theme/arc/hook/mode/persuasion-intelligence pre-seeded); dispatches ROLE-04 unconditionally as mandatory Phase -0.5.
4. Deck pipeline builds (PPTX Assembly emits the deck plus its portable-document export) and the Delivery Concierge delivers the finished bundle.

**Outputs:** none (routing contract).

**Hand to:** not applicable.

**Generic pass/fail examples:**
- PASS: owner sends a link with "make a deck out of this report" -> routed here, ingested, brief produced.
- FAIL: owner says "I have an idea for a webinar but no materials yet" -> mis-routed here; redirect to the Brainstorming Buddy.

**Escalation:** mis-routed here without a source -> redirect to the Brainstorming Buddy and tell the owner "Send me the link or file and I will turn it into a deck; if you only have the idea, our Brainstorming Buddy will shape it with you first."

---
