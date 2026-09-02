# SOPs Mirror -- Presenter's Speech Writer

**Source:** presentations/presenters-speech-writer.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9A. The Proven Webinar Structure (write to this arc)

This SOP set enforces the proven 11-stage webinar arc defined in Section 9A of the role file: **welcome -> who-this-is-for -> presenter credibility/origin story -> big promise -> teach the framework -> proof/case studies -> offer + value stack -> price drops/anchoring -> scarcity/close -> recap.** The OPEN must be a genuine live webinar welcome (greeting, congratulate them for being here, engagement question into the chat, housekeeping) and the CLOSE must circle back to and end on the hook. Source-backed (Brunson Perfect Webinar; Fladlien; Porterfield; Jim Edwards VSL; Informa TechTarget two-minute opening; ClickMeeting ~70/30 content-to-offer split). Per-stage word coverage is allocated by proportion of DURATION_MIN (see Section 9A table in the role file). The teach and proof stages weave in REAL CITED research; never fabricate a stat or quote. See the role file Section 9A for the full table and citations; the role file is authoritative.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md; voice authority: 30-fish-audio-api-reference/. Structure authority: Section 9A.

### SOP 9.0 -- Resilient Speech-Build Harness (budget-up-front + checkpoint-resume + auto-expand + retry)

**When to run:** Before SOP 9.1. This SOP governs HOW all API-driven generation in the speech pipeline is executed. It is not optional.

**Why it exists:** Two production failures drove this SOP:
1. A provider HTTP 529 "overloaded" response killed the build mid-slide, losing all generated text.
2. The length gate (SOP 9.2 step 3) fired AFTER writing, requiring manual expansion and full re-runs.

**The tool:** `presentations/scripts/speech_build_harness.py` (owned by this role; does NOT touch build_deck.py, sync_check.py, or PIPELINE-MANIFEST.json).

**Steps:**

**A. Up-front word budgeting (run before the first API call):**

1. Compute total word target from DURATION_MIN and WPM:
   - `pause_budget_sec` = (drop_count x 3s) + (misc_pause_count x 2s)
   - `net_spoken_sec` = (DURATION_MIN x 60) minus pause_budget_sec
   - `target_words` = net_spoken_sec x (WPM / 60)
2. Distribute target_words to PER-SLIDE budgets weighted by slide type (hook=1.40x, welcome=1.30x, close/cta=1.20-1.25x, offer/drop/final=1.15-1.20x, teach/proof/credibility=1.10-1.20x, recap=0.90x, normal=1.00x). Every slide gets a minimum of 30 words.
3. Assert that per-slide budgets sum within 2% of target_words. Log the math. GENERATION BEGINS ONLY AFTER THIS PASSES.
4. Record the budget math in the speech header: DURATION_MIN, WPM, pause_budget_sec, net_spoken_sec, target_words, per-slide type weights, per-stage allocations.

**B. Per-slide disk checkpointing:**

1. Working directory: `working/speech/` (or the --workdir argument). Create it if absent.
2. The moment a slide's spoken block is generated and passes a basic word-count check, write it to `working/speech/slide-NN.txt` (zero-padded two digits).
3. Maintain `working/speech/speech_ledger.json` with one record per slide: `{ slide_no, headline, kind, stage, word_budget, actual_words, status }` where status is `pending | written | verified`.
4. Write the ledger to disk after EVERY slide (not at the end). A crash between slides loses at most one slide's work.
5. On startup, read the ledger and restore any slides whose disk file exists and meets >= 90% of budget. Those slides are SKIPPED (no API call, no cost). Only `pending` or under-budget slides are generated.

**C. Transient-error resilience (wrap every API call):**

1. All model API calls go through `call_with_retry()`. Never call the API bare. The harness calls an
   OpenAI-compatible base only -- NEVER Anthropic (`speech_build_harness.py:122`, `:394`, `:408`).
