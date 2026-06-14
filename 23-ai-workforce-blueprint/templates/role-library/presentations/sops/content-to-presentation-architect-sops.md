# SOPs Mirror -- Content-to-Presentation Architect

**Source:** presentations/content-to-presentation-architect.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Source Ingestion per Modality (with the mandatory Privacy Rule)

**Purpose:** Acquire any owner-supplied source and produce clean, faithful text the rest of the pipeline can work from, while guaranteeing that no identity from a recording of people ever reaches an output.

**Hard rule:** For any Zoom recording, Google Meet recording, or any recording of identifiable people, NEVER carry a person's name, face, voice identity, employer, or any identifying detail into any output. Extract the LESSONS and the BIG POINTS only. Set `privacy_redaction_applied: true`. A raw un-redacted transcript is never written to the brief path and is never handed downstream.

**Enforcement check:** `transcript.txt` (for recordings) and `source_brief.json` are scanned for person names, employers, client/project names, and private figures. Zero identities present AND `privacy_redaction_applied: true` set = pass. Any leaked identity = hard fail (Gate 2). For non-recordings, a complete, non-fabricated transcript or extract = pass.

**When to run:** First, the instant a "turn this into a presentation" task arrives, before any analysis.

**Inputs:**
- The source reference (a URL, a file path, or an uploaded file) and its declared or inferred modality
- workspace SOUL.md / USER.md (context, never re-ask)

**Steps:**
1. Classify the modality and choose the realistic ingestion path:
   - **YouTube video / Vimeo video / any video file:** acquire the audio track and TRANSCRIBE it to text (speech-to-text). Capture timestamps. An accurate published caption track may serve as the transcript.
   - **Audio training (any audio file):** TRANSCRIBE to text with timestamps.
   - **Website / blog post:** FETCH the page and EXTRACT the main article content (readability extraction). Strip navigation, ads, comments, boilerplate. Keep headings, body, author-stated lists or steps.
   - **PDF / report / white paper:** PARSE the text layer to plain text, preserving section headings and figure captions. If no text layer exists, run optical character recognition. Keep page references.
   - **Zoom recording / Google Meet recording (and any recording of identifiable people):** TRANSCRIBE to text, THEN apply the PRIVACY RULE below before anything else uses the transcript.
2. **PRIVACY RULE (HARD, NON-SKIPPABLE):** replace every speaker name with a neutral role label or drop attribution; strip incidental identifying specifics (company/client/project names, account numbers, identifying anecdotes, private figures); if a point cannot be expressed without an identity, exclude it with `identity_bound: true` and notify the Director (never invent a substitute); set `privacy_redaction_applied: true`.
3. Write cleaned text to `working/content-to-presentation/<source-slug>/transcript.txt` (recordings/video/audio, already redacted) or `extract.md` (web/PDF/report/white-paper).
4. Record the ingestion result in the archive (modality, length, redaction flag).

**Outputs:** `transcript.txt` OR `extract.md` (redacted for recordings); archive entry.

**Hand to:** SOP 9.2 (Analysis).

**Generic pass/fail examples:**
- PASS: a 30-minute meeting recording becomes a redacted transcript with all speaker names replaced by role labels, one client name and one project code stripped, `privacy_redaction_applied: true`.
- FAIL: the brief states "the operations lead said to batch the work" -- the role label still ties the lesson to an identifiable person in a small named team; rewrite as "batch the work" with no attribution.
- FAIL: the source video is private and the transcript is invented from the title; report the failure instead.

**Escalation:** source cannot be acquired -> Director with exactly what failed and what is needed -> Operator via Telegram -> Human owner (must supply a usable source). Identity cannot be cleanly stripped from a load-bearing point -> exclude it, flag `identity_bound: true`, notify the Director -> Operator -> Human owner (clears the identity in writing).

---

### SOP 9.2 -- Analysis, Main-Theme Hook Discovery, and Step-by-Step Teaching Arc

**Purpose:** Turn the cleaned source text into the analytic spine of the deck: the major points, the one true main theme found by hook analysis, and a numbered teaching arc.

**Hard rule:** The brief must carry a single one-sentence `main_theme` derived from the source's through-line and a numbered `teaching_arc` where every step teaches exactly ONE major idea and states what it depends on. No multi-idea steps; no flat summary. This role does NOT search the open web for new facts -- claims needing proof are flagged for the Deep Research Specialist (ROLE-04), never asserted.

