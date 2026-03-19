# QC Checklist — Skill 30: Fish Audio API Reference

Run this checklist after installation to verify the skill is correctly installed and the agent has internalized all required knowledge.

---

## Section 1: File Structure Checks

Run each command and confirm the expected result.

```bash
# 1.1 - API reference document exists in master files
ls ~/Downloads/openclaw-master-files/service-integrations/fish-audio/fish-audio-api-reference.md
```
**Expected:** File exists, no error.

```bash
# 1.2 - Confirm file is not empty (should be ~841 lines)
wc -l ~/Downloads/openclaw-master-files/service-integrations/fish-audio/fish-audio-api-reference.md
```
**Expected:** Output shows 841 or more lines.

```bash
# 1.3 - Confirm the fish-audio directory exists
ls ~/Downloads/openclaw-master-files/service-integrations/fish-audio/
```
**Expected:** `fish-audio-api-reference.md` is listed.

```bash
# 1.4 - Check pending setup status (if credentials were not available at install time)
cat ~/.openclaw/skills/.pending-setup.md 2>/dev/null | grep -A5 "fish-audio"
```
**Expected (if credentials were entered):** No entry, or entry shows `Status: COMPLETE`.
**Expected (if pending):** Entry shows `Status: PENDING` with note to resume at Step 4.

---

## Section 2: Core File Update Checks

```bash
# 2.1 - Confirm FISH_AUDIO_API_KEY is present in clawdbot.json
grep -c "FISH_AUDIO_API_KEY" ~/.clawdbot/clawdbot.json
```
**Expected:** `1` (key is present). If `0`, credentials have not been added — complete INSTALL.md Step 4.

```bash
# 2.2 - Confirm FISH_AUDIO_VOICE_ID is present in clawdbot.json
grep -c "FISH_AUDIO_VOICE_ID" ~/.clawdbot/clawdbot.json
```
**Expected:** `1`

```bash
# 2.3 - Confirm both env vars are in the secrets .env file
grep "FISH_AUDIO_API_KEY" ~/clawd/secrets/.env
grep "FISH_AUDIO_VOICE_ID" ~/clawd/secrets/.env
```
**Expected:** Both lines print with non-empty values.

```bash
# 2.4 - Confirm Gemini Engine has indexed the reference document
python3 ~/clawd/scripts/gemini-search.py "fish audio tts endpoint" | head -5
```
**Expected:** Results reference `fish-audio-api-reference.md`. If no results, re-run `python3 ~/clawd/scripts/gemini-indexer.py`.

---

## Section 3: Knowledge Verification Questions

Ask the agent these questions directly. Correct answers are listed below each question. The agent must answer from memory or Gemini Engine lookup — it must NOT guess.

**Q1: What is the base URL for the Fish Audio API?**
> Correct: `https://api.fish.audio`

**Q2: What is the TTS endpoint path and method?**
> Correct: `POST /v1/tts`

**Q3: What is the default and required model for all BlackCEO use cases?**
> Correct: `s2-pro` — never `s1` unless explicitly instructed otherwise.

**Q4: What are the correct bitrate settings for phone calls vs. podcasts?**
> Correct: Phone calls = 64 kbps. Podcasts/content = 192 kbps. Both use `latency: normal`.

**Q5: What latency setting should be used for real-time live AI calling?**
> Correct: `balanced` (~300ms). All other use cases use `normal`.

**Q6: What is the Fish Audio pricing for TTS?**
> Correct: $15.00 per 1 million UTF-8 bytes. (~$0.40 per 30-minute podcast episode.)

**Q7: How does S2-Pro emotion tagging work? Give a valid example.**
> Correct: S2-Pro uses `[square bracket]` natural language tags — open-domain, not a fixed list.
> Example: `[calm and professional] Here is your briefing.` or `[excited] Big announcement today!`

**Q8: What are the paralanguage effects available for inline use?**
> Correct: `(breath)`, `(break)`, `(long-break)`, `(laugh)`, `(sigh)` — inserted inline in the text string.

**Q9: What is the recommended chunk size for long-form content over 15,000 characters?**
> Correct: Split into ~4,000 character chunks and stitch with FFmpeg using concat.