2. Retryable errors: HTTP 429, 500, 503, 529, and any response body containing "overloaded_error" or "overloaded". These are transient; retry without alarm.
3. Retry policy: exponential backoff with full jitter. Formula: `sleep = random.uniform(0, min(BASE * 2^(attempt-1), 60s))`. Maximum 5 retries per slide per pass.
4. Each retry attempt is logged: `[retry] slide-N-gen attempt K/5 (HTTP 529) -- sleeping X.Xs before retry`.
5. On retry exhaustion (5 retries all fail), the model-fallback hook fires: switch to `--fallback-model`
   (default `minimax-m3:cloud`, `speech_build_harness.py:932`) and retry the same slide on the fallback.
   The primary is `--model` (default `glm-5.2:cloud`, `:929`). Log the switch.
6. If fallback also exhausts, raise HardAPIError. The slide is left `pending` in the ledger. The run exits non-zero. A resumed run (Step B) will pick it up.

**D. Programmatic auto-expand loop (after each generation pass):**

1. After a full generation pass, count slides below 90% of their word budget.
2. If any exist, run an expand pass: re-prompt each under-budget slide with its current text and the budget gap. The prompt explicitly asks for expansion to hit the budget. Checkpoint the expanded text.
3. Repeat for up to K=3 rounds (--max-expand-rounds). Stop early if all slides reach budget.
4. The existing SOP 9.1 length gate (total within +/-10% of target) is the BACKSTOP. It should now pass on the first check. If it still fails after K rounds, flag to the Director; do NOT silently ship an under-budget speech.

**Outputs:**
- `working/speech/slide-NN.txt` (one per slide, written as generated)
- `working/speech/speech_ledger.json` (status per slide, updated after every slide)
- `working/presenter-speech/speech.md` (the assembled full speech, written at the end)

**Failure mode:** If a mid-run crash occurs, re-run with the SAME --workdir. The harness reads the ledger, restores completed slides from disk, and generates only the missing ones. Never wipe the workdir between runs of the same deck unless starting fresh intentionally.

**Enforcement check (what auto-fails):**
- Calling any generation API before per-slide word budgets are computed and logged = FAIL.
- Any API call made outside call_with_retry() = FAIL.
- speech_ledger.json not written after each slide = FAIL.
- A slide file on disk ignored at resume (not checked / not restored) = FAIL.
- Auto-expand loop not run after a generation pass = FAIL.
- Shipping a speech without running the length gate backstop check = FAIL.

**Dry-run / smoke test:** `python3 presentations/scripts/speech_build_harness.py --dry-run --intake /dev/null --slides /dev/null --arc /dev/null --out /tmp/speech_test.md --workdir /tmp/speech_test_work`. All four proofs (A budget sum, B kill-resume, C auto-expand, D retry backoff) must print PASS. Run this after any code change to the harness.

---

### SOP 9.1 -- Write the Word-for-Word Webinar Speech at 130 wpm

**Purpose:** Produce the exact, prolific, passionate words the owner says as a live WEBINAR HOST, following the proven webinar arc (Section 9A), paced so a human delivering it at 130 wpm with the doctrine's pauses lands the deck inside DURATION_MIN.

**The hard rule:** Every slide has a spoken block written verbatim in the owner's TONE, prolific and passionate, **as spoken live to a room**. The opening is a genuine live welcome (Section 9A); the close circles back to the hook. The total word count is budgeted at 130 words per minute against DURATION_MIN, MINUS the pause budget (count the mandatory pauses: 3 seconds on each DROP and FINAL, 2 to 3 seconds after the anchor and after big emotional lines). The script is spoken language, not written prose. No em dashes.

**Inputs:** slides_copy.md (PRESENTER NOTE, PURPOSE, SECTION, LADDER, HOOK_REFRAIN), arc_allocation.json, intake.json, the Deep Research Specialist's cited sources for this deck, talk_track.md if present.