**Enforcement check:** `main_theme` is one sentence with at least one verbatim `hook_seed`; `teaching_arc` is an ordered array, each step has a point, a one-big-idea `headline_candidate`, and a `depends_on`; any external-fact claim carries `needs_proof: true` rather than a fetched statistic. All present = pass.

**When to run:** Immediately after SOP 9.1, on the cleaned source text.

**Inputs:** `transcript.txt` or `extract.md` from SOP 9.1.

**Steps:**
1. **Extract the major points.** List every DISTINCT major point (the load-bearing ideas, not every sentence). Number them. Record `major_point_count` -- a direct input to SOP 9.4.
2. **Find the MAIN THEME via hook analysis.** Find the single idea the whole source is about -- the line it repeats, returns to, or opens and closes on; the promise it makes; the sentence that, if removed, makes the rest pointless. Write it as ONE sentence in the owner's plain language. Capture up to three verbatim `hook_seeds` (the most repeatable, promise-bearing lines).
3. **Build the STEP-BY-STEP teaching arc.** Order the major points so each step earns the next: where a learner starts, what each point depends on, the order that makes the next point land. Number the arc. Each step records the point, the one-big-idea headline candidate, and its dependency. Map to the canonical teaching beats (open on the theme -> teach one idea per step -> close back on the theme).
4. **Flag claims needing proof.** For any point asserting a statistic, outcome, or external fact a slide would present as true, mark `needs_proof: true` with a one-line note. Do NOT verify it and do NOT search the web -- flag it for ROLE-04 via the Director.

**Outputs:** the `analysis` block of `source_brief.json` (major_point_count, main_theme, hook_seeds, teaching_arc, proof_flags).

**Hand to:** SOP 9.3 (Teaching Devices).

**Generic pass/fail examples:**
- PASS: 6 major points; main theme = "Most teams lose deals in the follow-up, not the pitch"; 3 hook seeds; 6 numbered arc steps with dependencies; 2 points flagged `needs_proof` for ROLE-04.
- FAIL: a bullet list of every sentence in the source with no main theme and no step dependencies -- a summary, not a teaching arc.
- FAIL: the brief states "studies show a 40% higher close rate" with a URL the role fetched itself -- that is ROLE-04's job; it should be a `needs_proof` flag.

**Escalation:** source has no discernible main theme -> Director with the strongest candidate marked `theme_provisional: true` -> Operator -> Human owner.

---

### SOP 9.3 -- Teaching Devices (Analogy, Metaphor, Mnemonic) and the Simplify-When Trigger

**Purpose:** Make each arc step land and stick by choosing the right teaching device, and make dense or jargon-heavy passages clear without losing meaning.

**Hard rule:** Each major point cluster records a device decision -- ANALOGY (compare a mechanism to a familiar one), METAPHOR (reframe what something IS to raise stakes), MNEMONIC (a memory device for a set or sequence), or `none` -- each with a one-line rationale. Never force a device onto an already-plain point. Apply the SIMPLIFY-WHEN trigger and preserve the original in `source_excerpt`; never dumb down content that is already clear.

**Enforcement check:** every arc step has a `device_type` and `device_rationale`; where the simplify trigger fired, `simplified: true` with `source_excerpt` populated; where it did not fire, the source phrasing is kept. All present = pass.

**Device definitions and choosing rule:** mechanism the audience cannot picture -> ANALOGY; stakes or meaning they underrate -> METAPHOR; a list or sequence they must recall -> MNEMONIC.

**Worked examples (generic -- adapt, never copy verbatim):**
- ANALOGY: "compound interest grows slowly then explodes" -> "like a snowball rolling downhill -- tiny at the top, unstoppable at the bottom."
- METAPHOR: "untracked small expenses drain a budget" -> "those small charges are termites in the walls."
- MNEMONIC: "check accuracy, clarity, and tone before publishing" -> "the A-C-T check: Accuracy, Clarity, Tone."

**When to run:** After the teaching arc exists (SOP 9.2), on each arc step.

**Inputs:** the `teaching_arc` from SOP 9.2.

**Steps:**
1. For each arc step, apply the choosing rule and record `device_type`, `device_text`, and `device_rationale` (a step with no device records `device_type: none` with a reason).
2. **SIMPLIFY-WHEN TRIGGER:** simplify when ANY holds -- (a) jargon the stated audience would not know without a definition; (b) one sentence carries more than one major idea (split it); (c) more than roughly a third of the source's length on a point that is one bullet for this audience (compress it); (d) a dense document (white paper, report, study) for a non-specialist audience. When fired, rewrite in plain language at the audience's level, preserve meaning, set `simplified: true`, keep the original in `source_excerpt`. When not fired, keep the source's phrasing.

