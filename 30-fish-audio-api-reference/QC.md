# QC Checklist — Skill 30: Fish Audio API Reference

Run this after installation to verify the reference files, credentials, and live TTS behavior.

---

## Section 1: File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/30-fish-audio-api-reference"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/fish-audio-api-reference"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md README.md fish-audio-voice-sop.md skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

[ -f "$SKILL_DIR/references/fish-audio-api-reference.md" ] \
  && echo "PASS: references/fish-audio-api-reference.md" \
  || echo "FAIL: API reference missing"

[ -f "$SKILL_DIR/skill-version.txt" ] && echo "Installed version: $(cat "$SKILL_DIR/skill-version.txt")"
```

**Pass criteria:** all required files exist.

---

## Section 2: Credential + Env Checks

Required values:
- `FISH_AUDIO_API_KEY`
- `FISH_AUDIO_VOICE_ID`

```bash
source ~/clawd/secrets/.env 2>/dev/null || true
for var in FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID; do
  [ -n "$(printenv "$var" 2>/dev/null)" ] \
    && echo "PASS: $var set" \
    || echo "FAIL: $var missing"
done
```

If credentials are intentionally pending, verify the pending note exists instead of failing silently:

```bash
grep -A5 -i "fish audio" "$HOME/.openclaw/skills/.pending-setup.md" 2>/dev/null || echo "INFO: no pending-setup note found"
```

**Pass criteria:** credentials exist OR there is an explicit pending-setup note.

---

## Section 3: Core Knowledge Verification

**Q1.** What is the base URL?
> **Expected:** `https://api.fish.audio`

**Q2.** What is the main TTS endpoint?
> **Expected:** `POST /v1/tts`

**Q3.** What model should BlackCEO use by default?
> **Expected:** `s2-pro`

**Q4.** What bitrate should be used for phone calls?
> **Expected:** 64 kbps

**Q5.** What bitrate should be used for content / podcasts?
> **Expected:** 192 kbps

**Q6.** What latency should be used for most generation work?
> **Expected:** `normal`

**Q7.** What latency is the real-time exception?
> **Expected:** `balanced` for live streaming / real-time call situations

**Q8.** How does S2-Pro emotion tagging work?
> **Expected:** open-domain natural-language tags in square brackets, like `[calm and professional]`

**Q9.** What inline paralanguage effects are available?
> **Expected:** `(breath)`, `(break)`, `(long-break)`, `(laugh)`, `(sigh)`

**Q10.** What should happen to scripts longer than about 15,000 characters?
> **Expected:** split into about 4,000-character chunks and stitch them after generation.

**Pass criteria:** 10/10 answers correct.

---

## Section 4: Live API Smoke Test

Run only if credentials are present.

```bash
source ~/clawd/secrets/.env 2>/dev/null || true

HTTP_CODE=$(curl -s -o /tmp/fish_audio_qc_test.mp3 -w "%{http_code}" \
  -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d "{\"text\":\"Fish Audio QC passed. Ready.\",\"reference_id\":\"$FISH_AUDIO_VOICE_ID\",\"format\":\"mp3\",\"mp3_bitrate\":64,\"normalize\":true,\"latency\":\"normal\"}")

echo "HTTP: $HTTP_CODE"
ls -lh /tmp/fish_audio_qc_test.mp3 2>/dev/null || true
```

**Expected:** HTTP `200` and a non-empty MP3 file.

Optional audio sanity check:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/fish_audio_qc_test.mp3
```

---

## Section 5: Anti-Pattern Checks

Fail the skill if any of these happen:

- agent uses `s1` instead of `s2-pro` without explicit instruction
- agent uses 192 kbps for a phone call
- agent uses 64 kbps for a podcast/content file
- agent uses `balanced` latency for normal offline generation
- agent uses parenthesis-based emotion syntax instead of square-bracket natural language for S2-Pro
- agent sends very long scripts in one call instead of chunking
- agent guesses endpoint details without consulting the reference

**Pass criteria:** zero anti-patterns triggered.