**Steps:**
1. Compute the word budget AND the per-stage allocation. Pause budget = sum of mandatory pauses in seconds, converted to word-equivalents at 130 wpm (130 wpm = about 2.17 words/second). Net spoken seconds = (DURATION_MIN x 60) minus pause seconds. Target words = net spoken seconds x 2.17. Split the target across the 11 stages using the Section 9A allocation (tuned to arc_allocation.json). Record the math AND the per-stage word targets in the header.
2. Map every slide to its webinar stage (Section 9A) from its SECTION / LADDER marker. Note the stage on each slide block so the PDF can color and label it.
3. Write slide 1 as a live welcome following the Section 9A opening pattern: genuine welcome, congratulate them for being here, housekeeping, an engagement question into the chat. Never open as a monologue.
4. For every slide, write a SPOKEN block: the exact words, in the owner's voice, prolific and passionate, vivid and emotionally engaged, expanding the PRESENTER NOTE into full live delivery. The slide carries the one idea; the speech carries the narration; they must NOT duplicate each other (master SOP rule 15).
5. In the teach and proof stages, weave in REAL CITED research (facts, figures, quotes) from the deck's research, each tied to a real source. Never invent a stat or quote; flag "(OWNER/RESEARCH: need a real source here)" if missing. Stories before statistics; lead emotional, justify logical.
6. On HOOK_REFRAIN slides, the spoken block ends on the HOOK line verbatim (the Purple Rain refrain), word for word as recorded in intake.json, never reworded or extended. The closing slide circles back to and ends on the hook.
7. On LADDER slides, write the earned-reason line verbatim, then the price, then a written pause cue "(PAUSE 3 seconds)" the owner can see. On the FINAL slide, walk the strikethrough sequence in words and land the real price with the urgency window.
8. On CTA slides, write the complete spoken CTA: the action, the URL stated aloud, the urgency close.
9. Carry [CLIENT TO SUPPLY] forward as a spoken-prompt flag: "(OWNER: say your real client win here)". Never fabricate a win, a number, a testimonial, or a price.
10. Record per-slide word coverage and spoken-seconds on every block. Pace-check at the STAGE level too: each stage within +/-15% of its Section 9A allocation; total within +/-10% of target. If over, tighten teach narration first; never cut the CTA, the drops, or the welcome. Re-balance and re-check.
11. Write the clean script to working/presenter-speech/PRESENTERS-SPEECH.md with a header: DECK_TITLE, DURATION_MIN, SLIDE_COUNT, TONE, HOOK, SPOKEN_RATE_WPM = 130, pause budget, per-stage word targets, target words, actual words, and a "Sources cited on stage" list. Each slide block follows the parseable contract `## Slide N -- Headline  (STAGE)` then `> STAGE: ... KIND: ... BUDGET: Nw ACTUAL: Nw SECONDS: Ns` then the spoken text then `---` (the exact format the teleprompter generator parses in SOP 9.2).

**Enforcement check (what auto-fails):**
- Any slide without a spoken block = FAIL.
- Slide 1 is not a live webinar welcome (opens as a monologue, no greeting, no room, no engagement) = FAIL.
- The closing slide does not circle back to the hook = FAIL.
- Total words more than 10% off the pause-adjusted 130 wpm budget, OR any stage more than 15% off its Section 9A allocation = FAIL.
- Stiff, written-for-the-eye, corporate prose instead of prolific spoken language = FAIL.
- A statistic, study, or quote spoken on stage with no real source = FAIL (fabricated research).
- The hook reworded, extended, or misspelled in any spoken block = FAIL (it is a fixed verbatim refrain).
- The hook SUNG fewer than 5 or more than 20 times across the whole speech = FAIL (`AF-SPEECH-HOOK-COUNT`, `scripts/pitch_engines_check.py::chk_speech_hook_count`, SOP-PITCH-06 1.8). Count char-exact occurrences of `intake.json.hook` in `PRESENTERS-SPEECH.md` and assert `5 <= count <= 20`. The hook is SUNG, not stamped: it must recur verbatim 5-20 times in the spoken script (refrain beats + the close circle-back). This is the SPOKEN floor; the slide-side visual ceiling (`AF-HOOK-1`/`AF-C2`, 3-4 dedicated typography slides) is a separate VISUAL rule and is UNCHANGED -- visual ceiling vs spoken floor, reconciled in SOP-SLIDE-03. Checked at Phase Speech-QC by the Speech QC Specialist.
- A fabricated win/number/price in place of a [CLIENT TO SUPPLY] flag = FAIL.
- An em dash anywhere in the spoken script = FAIL.
- The spoken block duplicates the slide headline word for word = FAIL (slide is not the script).
- A spoken block with no per-slide word count / spoken-seconds recorded = FAIL.