**Outputs:** `teaching_arc` steps enriched with device fields and simplify flags.

**Hand to:** SOP 9.4 (Micro-vs-Full).

**Generic pass/fail examples:**
- PASS: a step explaining an unfamiliar process gets an analogy with the rationale "audience cannot picture the mechanism"; a plain step records `device_type: none, reason: already clear.`
- FAIL: a forced metaphor stacked on a point that was already plain, making it harder to follow.
- FAIL: a dense white-paper passage for a lay audience is copied verbatim with no simplification and no `source_excerpt`.

**Escalation:** no honest device fits a point -> use `none` and say so (a strained device is worse than a plain statement; no external escalation needed).

---

### SOP 9.4 -- Micro-vs-Full Decision

**Purpose:** Set the output scale so the deck pipeline builds the right size of presentation for the source and the owner's intended use.

**Hard rule:** `output_scale` (micro / full) is recorded WITH `scale_deciding_criteria` naming the specific factors that decided it. On a borderline with no stated intended use, ask the owner one question; never guess. When criteria conflict, the owner's stated intended use wins.

**Enforcement check:** `output_scale` is set and `scale_deciding_criteria` names the deciding factors (point count / source length / intended use / owner override). Present = pass.

**Decision criteria:**
- **MICRO** when ALL hold: 1 to 3 distinct major points; short or single-topic source; intended use is a quick teach, a single-idea share, or a fast internal briefing. Targets roughly 3 to 10 slides around ONE theme.
- **FULL** when ANY holds: 4 or more distinct major points; long or multi-topic source (full video, multi-section report, white paper); intended use is a full teaching deck, webinar, or flagship talk. Targets the pipeline's normal full-length arc.
- Conflict -> the owner's stated intended use wins; record the conflict and the deciding factor.

**When to run:** After the arc and devices exist (SOP 9.3), before handoff.

**Inputs:** `major_point_count`, source length, the owner's stated intended use.

**Steps:**
1. Compute the call from the criteria. Record `output_scale` and `scale_deciding_criteria`.
2. If intended use was never stated and the point count is borderline, ask the owner ONE question ("Is this a quick single-idea teach, or a full presentation?") and record the answer.

**Outputs:** `output_scale`, `scale_deciding_criteria` in `source_brief.json`.

**Hand to:** SOP 9.5 (Handoff).

**Generic pass/fail examples:**
- PASS: 6 points + 42-minute source + owner wants a webinar -> FULL, criteria = "point count + source length + intended use."
- PASS: 2 points + one short blog post + internal briefing -> MICRO, criteria = "point count + source length + intended use."
- FAIL: `output_scale: full` recorded with no `scale_deciding_criteria`, on a borderline source, without asking the owner.

**Escalation:** owner does not answer the borderline question in the working window -> default to MICRO, mark `scale_defaulted: true`, tell the Director the owner can upgrade on request (a defaulted micro is recoverable; an unrequested full build wastes budget).

---

### SOP 9.5 -- Handoff (Produce the Source Brief, Hand to the Director)

**Purpose:** Package everything into one `source_brief.json` and route it to the Director so the deck pipeline can build, without inventing any audience or representation field.

**Hard rule:** `source_brief.json` PROVIDES the theme (a derived hook seed), the teaching arc (one big idea per slide), the micro-vs-full call, and the proof flags. It NEVER fills REPRESENTATION_MIX, AUDIENCE_COMPOSITION_NOTE, VISUAL_MIX, DARK_OK, GROUNDED_CONTENT, or DELIVERABLE_SET -- those route to the Brainstorming Buddy's SOP 9.0. The handoff states this routing need explicitly so no audience default is invented downstream.

**Enforcement check:** the brief validates against the schema below; the audience/representation/style fields are absent (not guessed); the handoff message names the Director and states the SOP 9.0 routing need. Pass when all hold.

**When to run:** After SOP 9.4, once the brief is complete.

**Inputs:** every block produced by SOP 9.1 through 9.4.

