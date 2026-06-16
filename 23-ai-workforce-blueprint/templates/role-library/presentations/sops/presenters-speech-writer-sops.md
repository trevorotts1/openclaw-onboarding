# SOPs Mirror -- Presenter's Speech Writer

**Source:** presentations/presenters-speech-writer.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md; voice authority: 30-fish-audio-api-reference/.

### SOP 9.1 -- Write the Word-for-Word Speech at 130 wpm

**Purpose:** Produce the exact, friendly, marketable words the owner says, paced so a human delivering it at 130 wpm with the doctrine's pauses lands the deck inside DURATION_MIN.

**The hard rule:** Every slide has a spoken block written verbatim in the owner's TONE. The total word count is budgeted at 130 words per minute against DURATION_MIN, MINUS the pause budget (count the mandatory pauses: 3 seconds on each DROP and FINAL, 2 to 3 seconds after the anchor and after big emotional lines). The script is spoken language, not written prose. No em dashes.

**Inputs:** slides_copy.md (PRESENTER NOTE, PURPOSE, LADDER, HOOK_REFRAIN), arc_allocation.json, intake.json, talk_track.md if present.

**Steps:**
1. Compute the word budget. Pause budget = sum of mandatory pauses in seconds, converted to word-equivalents at 130 wpm (130 wpm = about 2.17 words/second). Net spoken seconds = (DURATION_MIN x 60) minus pause seconds. Target words = net spoken seconds x 2.17. Record the math in the header.
2. For every slide, write a SPOKEN block: the exact words, in the owner's voice, friendly and marketable, expanding the PRESENTER NOTE into full delivery. The slide carries the one idea; the speech carries the narration; they must NOT duplicate each other (master SOP rule 15).
3. On HOOK_REFRAIN slides, the spoken block ends on the HOOK line verbatim (the Purple Rain refrain), word for word as recorded in intake.json, never reworded or extended.
4. On LADDER slides, write the earned-reason line verbatim, then the price, then a written pause cue "(PAUSE 3 seconds)" the owner can see. On the FINAL slide, walk the strikethrough sequence in words and land the real price with the urgency window.
5. On CTA slides, write the complete spoken CTA: the action, the URL stated aloud, the urgency close.
6. Carry [CLIENT TO SUPPLY] forward as a spoken-prompt flag: "(OWNER: say your real client win here)". Never fabricate a win, a number, a testimonial, or a price.
7. Pace-check: total words within +/- 10% of target. If over, tighten teach narration first (appetizer not dinner); never cut the CTA or the drops. Re-balance and re-check.
8. Write the clean script to working/presenter-speech/speech.md with a header: DECK_TITLE, DURATION_MIN, SLIDE_COUNT, TONE, HOOK, SPOKEN_RATE_WPM = 130, pause budget, target words, actual words.

**Enforcement check (what auto-fails):**
- Any slide without a spoken block = FAIL.
- Total words more than 10% off the pause-adjusted 130 wpm budget = FAIL.
- The hook reworded, extended, or misspelled in any spoken block = FAIL (it is a fixed verbatim refrain).
- A fabricated win/number/price in place of a [CLIENT TO SUPPLY] flag = FAIL.
- An em dash anywhere in the spoken script = FAIL.
- The spoken block duplicates the slide headline word for word = FAIL (slide is not the script).

**PASS example (illustrative -- substitute your DISCOVERY VARIABLES, hook slide):** "...so when I say there is a difference between parenting by control and parenting through clarity, I am not talking about being soft. I am talking about being clear. (PAUSE 2 seconds) There is a difference between parenting by control and parenting through clarity."

**FAIL example:** a flat written paragraph ("[Co-Founder Name] is a licensed counselor and [Founder Name] spent years in executive recruitment, which qualifies us to...") that reads like a credentials dump and would also be wrong on the slide.

**Outputs:** working/presenter-speech/speech.md.

**Hand to:** SOP 9.2 (PDF/Notion) and SOP 9.3 (expression tagging for audio).

**Failure mode:** If a PRESENTER NOTE is blank or under 10 words, flag the slide [INCOMPLETE PRESENTER NOTE], log it, notify the Director; do not invent the spoken block.

---

### SOP 9.2 -- Render the Beautiful PDF + Notion

**Purpose:** Deliver the script as a beautiful, readable PDF and a Notion doc.

**The hard rule:** No text below 12pt in the PDF (a presenter reads this live). Brand-matched to the deck (design system font and accents). Pause cues, hook refrains, and OWNER prompts visually distinct. Notion mirrors the PDF and the URL is verified.

**Inputs:** speech.md, design_system.json (optional brand match), Notion credentials.