**PASS example (live welcome, slide 1):** "Hello and welcome, everybody. Congratulations on taking the first step just by being here. (PAUSE 2 seconds) Do me a favor and drop in the chat where you are watching from today. Quick housekeeping: stay with me to the very end, the most important part is the last ten minutes."

**FAIL example:** "Hey, so today I want to talk about parenting..." (a podcast monologue open, no welcome, no room, no engagement). Also a flat written credentials dump that reads like prose and would be wrong on the slide.

**Outputs:** working/presenter-speech/PRESENTERS-SPEECH.md.

**Hand to:** SOP 9.2 (teleprompter PDF + HTML + Notion) and SOP 9.3 (Fish-tagged deliverable + audio source).

**Failure mode:** If a PRESENTER NOTE is blank or under 10 words, flag the slide [INCOMPLETE PRESENTER NOTE], log it, notify the Director; do not invent the spoken block.

---

### SOP 9.2 -- Render the Teleprompter PDF + HTML + Notion

**Purpose:** Deliver the webinar script as a beautiful, easy-to-read TELEPROMPTER the presenter can follow live: a print/PDF teleprompter (`PRESENTERS-SPEECH.pdf`), a self-contained scrollable teleprompter (`presenter-teleprompter.html`), and a Notion mirror.

**The hard rule (teleprompter spec):** No text below **14pt** anywhere in the PDF (teleprompter floor). Layout is **bar-per-slide**: each slide leads with a "Slide N  [ LABEL ]" bar (slide number in dark ink, LABEL in grey caps) + a thin rule, like the reference target — NOT a heavy per-stage color band (at most a slim stage tint on the bar). The cover is the lean reference header (title + "Owner — Deck — Word for Word" + one pacing/legend line + the "WORD-FOR-WORD SPEECH" header) so slide-1 content starts on page 1. The spoken block is split into readable paragraphs. Pacing cues render as their own amber cue line, supporting BOTH `[PAUSE]`/`[BREATHE]`/`[BREAK]` AND `(PAUSE 2 seconds)` forms. OWNER prompts are amber. Per-slide pacing (words + spoken seconds) is KEPT (a KPI) but restyled as a small grey margin note. Output filename `PRESENTERS-SPEECH.pdf`. Notion mirrors the script and the URL is verified.

**The visual target:** the PDF must visually match the department reference `STANDARD-presenter-speech-layout.pdf` (the gold standard for the lean cover, the bar-per-slide layout, the amber cue lines, and the grey margin pacing note).

**The tools:** `presentations/scripts/presenters_speech_pdf.py` (reportlab) takes a JSON speech spec and enforces the **14pt floor** in code, renders the bar-per-slide layout + lean cover + amber cue lines (both forms) + grey margin pacing note. `presentations/scripts/build_teleprompter.py` is a no-AI generator that reads the finished PRESENTERS-SPEECH.md (parsing `## Slide N -- Headline (STAGE)` + `> ... SECONDS: Ns`) and emits the self-contained `presenter-teleprompter.html` (inline CSS+JS+speech JSON; big adjustable font, scroll-speed slider seeded from WPM, play/pause on Space, mirror mode, progress bar, slide rail/jump, per-slide pacing countdown from the SECONDS metadata, fullscreen, localStorage, dark high-contrast theme, brand from intake.json). Do NOT edit build_deck.py / sync_check.py / PIPELINE-MANIFEST.json (other owners); build_deck registers the `presenter-teleprompter.html` filename in the bundle.

**Inputs:** PRESENTERS-SPEECH.md (per-stage/per-slide structure from SOP 9.1), design_system.json (optional brand match), intake.json (brand/company name for the HTML), Notion credentials.

