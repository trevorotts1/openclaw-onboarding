# SOPs Mirror -- Audio Demonstration + Fish Audio Expression Specialist

**Source:** presentations/audio-demonstration-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Version:** 1.0

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Expression Tagging

**When to run:** After the Presenters Speech passes QC and WANT_AUDIO_DEMO = true.

**Inputs:**
- working/presenter-speech/presenters_speech.md (the QC-passed script)
- working/copy/hook_package.json (the hook beats)
- working/copy/price_ladder.json (the drops)
- the chosen demo voice / persona from the brief
- the selected TTS engine (Fish S2 default)

**Steps:**

1. Tag the script with expression tags BY ENGINE:
   - **Fish S2-Pro (default):** `[bracket]` free-form natural-language tags (for example `[speaking with calm conviction]`, `[building energy]`).
   - **ElevenLabs v3 (fallback):** inline audio tags like `[excited]`, `[whisper]`, `[sigh]`.
   - **Fish S1 (legacy fallback):** `(parenthesis)` fixed-set tags like `(excited)`, `(whispering)`, `(break)`.
   Choose the tag syntax that matches the engine the chunk will be synthesized on. (Verified facts per 30-fish-audio-api-reference/references/fish-audio-api-reference.md: S2 brackets / S1 parens.)

2. Apply MARKETABLE DELIVERY mapping:
   - Emphasis on the HOOK line at each scheduled hook beat (the line should land).
   - PAUSE on the jaw-dropper standalone slides (let the one sentence breathe).
   - ENERGY on the price DROPS (the number lands with momentum).

3. Enforce MAX 2 TAGS PER LINE, pairing one PHYSICAL tag (pause, breath, tempo) with one EMOTIONAL tag (conviction, excitement, warmth). More than two tags per line muddies the delivery.

4. For Fish, when fine control matters, set `normalize: false` so the API does not alter the intonation of control tags (per the Fish reference).

5. Write the tag-annotated script alongside the audio output (working/audio-demo/<deck>_tagged_script.md) so the tagging is auditable and re-runnable.

**Outputs:**
- working/audio-demo/<deck>_tagged_script.md (the script with per-engine expression tags)

**Hand to:** SOP 9.2 (Chunk + Synthesize).

**Failure mode:** If the chosen engine's tag syntax is unclear, VERIFY against the live provider docs before tagging; never guess a tag syntax. If WANT_AUDIO_DEMO carries no voice/persona, ask the owner via the Director before synthesizing; do not default a voice silently.

---

### SOP 9.2 -- Chunk + Synthesize with the Fallback Chain

**When to run:** After SOP 9.1 produces the tagged script.

**Inputs:**
- working/audio-demo/<deck>_tagged_script.md
- TTS keys from client env stores (FISH_AUDIO, ELEVENLABS)

**Steps:**

1. CHUNK the ENTIRE speech into segments at or below the API input limit. The Fish Audio per-request limit is `chunk_length` MAX 300 characters (per 30-fish-audio-api-reference); pre-chunk to <= 280 chars and send EACH chunk as its own `/v1/tts` request so a single oversized request can never silently truncate the talk. Split on sentence / paragraph / slide boundaries. Each chunk keeps its expression tags.

   **FULL-COVERAGE RULE (hard):** Every spoken word of the QC-passed speech MUST land in some chunk. The chunker MUST assert >= 95% character coverage of the cleaned spoken text BEFORE any synthesis; if coverage is below that, ABORT and fix the chunker -- do not synthesize a partial speech. NEVER synthesize only a "key beats" / "sizzle" / highlight subset and pass it off as the presentation audio. (Root-cause of the Corey 2026-06 incident: only 7 hand-picked beats -- ~4 min -- were synthesized instead of the full ~25 min, 62-slide speech.) If a SHORT highlight reel is explicitly requested, it is a SEPARATE deliverable with its own name (e.g. `<deck>_sizzle.mp3`) and MUST NOT overwrite the full presenter audio.

   The committed pipeline that does this correctly is `Presentations/scripts/synthesize_full_speech.py` (cleans front-matter / headings / stage-directions out of the speech, chunks the whole talk, synthesizes every chunk via Fish Audio, concatenates with ffmpeg, and enforces the SOP 9.3 duration gate). Use it; do not hand-roll an ad-hoc subset run.

   **EXPRESSIVE AUDIO (GAUNTLET LOOP 2, Feature A):** synthesize the **FISH-TAGGED**
   speech (`PRESENTERS-SPEECH-FISH-TAGGED.md`, produced by `speech_fish_tag.py`) — pass
   it via `--tagged-speech`. The untagged `PRESENTERS-SPEECH.md` alone produces FLAT
   audio because the `[bracket]` reader tags never reach the Fish API. The executor now
   sends `temperature: 0.9`, `top_p: 0.8`, `repetition_penalty: 1.2`, and
   `prosody: {speed, volume, normalize_loudness}` (fields verified against the Fish
   OpenAPI), and splices MEASURED silence (defaults 0.8 s / 1.2 s / 2.5 s) at
   `[pause]` / `[long pause]` markers via ffmpeg — the Fish tags alone have no
   documented duration. Reader-tag palettes: `presentations/fish-audio/
   FISH-READER-TAG-LIBRARY.md`. If the audio executor is invoked directly, the P9-DELIVER
   manifest cmd already passes `--tagged-speech`; never point it at the untagged file.