**Steps:**
1. Convert speech.md to a styled document: cover page ("Presenter's Speech -- Word for Word, Speaker-Facing"), then per-section spoken blocks with the slide number and headline as a marker.
2. Apply brand; render pause cues and "(OWNER: ...)" prompts in the accent color; hook refrains bold.
3. Enforce the 12pt floor; verify after render.
4. Render working/presenter-speech/Presenters_Speech_<DeckTitle>.pdf; confirm it opens.
5. Publish the Notion page; capture and verify the URL in notion_url.json.

**Enforcement check (what auto-fails):**
- Any text below 12pt = FAIL.
- PDF does not open or is zero bytes = FAIL.
- notion_url.json missing or URL does not resolve = FAIL.

**Outputs:** the PDF and notion_url.json.

**Hand to:** SOP 9.5 (delivery).

**Failure mode:** No PDF toolchain or no Notion credential after a full env-store check, escalate to ROLE-03 and the operator; deliver what is available and flag the blocked step, never silently skip.

---

### SOP 9.3 -- Expression Tagging Handoff (to ROLE-21)

**Purpose:** The audio demo must sound expressive, not flat. The clean script is handed to the Fish Audio / Expression Specialist (ROLE-21), who marks it up with expression tags for the chosen voice tool.

**The hard rule:** The audio is rendered from the EXPRESSION-TAGGED script (speech_tagged.md), never the bare script, so the demo carries emphasis and emotion. The plain-language PDF/Notion the owner reads stays clean (no tags); only the audio source carries tags.

**Inputs:** speech.md, intake.json TONE, the selected TTS tier (from SOP 9.4 step 1).

**Steps:**
1. Tell ROLE-21 which TTS tier is the target (Fish S2-pro uses [bracket] open-domain tags; ElevenLabs uses its own emotion controls and v2-vs-v3 differences; the local tool may support none). The tag syntax depends on the tier.
2. Hand speech.md plus the TONE to ROLE-21. ROLE-21 returns working/presenter-speech/speech_tagged.md.
3. Confirm the tagged script preserves every word of the clean script (tags added, words unchanged) and the hook refrains remain verbatim.

**Enforcement check (what auto-fails):**
- Audio rendered from the untagged script when an expressive tier (Fish/ElevenLabs) is in use = FAIL.
- Tagging altered the words (not just added tags) = FAIL.

**Outputs:** confirmation that speech_tagged.md exists and is word-faithful.

**Hand to:** SOP 9.4 (audio render).

**Failure mode:** If the chosen tier is the local tool with no tag support, skip tagging and note "tier has no expression markup; audio is plain." Still produce the demo.

---

### SOP 9.4 -- Audio Demonstration via the TTS Fallback Chain (chunk + stitch)

**Purpose:** Produce an audio demonstration of the full speech so the owner hears how it should sound, using an explicit fallback order and stitching long pieces.

**The hard rule:** Attempt the TTS tiers in this order and STOP at the first that succeeds: (1) Fish Audio s2-pro first, rendering from the expression-tagged script; (2) ElevenLabs second; (3) the client's local speech tool (Whisper-family / local TTS) third. If the chosen tool cannot render a long (about 60 minute) piece in one call, CHUNK the script and stitch the audio with ffmpeg into one continuous file. Log which tier rendered and why any earlier tier was skipped.