**Steps:**
1. Convert PRESENTERS-SPEECH.md into the generator's JSON speech spec (deck_title, owner_name, company_name, duration_min, tone, hook, spoken_rate_wpm, optional brand; ordered stages each with slides carrying slide_no, headline, optional purpose, spoken text, and kind).
2. Run python3 presentations/scripts/presenters_speech_pdf.py --spec <spec.json> --out working/presenter-speech/PRESENTERS-SPEECH.pdf.
3. Run python3 presentations/scripts/build_teleprompter.py --speech working/presenter-speech/PRESENTERS-SPEECH.md --out working/delivery/presenter-teleprompter.html --intake working/copy/intake.json; confirm it parses every slide and opens.
4. Confirm printed total words and per-slide pacing match PRESENTERS-SPEECH.md; 14pt floor enforced by the generator; verify visually against STANDARD-presenter-speech-layout.pdf.
5. Confirm the PDF opens and is non-zero bytes, and the HTML is self-contained.
6. Publish the Notion page mirroring the same stage/slide structure; capture and verify the URL in notion_url.json.

**Enforcement check (what auto-fails):**
- Any text below 14pt in the PDF = FAIL (teleprompter floor).
- Not bar-per-slide, or any slide not labeled with its number/headline = FAIL.
- Cover pushes slide-1 off page 1, or not the lean reference header = FAIL.
- Pacing cues not on their own line, or only one cue form supported = FAIL.
- Per-slide pacing (word count / spoken-seconds) missing = FAIL (keep it as a small grey margin note).
- PDF does not visually match STANDARD-presenter-speech-layout.pdf = FAIL.
- presenter-teleprompter.html not produced, not self-contained, does not parse the speech, or is under 20,000 bytes = FAIL (`AF-BUNDLE-COMPLETE` floor; `build_teleprompter.py` exits non-zero rather than write a degenerate file).
- PRESENTERS-SPEECH.pdf does not open, is zero bytes, or is under 3,000 bytes = FAIL (`AF-BUNDLE-COMPLETE` floor; `presenters_speech_pdf.py` exits non-zero on a sub-floor render).
- notion_url.json missing or URL does not resolve = FAIL.

> **Gate tie-in:** the teleprompter HTML and the speech files (`PRESENTERS-SPEECH.md` / `.pdf`) are REQUIRED deliverables gated at `AF-BUNDLE-COMPLETE` — the bundle cannot complete if any is absent or under its byte floor (HTML >= 20,000 bytes, PDF >= 3,000 bytes). The gate is skippable ONLY by a logged `owner/founder` approval token (`owner_skip_approval`) recorded in `process_manifest.json` — never silently, never by the agent's own choice.

**Outputs:** PRESENTERS-SPEECH.pdf, presenter-teleprompter.html, the speech spec JSON, and notion_url.json.

**Hand to:** SOP 9.5 (delivery).

**Failure mode:** No PDF toolchain or no Notion credential after a full env-store check, escalate to ROLE-03 and the operator; deliver what is available and flag the blocked step, never silently skip.

---

### SOP 9.3 -- The Fish-Tagged Deliverable (shipped; tagging handoff to ROLE-29)

**Purpose:** Produce `PRESENTERS-SPEECH-FISH-TAGGED.md` — the SAME words as the pure speech with inline Fish Audio expression tags ADDED — as BOTH a shipped owner-facing deliverable AND the audio source. ROLE-29 applies the tags; this role owns the deliverable.

**The hard rule:** The Fish-tagged markdown is **word-for-word identical** to PRESENTERS-SPEECH.md; only Fish tags are added, never a word changed, reordered, added, or removed. Existing pacing cues are preserved. Default **S2/S2-Pro square-bracket, open-domain**; S1 fallback is the fixed named tag set in `(parentheses)`. The owner receives this file (it ships) so they can re-render/re-voice; it is also the audio source for SOP 9.4. The pure PDF/Notion stays clean.