**Steps:**
1. Assemble `working/content-to-presentation/<source-slug>/source_brief.json` (source_slug, modality, source_reference, privacy_redaction_applied, analysis block with major_point_count/main_theme/theme_provisional/hook_seeds/teaching_arc/proof_flags, output_scale, scale_deciding_criteria, scale_defaulted, handoff_to, handoff_at).
2. Map the source brief onto the Director's `deck_brief.json` intake (theme -> derived HOOK SEED; teaching arc -> one-big-idea-per-slide outline; micro-vs-full -> deck size; proof flags -> ROLE-04 routing). Do NOT add audience/representation/style fields.
3. Route the handoff to the Director. Because audience/representation fields are not captured, the Director either routes the owner through the Brainstorming Buddy's SOP 9.0 (with the theme/arc/hook pre-seeded so they are not re-asked) or, if those fields are on file, validates and proceeds. State this routing need explicitly.
4. Notify the owner via openclaw message send (never direct API): "I have turned your [modality] into a presentation brief -- main theme captured, [N] teaching steps mapped, built as a [micro/full] presentation. The Presentations team will confirm your audience and style, then build it."
5. Record the handoff in the archive.

**Outputs:** `source_brief.json`; archive entry; owner notified; Director holds the build.

**Hand to:** Director of Presentations (validates, collects audience/style via the Brainstorming Buddy if needed, dispatches: Hook Strategist -> Slide Copywriter / Offer Price Strategist -> Brand Steward -> Typography Architect -> Slide Image Creator -> QC -> Slide Submitter -> Media Librarian -> PPTX Assembly -> QC -> Presenter Coach -> Delivery Concierge).

**Generic pass/fail examples:**
- PASS: a complete `source_brief.json` with theme, arc, micro/full call, and proof flags, handed to the Director with the note "audience/representation not captured -- route through the Brainstorming Buddy SOP 9.0; theme/arc/hook pre-seeded."
- FAIL: the brief sets REPRESENTATION_MIX to a guessed ratio because the source did not state the audience.
- FAIL: the completed brief is left in the working directory and never handed to the Director.

**Escalation:** Director / Head role missing or errors on dispatch -> Master Orchestrator with the source brief attached. Never silently drop a completed brief.

---

### SOP 9.6 -- Trigger Standard (the owner phrases that route work to this role)

**Purpose:** Define exactly which owner phrasing routes a source-conversion request to this role and how that request flows to a finished deck.

**Hard rule:** A request routes here ONLY when a SOURCE is present (a link, a file, a recording). An idea-only request routes to the Brainstorming Buddy (ROLE-17). The trigger pattern is: "turn this <video | Vimeo | blog | PDF | report | white paper | audio | Zoom | Google Meet | recording | link> into a presentation (or deck / slides)."

**Enforcement check:** the Master Orchestrator / Director matches owner phrasing against the trigger list; a source-present request reaches this role; an idea-only request is redirected to the Buddy. Correct routing = pass.

**When to run:** This SOP is the routing contract; this role conforms to it rather than executing it.

**Trigger phrases:** "turn this video into a presentation," "turn this Vimeo into a presentation," "turn this blog post into a presentation," "turn this blog into a deck," "turn this PDF into a presentation," "turn this report into a presentation," "turn this white paper into a presentation," "turn this audio into a presentation," "turn this training into a deck," "turn this Zoom recording into a presentation," "turn this Google Meet recording into a presentation," "make a presentation from this [link/file]," "summarize this [video/article/document] as slides," "make a deck out of this."

**Disambiguation:** source present -> this role. Idea only, no source -> the Brainstorming Buddy. Both present -> ingest the source first, note the owner's additions in the handoff for the Buddy/Director.

**Flow from trigger to finished deck:**
1. Owner says a trigger phrase with a source -> Master Orchestrator / Director routes here.
2. This role: SOP 9.1 ingest (privacy rule on recordings) -> SOP 9.2 analysis + theme + arc -> SOP 9.3 devices + simplify -> SOP 9.4 micro-vs-full -> SOP 9.5 hand `source_brief.json` to the Director.
3. Director: validates, collects audience/representation/style via the Buddy's SOP 9.0 if not on file (theme/arc/hook pre-seeded), dispatches ROLE-04 only if proof flags want it.
4. Deck pipeline builds and the Delivery Concierge delivers the finished deck.

**Outputs:** none (routing contract).

**Hand to:** not applicable.

**Generic pass/fail examples:**
- PASS: owner sends a link with "make a deck out of this report" -> routed here, ingested, brief produced.
- FAIL: owner says "I have an idea for a webinar but no materials yet" -> mis-routed here; redirect to the Brainstorming Buddy.

**Escalation:** mis-routed here without a source -> redirect to the Brainstorming Buddy and tell the owner "Send me the link or file and I will turn it into a deck; if you only have the idea, our Brainstorming Buddy will shape it with you first."

---