**Q10: What is the WebSocket streaming endpoint, and which model does it currently support?**
> Correct: `wss://api.fish.audio/v1/tts/live` — currently supports `s1` only (not s2-pro).

**Q11: What two content types does the TTS endpoint accept, and when is each used?**
> Correct: `application/json` for standard requests with a `reference_id`. `application/msgpack` is required for inline zero-shot voice cloning with reference audio bytes.

**Q12: What should the agent do if FISH_AUDIO_API_KEY or FISH_AUDIO_VOICE_ID are missing?**
> Correct: Remind the client once per session that setup is PENDING. When credentials are provided, add both to `clawdbot.json` and `~/clawd/secrets/.env`, run `python3 ~/clawd/scripts/gemini-indexer.py`, and mark the pending entry as COMPLETE.

---

## Section 4: Live Behavior Test

Run this only if credentials are present and confirmed in Step 2.

```bash
# 4.1 - Live API call test
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d "{
    \"text\": \"Fish Audio skill installation confirmed. Ready.\",
    \"reference_id\": \"$FISH_AUDIO_VOICE_ID\",
    \"format\": \"mp3\",
    \"mp3_bitrate\": 64,
    \"normalize\": true,
    \"latency\": \"normal\"
  }" \
  --output /tmp/fish_audio_qc_test.mp3 \
  -w "%{http_code}"
```

**Expected:** HTTP status `200` printed to terminal. File at `/tmp/fish_audio_qc_test.mp3` exists and is non-zero bytes.

```bash
# 4.2 - Confirm output file was generated
ls -lh /tmp/fish_audio_qc_test.mp3
```
**Expected:** File size > 0 bytes. Play the file to confirm the voice output sounds correct.

---

## Section 5: Anti-Pattern Checks

Verify the agent does NOT exhibit any of the following failure behaviors.

| # | Anti-Pattern | Check |
|---|-------------|-------|
| 5.1 | Agent uses `s1` model instead of `s2-pro` without being told | Ask agent: "What model do I use for a podcast?" — must answer `s2-pro` |
| 5.2 | Agent uses `latency: balanced` for podcast generation | Ask agent: "What latency for a 30-minute podcast?" — must answer `normal` |
| 5.3 | Agent uses `latency: normal` for a live real-time AI calling scenario | Ask agent: "What latency for a live phone call AI?" — must answer `balanced` |
| 5.4 | Agent guesses endpoint parameters without reading the reference | If agent says any endpoint without citing the reference doc or Gemini Engine, flag as FAIL |
| 5.5 | Agent loads `fish-audio-voice-sop.md` into core files or system prompt | This file must be read via TYP only — never injected into `core.md` or live prompts |
| 5.6 | Agent uses `(parenthesis)` emotion syntax with S2-Pro | S2-Pro uses `[square bracket]` natural language — parenthesis syntax is S1 only |
| 5.7 | Agent uses `192 kbps` for a phone call | Phone calls must use `64 kbps` to match telephony standards |
| 5.8 | Agent sends long scripts (>15,000 chars) as a single API call without chunking | Must split at ~4,000 chars and stitch with FFmpeg |

---

## Section 6: Pass Criteria

Skill 30 passes QC when ALL of the following are true:

- [ ] `fish-audio-api-reference.md` exists at the correct master files path (Section 1)
- [ ] File is 841+ lines (not truncated or empty) (Section 1)
- [ ] `FISH_AUDIO_API_KEY` and `FISH_AUDIO_VOICE_ID` are present in `clawdbot.json` and `.env` — OR a valid PENDING entry exists in `.pending-setup.md` (Section 2)
- [ ] Gemini Engine search returns results for Fish Audio content (Section 2)
- [ ] Agent answers all 12 knowledge questions correctly without guessing (Section 3)
- [ ] Live API call returns HTTP 200 with non-zero audio output (Section 4) — *skip if credentials pending*
- [ ] All 8 anti-patterns are absent (Section 5)

**If any item is unchecked:** Return to `INSTALL.md` and complete the relevant step, then re-run this checklist.