**Density and palette (FISH-AUDIO-STRATEGIC-PLAN.md):** ~1 emotion tag every 80-120 words, rising into the Offer and easing either side; **lowest density in Teach and Proof** (restraint = authority/truth). Custom S2 descriptors allowed but tight. Stack at most 3 cues per sentence; emotion cue at the START of its sentence; never two fully-tagged sentences in a row outside the Offer peak. Per-stage palette to match Section 9A: welcome/who-for/hook = [warm and welcoming], [smiling while speaking], [building excitement]; origin story = [reflective, looking back], [vulnerable, almost confessional]; big promise = [unshakeable confidence] + a pause; teach = [building excitement], [calm, grounded authority], [emphasis]; proof = [confident and factual], [proud but humble]; offer = [warm and welcoming], [building to a crescendo]; price drops = [measured and deliberate] + [long-break]/(PAUSE 3s); scarcity/close = [urgent but controlled], [direct eye-contact energy]; recap = [calm, grounded authority]. Syntax depends on tier: S2/S2-Pro = [square brackets] (default, open-domain); S1 = (parentheses) (fallback); ElevenLabs v3 supports inline bracket cues, v2 does NOT (strip and drive via voice-settings).

**Inputs:** PRESENTERS-SPEECH.md, intake.json TONE, the per-stage emotional arc (Section 9A), FISH-AUDIO-TAGS-MASTER.md, FISH-AUDIO-STRATEGIC-PLAN.md, the selected TTS tier (from SOP 9.4 step 1).

**Steps:**
1. Tell ROLE-29 which TTS tier is the target (default Fish S2-pro brackets) and point them at FISH-AUDIO-TAGS-MASTER.md + FISH-AUDIO-STRATEGIC-PLAN.md for valid markers and density.
2. Hand PRESENTERS-SPEECH.md plus the TONE, the per-stage tag plan, and the density rules to ROLE-29. ROLE-29 returns working/presenter-speech/PRESENTERS-SPEECH-FISH-TAGGED.md with tags applied per stage.
3. Confirm the tagged file preserves EVERY word of the clean script (tags added, words unchanged), the hook refrains verbatim, the per-slide contract preserved, and tags use the syntax valid for the chosen tier. Run a word-for-word diff (strip all brackets/parens/owner-prompts/metadata from both; remaining words identical per slide).
4. Ship PRESENTERS-SPEECH-FISH-TAGGED.md to the owner alongside the pure speech and the PDF (SOP 9.5), AND use it as the audio source (SOP 9.4).

**Enforcement check (what auto-fails):**
- Audio rendered from the untagged script when an expressive tier (Fish/ElevenLabs) is in use = FAIL.
- Tagging altered the words (not just added tags), per the diff = FAIL.
- PRESENTERS-SPEECH-FISH-TAGGED.md not produced or not shipped to the owner = FAIL (it is a shipped deliverable).
- A bracket description so long it reads as a paragraph, or more emotion tags than sentences in a paragraph (over-tagging) = FAIL.

**Outputs:** working/presenter-speech/PRESENTERS-SPEECH-FISH-TAGGED.md (shipped deliverable + audio source), confirmed word-faithful.

**Hand to:** SOP 9.4 (audio render) and SOP 9.5 (delivery — it ships to the owner).

**Failure mode:** If the chosen tier is the local tool with no tag support, still produce PRESENTERS-SPEECH-FISH-TAGGED.md (valuable for any future re-voice) and note in the manifest "tier has no expression markup; audio is plain." Still produce the demo.

---

### SOP 9.4 -- Audio Demonstration via the TTS Fallback Chain (chunk + stitch)

**Purpose:** Produce an audio demonstration of the full speech so the owner hears how it should sound, using an explicit fallback order and stitching long pieces.

**The hard rule:** Attempt the TTS tiers in this order and STOP at the first that succeeds: (1) Fish Audio s2-pro first, rendering from the expression-tagged script; (2) ElevenLabs second; (3) the client's local speech tool (Whisper-family / local TTS) third. If the chosen tool cannot render a long (about 60 minute) piece in one call, CHUNK the script and stitch the audio with ffmpeg into one continuous file. Log which tier rendered and why any earlier tier was skipped.