2. Synthesize EACH chunk through the FALLBACK CHAIN, in order, falling through (LOUD-FAIL, log the leg error) on any leg failure:
   - PRIMARY: Fish Audio S2-Pro (`POST https://api.fish.audio/v1/tts`, Bearer auth, `model: s2-pro`, json or msgpack body, mp3 192 kbps; `normalize: false` for tag fidelity). Re-tag the chunk in S2 bracket syntax.
   - FALLBACK 1: ElevenLabs v3 (`eleven_v3`, inline audio tags). Re-tag the chunk in EL v3 inline-tag syntax. (Verify v3 capabilities/cost against live docs first.)
   - FALLBACK 2: ElevenLabs v2 (`eleven_multilingual_v2`, NO inline emotion tags; set Style and Stability sliders to approximate the intended delivery, since v2 cannot take inline tags).
   The FINAL leg is NOT a synthesis leg: it is the Whisper-STT verification in SOP 9.4. Whisper cannot synthesize. If all synthesis legs fail, escalate; do not attempt to "synthesize with Whisper."

3. On a leg error (auth failure, rate limit, 4xx/5xx), LOG the failCode, fall through to the next leg, and record which leg ultimately produced each chunk. Keys come from the client env stores (search all stores; do not conclude a key is missing from a single file grep).

4. Save each chunk's mp3 to working/audio-demo/chunks/ with an order-preserving name.