**The fallback order, with the differences that matter:**
- **Fish Audio (primary).** Endpoint POST https://api.fish.audio/v1/tts, header model: s2-pro, Bearer key. S2 uses [bracket] open-domain expression tags (over 15,000 tags, free-form natural language), which is exactly why it is first: the audio can be made expressive. Use prosody.speed near 1.0 (the script is already paced for 130 wpm; do not double-correct), format mp3, normalize true for numbers and prices, chunk_length 100 to 300 characters. Pricing is about $15 per million UTF-8 bytes (roughly 12 hours of speech per million bytes); a 60-minute demo is a small fraction of that, so cost is not a blocker, but render once and cache.
- **ElevenLabs (fallback). v2 versus v3 differ and it matters:** the v2-generation models (for example multilingual v2 / turbo v2) are the stable, production, low-latency models and use voice-settings controls (stability, similarity, style) for delivery; they do NOT interpret inline emotion tags the way Fish does. The v3 generation is the expressive, alpha-grade model that DOES support inline audio-tag style direction (for example bracketed delivery cues) and richer emotion, but is less stable for long single calls and may not be available on every account tier. So: if v3 is available and the script is tag-driven, prefer v3 for expressiveness; if only v2 is available, strip the Fish-style inline tags and drive delivery through v2 voice-settings instead, since v2 will read the bracket tags literally as words if left in. Verify the available model from the account before rendering; do not assume v3.
- **Local tool (final fallback).** Whatever the box has (a local TTS, or a Whisper-family tool used in its TTS-adjacent capacity per the box's setup). Likely no expression-tag support: render the plain script. The point is to give the owner SOMETHING to hear even with no cloud key.

**Inputs:** speech_tagged.md (or speech.md for the local tier), capacity_plan.json (tools and keys), the credentials from the env stores (checked per the credential rule, never assumed missing).

**Steps:**
1. Determine the available tier from capacity_plan.json and a live credential check of the process env (not just a file grep). Record the chosen tier and the skip reasons.
2. Estimate the single-call limit of the chosen tool. If the full script exceeds it (a 60-minute speech will, for most tools), CHUNK: split the script on natural boundaries (section breaks, then slide breaks), keeping each chunk under the limit and never splitting mid-sentence. Number the chunks.
3. Render each chunk to working/presenter-speech/audio/chunk-NN.mp3. For Fish, keep condition_on_previous_chunks true for voice consistency across chunks. Retry a failed chunk once (transient errors); if a tier hard-fails, fall to the next tier and restart the render for remaining chunks on that tier (do not mix tiers in one file unless unavoidable; if unavoidable, note it).
4. Stitch with ffmpeg into one continuous file: build a concat list and run ffmpeg concat to working/presenter-speech/audio/Presenters_Speech_<DeckTitle>_demo.mp3. Insert short silences at pause cues if the tool did not honor them (ffmpeg can pad), so the drops breathe.
5. Verify the stitched file: it plays, its duration is within a sensible range of DURATION_MIN (it will run a bit longer with pauses, which is correct), and there are no abrupt chunk seams.
6. Write working/presenter-speech/audio_manifest.json: tier used, tiers skipped and why, chunk count, per-chunk durations, stitch log, final duration, file path.

**Enforcement check (what auto-fails):**
- No audio demonstration produced = FAIL (every speech ships with a demo, even on the local tier).
- Fish skipped without a logged reason (key truly absent, hard error) = FAIL (Fish is primary).
- ElevenLabs rendered with Fish-style inline tags left in for a v2-only account = FAIL (v2 will speak the tags as words).
- A long piece rendered as a single overflowing call that truncated = FAIL (must chunk and stitch).
- The stitched file has audible seams or missing chunks = FAIL.
- audio_manifest.json missing = FAIL.

**Outputs:** the stitched demo mp3, the chunk files, audio_manifest.json.

**Hand to:** SOP 9.5 (delivery).

**Failure mode:** If ALL tiers fail (no Fish key, no ElevenLabs, no local tool), do not silently ship without audio: flag to the Director and operator that no voice tool is available on this box, deliver the PDF and Notion, and request a key or a local tool so the demo can be produced. Log the gap.

---

### SOP 9.5 -- Surface-Boundary Audit and Delivery

**Purpose:** Prove the script never leaked onto the audience deck, then deliver the PDF, Notion, and audio demo, and verify.

**The hard rule:** Script content lives only in the speaker surfaces (PDF, Notion, audio). Deliver all three, label which artifact is which surface, and verify existence before reporting done.

**Inputs:** the PDF, notion_url.json, the demo mp3, slides_copy.md (to confirm no leakage), intake.json (destinations).

**Steps:**
1. Surface-boundary check: confirm no spoken-block text was copied onto the audience deck (grep slide copy and prompt files). If any appears on the deck, flag to the Director (deck must be corrected) and hold delivery.
2. Deliver per master SOP Section 11.4: Mac clients get the PDF and the demo mp3 copied to Downloads with clear names; include the Notion link. If the environment is unclear, ASK.
3. Notify the owner via openclaw message send, naming surfaces: "Your Presenter's Speech is ready: the exact words (PDF and Notion) plus an audio demo so you can hear how it should sound. This is for YOU, the speaker. The slide deck is what the audience sees; this script and the audio are only for you. The Presenter's Guide is your map of points; this Speech is the words."
4. Verify file existence at every destination before reporting done.
5. Update run_ledger.json: `presenter_speech_phase: "complete"`, PDF path, Notion URL, audio path, TTS tier.

**Enforcement check (what auto-fails):**
- Any script content found on the audience deck = FAIL (block, escalate).
- Delivery reported done without verified files = FAIL.
- Delivery message does not name which artifact is which surface = FAIL.

**Outputs:** delivered PDF, Notion, audio; run_ledger.json updated.

**Hand to:** Director (completion); Presenter Coach (ROLE-14) uses the script as the basis for the timed talk track and rehearsal.

**Failure mode:** Owner unreachable: deliver to the default location (Downloads), log, follow up once; never hold a finished speech for a reply.

---