**The fallback order, with the differences that matter:**
- **Fish Audio (primary).** Endpoint POST https://api.fish.audio/v1/tts, header model: s2-pro, Bearer key. S2 uses [bracket] open-domain expression tags (over 15,000 tags, free-form natural language), which is exactly why it is first: the audio can be made expressive. Use prosody.speed near 1.0 (the script is already paced for 130 wpm; do not double-correct), format mp3, normalize true for numbers and prices, chunk_length 100 to 300 characters. Pricing is about $15 per million UTF-8 bytes (roughly 12 hours of speech per million bytes); a 60-minute demo is a small fraction of that, so cost is not a blocker, but render once and cache.
- **ElevenLabs (fallback). v2 versus v3 differ and it matters:** the v2-generation models (for example multilingual v2 / turbo v2) are the stable, production, low-latency models and use voice-settings controls (stability, similarity, style) for delivery; they do NOT interpret inline emotion tags the way Fish does. The v3 generation is the expressive, alpha-grade model that DOES support inline audio-tag style direction (for example bracketed delivery cues) and richer emotion, but is less stable for long single calls and may not be available on every account tier. So: if v3 is available and the script is tag-driven, prefer v3 for expressiveness; if only v2 is available, strip the Fish-style inline tags and drive delivery through v2 voice-settings instead, since v2 will read the bracket tags literally as words if left in. Verify the available model from the account before rendering; do not assume v3.
- **Local tool (final fallback).** Whatever the box has (a local TTS, or a Whisper-family tool used in its TTS-adjacent capacity per the box's setup). Likely no expression-tag support: render the plain script. The point is to give the owner SOMETHING to hear even with no cloud key.

**Inputs:** PRESENTERS-SPEECH-FISH-TAGGED.md (or PRESENTERS-SPEECH.md for the local tier), capacity_plan.json (tools and keys), the credentials from the env stores (checked per the credential rule, never assumed missing).

**Steps:**
1. Determine the available tier from capacity_plan.json and a live credential check of the process env (not just a file grep). Record the chosen tier and the skip reasons.
2. Estimate the single-call limit of the chosen tool. If the full script exceeds it (a 60-minute speech will, for most tools), CHUNK: split the script on natural boundaries (section breaks, then slide breaks), keeping each chunk under the limit and never splitting mid-sentence. Number the chunks.
3. Render each chunk to working/presenter-speech/audio/chunk-NN.mp3. For Fish, keep condition_on_previous_chunks true for voice consistency across chunks. Retry a failed chunk once (transient errors); if a tier hard-fails, fall to the next tier and restart the render for remaining chunks on that tier (do not mix tiers in one file unless unavoidable; if unavoidable, note it).
4. Stitch with ffmpeg into one continuous file: build a concat list and run ffmpeg concat to working/presenter-speech/audio/PRESENTER-AUDIO.mp3 (locked filename). Insert short silences at pause cues if the tool did not honor them (ffmpeg can pad), so the drops breathe.
5. Verify the stitched file: it plays, its duration is within a sensible range of DURATION_MIN (it will run a bit longer with pauses, which is correct), and there are no abrupt chunk seams.
6. Write working/presenter-speech/audio_manifest.json: tier used, tiers skipped and why, chunk count, per-chunk durations, stitch log, final duration, file path.

**Enforcement check (what auto-fails):**
- No audio demonstration produced = FAIL (every speech ships with a demo, even on the local tier).
- Fish skipped without a logged reason (key truly absent, hard error) = FAIL (Fish is primary).
- ElevenLabs rendered with Fish-style inline tags left in for a v2-only account = FAIL (v2 will speak the tags as words).
- A long piece rendered as a single overflowing call that truncated = FAIL (must chunk and stitch).
- The stitched file has audible seams or missing chunks = FAIL.
- audio_manifest.json missing = FAIL.

**Outputs:** the stitched demo PRESENTER-AUDIO.mp3, the chunk files, audio_manifest.json.

**Hand to:** SOP 9.5 (delivery).

**Failure mode:** If ALL tiers fail (no Fish key, no ElevenLabs, no local tool), do not silently ship without audio: flag to the Director and operator that no voice tool is available on this box, deliver the three docs (pure speech, teleprompter PDF, Fish-tagged md) and Notion, and request a key or a local tool so the demo can be produced. Log the gap.

---

### SOP 9.5 -- Surface-Boundary Audit and Delivery

**Purpose:** Prove the script never leaked onto the audience deck, then deliver all FOUR artifacts (the three owner-facing docs + the audio demo) plus the teleprompter HTML and Notion, and verify.

**The hard rule:** Script content lives only in the speaker surfaces. Deliver the full set — `PRESENTERS-SPEECH.md`, `PRESENTERS-SPEECH.pdf`, `PRESENTERS-SPEECH-FISH-TAGGED.md`, `PRESENTER-AUDIO.mp3` — plus `presenter-teleprompter.html` and the Notion link; label which artifact is which; verify existence before reporting done. The four filenames are exact.

**Inputs:** PRESENTERS-SPEECH.md, PRESENTERS-SPEECH.pdf, PRESENTERS-SPEECH-FISH-TAGGED.md, presenter-teleprompter.html, notion_url.json, PRESENTER-AUDIO.mp3, slides_copy.md (to confirm no leakage), intake.json (destinations).

**Steps:**
1. Surface-boundary check: confirm no spoken-block text was copied onto the audience deck (grep slide copy and prompt files). If any appears on the deck, flag to the Director (deck must be corrected) and hold delivery.
2. Deliver per SOP-PITCH-05-DELIVERABLE-BUNDLE + delivery-concierge SOP + CLIENT-WEBINAR-DECK-SOP.md Section 9a (PRESENTATION-MASTER-DOCTRINE.md §4): Mac clients get PRESENTERS-SPEECH.pdf, PRESENTERS-SPEECH.md, PRESENTERS-SPEECH-FISH-TAGGED.md, presenter-teleprompter.html, and PRESENTER-AUDIO.mp3 copied to Downloads with clear names; include the Notion link. If the environment is unclear, ASK.
3. Notify the owner via openclaw message send, naming surfaces: "Your Presenter's Speech is ready. You get four things, all for YOU, the speaker. One: PRESENTERS-SPEECH.pdf, your word-for-word teleprompter to read live (also open presenter-teleprompter.html in any browser for a scrolling teleprompter). Two: PRESENTERS-SPEECH.md, the same words in plain text. Three: PRESENTERS-SPEECH-FISH-TAGGED.md, the same words with voice-direction tags so you can re-voice it anytime. Four: PRESENTER-AUDIO.mp3, an audio demo so you can hear how it should sound. The slide deck is what the audience sees; this script and the audio are only for you. The Presenter's Guide is your map of points; this Speech is the words."
4. Verify file existence at every destination before reporting done (all four artifacts + the HTML).
5. Update run_ledger.json: `presenter_speech_phase: "complete"`, PRESENTERS-SPEECH.md path, PRESENTERS-SPEECH.pdf path, PRESENTERS-SPEECH-FISH-TAGGED.md path, presenter-teleprompter.html path, Notion URL, PRESENTER-AUDIO.mp3 path, TTS tier.

**Enforcement check (what auto-fails):**
- Any script content found on the audience deck = FAIL (block, escalate).
- Any of the four artifacts (PRESENTERS-SPEECH.md/.pdf, PRESENTERS-SPEECH-FISH-TAGGED.md, PRESENTER-AUDIO.mp3) or presenter-teleprompter.html not delivered/verified = FAIL.
- Delivery reported done without verified files = FAIL.
- Delivery message does not name which artifact is which surface = FAIL.

**Outputs:** delivered four artifacts + teleprompter HTML + Notion; run_ledger.json updated.

**Hand to:** Director (completion); Presenter Coach (ROLE-14) uses the script as the basis for the timed talk track and rehearsal.

**Failure mode:** Owner unreachable: deliver to the default location (Downloads), log, follow up once; never hold a finished speech for a reply.

---