**Outputs:**
- working/audio-demo/chunks/*.mp3 (one per chunk, with a record of which leg produced each)

**Hand to:** SOP 9.3 (ffmpeg Stitch + Normalize).

**Failure mode:** If ALL synthesis legs fail for a chunk (Fish, EL v3, EL v2), do NOT fabricate audio and do NOT route to Whisper to "make" audio. File a failCode to the Bugs Department, escalate to the Director and the Healer, and hold the demo. An incomplete demo is held, never faked.

---

### SOP 9.3 -- ffmpeg Stitch + Loudness Normalize

**When to run:** After all chunks synthesize successfully.

**Inputs:**
- working/audio-demo/chunks/*.mp3 (in order)

**Steps:**

1. Concatenate the chunks in script order into one mp3 using the ffmpeg concat path (reuse the 27-video-editor ffmpeg tooling). Use a concat list file to preserve exact order.

2. LOUDNESS-NORMALIZE the stitched mp3 (ffmpeg loudnorm) so the demo plays at a consistent, marketable level (target an integrated loudness suitable for spoken-word content). The hook emphasis and drop energy should remain dynamic but the overall level should be even.

3. **DURATION SANITY GATE (HARD CHECK -- FAIL LOUD, NON-NEGOTIABLE).** Measure the stitched mp3 duration with `ffprobe`. Compute the expected runtime from the cleaned spoken word count: `expected_sec = spoken_words / TARGET_WPM * 60` (TARGET_WPM = 140). The rendered audio duration MUST be `>= 0.80 * expected_sec`. If it is not, the audio does NOT cover the full speech: do NOT name it the deliverable, do NOT hand it to delivery -- move the short file aside (`*.FAILED-SHORT`), EXIT NON-ZERO, and re-run synthesis over the ENTIRE speech (SOP 9.2). This gate is what catches the failure where TTS only voiced a fraction of the talk. It is enforced in code by `scripts/synthesize_full_speech.py` (`--wpm`, `--min-ratio`, default 0.80); the script aborts on its own if the render is short. Also verify the file is non-empty and plays.

   Worked example (Corey *Explore Growth*): spoken_words = 3,516 -> expected ~1,507s (~25 min) -> gate floor ~1,205s (~20 min). The original 4-min sizzle (242s) and even the 18.5-min cut (1,110s) FAIL this gate; a full render (~25 min) passes.

4. Name the file working/audio-demo/<deck>_demo.mp3 (full presenter audio). A short highlight reel, if separately requested, is named `<deck>_sizzle.mp3` and is exempt from the duration gate ONLY because it is explicitly a partial deliverable -- it never substitutes for the full audio.

**Outputs:**
- working/audio-demo/<deck>_demo.mp3 (stitched, loudness-normalized, duration-gated to the full speech length)

**Hand to:** SOP 9.4 (STT Verify).

**Failure mode:** If the concat or normalize fails, fall back to a re-encode pass before concat (normalize each chunk to the same codec/sample-rate first). If ffmpeg is unavailable on the box, escalate to the Capacity and Reliability Engineer. **If the duration gate fails, the audio is INCOMPLETE -- hold it, never deliver it, and re-synthesize the full speech.** Never deliver an un-normalized, partial, or duration-gate-failing mp3. A short audio that does not match the true presentation length is a defect, not a deliverable.

---

### SOP 9.4 -- STT Verify (Whisper transcribes the rendered audio; word-match vs the script)

**When to run:** After the demo mp3 is stitched and normalized.

**Inputs:**
- working/audio-demo/<deck>_demo.mp3
- working/audio-demo/<deck>_tagged_script.md (with tags stripped for the word comparison)

**Steps:**

1. Transcribe the rendered demo mp3 with faster-whisper (per platform/mac/STT-TRANSCRIPTION.md). Whisper is the VERIFICATION leg: it converts the synthesized audio back to text. It does not synthesize.

2. Strip the expression tags from the source script and WORD-MATCH the Whisper transcript against it. Compute a match percentage.

3. ASSERT the word-match is >= 95%. Below that, the synthesis garbled or dropped words: identify the failing chunk, re-synthesize it (fall through the chain again if needed), re-stitch, and re-verify.

4. Record the verification result: `{ "stt_engine": "faster-whisper", "word_match_pct": N, "failing_chunks": [...], "verdict": "PASS|FAIL" }`.

**Outputs:**
- The STT verification record alongside the demo

**Hand to:** SOP 9.5 (Deliver) on PASS; back to SOP 9.2 for the failing chunk on FAIL.

**Failure mode:** If a chunk repeatedly fails the word-match on the same provider, fall through to the next synthesis leg for that chunk and re-verify. If no provider yields a >= 95% match for a chunk, escalate to the Director and the Healer with the failing text; the script may contain a pronunciation trap (route phonemes via Fish phoneme tags). Never deliver a demo that failed STT verification.

---

### SOP 9.5 -- Deliver the Demo mp3 (verified, via the Delivery Concierge)

**When to run:** After the STT verification passes.

**Inputs:**
- working/audio-demo/<deck>_demo.mp3
- working/audio-demo/<deck>_tagged_script.md
- the STT verification record

**Steps:**

1. Hand the demo mp3 and the tag-annotated script to the Delivery Concierge (ROLE-13) using the standard dispatch contract, destinations resolved from intake.json (Mac Downloads / GHL / Drive per client box type).

2. The Delivery Concierge resolves destinations, uploads, sends the verified delivery notification via openclaw message send, and runs ground-truth verification (file hash + size). You do NOT upload or notify yourself.

3. Wait for the Delivery Concierge's verified-delivery confirmation (its delivery_complete ledger entry). Only then is the audio demo considered shipped. Record the confirmation reference and notify the Director.

**Outputs:**
- A verified-delivery confirmation from the Delivery Concierge for the demo mp3 + tagged script

**Hand to:** Delivery Concierge (executes and verifies delivery); Director of Presentations (notified on verified delivery).

**Failure mode:** If the Delivery Concierge reports a delivery failure, do NOT self-report success; surface it to the Director and re-dispatch after the cause is fixed. An unverified delivery is not a delivery.

---
